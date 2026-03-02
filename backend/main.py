"""
Feature Dashboard Backend API
==============================

FastAPI server exposing feature data from SQLite database.
"""

import asyncio
import json
import secrets
import sqlite3
import subprocess
import sys
import tempfile
import urllib.request
import urllib.error
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import func as sa_func

from api.database import Comment, DescriptionToken, Feature, NameToken, create_database
from api.tokens import normalize_tokens
from backend.providers import REGISTRY, get_provider

# Initialize FastAPI app
app = FastAPI(
    title="Feature Dashboard API",
    description="API for managing project features and backlog",
    version="1.0.0"
)

# CORS middleware for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174", "http://127.0.0.1:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database setup
PROJECT_DIR = Path(__file__).parent.parent
CONFIG_FILE = PROJECT_DIR / "dashboards.json"
SETTINGS_FILE = PROJECT_DIR / "settings.json"

DEFAULT_PROMPT_TEMPLATE = (
    "Please work on the following feature:\n\n"
    "Feature #{feature_id} [{category}]: {name}\n\n"
    "Description:\n{description}\n\n"
    "Steps:\n{steps}"
)

# Text patterns (lowercased) in Claude CLI stdout/stderr that indicate a rate or
# session limit.  A case-insensitive substring search is performed against the
# concatenated process output so we can surface a friendly message instead of a
# generic red error banner.
CLAUDE_RATE_LIMIT_PATTERNS: frozenset[str] = frozenset([
    "rate limit",
    "usage limit",
    "session limit",
    "rate_limit_error",
    "overloaded_error",
    "claude usage limit reached",
    "you've reached your usage limit",
    # Context / token limit errors emitted by the Claude CLI or Anthropic API
    "context_length_exceeded",
    "prompt is too long",
    "input_too_long",
    "too many tokens",
])

# Process exit codes that the Claude CLI uses to signal a session or rate limit.
# 130 = SIGINT (128 + 2) — commonly emitted when a CLI tool is stopped externally.
CLAUDE_SESSION_LIMIT_EXIT_CODES: frozenset[int] = frozenset([130])

# Maximum time a single Claude process may run before it is forcibly killed.
# Tasks are expected to be small; this guards against Claude getting stuck
# after a terminal API error (e.g. max_output_tokens) where the process
# never exits on its own.
AUTOPILOT_PROCESS_TIMEOUT_SECS = 1800  # 30 minutes

PLAN_TASKS_PROMPT_TEMPLATE = """\
You are a Project Expansion Assistant for the Feature Dashboard project.

## Project Context

Feature Dashboard is a web application for visualizing and managing project features stored \
in a SQLite database. It uses React 18 + Vite on the frontend and FastAPI + SQLite on the backend. \
Features are tracked in a kanban board with TODO, In Progress, and Done lanes.

**Available MCP tools:** feature_create_bulk, feature_create, feature_get_stats, \
feature_get_next, feature_mark_passing, feature_skip

## User Request

The user wants to expand the project with the following:

{description}

## Your Role

Follow the expand-project process:

**Phase 1: Clarify Requirements**
Ask focused questions to fully understand what the user wants:
- What the user sees (UI/UX flows)
- What actions they can take
- What happens as a result
- Error states and edge cases

**Phase 2: Present Feature Breakdown**
Count testable behaviors and present a breakdown by category for approval before creating anything:
- `functional` - Core functionality, CRUD operations, workflows
- `style` - Visual design, layout, responsive behavior
- `navigation` - Routing, links, breadcrumbs
- `error-handling` - Error states, validation, edge cases
- `data` - Data integrity, persistence

**Phase 3: Create Features**
Once the user approves the breakdown, call `feature_create_bulk` with ALL features at once.

Start by greeting the user, summarizing what they want to add, and asking clarifying questions.
"""

# Support test database via environment variable
import os
TEST_DB_PATH = os.environ.get("TEST_DB_PATH")
if TEST_DB_PATH:
    # Use test database for E2E tests
    test_db_path = Path(TEST_DB_PATH)
    _current_db_path = test_db_path
    _engine, _session_maker = create_database(test_db_path.parent, db_filename=test_db_path.name)
else:
    # Use production database
    _current_db_path = PROJECT_DIR / "features.db"
    _engine, _session_maker = create_database(PROJECT_DIR)


class LogEntry(BaseModel):
    """A single auto-pilot log entry with timestamp, severity level, and message."""
    timestamp: str          # ISO 8601 UTC timestamp
    level: str              # 'info' | 'success' | 'error'
    message: str


@dataclass
class LogLine:
    """A single captured output line from a Claude subprocess."""
    timestamp: str          # ISO 8601 UTC timestamp
    stream: str             # 'stdout' | 'stderr'
    text: str


class ClaudeProcessLog:
    """In-memory ring buffer of stdout/stderr lines from a Claude process."""

    def __init__(self, feature_id: int) -> None:
        self.feature_id = feature_id
        self.lines: deque = deque(maxlen=500)

    def append(self, stream: str, text: str) -> None:
        self.lines.append(LogLine(
            timestamp=datetime.now(timezone.utc).isoformat(),
            stream=stream,
            text=text,
        ))


# Per-feature stdout/stderr capture buffers, keyed by feature_id.
# Created when a Claude process starts, removed when monitoring ends.
_claude_process_logs: dict[int, ClaudeProcessLog] = {}


# Auto-pilot in-memory state, keyed by database path string
class _AutoPilotState:
    """Tracks auto-pilot mode for a single database."""
    def __init__(self):
        self.enabled: bool = False
        self.stopping: bool = False  # True when disabled but Claude process still running
        self.current_feature_id: Optional[int] = None
        self.current_feature_name: Optional[str] = None
        self.current_feature_model: Optional[str] = None
        self.last_error: Optional[str] = None
        self.log: deque = deque(maxlen=100)  # LogEntry items, circular buffer
        self.active_process = None  # subprocess.Popen handle, if any
        self.monitor_task = None  # asyncio.Task handle, if monitoring
        self.consecutive_skip_count: int = 0  # incremented when same feature is returned consecutively
        self.last_skipped_feature_id: Optional[int] = None  # last feature id given to the sequencer
        self.features_completed: int = 0  # number of features completed in this session
        self.budget_exhausted: bool = False  # True when stopped by budget limit
        # Manual launch tracking (user clicked "Launch Claude" in the detail panel)
        self.manual_active: bool = False
        self.manual_feature_id: Optional[int] = None
        self.manual_feature_name: Optional[str] = None
        self.manual_feature_model: Optional[str] = None
        self.manual_process = None  # subprocess.Popen handle for manual launch
        self.manual_monitor_task = None  # asyncio.Task monitoring manual process
        # JSONL session log tracking
        self.session_start_time: Optional[datetime] = None
        self.session_prompt_snippet: Optional[str] = None  # snippet from the feature prompt for JSONL matching
        self.session_jsonl_path: Optional[Path] = None     # cached path once the session file is identified


_autopilot_states: dict[str, _AutoPilotState] = {}


def get_autopilot_state() -> _AutoPilotState:
    """Get or create the autopilot state for the currently active database.

    When creating a new state entry, initialises the ``enabled`` flag from the
    persisted value in dashboards.json so that the UI toggle is restored
    correctly after a frontend reload (without a backend restart).
    """
    db_key = str(_current_db_path)
    if db_key not in _autopilot_states:
        state = _AutoPilotState()
        state.enabled = _read_autopilot_from_config()
        _autopilot_states[db_key] = state
    return _autopilot_states[db_key]


def _append_log(state: _AutoPilotState, level: str, message: str) -> None:
    """Append a structured log entry (timestamp + level + message) to autopilot state."""
    state.log.append(LogEntry(
        timestamp=datetime.now(timezone.utc).isoformat(),
        level=level,
        message=message,
    ))


async def _read_stream_to_buffer(stream, stream_name: str, log: ClaudeProcessLog) -> None:
    """Read lines from a subprocess pipe and append each to *log*.

    Runs until EOF (process closed its write end).  Each line is stripped of
    trailing CR/LF before storing.  Decoding errors are replaced with U+FFFD.
    """
    loop = asyncio.get_event_loop()
    while True:
        try:
            line = await loop.run_in_executor(None, stream.readline)
        except Exception:
            break
        if not line:  # EOF
            break
        log.append(stream_name, line.decode('utf-8', errors='replace').rstrip('\r\n'))


def _get_claude_projects_slug(working_dir: str) -> str:
    """Convert a working directory path to a Claude projects slug.

    Claude encodes the project path by replacing ':' with '-' and path separators with '-'.
    Example: 'F:\\Work\\Godot\\feature-dashboard' -> 'F--Work-Godot-feature-dashboard'
    """
    return working_dir.replace(':', '-').replace('\\', '-').replace('/', '-')


def _get_claude_projects_dir(working_dir: str) -> Optional[Path]:
    """Return the ~/.claude/projects/{slug}/ directory for the given working directory."""
    slug = _get_claude_projects_slug(working_dir)
    projects_dir = Path.home() / '.claude' / 'projects' / slug
    return projects_dir if projects_dir.exists() else None


def _find_session_jsonl(
    projects_dir: Path,
    since: datetime,
    prompt_snippet: Optional[str] = None,
) -> Optional[Path]:
    """Find the JSONL session file for the active Claude process.

    Candidates are files in *projects_dir* whose mtime is >= *since*.
    When *prompt_snippet* is provided the candidates are scanned (newest
    first) for one whose early user messages contain the snippet — this
    reliably distinguishes the autopilot subprocess from any concurrent
    interactive Claude session that shares the same projects directory.
    Falls back to the newest candidate if no content match is found.
    Returns None when there are no candidates at all.
    """
    since_ts = since.timestamp()
    candidates = [
        f for f in projects_dir.glob('*.jsonl')
        if f.stat().st_mtime >= since_ts
    ]
    if not candidates:
        return None

    # Sort newest-first so we check the most-likely match first.
    candidates.sort(key=lambda f: f.stat().st_mtime, reverse=True)

    if prompt_snippet:
        for f in candidates:
            if _jsonl_contains_prompt(f, prompt_snippet):
                return f

    # Fallback: return the newest candidate even without a content match.
    return candidates[0]


def _jsonl_contains_prompt(jsonl_file: Path, prompt_snippet: str) -> bool:
    """Return True if any user message in *jsonl_file* contains *prompt_snippet*.

    Only reads the first 50 KB of the file — the initial user message always
    appears near the top, so there is no need to scan the whole file.
    """
    try:
        with open(jsonl_file, 'r', encoding='utf-8', errors='replace') as f:
            head = f.read(50_000)
    except (IOError, OSError):
        return False

    for line in head.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get('type') != 'user':
            continue
        msg = obj.get('message', {})
        if not isinstance(msg, dict):
            continue
        content = msg.get('content', '')
        if isinstance(content, str) and prompt_snippet in content:
            return True
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    text = item.get('text', '')
                    if isinstance(text, str) and prompt_snippet in text:
                        return True
                elif isinstance(item, str) and prompt_snippet in item:
                    return True
    return False


def _format_tool_call(tool_name: str, tool_input: dict) -> str:
    """Format a Claude tool call into a human-readable string."""
    if tool_name == 'Bash':
        desc = tool_input.get('description', '')
        cmd = tool_input.get('command', '')
        return f"$ {desc or cmd[:120]}"
    elif tool_name == 'Read':
        path = tool_input.get('file_path', '')
        return f"Read: {Path(path).name if path else '?'}"
    elif tool_name == 'Edit':
        path = tool_input.get('file_path', '')
        return f"Edit: {Path(path).name if path else '?'}"
    elif tool_name == 'Write':
        path = tool_input.get('file_path', '')
        return f"Write: {Path(path).name if path else '?'}"
    elif tool_name == 'Glob':
        pattern = tool_input.get('pattern', '')
        return f"Glob: {pattern}"
    elif tool_name == 'Grep':
        pattern = tool_input.get('pattern', '')
        return f"Grep: {pattern}"
    elif tool_name == 'Task':
        desc = tool_input.get('description', '')
        return f"Task: {desc[:80]}"
    elif tool_name == 'TaskCreate':
        subject = tool_input.get('subject', '')
        return f"Task Create: {subject}"
    elif tool_name == 'TaskUpdate':
        status = tool_input.get('status', '')
        task_id = tool_input.get('taskId', '')
        return f"Task Update #{task_id}: {status}"
    elif tool_name.startswith('mcp__features__'):
        feature_tool = tool_name.replace('mcp__features__', '')
        feature_id = tool_input.get('feature_id', '')
        if feature_id:
            return f"Feature #{feature_id}: {feature_tool}"
        return f"Feature: {feature_tool}"
    else:
        return tool_name


def _parse_jsonl_log(jsonl_file: Path, limit: int = 50) -> list[dict]:
    """Parse a Claude JSONL session file and return the last N meaningful log entries.

    For large files (>500KB), reads only the last 100KB for performance.
    Returns entries in chronological order.
    """
    entries: list[dict] = []
    file_size = 0
    try:
        file_size = jsonl_file.stat().st_size
    except OSError:
        return []

    try:
        with open(jsonl_file, 'r', encoding='utf-8', errors='replace') as f:
            if file_size > 500_000:
                f.seek(max(0, file_size - 100_000))
                f.readline()  # Skip partial first line
            lines = f.readlines()
    except (IOError, OSError):
        return []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        if obj.get('type') != 'assistant':
            continue

        msg = obj.get('message', {})
        if not isinstance(msg, dict):
            continue

        content = msg.get('content', [])
        if not isinstance(content, list):
            continue

        timestamp = obj.get('timestamp', '')

        for item in content:
            if not isinstance(item, dict):
                continue
            item_type = item.get('type', '')
            if item_type == 'tool_use':
                tool_name = item.get('name', 'unknown')
                tool_input = item.get('input', {}) or {}
                entries.append({
                    'timestamp': timestamp,
                    'entry_type': 'tool_use',
                    'tool_name': tool_name,
                    'text': _format_tool_call(tool_name, tool_input),
                })
            elif item_type == 'text':
                text = item.get('text', '').strip()
                if text:
                    text = text.replace('\n', ' ').replace('\r', '')
                    entries.append({
                        'timestamp': timestamp,
                        'entry_type': 'text',
                        'tool_name': None,
                        'text': text[:200],
                    })

    return entries[-limit:] if len(entries) > limit else entries


def _launch_claude_terminal(
    prompt: str, working_dir: str, model: Optional[str] = None
) -> None:
    """Open Claude interactively in a new terminal window with *prompt* as the first message.

    On Windows, writes the prompt to a temp file and opens pwsh/powershell with
    CREATE_NEW_CONSOLE so a visible window appears. Uses the PowerShell sub-expression
    ``(Get-Content -LiteralPath "..." -Raw)`` to pass the prompt — this avoids shell
    quoting issues and the wt pane-separator problem caused by ``|`` and ``;``.

    On Linux/macOS, passes the prompt as a positional argument directly to claude.

    Raises HTTPException(500) if no suitable executable is found.
    """
    model_flag = f"--model {model} " if model else ""

    if sys.platform == "win32":
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write(prompt)
            prompt_file = f.name

        ps_cmd = f'claude {model_flag}--dangerously-skip-permissions (Get-Content -LiteralPath "{prompt_file}" -Raw)'
        for ps_exe in ["pwsh", "powershell"]:
            try:
                subprocess.Popen(
                    [ps_exe, "-Command", ps_cmd],
                    cwd=working_dir,
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                )
                return
            except FileNotFoundError:
                continue
        raise HTTPException(
            status_code=500,
            detail="No PowerShell found. Install PowerShell 7 (pwsh) or ensure powershell.exe is available.",
        )
    else:
        cmd = ["claude", "--dangerously-skip-permissions"]
        if model:
            cmd += ["--model", model]
        cmd.append(prompt)
        try:
            subprocess.Popen(cmd, cwd=working_dir)
        except FileNotFoundError:
            raise HTTPException(
                status_code=500,
                detail="Claude CLI not found. Make sure 'claude' is in your PATH.",
            )


async def monitor_manual_process(state: "_AutoPilotState") -> None:
    """Wait for a manually launched Claude process to finish and update the log.

    Runs in the background as an asyncio task. When the process exits it appends a
    success or info log entry and clears all ``manual_*`` state fields.

    If the process has stdout/stderr pipes (hidden-execution mode) the output is
    captured into ``_claude_process_logs`` keyed by feature_id.
    """
    process = state.manual_process
    feature_id = state.manual_feature_id
    feature_name = state.manual_feature_name

    # Set up log buffer and reader tasks if the process has pipes
    log: Optional[ClaudeProcessLog] = None
    reader_tasks: list[asyncio.Task] = []
    proc_stdout = getattr(process, 'stdout', None)
    proc_stderr = getattr(process, 'stderr', None)
    if feature_id is not None and (proc_stdout or proc_stderr):
        log = ClaudeProcessLog(feature_id=feature_id)
        _claude_process_logs[feature_id] = log
        if proc_stdout:
            reader_tasks.append(asyncio.create_task(
                _read_stream_to_buffer(proc_stdout, 'stdout', log)
            ))
        if proc_stderr:
            reader_tasks.append(asyncio.create_task(
                _read_stream_to_buffer(proc_stderr, 'stderr', log)
            ))

    try:
        loop = asyncio.get_event_loop()
        return_code = await loop.run_in_executor(None, process.wait)
        # Drain remaining pipe output now that the process has exited
        if reader_tasks:
            await asyncio.gather(*reader_tasks, return_exceptions=True)
            reader_tasks.clear()
        if return_code == 0:
            _append_log(state, 'success', f"Manual run complete \u2014 feature #{feature_id}: {feature_name}")
        else:
            _append_log(state, 'info', f"Manual run finished \u2014 feature #{feature_id}: {feature_name} (exit {return_code})")
    except Exception as exc:
        _append_log(state, 'error', f"Manual run monitor error \u2014 feature #{feature_id}: {exc}")
    finally:
        for task in reader_tasks:
            if not task.done():
                task.cancel()
        if feature_id is not None:
            _claude_process_logs.pop(feature_id, None)
        # Only clear if this task is still tracking the same process
        if state.manual_process is process:
            state.manual_active = False
            state.manual_feature_id = None
            state.manual_feature_name = None
            state.manual_feature_model = None
            state.manual_process = None
            state.manual_monitor_task = None


def handle_all_complete(state: "_AutoPilotState") -> None:
    """Cleanly stop auto-pilot when no features remain.

    Sets enabled=False, clears current_feature_id, current_feature_name,
    last_error, active_process, and monitor_task, then appends an info log
    entry indicating all tasks are done.
    """
    state.enabled = False
    state.current_feature_id = None
    state.current_feature_name = None
    state.current_feature_model = None
    state.last_error = None
    state.active_process = None
    state.monitor_task = None
    _append_log(state, 'info', "All tasks complete \u2014 auto-pilot disabled")


def get_next_autopilot_feature(session) -> Optional["Feature"]:
    """Return the next feature to work on: in-progress first, then TODO by priority.

    Selection order:
    1. in_progress=True, passes=False  — ordered by priority ASC
    2. in_progress=False, passes=False — ordered by priority ASC
    3. None if no eligible features remain
    """
    feature = (
        session.query(Feature)
        .filter(Feature.passes == False, Feature.in_progress == True)  # noqa: E712
        .order_by(Feature.priority.asc())
        .first()
    )
    if feature is None:
        feature = (
            session.query(Feature)
            .filter(Feature.passes == False, Feature.in_progress == False)  # noqa: E712
            .order_by(Feature.priority.asc())
            .first()
        )
    return feature


def spawn_claude_for_autopilot(feature, settings: dict, working_dir: str) -> "subprocess.Popen":
    """Spawn a background AI process for auto-pilot mode and return the Popen handle.

    Delegates to the AI provider configured in settings (default: 'claude').

    Args:
        feature:     Feature ORM object (must have id, category, name, description, steps, model).
        settings:    Settings dict containing 'provider' and provider-specific configuration.
        working_dir: Working directory string for the spawned process.

    Returns:
        subprocess.Popen handle for the spawned process.
    """
    provider_name = settings.get("provider", "claude")
    provider = get_provider(provider_name)
    return provider.spawn_process(feature, settings, working_dir)


def handle_budget_exhausted(state: "_AutoPilotState") -> None:
    """Stop auto-pilot because the session budget limit has been reached."""
    limit = state.features_completed
    msg = f"Session budget reached: {limit} feature{'s' if limit != 1 else ''} completed"
    _append_log(state, 'info', msg)
    state.enabled = False
    state.budget_exhausted = True
    state.current_feature_id = None
    state.current_feature_name = None
    state.current_feature_model = None
    state.active_process = None
    state.monitor_task = None


async def handle_autopilot_success(
    feature_id: int, state: "_AutoPilotState", db_path: Path
) -> None:
    """Handle successful feature completion (feature.passes=True after process exits).

    Logs the success, then picks the next pending feature and spawns Claude for it.
    If no further work remains, disables auto-pilot and logs completion.
    """
    feature_name = state.current_feature_name or "unknown"
    _append_log(state, 'success', f"Feature #{feature_id} completed: {feature_name}")
    state.features_completed += 1

    # Budget limit check: stop if the session limit has been reached
    settings = load_settings()
    budget_limit = settings.get("autopilot_budget_limit", 0)
    if budget_limit > 0 and state.features_completed >= budget_limit:
        handle_budget_exhausted(state)
        return

    # Fetch the next feature with a fresh session
    from sqlalchemy import create_engine as _create_engine
    from sqlalchemy.orm import sessionmaker as _sessionmaker

    db_url = f"sqlite:///{db_path.as_posix()}"
    engine = _create_engine(db_url, connect_args={"check_same_thread": False})
    sm = _sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = sm()
    next_feature = None
    try:
        next_feature = get_next_autopilot_feature(session)
    finally:
        session.close()
        engine.dispose()

    if next_feature is None:
        handle_all_complete(state)
        return

    # Skip loop guard: abort if the same feature is returned consecutively 3+ times
    if next_feature.id == state.last_skipped_feature_id:
        state.consecutive_skip_count += 1
        if state.consecutive_skip_count >= 3:
            msg = f"Dead loop detected: Feature #{next_feature.id} skipped 3 times consecutively"
            state.last_error = msg
            _append_log(state, 'error', msg)
            state.enabled = False
            state.current_feature_id = None
            state.current_feature_name = None
            state.current_feature_model = None
            state.active_process = None
            state.monitor_task = None
            return
    else:
        state.consecutive_skip_count = 0
        state.last_skipped_feature_id = next_feature.id

    state.current_feature_id = next_feature.id
    state.current_feature_name = next_feature.name
    state.current_feature_model = next_feature.model or "sonnet"
    # Reset session log tracking so the new task's JSONL is discovered (not the old one)
    state.session_start_time = datetime.now(timezone.utc)
    state.session_prompt_snippet = f"Feature #{next_feature.id} [{next_feature.category}]"
    state.session_jsonl_path = None
    try:
        proc = spawn_claude_for_autopilot(next_feature, settings, str(db_path.parent))
        state.active_process = proc
        _append_log(state, 'info', f"Starting feature #{next_feature.id}: {next_feature.name}")
        state.monitor_task = asyncio.create_task(
            monitor_claude_process(next_feature.id, proc, db_path, state)
        )
    except (FileNotFoundError, RuntimeError) as e:
        state.enabled = False
        state.current_feature_id = None
        state.current_feature_name = None
        state.current_feature_model = None
        state.active_process = None
        state.monitor_task = None
        err = str(e)
        state.last_error = err
        _append_log(state, 'error', f"Failed to spawn Claude: {err}")


def _extract_output_snippet(output_text: str, max_lines: int = 3, max_chars: int = 200) -> str:
    """Extract the last few non-empty lines of process output for display in error messages.

    This is used to surface the actual error reason (e.g. API error text, limit message)
    when the auto-pilot process exits with a non-zero code and no recognised pattern is found.

    Args:
        output_text: Full concatenated stdout+stderr text from the Claude process.
        max_lines:   Maximum number of trailing non-empty lines to include.
        max_chars:   Total character limit for the returned snippet.

    Returns:
        A short string like ``"some error text | more text"`` or ``""`` when
        *output_text* is blank.
    """
    lines = [line.strip() for line in output_text.splitlines() if line.strip()]
    tail = lines[-max_lines:] if lines else []
    snippet = " | ".join(tail)
    if len(snippet) > max_chars:
        snippet = snippet[:max_chars - 1] + "\u2026"  # ellipsis
    return snippet


async def handle_autopilot_failure(
    feature_id: int, exit_code: int, state: "_AutoPilotState", output_text: str = ""
) -> None:
    """Handle failed feature (process exited but feature.passes=False).

    Checks the exit code and concatenated process output for known rate/session-limit
    signals.  If detected, sets budget_exhausted=True and emits a friendly info-level
    message so the info banner (not the red error banner) is shown in the UI.
    Otherwise keeps the existing red error banner behaviour.  For generic failures the
    last few lines of process output are appended to the error message so the user can
    see the actual reason rather than a bare exit code.

    The raw exit code is always appended to the log first for debugging purposes.

    Args:
        feature_id:  Feature that was being processed.
        exit_code:   Exit code returned by the Claude process.
        state:       Current autopilot state (mutated in place).
        output_text: Concatenated stdout+stderr captured from the process; used to
                     detect rate-limit messages in CLI output.
    """
    # Always log the raw exit code for debugging
    _append_log(state, 'info', f"Feature #{feature_id}: process exited with code {exit_code}")

    # Detect rate/session limit via exit code or output text
    output_lower = output_text.lower()
    is_limit = (
        exit_code in CLAUDE_SESSION_LIMIT_EXIT_CODES
        or any(pattern in output_lower for pattern in CLAUDE_RATE_LIMIT_PATTERNS)
    )

    if is_limit:
        msg = (
            f"Feature #{feature_id}: Claude session/rate limit reached"
            " \u2014 please wait before retrying"
        )
        state.last_error = msg
        _append_log(state, 'info', msg)
        state.budget_exhausted = True
    else:
        snippet = _extract_output_snippet(output_text)
        snippet_part = f" \u2014 {snippet}" if snippet else ""
        msg = (
            f"Feature #{feature_id} failed: process exited with code {exit_code}"
            f" and was not marked as passing{snippet_part}"
        )
        state.last_error = msg
        _append_log(state, 'error', msg)

    state.enabled = False
    state.current_feature_id = None
    state.current_feature_name = None
    state.current_feature_model = None
    state.active_process = None
    state.monitor_task = None


async def monitor_claude_process(
    feature_id: int,
    process: "subprocess.Popen",
    db_path: Path,
    state: "_AutoPilotState",
) -> None:
    """Monitor a Claude process and trigger success or failure flow when it exits.

    Waits for the process without blocking the event loop by using run_in_executor.
    After the process exits, opens a fresh DB session to check feature.passes:
    - passes=True  → calls handle_autopilot_success
    - passes=False → calls handle_autopilot_failure
    Handles CancelledError silently so auto-pilot disable does not raise.

    If the process runs longer than AUTOPILOT_PROCESS_TIMEOUT_SECS, it is killed
    and auto-pilot is disabled with an error.  This prevents the autopilot from
    getting permanently stuck when Claude encounters a terminal API error (e.g.
    max_output_tokens) and its process never exits on its own.

    stdout/stderr are captured into ``_claude_process_logs[feature_id]`` while the
    process runs.  The buffer is cleaned up when this coroutine exits.
    """
    # Create per-feature log buffer and start async reader tasks for stdout/stderr
    log = ClaudeProcessLog(feature_id=feature_id)
    _claude_process_logs[feature_id] = log

    reader_tasks: list[asyncio.Task] = []
    stdout = getattr(process, 'stdout', None)
    stderr = getattr(process, 'stderr', None)
    if stdout:
        reader_tasks.append(asyncio.create_task(
            _read_stream_to_buffer(stdout, 'stdout', log)
        ))
    if stderr:
        reader_tasks.append(asyncio.create_task(
            _read_stream_to_buffer(stderr, 'stderr', log)
        ))

    try:
        loop = asyncio.get_event_loop()
        wait_future = loop.run_in_executor(None, process.wait)

        timed_out = False
        try:
            # asyncio.shield prevents wait_future from being cancelled when
            # wait_for times out, so we can still await it after killing the process.
            exit_code = await asyncio.wait_for(
                asyncio.shield(wait_future), timeout=AUTOPILOT_PROCESS_TIMEOUT_SECS
            )
        except asyncio.TimeoutError:
            timed_out = True
            try:
                process.kill()
            except (ProcessLookupError, OSError):
                pass  # Process already dead
            # wait_future is still running; process.kill() causes process.wait()
            # to return quickly, so this await completes almost immediately.
            exit_code = await wait_future

        # Drain any remaining output now that the process has exited and pipes are at EOF
        if reader_tasks:
            await asyncio.gather(*reader_tasks, return_exceptions=True)
            reader_tasks.clear()

        if timed_out:
            mins = AUTOPILOT_PROCESS_TIMEOUT_SECS // 60
            msg = (
                f"Feature #{feature_id} timed out after {mins}min"
                " — process killed, auto-pilot disabled"
            )
            state.last_error = msg
            _append_log(state, 'error', msg)
            state.enabled = False
            state.current_feature_id = None
            state.current_feature_name = None
            state.current_feature_model = None
            state.active_process = None
            state.monitor_task = None
            return

        # Open a fresh DB session — the process may have updated the DB while running
        from sqlalchemy import create_engine as _create_engine
        from sqlalchemy.orm import sessionmaker as _sessionmaker

        db_url = f"sqlite:///{db_path.as_posix()}"
        engine = _create_engine(db_url, connect_args={"check_same_thread": False})
        sm = _sessionmaker(autocommit=False, autoflush=False, bind=engine)
        session = sm()
        try:
            feature = session.query(Feature).filter(Feature.id == feature_id).first()
            passes = feature is not None and feature.passes
        finally:
            session.close()
            engine.dispose()

        if passes:
            await handle_autopilot_success(feature_id, state, db_path)
        else:
            # Collect captured stdout/stderr for rate-limit detection.
            # The log buffer is still present here; it is removed in the finally block.
            process_log = _claude_process_logs.get(feature_id)
            output_text = (
                "\n".join(line.text for line in process_log.lines)
                if process_log else ""
            )
            await handle_autopilot_failure(feature_id, exit_code, state, output_text)
    except asyncio.CancelledError:
        # Auto-pilot was disabled externally — exit cleanly without propagating
        pass
    finally:
        # Cancel any still-running reader tasks and remove the log buffer
        for task in reader_tasks:
            if not task.done():
                task.cancel()
        _claude_process_logs.pop(feature_id, None)


@app.on_event("startup")
async def startup_migrate_all():
    """Run schema migrations on all configured databases at startup."""
    from api.migration import migrate_all_dashboards
    migrate_all_dashboards()


def _reset_autopilot_in_config() -> None:
    """Reset autopilot to False in dashboards.json if persisted.

    Preventive measure: clears any persisted autopilot state so that a backend
    restart does not unexpectedly resume auto-pilot without user action.
    """
    if not CONFIG_FILE.exists():
        return
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        modified = False
        if isinstance(data, list):
            for entry in data:
                if isinstance(entry, dict) and entry.get('autopilot'):
                    entry['autopilot'] = False
                    modified = True
        if modified:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
    except Exception:
        pass  # Never fail startup due to config file issues


def _read_autopilot_from_config() -> bool:
    """Read the persisted autopilot state for the currently active database.

    Returns the ``autopilot`` boolean stored in dashboards.json for the entry
    whose path matches ``_current_db_path``.  Returns False if the config file
    cannot be read, the current path is not listed, or the field is absent.
    """
    if not CONFIG_FILE.exists():
        return False
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list):
            for entry in data:
                if isinstance(entry, dict):
                    entry_path = Path(entry.get('path', ''))
                    if not entry_path.is_absolute():
                        entry_path = PROJECT_DIR / entry_path
                    if entry_path.resolve() == _current_db_path.resolve():
                        return bool(entry.get('autopilot', False))
    except Exception:
        pass
    return False


def _write_autopilot_to_config(enabled: bool) -> None:
    """Persist the autopilot toggle state for the currently active database.

    Finds the dashboards.json entry whose path matches ``_current_db_path`` and
    sets its ``autopilot`` field to *enabled*.  Silently does nothing when the
    config file is absent, cannot be parsed, or does not contain a matching
    entry (e.g. when running against a temporary test database).
    """
    if not CONFIG_FILE.exists():
        return
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list):
            for entry in data:
                if isinstance(entry, dict):
                    entry_path = Path(entry.get('path', ''))
                    if not entry_path.is_absolute():
                        entry_path = PROJECT_DIR / entry_path
                    if entry_path.resolve() == _current_db_path.resolve():
                        entry['autopilot'] = enabled
                        break
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
    except Exception:
        pass  # Never fail an API call due to config file issues


@app.on_event("startup")
async def startup_reset_autopilot():
    """Reset auto-pilot state on every backend startup.

    Ensures no orphaned autopilot state from a previous session causes
    unexpected behavior after a backend restart (e.g., DevServer reload).
    In-memory state is implicitly empty on first import; this function makes
    the intent explicit and also handles persisted config fields.
    """
    # Defensive clear: dict is already empty on fresh module load, but explicit
    # is better than implicit — particularly when tests re-use the module.
    _autopilot_states.clear()

    # Reset any autopilot fields persisted in dashboards.json
    _reset_autopilot_in_config()

    # Log the reset for the current database's state
    state = get_autopilot_state()
    _append_log(state, 'info', 'Auto-pilot reset on backend restart')


def get_session():
    """Get a database session."""
    return _session_maker()


def get_comment_counts(session, feature_ids: list[int]) -> dict[int, int]:
    """Return a mapping of feature_id -> comment_count for the given feature IDs."""
    if not feature_ids:
        return {}
    rows = (
        session.query(Comment.feature_id, sa_func.count(Comment.id))
        .filter(Comment.feature_id.in_(feature_ids))
        .group_by(Comment.feature_id)
        .all()
    )
    return {fid: count for fid, count in rows}


def get_recent_logs(session, feature_ids: list[int]) -> dict[int, str]:
    """Return a mapping of feature_id -> most recent comment content for the given feature IDs."""
    if not feature_ids:
        return {}
    # Subquery: latest comment id per feature
    subq = (
        session.query(
            Comment.feature_id,
            sa_func.max(Comment.id).label("max_id"),
        )
        .filter(Comment.feature_id.in_(feature_ids))
        .group_by(Comment.feature_id)
        .subquery()
    )
    rows = (
        session.query(Comment.feature_id, Comment.content)
        .join(subq, Comment.id == subq.c.max_id)
        .all()
    )
    return {fid: content for fid, content in rows}


def feature_to_response(
    feature,
    comment_counts: dict[int, int],
    recent_logs: dict[int, str] | None = None,
) -> "FeatureResponse":
    """Convert a Feature ORM object to FeatureResponse including comment_count and recent_log."""
    d = feature.to_dict()
    d["comment_count"] = comment_counts.get(feature.id, 0)
    d["recent_log"] = (recent_logs or {}).get(feature.id)
    return FeatureResponse(**d)


def load_settings() -> dict:
    """Load settings from settings.json, returning defaults if not found."""
    defaults = {
        "claude_prompt_template": DEFAULT_PROMPT_TEMPLATE,
        "plan_tasks_prompt_template": PLAN_TASKS_PROMPT_TEMPLATE,
        "autopilot_budget_limit": 0,
        "provider": "claude",
    }
    if not SETTINGS_FILE.exists():
        return defaults
    try:
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for key, default in defaults.items():
            if key not in data:
                data[key] = default
        return data
    except Exception:
        return defaults


def save_settings(settings: dict) -> None:
    """Save settings to settings.json."""
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)


def load_dashboards_config() -> list[dict]:
    """Load dashboards configuration from JSON file."""
    if not CONFIG_FILE.exists():
        return [{"name": "Feature Dashboard", "path": "features.db"}]

    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load dashboards config: {str(e)}")


def validate_db_path(db_path: Path) -> bool:
    """Validate that the path is a valid SQLite database."""
    if not db_path.exists():
        return False

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        # Check if it's a valid SQLite database with features table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='features'")
        result = cursor.fetchone()
        conn.close()
        return result is not None
    except sqlite3.DatabaseError:
        return False


def switch_database(db_path: Path) -> None:
    """Switch the active database connection."""
    global _current_db_path, _engine, _session_maker

    if not validate_db_path(db_path):
        raise HTTPException(status_code=400, detail=f"Invalid database path: {db_path}")

    # Create a temporary directory path that will resolve correctly
    # We need to create the engine with a custom URL since create_database expects project_dir
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    db_url = f"sqlite:///{db_path.as_posix()}"
    _engine = create_engine(db_url, connect_args={"check_same_thread": False})
    _session_maker = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    _current_db_path = db_path


# Response models
VALID_MODELS = {"opus", "sonnet", "haiku"}


class FeatureResponse(BaseModel):
    """Feature data response."""
    model_config = {"from_attributes": True}

    id: int
    priority: int
    category: str
    name: str
    description: str
    steps: list[str]
    passes: bool
    in_progress: bool
    model: Optional[str] = "sonnet"
    created_at: Optional[str] = None
    modified_at: Optional[str] = None
    completed_at: Optional[str] = None
    comment_count: int = 0
    recent_log: Optional[str] = None


class StatsResponse(BaseModel):
    """Statistics response."""
    passing: int
    in_progress: int
    total: int
    percentage: float


class PaginatedFeaturesResponse(BaseModel):
    """Paginated features response with metadata."""
    features: list[FeatureResponse]
    total: int
    limit: int
    offset: int


# Database response models
class DatabaseInfo(BaseModel):
    """Database information."""
    name: str
    path: str
    exists: bool
    is_active: bool


class SelectDatabaseRequest(BaseModel):
    """Request to select a database."""
    path: str


# Request models for CRUD operations
class CreateFeatureRequest(BaseModel):
    """Request to create a new feature."""
    category: str
    name: str
    description: str
    steps: list[str]
    model: Optional[str] = "sonnet"


class UpdateFeatureRequest(BaseModel):
    """Request to update feature fields."""
    category: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    steps: Optional[list[str]] = None
    model: Optional[str] = None


class UpdateFeatureStateRequest(BaseModel):
    """Request to change feature state (passes/in_progress)."""
    passes: Optional[bool] = None
    in_progress: Optional[bool] = None


class UpdateFeaturePriorityRequest(BaseModel):
    """Request to set a specific priority value."""
    priority: int


class MoveFeatureRequest(BaseModel):
    """Request to move feature up or down within its lane."""
    direction: str  # "up" or "down"


class ReorderFeatureRequest(BaseModel):
    """Request to reorder a feature by placing it before or after a target feature."""
    target_id: int
    insert_before: bool


class LaunchClaudeRequest(BaseModel):
    """Request body for launching a Claude Code session."""
    hidden_execution: bool = True


class LaunchClaudeResponse(BaseModel):
    """Response for launching a Claude Code session."""
    launched: bool
    feature_id: int
    prompt: str
    working_directory: str
    model: str
    hidden_execution: bool


class PlanTasksRequest(BaseModel):
    """Request body for launching a plan-tasks Claude session."""
    description: str


class PlanTasksResponse(BaseModel):
    """Response for launching a plan-tasks Claude session."""
    launched: bool
    prompt: str
    working_directory: str


class SettingsResponse(BaseModel):
    """Application settings response."""
    claude_prompt_template: str
    plan_tasks_prompt_template: str
    autopilot_budget_limit: int = 0
    provider: str = "claude"
    available_providers: list[str] = []


class UpdateSettingsRequest(BaseModel):
    """Request to update application settings."""
    claude_prompt_template: str
    plan_tasks_prompt_template: Optional[str] = None
    autopilot_budget_limit: int = 0
    provider: str = "claude"


class CommentResponse(BaseModel):
    """Comment data response."""
    id: int
    feature_id: int
    content: str
    created_at: Optional[str] = None


class CreateCommentRequest(BaseModel):
    """Request to add a comment to a feature."""
    content: str


class ClaudeLogLineResponse(BaseModel):
    """A single captured output line returned by the claude-log endpoint."""
    timestamp: str
    stream: str
    text: str


class ClaudeLogResponse(BaseModel):
    """Response for GET /api/features/{id}/claude-log."""
    feature_id: int
    active: bool
    lines: list[ClaudeLogLineResponse]
    total_lines: int


class SessionLogEntry(BaseModel):
    """A single entry from the Claude JSONL session log."""
    timestamp: str
    entry_type: str  # 'tool_use' | 'text'
    tool_name: Optional[str] = None
    text: str


class SessionLogResponse(BaseModel):
    """Response for GET /api/autopilot/session-log."""
    active: bool
    session_file: Optional[str] = None
    entries: list[SessionLogEntry]
    total_entries: int


class AutoPilotStatusResponse(BaseModel):
    """Response for auto-pilot enable/status."""
    enabled: bool
    stopping: bool = False  # True when disabled but Claude process still running
    current_feature_id: Optional[int] = None
    current_feature_name: Optional[str] = None
    current_feature_model: Optional[str] = None
    last_error: Optional[str] = None
    log: list[LogEntry] = []
    # Manual launch fields (user clicked "Launch Claude" in detail panel)
    manual_active: bool = False
    manual_feature_id: Optional[int] = None
    manual_feature_name: Optional[str] = None
    manual_feature_model: Optional[str] = None
    # Budget fields
    budget_limit: int = 0
    features_completed: int = 0
    budget_exhausted: bool = False


class BudgetPeriodData(BaseModel):
    """Usage data for a single AI billing period."""
    utilization: float      # 0–100 percentage (may exceed 100 when exhausted)
    resets_at: str          # ISO 8601 UTC timestamp from the provider
    resets_formatted: str   # Human-readable: "14:30" (today) or "Mon 14:30"


class BudgetResponse(BaseModel):
    """AI provider budget/usage response."""
    provider: str = "anthropic"
    five_hour: Optional[BudgetPeriodData] = None
    seven_day: Optional[BudgetPeriodData] = None
    error: Optional[str] = None


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Feature Dashboard API",
        "version": "1.0.0",
        "endpoints": {
            "get_features": "GET /api/features",
            "create_feature": "POST /api/features",
            "get_feature": "GET /api/features/{id}",
            "update_feature": "PUT /api/features/{id}",
            "delete_feature": "DELETE /api/features/{id}",
            "update_state": "PATCH /api/features/{id}/state",
            "update_priority": "PATCH /api/features/{id}/priority",
            "move_feature": "PATCH /api/features/{id}/move",
            "stats": "GET /api/features/stats",
            "databases": "GET /api/databases",
            "databases_active": "GET /api/databases/active",
            "databases_select": "POST /api/databases/select",
            "launch_claude": "POST /api/features/{id}/launch-claude",
            "plan_tasks": "POST /api/plan-tasks",
            "autopilot_enable": "POST /api/autopilot/enable",
            "autopilot_disable": "POST /api/autopilot/disable",
            "autopilot_status": "GET /api/autopilot/status",
            "autopilot_log_clear": "POST /api/autopilot/log/clear",
            "get_settings": "GET /api/settings",
            "update_settings": "PUT /api/settings"
        }
    }


@app.get("/api/databases", response_model=list[DatabaseInfo])
async def get_databases():
    """
    Get list of configured databases.

    Returns the list from dashboards.json with existence and active status.
    """
    config = load_dashboards_config()
    result = []

    for db_config in config:
        db_path = PROJECT_DIR / db_config["path"]
        result.append(DatabaseInfo(
            name=db_config["name"],
            path=db_config["path"],
            exists=db_path.exists() and validate_db_path(db_path),
            is_active=db_path.resolve() == _current_db_path.resolve()
        ))

    return result


@app.get("/api/databases/active", response_model=DatabaseInfo)
async def get_active_database():
    """Get the currently active database."""
    config = load_dashboards_config()

    # Find the matching config entry
    for db_config in config:
        db_path = PROJECT_DIR / db_config["path"]
        if db_path.resolve() == _current_db_path.resolve():
            return DatabaseInfo(
                name=db_config["name"],
                path=db_config["path"],
                exists=True,
                is_active=True
            )

    # If not in config, return current path info
    return DatabaseInfo(
        name="Current Database",
        path=str(_current_db_path.relative_to(PROJECT_DIR)),
        exists=_current_db_path.exists(),
        is_active=True
    )


@app.post("/api/databases/select")
async def select_database(request: SelectDatabaseRequest):
    """
    Select a different database to use.

    Args:
        request: Contains the path to the database to select

    Returns:
        Success message with the new active database
    """
    db_path = PROJECT_DIR / request.path

    if not db_path.exists():
        raise HTTPException(status_code=404, detail=f"Database file not found: {request.path}")

    if not validate_db_path(db_path):
        raise HTTPException(status_code=400, detail=f"Invalid SQLite database or missing features table: {request.path}")

    try:
        switch_database(db_path)
        return {
            "message": "Database switched successfully",
            "active_database": request.path
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to switch database: {str(e)}")


@app.get("/api/features")
async def get_features(
    passes: Optional[bool] = None,
    in_progress: Optional[bool] = None,
    category: Optional[str] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None
):
    """
    Get all features with optional filters and pagination.

    Query parameters:
    - passes: Filter by passing status (true/false)
    - in_progress: Filter by in-progress status (true/false)
    - category: Filter by category name
    - limit: Maximum number of features to return (pagination)
    - offset: Number of features to skip (pagination)

    Returns:
    - If limit is provided: PaginatedFeaturesResponse with metadata
    - Otherwise: list[FeatureResponse] (backward compatible)
    """
    session = get_session()
    try:
        query = session.query(Feature)

        if passes is not None:
            query = query.filter(Feature.passes == passes)

        if in_progress is not None:
            query = query.filter(Feature.in_progress == in_progress)

        if category is not None:
            query = query.filter(Feature.category == category)

        # Order by completed_at DESC for done features (passes=true), otherwise by priority
        if passes is True:
            query = query.order_by(Feature.completed_at.desc().nulls_last())
        else:
            query = query.order_by(Feature.priority.asc())

        # If pagination parameters provided, return paginated response
        if limit is not None:
            # Get total count before pagination
            total = query.count()

            # Apply pagination with default limit of 20 for done features
            actual_limit = limit if limit > 0 else 20
            actual_offset = offset if offset is not None else 0

            features = query.limit(actual_limit).offset(actual_offset).all()
            fids = [f.id for f in features]
            counts = get_comment_counts(session, fids)
            logs = get_recent_logs(session, fids)

            return PaginatedFeaturesResponse(
                features=[feature_to_response(f, counts, logs) for f in features],
                total=total,
                limit=actual_limit,
                offset=actual_offset
            )

        # Otherwise return simple list (backward compatible)
        features = query.all()
        fids = [f.id for f in features]
        counts = get_comment_counts(session, fids)
        logs = get_recent_logs(session, fids)
        return [feature_to_response(f, counts, logs) for f in features]
    finally:
        session.close()


@app.get("/api/features/stats", response_model=StatsResponse)
async def get_stats():
    """Get feature statistics."""
    session = get_session()
    try:
        total = session.query(Feature).count()
        passing = session.query(Feature).filter(Feature.passes == True).count()
        in_progress = session.query(Feature).filter(Feature.in_progress == True).count()
        percentage = round((passing / total) * 100, 1) if total > 0 else 0.0

        return StatsResponse(
            passing=passing,
            in_progress=in_progress,
            total=total,
            percentage=percentage
        )
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Autocomplete endpoints
# ---------------------------------------------------------------------------

@app.get("/api/autocomplete/name")
def get_autocomplete_name(prefix: str = ""):
    """Return up to 5 name token suggestions matching the given prefix.

    Returns an empty suggestion list if the prefix is shorter than 3 characters.
    Results are ordered by usage_count descending.
    """
    if len(prefix) < 3:
        return {"suggestions": []}

    session = get_session()
    try:
        rows = (
            session.query(NameToken.token)
            .filter(NameToken.token.like(f"{prefix}%"))
            .order_by(NameToken.usage_count.desc())
            .limit(5)
            .all()
        )
        return {"suggestions": [row.token for row in rows]}
    finally:
        session.close()


@app.get("/api/autocomplete/description")
def get_autocomplete_description(prefix: str = ""):
    """Return up to 5 description token suggestions matching the given prefix.

    Returns an empty suggestion list if the prefix is shorter than 3 characters.
    Results are ordered by usage_count descending.
    """
    if len(prefix) < 3:
        return {"suggestions": []}

    session = get_session()
    try:
        rows = (
            session.query(DescriptionToken.token)
            .filter(DescriptionToken.token.like(f"{prefix}%"))
            .order_by(DescriptionToken.usage_count.desc())
            .limit(5)
            .all()
        )
        return {"suggestions": [row.token for row in rows]}
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Feature stream — SSE endpoint for immediate board refresh
# ---------------------------------------------------------------------------

# Module-level subscriber list for feature events.
# Each subscriber is an asyncio.Queue; broadcast() puts events onto every queue.
_feature_subscribers: list[asyncio.Queue] = []

# Heartbeat interval for the feature SSE stream (seconds).
# Override in tests to avoid long waits.
_FEATURE_SSE_HEARTBEAT_SECONDS: float = 15.0


async def _broadcast_feature_event(event: dict) -> None:
    """Push an event dict to every connected /api/features/stream subscriber."""
    for q in list(_feature_subscribers):
        await q.put(event)


@app.get("/api/features/stream")
async def feature_stream():
    """
    SSE endpoint for real-time board refresh notifications.

    The browser subscribes here once on page load.  Events pushed:
      - feature_created: when a new feature is created (e.g. via the interview skill)
      - heartbeat:       every 15 s to keep the connection alive through proxies

    On disconnect the subscriber queue is automatically removed.
    """
    queue: asyncio.Queue = asyncio.Queue()
    _feature_subscribers.append(queue)

    async def event_generator():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=_FEATURE_SSE_HEARTBEAT_SECONDS)
                except asyncio.TimeoutError:
                    yield "event: heartbeat\ndata: {}\n\n"
                    continue

                if event["type"] == "feature_created":
                    yield (
                        f"event: feature_created\n"
                        f"data: {json.dumps({'id': event.get('id'), 'name': event.get('name')})}\n\n"
                    )
        finally:
            try:
                _feature_subscribers.remove(queue)
            except ValueError:
                pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/features/notify", status_code=200)
async def notify_feature_created(feature_id: int, name: str):
    """
    Broadcast a feature_created event to all /api/features/stream subscribers.

    Called by the interview skill after feature_create MCP tool succeeds,
    so the board refreshes immediately without waiting for the 5-second poll.
    """
    await _broadcast_feature_event({"type": "feature_created", "id": feature_id, "name": name})
    return {"status": "notified", "subscribers": len(_feature_subscribers)}


@app.get("/api/debug/features/{feature_id}")
async def get_feature_raw(feature_id: int):
    """Get raw feature dict for debugging."""
    session = get_session()
    try:
        feature = session.query(Feature).filter(Feature.id == feature_id).first()

        if feature is None:
            raise HTTPException(status_code=404, detail=f"Feature {feature_id} not found")

        return feature.to_dict()
    finally:
        session.close()


@app.get("/api/features/{feature_id}", response_model=FeatureResponse, response_model_exclude_none=False)
async def get_feature(feature_id: int):
    """Get a single feature by ID."""
    session = get_session()
    try:
        feature = session.query(Feature).filter(Feature.id == feature_id).first()

        if feature is None:
            raise HTTPException(status_code=404, detail=f"Feature {feature_id} not found")

        counts = get_comment_counts(session, [feature_id])
        logs = get_recent_logs(session, [feature_id])
        return feature_to_response(feature, counts, logs)
    finally:
        session.close()


@app.get("/api/features/{feature_id}/claude-log", response_model=ClaudeLogResponse)
async def get_claude_log(feature_id: int, limit: int = 10, stream: str = "all"):
    """Get the last N lines of Claude process output for a feature.

    Returns 404 if no log buffer exists for the feature (process never started
    or has already exited and been cleaned up).  Returns 200 with an empty
    ``lines`` list if the process started but has not yet produced output.

    Query params:
    - limit: number of lines to return, clamped to 1–500 (default 10)
    - stream: 'stdout' | 'stderr' | 'all' (default 'all')
    """
    if feature_id not in _claude_process_logs:
        raise HTTPException(status_code=404, detail=f"No Claude log found for feature {feature_id}")

    log = _claude_process_logs[feature_id]
    all_lines = list(log.lines)

    if stream != "all":
        all_lines = [ln for ln in all_lines if ln.stream == stream]

    total = len(all_lines)
    clamped_limit = max(1, min(limit, 500))
    selected = all_lines[-clamped_limit:] if all_lines else []

    return ClaudeLogResponse(
        feature_id=feature_id,
        active=feature_id in _claude_process_logs,
        lines=[
            ClaudeLogLineResponse(timestamp=ln.timestamp, stream=ln.stream, text=ln.text)
            for ln in selected
        ],
        total_lines=total,
    )


@app.get("/api/autopilot/session-log", response_model=SessionLogResponse)
async def get_autopilot_session_log(limit: int = 50):
    """Get log entries from the active Claude JSONL session file.

    Reads ~/.claude/projects/{slug}/*.jsonl files created after the current
    autopilot or manual session started. Returns tool calls and text responses.

    Query params:
    - limit: number of entries to return (1–200, default 50)
    """
    state = get_autopilot_state()
    # Include stopping state: autopilot disabled but Claude process still running —
    # the session log should remain readable until the process actually exits.
    active = state.enabled or state.manual_active or state.stopping

    if not active or state.session_start_time is None:
        return SessionLogResponse(
            active=active,
            session_file=None,
            entries=[],
            total_entries=0,
        )

    working_dir = str(_current_db_path.parent)
    projects_dir = _get_claude_projects_dir(working_dir)

    if projects_dir is None:
        return SessionLogResponse(
            active=active,
            session_file=None,
            entries=[],
            total_entries=0,
        )

    # Use cached session file if already identified; otherwise search.
    if state.session_jsonl_path is not None:
        session_file = state.session_jsonl_path
    else:
        session_file = _find_session_jsonl(
            projects_dir,
            state.session_start_time,
            prompt_snippet=state.session_prompt_snippet,
        )
        if session_file is not None:
            state.session_jsonl_path = session_file  # cache for future polls

    if session_file is None:
        return SessionLogResponse(
            active=active,
            session_file=None,
            entries=[],
            total_entries=0,
        )

    clamped_limit = max(1, min(limit, 200))
    entries = _parse_jsonl_log(session_file, limit=clamped_limit)

    return SessionLogResponse(
        active=active,
        session_file=session_file.name,
        entries=[SessionLogEntry(**e) for e in entries],
        total_entries=len(entries),
    )


@app.post("/api/features", response_model=FeatureResponse, status_code=201)
async def create_feature(request: CreateFeatureRequest):
    """
    Create a new feature.

    Automatically assigns priority as max(existing_priorities) + 1.
    Sets passes=False and in_progress=False by default.
    """
    session = get_session()
    try:
        # Append after the current highest priority among active (non-passing) features
        max_priority = session.query(Feature.priority).filter(Feature.passes == False).order_by(Feature.priority.desc()).first()
        next_priority = (max_priority[0] + _PRIORITY_STEP) if max_priority else _PRIORITY_STEP

        # Validate model if provided
        if request.model is not None and request.model not in VALID_MODELS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid model '{request.model}'. Must be one of: {', '.join(sorted(VALID_MODELS))}"
            )

        # Create new feature
        new_feature = Feature(
            priority=next_priority,
            category=request.category,
            name=request.name,
            description=request.description,
            steps=request.steps,
            passes=False,
            in_progress=False,
            model=request.model or "sonnet",
        )

        session.add(new_feature)
        session.commit()
        session.refresh(new_feature)

        # Upsert name_tokens for each token in the new feature's name
        for token in set(normalize_tokens(new_feature.name)):
            existing = session.query(NameToken).filter(NameToken.token == token).first()
            if existing:
                existing.usage_count += 1
            else:
                session.add(NameToken(token=token, usage_count=1))

        # Upsert description_tokens for each token in the new feature's description
        for token in set(normalize_tokens(new_feature.description)):
            existing = session.query(DescriptionToken).filter(DescriptionToken.token == token).first()
            if existing:
                existing.usage_count += 1
            else:
                session.add(DescriptionToken(token=token, usage_count=1))
        session.commit()

        return feature_to_response(new_feature, {})
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create feature: {str(e)}")
    finally:
        session.close()


@app.put("/api/features/{feature_id}", response_model=FeatureResponse)
async def update_feature(feature_id: int, request: UpdateFeatureRequest):
    """
    Update feature fields.

    Only updates fields that are provided in the request.
    Automatically updates modified_at timestamp.
    """
    session = get_session()
    try:
        feature = session.query(Feature).filter(Feature.id == feature_id).first()

        if feature is None:
            raise HTTPException(status_code=404, detail=f"Feature {feature_id} not found")

        # Update only provided fields
        if request.category is not None:
            feature.category = request.category
        if request.name is not None:
            feature.name = request.name
        if request.description is not None:
            feature.description = request.description
        if request.steps is not None:
            feature.steps = request.steps
        if request.model is not None:
            if request.model not in VALID_MODELS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid model '{request.model}'. Must be one of: {', '.join(sorted(VALID_MODELS))}"
                )
            feature.model = request.model

        session.commit()
        session.refresh(feature)

        # Upsert name_tokens if name was updated (append-only, no decrement)
        if request.name is not None:
            for token in set(normalize_tokens(feature.name)):
                existing = session.query(NameToken).filter(NameToken.token == token).first()
                if existing:
                    existing.usage_count += 1
                else:
                    session.add(NameToken(token=token, usage_count=1))
            session.commit()

        # Upsert description_tokens if description was updated (append-only, no decrement)
        if request.description is not None:
            for token in set(normalize_tokens(feature.description)):
                existing = session.query(DescriptionToken).filter(DescriptionToken.token == token).first()
                if existing:
                    existing.usage_count += 1
                else:
                    session.add(DescriptionToken(token=token, usage_count=1))
            session.commit()

        return feature_to_response(feature, get_comment_counts(session, [feature.id]), get_recent_logs(session, [feature.id]))
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update feature: {str(e)}")
    finally:
        session.close()


@app.delete("/api/features/{feature_id}", status_code=204)
async def delete_feature(feature_id: int):
    """
    Delete a feature permanently.

    Returns 204 No Content on success.
    """
    session = get_session()
    try:
        feature = session.query(Feature).filter(Feature.id == feature_id).first()

        if feature is None:
            raise HTTPException(status_code=404, detail=f"Feature {feature_id} not found")

        session.delete(feature)
        session.commit()

        return None
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete feature: {str(e)}")
    finally:
        session.close()


@app.patch("/api/features/{feature_id}/state", response_model=FeatureResponse)
async def update_feature_state(feature_id: int, request: UpdateFeatureStateRequest):
    """
    Update feature state (passes/in_progress).

    This is used to move features between lanes (TODO, In Progress, Done).
    When setting passes=True, sets completed_at timestamp.
    When setting passes=False, clears completed_at timestamp.
    """
    from datetime import datetime

    session = get_session()
    try:
        feature = session.query(Feature).filter(Feature.id == feature_id).first()

        if feature is None:
            raise HTTPException(status_code=404, detail=f"Feature {feature_id} not found")

        # Update state fields
        if request.passes is not None:
            feature.passes = request.passes
            # Set/clear completed_at based on passes status
            if request.passes:
                feature.completed_at = datetime.now()
            else:
                feature.completed_at = None

        if request.in_progress is not None:
            feature.in_progress = request.in_progress

        session.commit()
        session.refresh(feature)

        return feature_to_response(feature, get_comment_counts(session, [feature.id]), get_recent_logs(session, [feature.id]))
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update feature state: {str(e)}")
    finally:
        session.close()


@app.patch("/api/features/{feature_id}/priority", response_model=FeatureResponse)
async def update_feature_priority(feature_id: int, request: UpdateFeaturePriorityRequest):
    """
    Update feature priority to a specific value.

    This is used for direct reordering by dragging features to specific positions.
    """
    session = get_session()
    try:
        feature = session.query(Feature).filter(Feature.id == feature_id).first()

        if feature is None:
            raise HTTPException(status_code=404, detail=f"Feature {feature_id} not found")

        if request.priority < 1:
            raise HTTPException(status_code=400, detail="Priority must be >= 1")

        feature.priority = request.priority

        session.commit()
        session.refresh(feature)

        return feature_to_response(feature, get_comment_counts(session, [feature.id]), get_recent_logs(session, [feature.id]))
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update feature priority: {str(e)}")
    finally:
        session.close()


_PRIORITY_STEP = 100  # Gap between adjacent feature priorities


def _normalize_lane_priorities(features_in_order: list) -> None:
    """
    Assign clean sequential priorities (100, 200, 300, ...) to features in order.

    Normalizing the whole lane on every move/reorder keeps priorities distinct and
    well-spaced so that subsequent swaps never produce conflicts.
    """
    for i, f in enumerate(features_in_order, start=1):
        f.priority = i * _PRIORITY_STEP


@app.patch("/api/features/{feature_id}/move", response_model=FeatureResponse)
async def move_feature(feature_id: int, request: MoveFeatureRequest):
    """
    Move a feature up or down within its current lane.

    Finds the adjacent feature by sorted position (not priority comparison) so
    that duplicate priority values are handled correctly. Deduplicates lane
    priorities after swapping to guarantee all values remain distinct.
    Direction must be "up" or "down".
    """
    if request.direction not in ["up", "down"]:
        raise HTTPException(status_code=400, detail="Direction must be 'up' or 'down'")

    session = get_session()
    try:
        feature = session.query(Feature).filter(Feature.id == feature_id).first()

        if feature is None:
            raise HTTPException(status_code=404, detail=f"Feature {feature_id} not found")

        # Get all features in the same lane sorted by (priority, id) for stable ordering.
        # Using id as a tiebreaker ensures deterministic results when priorities are equal.
        lane_features = session.query(Feature).filter(
            Feature.passes == feature.passes,
            Feature.in_progress == feature.in_progress,
        ).order_by(Feature.priority.asc(), Feature.id.asc()).all()

        # Find this feature's position in the sorted lane.
        feature_idx = next((i for i, f in enumerate(lane_features) if f.id == feature_id), None)

        if request.direction == "up":
            if feature_idx == 0:
                raise HTTPException(status_code=400, detail=f"Cannot move feature {request.direction}: already at the edge")
            adj_idx = feature_idx - 1
        else:
            if feature_idx == len(lane_features) - 1:
                raise HTTPException(status_code=400, detail=f"Cannot move feature {request.direction}: already at the edge")
            adj_idx = feature_idx + 1

        # Swap positions in the ordered list, then normalize the whole lane to clean
        # 100-step priorities. This resolves any pre-existing duplicates and ensures
        # future swaps never produce conflicts.
        lane_features[feature_idx], lane_features[adj_idx] = lane_features[adj_idx], lane_features[feature_idx]
        _normalize_lane_priorities(lane_features)

        session.commit()
        session.refresh(feature)

        return feature_to_response(feature, get_comment_counts(session, [feature.id]), get_recent_logs(session, [feature.id]))
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to move feature: {str(e)}")
    finally:
        session.close()


@app.patch("/api/features/{feature_id}/reorder", response_model=FeatureResponse)
async def reorder_feature(feature_id: int, request: ReorderFeatureRequest):
    """
    Reorder a feature by placing it immediately before or after a target feature.

    Both features must be in the same lane. Redistributes priority values so
    the dragged card ends up at the exact drop position regardless of distance.
    """
    session = get_session()
    try:
        feature = session.query(Feature).filter(Feature.id == feature_id).first()
        if feature is None:
            raise HTTPException(status_code=404, detail=f"Feature {feature_id} not found")

        target = session.query(Feature).filter(Feature.id == request.target_id).first()
        if target is None:
            raise HTTPException(status_code=404, detail=f"Target feature {request.target_id} not found")

        if feature.passes != target.passes or feature.in_progress != target.in_progress:
            raise HTTPException(status_code=400, detail="Features must be in the same lane")

        # Get all features in the lane sorted by (priority, id) for stable ordering.
        lane_features = session.query(Feature).filter(
            Feature.passes == feature.passes,
            Feature.in_progress == feature.in_progress,
        ).order_by(Feature.priority.asc(), Feature.id.asc()).all()

        # Build new order: remove dragged feature, insert at target position
        ordered = [f for f in lane_features if f.id != feature_id]
        target_idx = next((i for i, f in enumerate(ordered) if f.id == request.target_id), None)

        if target_idx is None:
            raise HTTPException(status_code=400, detail="Target feature not found in the same lane")

        insert_idx = target_idx if request.insert_before else target_idx + 1
        ordered.insert(insert_idx, feature)

        # Normalize the whole lane to clean 100-step priorities. This eliminates
        # any pre-existing duplicates and gives room between slots so future moves
        # never produce conflicts.
        _normalize_lane_priorities(ordered)

        session.commit()
        session.refresh(feature)

        return feature_to_response(feature, get_comment_counts(session, [feature.id]), get_recent_logs(session, [feature.id]))
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to reorder feature: {str(e)}")
    finally:
        session.close()


@app.get("/api/settings", response_model=SettingsResponse)
async def get_settings():
    """Get application settings."""
    settings = load_settings()
    settings["available_providers"] = sorted(REGISTRY.keys())
    return SettingsResponse(**settings)


@app.put("/api/settings", response_model=SettingsResponse)
async def update_settings(request: UpdateSettingsRequest):
    """Update application settings."""
    try:
        # Validate the requested provider before saving
        get_provider(request.provider)
        current = load_settings()
        settings = {
            "claude_prompt_template": request.claude_prompt_template,
            "plan_tasks_prompt_template": (
                request.plan_tasks_prompt_template
                if request.plan_tasks_prompt_template is not None
                else current.get("plan_tasks_prompt_template", PLAN_TASKS_PROMPT_TEMPLATE)
            ),
            "autopilot_budget_limit": request.autopilot_budget_limit,
            "provider": request.provider,
        }
        save_settings(settings)
        settings["available_providers"] = sorted(REGISTRY.keys())
        return SettingsResponse(**settings)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save settings: {str(e)}")


@app.get("/api/budget", response_model=BudgetResponse)
async def get_budget():
    """Get AI provider budget/usage information.

    Reads the Claude OAuth credentials from ~/.claude/.credentials.json and
    calls the Anthropic usage API to return 5-hour and 7-day utilization
    percentages with reset times.  Returns an error field instead of raising
    an HTTP exception so the UI can degrade gracefully when credentials are
    absent or the API is unreachable.
    """

    def _format_reset_time(reset_at: str) -> str:
        """Return a human-readable reset time: 'HH:MM' today, 'ddd HH:MM' otherwise."""
        if not reset_at:
            return "unknown"
        bare = reset_at[:19] if len(reset_at) >= 19 else reset_at
        try:
            utc_time = datetime.fromisoformat(bare).replace(tzinfo=timezone.utc)
            local_time = utc_time.astimezone()
            now = datetime.now(local_time.tzinfo)
            if local_time.date() == now.date():
                return local_time.strftime('%H:%M')
            return local_time.strftime('%a %H:%M')
        except Exception:
            return reset_at

    def _fetch_usage():
        cred_path = Path.home() / '.claude' / '.credentials.json'
        if not cred_path.exists():
            return None, "Credentials not found (~/.claude/.credentials.json)"
        try:
            creds = json.loads(cred_path.read_text(encoding='utf-8'))
            token = creds.get('claudeAiOauth', {}).get('accessToken')
            if not token:
                return None, "No OAuth access token found in credentials"
        except Exception as exc:
            return None, f"Failed to read credentials: {exc}"
        try:
            req = urllib.request.Request(
                'https://api.anthropic.com/api/oauth/usage',
                headers={
                    'Accept': 'application/json',
                    'Authorization': f'Bearer {token}',
                    'anthropic-beta': 'oauth-2025-04-20',
                }
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read().decode('utf-8')), None
        except urllib.error.HTTPError as exc:
            return None, f"API error: {exc.code} {exc.reason}"
        except Exception as exc:
            return None, f"Request failed: {exc}"

    data, error = await asyncio.get_event_loop().run_in_executor(None, _fetch_usage)
    if error:
        return BudgetResponse(error=error)

    result = BudgetResponse()
    fh = data.get('five_hour')
    if fh is not None:
        result.five_hour = BudgetPeriodData(
            utilization=round(float(fh.get('utilization', 0)), 1),
            resets_at=fh.get('resets_at', ''),
            resets_formatted=_format_reset_time(fh.get('resets_at', '')),
        )
    sd = data.get('seven_day')
    if sd is not None:
        result.seven_day = BudgetPeriodData(
            utilization=round(float(sd.get('utilization', 0)), 1),
            resets_at=sd.get('resets_at', ''),
            resets_formatted=_format_reset_time(sd.get('resets_at', '')),
        )
    return result


@app.post("/api/features/{feature_id}/launch-claude", response_model=LaunchClaudeResponse)
async def launch_claude_for_feature(feature_id: int, request: LaunchClaudeRequest = None):
    """
    Launch a Claude Code session to work on a specific feature.

    Opens Claude in a new terminal window with the feature context as the initial prompt.
    When hidden_execution=True (default), Claude runs with --print so the session closes
    automatically when the task is complete. When hidden_execution=False, Claude opens
    in interactive mode and the terminal stays open.

    The working directory is the folder containing the active features.db, so Claude
    operates in the correct project context.

    Only works for TODO and IN PROGRESS features (not completed features).
    """
    if request is None:
        request = LaunchClaudeRequest()

    session = get_session()
    try:
        feature = session.query(Feature).filter(Feature.id == feature_id).first()

        if feature is None:
            raise HTTPException(status_code=404, detail=f"Feature {feature_id} not found")

        if feature.passes:
            raise HTTPException(status_code=400, detail="Cannot launch Claude for a completed feature")

        # Load prompt template from settings
        settings = load_settings()
        template = settings.get("claude_prompt_template", DEFAULT_PROMPT_TEMPLATE)

        # Build steps text
        steps_text = "\n".join(f"{i + 1}. {step}" for i, step in enumerate(feature.steps))

        # Build prompt using template
        prompt = template.format(
            feature_id=feature.id,
            category=feature.category,
            name=feature.name,
            description=feature.description,
            steps=steps_text
        )

        # Determine which model to use
        feature_model = feature.model or "sonnet"

        # Launch Claude in the directory containing the active features.db
        working_dir = str(_current_db_path.parent)

        launched_process = None
        try:
            if sys.platform == "win32":
                # Write prompt to a temp file to avoid shell quoting issues
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".txt", delete=False, encoding="utf-8"
                ) as f:
                    f.write(prompt)
                    prompt_file = f.name

                if request.hidden_execution:
                    # Hidden: capture stdout/stderr for log monitoring
                    ps_cmd = f'claude --model {feature_model} --dangerously-skip-permissions --print (Get-Content -LiteralPath "{prompt_file}" -Raw)'
                    ps_executables = ["pwsh", "powershell"]
                    launched = False
                    for ps_exe in ps_executables:
                        try:
                            launched_process = subprocess.Popen(
                                [ps_exe, "-Command", ps_cmd],
                                cwd=working_dir,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                            )
                            launched = True
                            break
                        except FileNotFoundError:
                            continue
                    if not launched:
                        raise HTTPException(
                            status_code=500,
                            detail="No PowerShell found. Install PowerShell 7 (pwsh) or ensure powershell.exe is available.",
                        )
                else:
                    _launch_claude_terminal(prompt, working_dir, model=feature_model)
                    launched_process = None
            else:
                if request.hidden_execution:
                    cmd = ["claude", "--model", feature_model, "--dangerously-skip-permissions", "--print", prompt]
                    launched_process = subprocess.Popen(
                        cmd,
                        cwd=working_dir,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                else:
                    _launch_claude_terminal(prompt, working_dir, model=feature_model)
                    launched_process = None
        except FileNotFoundError:
            raise HTTPException(
                status_code=500,
                detail="Claude CLI not found. Make sure 'claude' is in your PATH.",
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to launch Claude: {str(e)}")

        # Track the manual launch in autopilot state so the UI can show progress
        state = get_autopilot_state()
        # Cancel any previous manual monitor task
        if state.manual_monitor_task and not state.manual_monitor_task.done():
            state.manual_monitor_task.cancel()
        state.manual_active = True
        state.manual_feature_id = feature_id
        state.manual_feature_name = feature.name
        state.manual_feature_model = feature_model
        state.manual_process = launched_process
        state.session_start_time = datetime.now(timezone.utc)
        state.session_prompt_snippet = f"Feature #{feature_id} [{feature.category}]"
        state.session_jsonl_path = None
        mode = "hidden" if request.hidden_execution else "interactive"
        _append_log(state, 'info', f"Manual launch \u2014 feature #{feature_id}: {feature.name} ({mode}, {feature_model})")
        state.manual_monitor_task = asyncio.create_task(monitor_manual_process(state))

        return LaunchClaudeResponse(
            launched=True,
            feature_id=feature_id,
            prompt=prompt,
            working_directory=working_dir,
            model=feature_model,
            hidden_execution=request.hidden_execution,
        )
    finally:
        session.close()


@app.post("/api/plan-tasks", response_model=PlanTasksResponse)
async def plan_tasks(request: PlanTasksRequest):
    """
    Launch an interactive Claude Code session for planning new features.

    Builds a planning prompt from the expand-project template adapted for this dashboard,
    then launches Claude CLI in interactive mode (no --print flag) so the user can have
    a conversation with Claude. The Claude session uses MCP tools to create features
    directly in the database.

    The working directory is the project root so Claude has access to .mcp.json and
    the active features.db.
    """
    if not request.description.strip():
        raise HTTPException(status_code=400, detail="Description cannot be empty")

    settings = load_settings()
    template = settings.get("plan_tasks_prompt_template", PLAN_TASKS_PROMPT_TEMPLATE)
    prompt = template.format(description=request.description.strip())
    working_dir = str(_current_db_path.parent)

    try:
        _launch_claude_terminal(prompt, working_dir)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to launch Claude: {str(e)}")

    return PlanTasksResponse(
        launched=True,
        prompt=prompt,
        working_directory=working_dir,
    )


@app.post("/api/autopilot/enable", response_model=AutoPilotStatusResponse)
async def enable_autopilot():
    """
    Enable auto-pilot mode for the currently active database.

    Picks the next available feature (in-progress first, then TODO by priority),
    spawns a Claude process for it with hidden_execution=True, and returns the
    current auto-pilot status.

    Returns 409 if auto-pilot is already enabled.
    If no tasks are available, returns enabled=False with a log message.
    """
    state = get_autopilot_state()

    if state.enabled:
        raise HTTPException(status_code=409, detail="Auto-pilot is already enabled")

    # Clear any lingering stopping state (user re-enabled before old process exited).
    if state.stopping:
        # Cancel the waiting task first so its completion callback does NOT race
        # against the state we are about to set for the new run.
        if state.monitor_task is not None:
            state.monitor_task.cancel()
            state.monitor_task = None
        # Attempt to kill the old orphaned process so it does not interfere with
        # the new Claude run (especially on Windows where the child may outlive
        # the PowerShell wrapper).
        if state.active_process is not None:
            try:
                state.active_process.terminate()
            except Exception:
                pass
            state.active_process = None
        state.stopping = False
        state.current_feature_id = None
        state.current_feature_name = None
        state.current_feature_model = None

    session = get_session()
    try:
        feature = get_next_autopilot_feature(session)

        if feature is None:
            _append_log(state, 'info', 'No tasks available')
            settings = load_settings()
            return AutoPilotStatusResponse(
                enabled=False,
                current_feature_id=None,
                current_feature_name=None,
                last_error=None,
                log=list(state.log),
                budget_limit=settings.get("autopilot_budget_limit", 0),
                features_completed=state.features_completed,
                budget_exhausted=state.budget_exhausted,
            )

        state.enabled = True
        state.current_feature_id = feature.id
        state.current_feature_name = feature.name
        state.current_feature_model = feature.model or "sonnet"
        state.last_error = None
        state.budget_exhausted = False
        state.last_skipped_feature_id = feature.id
        state.consecutive_skip_count = 0
        state.features_completed = 0
        state.log.clear()
        state.session_start_time = datetime.now(timezone.utc)
        state.session_prompt_snippet = f"Feature #{feature.id} [{feature.category}]"
        state.session_jsonl_path = None
        _append_log(state, 'info', f"Auto-pilot enabled for database: {_current_db_path.name}")
        _append_log(state, 'info', f"Starting feature #{feature.id}: {feature.name}")

        settings = load_settings()
        working_dir = str(_current_db_path.parent)
        feature_model = feature.model or "sonnet"

        try:
            proc = spawn_claude_for_autopilot(feature, settings, working_dir)
            state.active_process = proc
        except (FileNotFoundError, RuntimeError) as e:
            state.enabled = False
            state.current_feature_id = None
            state.current_feature_name = None
            state.current_feature_model = None
            err = str(e)
            state.last_error = err
            _append_log(state, 'error', err)
            raise HTTPException(status_code=500, detail=err)
        except Exception as e:
            state.enabled = False
            state.current_feature_id = None
            state.current_feature_name = None
            state.current_feature_model = None
            err = f"Failed to launch Claude: {str(e)}"
            state.last_error = err
            raise HTTPException(status_code=500, detail=err)

        _append_log(state, 'info', f"Claude launched for feature #{feature.id} with model {feature_model}")
        state.monitor_task = asyncio.create_task(
            monitor_claude_process(feature.id, proc, _current_db_path, state)
        )
        _write_autopilot_to_config(True)

        return AutoPilotStatusResponse(
            enabled=True,
            current_feature_id=feature.id,
            current_feature_name=feature.name,
            current_feature_model=feature.model or "sonnet",
            last_error=None,
            log=list(state.log),
            budget_limit=settings.get("autopilot_budget_limit", 0),
            features_completed=state.features_completed,
            budget_exhausted=state.budget_exhausted,
        )
    finally:
        session.close()


def _get_child_procs(proc) -> list:
    """Return psutil Process objects for all descendants of *proc*.

    Must be called BEFORE proc.terminate() while the process tree is intact.
    Returns an empty list when psutil is unavailable or the process is not found.
    This is primarily useful on Windows where Claude runs as a child of a
    PowerShell wrapper — terminating the wrapper orphans Claude, so we need to
    track children separately to know when Claude actually exits.
    """
    try:
        import psutil
        try:
            return psutil.Process(proc.pid).children(recursive=True)
        except psutil.NoSuchProcess:
            return []
    except ImportError:
        return []


def _any_proc_running(procs: list) -> bool:
    """Return True if any psutil process in *procs* is still running."""
    for p in procs:
        try:
            if p.is_running() and p.status() != "zombie":
                return True
        except Exception:
            pass
    return False


def _wait_for_process_and_children(proc, children: list) -> None:
    """Block until *proc* and all psutil *children* have exited.

    Run in a thread-pool executor so the event loop is not blocked.
    Each wait is guarded with a bare except so one failure does not prevent
    the remaining processes from being waited on.
    """
    try:
        proc.wait()
    except Exception:
        pass
    for child in children:
        try:
            child.wait()
        except Exception:
            pass


async def _wait_for_stopping_process(
    proc: "subprocess.Popen",
    state: "_AutoPilotState",
    child_procs: list | None = None,
) -> None:
    """Wait for a Claude process (and any orphaned children) to exit.

    Called when terminate() was sent but the process (or a child it spawned on
    Windows) is still alive.  Once ALL processes exit the stopping flag and
    feature fields are cleared so the status bar disappears from the UI.

    On Windows, Claude runs inside a PowerShell wrapper.  Terminating the
    wrapper exits it quickly but leaves Claude alive as an orphan.  *child_procs*
    should contain the psutil handles for those children, collected before
    terminate() was called.  When empty (non-Windows or psutil unavailable),
    this function waits only for the parent process — the previous behaviour.

    If the task is cancelled (e.g. because the user re-enabled autopilot before
    the process finished) we return immediately WITHOUT touching state, because
    enable_autopilot() has already taken ownership of the state fields.

    Note: DB state (in_progress, passes) is exclusively managed by the Claude
    instance via MCP tools. The backend only manages process lifecycle and
    in-memory autopilot state.
    """
    children = child_procs or []
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _wait_for_process_and_children, proc, children)
    except asyncio.CancelledError:
        # Caller (enable_autopilot) cancelled this task and is responsible for
        # resetting state — do not touch anything here.
        return
    except Exception:
        pass
    # Normal completion: process has exited, clear stopping state.
    state.stopping = False
    state.current_feature_id = None
    state.current_feature_name = None
    state.current_feature_model = None
    state.active_process = None
    state.monitor_task = None
    _append_log(state, 'info', "Claude process finished — auto-pilot fully stopped")


@app.post("/api/autopilot/disable", response_model=AutoPilotStatusResponse)
async def disable_autopilot():
    """
    Disable auto-pilot mode for the currently active database.

    Terminates any active Claude process, clears the current feature, and sets
    enabled=false. Appends a 'Auto-pilot manually disabled' log entry.

    Always returns 200 — idempotent even if auto-pilot was already disabled.
    """
    state = get_autopilot_state()

    # Cancel the async monitor task so it no longer drives the autopilot loop.
    if state.monitor_task is not None:
        state.monitor_task.cancel()
        state.monitor_task = None

    # Attempt to terminate the Claude process.
    proc = state.active_process
    if proc is not None:
        # Collect child processes BEFORE terminating.  On Windows the spawned
        # process is a PowerShell wrapper; terminating it exits the wrapper
        # quickly but leaves Claude itself alive as an orphan.  We capture
        # the children now (while the tree is intact) so _wait_for_stopping_process
        # can also wait for Claude to actually finish.
        child_procs: list = _get_child_procs(proc)

        try:
            proc.terminate()
        except Exception:
            pass  # Process may have already exited

        # Check whether the parent process OR any of its children are still
        # alive.  On Windows the parent (PowerShell) may have exited already
        # even though Claude (child) is still running — so polling only the
        # parent is not sufficient.
        try:
            parent_running = proc.poll() is None
            children_running = _any_proc_running(child_procs)
            still_running = parent_running or children_running
        except Exception:
            still_running = False

        if still_running:
            # Process is still running — enter stopping state so the status bar
            # remains visible until Claude actually finishes.
            state.enabled = False
            state.stopping = True
            state.last_error = None
            # Keep current_feature_id / name / model for display purposes.
            _append_log(state, 'info', "Auto-pilot manually disabled — waiting for Claude process to finish")
            _write_autopilot_to_config(False)
            # Spawn a task that waits for the process (and children) and clears stopping state.
            state.monitor_task = asyncio.create_task(
                _wait_for_stopping_process(proc, state, child_procs)
            )
            _settings = load_settings()
            return AutoPilotStatusResponse(
                enabled=False,
                stopping=True,
                current_feature_id=state.current_feature_id,
                current_feature_name=state.current_feature_name,
                current_feature_model=state.current_feature_model,
                last_error=None,
                log=list(state.log),
                budget_limit=_settings.get("autopilot_budget_limit", 0),
                features_completed=state.features_completed,
                budget_exhausted=state.budget_exhausted,
            )
        else:
            # Process already exited — clear the handle.
            state.active_process = None

    # No running process — clean up immediately.
    state.enabled = False
    state.stopping = False
    state.current_feature_id = None
    state.current_feature_name = None
    state.current_feature_model = None
    state.last_error = None
    _append_log(state, 'info', "Auto-pilot manually disabled")
    _write_autopilot_to_config(False)

    _settings = load_settings()
    return AutoPilotStatusResponse(
        enabled=False,
        stopping=False,
        current_feature_id=None,
        current_feature_name=None,
        current_feature_model=None,
        last_error=None,
        log=list(state.log),
        budget_limit=_settings.get("autopilot_budget_limit", 0),
        features_completed=state.features_completed,
        budget_exhausted=state.budget_exhausted,
    )


@app.post("/api/autopilot/log/clear")
async def clear_autopilot_log():
    """
    Clear all auto-pilot log entries for the active database.

    Empties the in-memory log deque without affecting the enabled/running state.
    Always returns 200 — idempotent even if the log is already empty.
    """
    state = get_autopilot_state()
    state.log.clear()
    return {"cleared": True}


@app.post("/api/autopilot/clear-error")
async def clear_autopilot_error():
    """
    Clear the last_error field for the active database's auto-pilot state.

    Allows the user to dismiss the error banner after auto-pilot stops on failure.
    Always returns 200 — idempotent even if last_error is already null.
    """
    state = get_autopilot_state()
    state.last_error = None
    state.budget_exhausted = False
    return {"cleared": True}


@app.get("/api/autopilot/status", response_model=AutoPilotStatusResponse)
async def get_autopilot_status():
    """
    Get the current auto-pilot state for the active database.

    Returns the enabled flag, the feature currently being worked on (id and name),
    the last error message (if any), and the event log (up to 100 entries).

    The frontend polls this endpoint every 2 seconds while auto-pilot is enabled.
    """
    state = get_autopilot_state()
    settings = load_settings()
    return AutoPilotStatusResponse(
        enabled=state.enabled,
        stopping=state.stopping,
        current_feature_id=state.current_feature_id,
        current_feature_name=state.current_feature_name,
        current_feature_model=state.current_feature_model,
        last_error=state.last_error,
        log=list(state.log),
        manual_active=state.manual_active,
        manual_feature_id=state.manual_feature_id,
        manual_feature_name=state.manual_feature_name,
        manual_feature_model=state.manual_feature_model,
        budget_limit=settings.get("autopilot_budget_limit", 0),
        features_completed=state.features_completed,
        budget_exhausted=state.budget_exhausted,
    )


@app.get("/api/features/{feature_id}/comments", response_model=list[CommentResponse])
async def get_comments(feature_id: int):
    """Get all comments for a feature, ordered by created_at ascending."""
    session = get_session()
    try:
        feature = session.query(Feature).filter(Feature.id == feature_id).first()
        if feature is None:
            raise HTTPException(status_code=404, detail=f"Feature {feature_id} not found")

        comments = session.query(Comment).filter(Comment.feature_id == feature_id).order_by(Comment.created_at.asc()).all()
        return [CommentResponse(**c.to_dict()) for c in comments]
    finally:
        session.close()


@app.post("/api/features/{feature_id}/comments", response_model=CommentResponse, status_code=201)
async def add_comment(feature_id: int, request: CreateCommentRequest):
    """Add a comment to a feature."""
    if not request.content.strip():
        raise HTTPException(status_code=400, detail="Comment content cannot be empty")

    session = get_session()
    try:
        feature = session.query(Feature).filter(Feature.id == feature_id).first()
        if feature is None:
            raise HTTPException(status_code=404, detail=f"Feature {feature_id} not found")

        comment = Comment(feature_id=feature_id, content=request.content.strip())
        session.add(comment)
        session.commit()
        session.refresh(comment)

        return CommentResponse(**comment.to_dict())
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to add comment: {str(e)}")
    finally:
        session.close()


@app.delete("/api/features/{feature_id}/comments/{comment_id}", status_code=204)
async def delete_comment(feature_id: int, comment_id: int):
    """Delete a comment from a feature."""
    session = get_session()
    try:
        comment = session.query(Comment).filter(
            Comment.id == comment_id,
            Comment.feature_id == feature_id
        ).first()

        if comment is None:
            raise HTTPException(status_code=404, detail=f"Comment {comment_id} not found on feature {feature_id}")

        session.delete(comment)
        session.commit()
        return None
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete comment: {str(e)}")
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Interview endpoints
# ---------------------------------------------------------------------------

from backend.interview_state import get_interview_session, _log_event as _log_interview_event, get_debug_log  # noqa: E402


class InterviewQuestionRequest(BaseModel):
    text: str
    options: list[str]


@app.post("/api/interview/question", status_code=200)
async def post_interview_question(
    request: InterviewQuestionRequest,
    x_interview_token: Optional[str] = Header(None),
):
    """
    Push a new question into the interview session.

    Called by Claude Code to send the next question to the browser.
    Overwrites any previously active question and resets answer state.

    Session token guard (duplicate-instance prevention):
      - First call (no active session): generates a session token, stores it,
        and returns it as ``session_token`` in the response body.
      - Subsequent calls: must supply the token in the ``X-Interview-Token``
        request header.  Returns 409 Conflict if the token is missing or
        does not match the stored owner token.

    Also returns 409 if the browser has already submitted an answer that Claude
    has not yet consumed via GET /api/interview/answer.
    """
    if not request.text.strip():
        raise HTTPException(status_code=422, detail="Question text must not be empty")
    if not request.options:
        raise HTTPException(status_code=422, detail="At least one option is required")

    session = get_interview_session()

    # --- Duplicate-session guard ---
    if session.owner_token is None:
        # No active session — this caller becomes the owner.
        new_token = session.claim_session()
    else:
        # A session is already in progress — validate the caller's token.
        if x_interview_token != session.owner_token:
            raise HTTPException(
                status_code=409,
                detail="An interview session is already active. "
                       "Only the session owner may post questions.",
            )
        new_token = None  # token already known by caller, no need to return it

    if session.has_unconsumed_answer():
        raise HTTPException(
            status_code=409,
            detail="An answer is pending and has not been consumed yet. "
                   "Call GET /api/interview/answer before posting a new question.",
        )

    await session.set_question(request.text, request.options)

    response: dict = {
        "text": session.active_question["text"],
        "options": session.active_question["options"],
    }
    if new_token is not None:
        response["session_token"] = new_token
    return response


# Heartbeat interval for the SSE stream (seconds).
# Override in tests to avoid 15-second waits.
_SSE_HEARTBEAT_SECONDS: float = 15.0


@app.get("/api/interview/question/stream")
async def interview_question_stream():
    """
    SSE endpoint for receiving interview questions in real time.

    Browser subscribes to this endpoint for the duration of an interview.
    Events pushed:
      - question:   when Claude posts a new question via POST /api/interview/question
      - heartbeat:  every 15 s to keep the connection alive through proxies
      - end:        when the session is terminated via DELETE /api/interview/session
    """
    session = get_interview_session()
    queue = session.subscribe()
    _log_interview_event(session, "sse_connect", {})

    async def event_generator():
        try:
            # Send the currently active question immediately if one exists
            if session.active_question:
                q = session.active_question
                yield (
                    f"event: question\n"
                    f"data: {json.dumps({'text': q['text'], 'options': q['options']})}\n\n"
                )

            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=_SSE_HEARTBEAT_SECONDS)
                except asyncio.TimeoutError:
                    yield "event: heartbeat\ndata: {}\n\n"
                    continue

                if event["type"] == "question":
                    yield (
                        f"event: question\n"
                        f"data: {json.dumps({'text': event['text'], 'options': event['options']})}\n\n"
                    )
                elif event["type"] == "answer_received":
                    yield "event: answer_received\ndata: {}\n\n"
                elif event["type"] == "session_paused":
                    yield "event: session-paused\ndata: {}\n\n"
                elif event["type"] == "session_timeout":
                    yield "event: session-timeout\ndata: {}\n\n"
                    break
                elif event["type"] == "session_ended":
                    features_created = event.get("features_created", 0)
                    yield f"event: end\ndata: {json.dumps({'features_created': features_created})}\n\n"
                    break
        finally:
            session.unsubscribe(queue)
            _log_interview_event(session, "sse_disconnect", {})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# Timeouts for GET /api/interview/answer long-poll (seconds).
# Override in tests to avoid multi-minute waits.
#   Soft timeout: no answer yet → broadcast session_paused to browser (session stays alive)
#   Hard timeout: still no answer → kill session, return 408 to Claude
_SOFT_TIMEOUT_SECONDS: float = 300.0   # 5 minutes
_HARD_TIMEOUT_SECONDS: float = 600.0   # 10 minutes


@app.get("/api/interview/answer")
async def get_interview_answer():
    """
    Long-polling endpoint that blocks until the user submits an answer.

    Called by Claude immediately after posting a question.  Two-phase timeout:

    • Soft timeout (_SOFT_TIMEOUT_SECONDS, default 5 min): no answer yet → the
      server broadcasts a ``session_paused`` SSE event so the browser shows a
      Revive button.  Session state is preserved; Claude continues blocking on
      this endpoint.

    • Hard timeout (_HARD_TIMEOUT_SECONDS, default 10 min total): still no
      answer → session is cleared, ``session_timeout`` is broadcast, and 408 is
      returned to Claude.

    Returns 408 Request Timeout if no answer arrives within the hard timeout.
    """
    session = get_interview_session()
    answer = await session.wait_for_answer(
        soft_timeout=_SOFT_TIMEOUT_SECONDS,
        hard_timeout=_HARD_TIMEOUT_SECONDS,
    )

    if answer is None:
        # Hard timeout: broadcast session-timeout and clear state
        await session.timeout()
        raise HTTPException(
            status_code=408,
            detail="No answer received within the timeout period.",
        )

    return {"value": answer}


class InterviewAnswerRequest(BaseModel):
    value: str


@app.post("/api/interview/answer", status_code=200)
async def post_interview_answer(request: InterviewAnswerRequest):
    """
    Submit the user's answer to the current interview question.

    Called by the browser when the user selects an answer option.
    Stores the answer in session state and broadcasts an answer_received event
    to all SSE subscribers so the browser can show a waiting state.

    Returns 400 if there is no active question pending an answer, or if an
    answer has already been submitted and not yet consumed by Claude.
    """
    if not request.value.strip():
        raise HTTPException(status_code=422, detail="Answer value must not be empty")

    session = get_interview_session()

    if session.active_question is None:
        raise HTTPException(
            status_code=400,
            detail="No active question is pending an answer.",
        )

    if session.has_unconsumed_answer():
        raise HTTPException(
            status_code=400,
            detail="An answer has already been submitted and not yet consumed.",
        )

    await session.submit_answer(request.value)

    return {"status": "received", "value": request.value}


@app.delete("/api/interview/session", status_code=200)
async def delete_interview_session(features_created: int = 0):
    """
    End the current interview session and notify all connected browsers.

    Clears all session state (active question, pending answer) and broadcasts
    a session_ended event to every SSE subscriber so the browser can close
    the interview UI.

    Optional query parameter:
        features_created (int, default 0): number of features created during
        the session, forwarded to SSE subscribers in the end event payload.

    Idempotent: safe to call even when no session is active.
    """
    session = get_interview_session()
    await session.reset(features_created=features_created)
    return {"message": "Session ended"}


@app.post("/api/interview/revive", status_code=200)
async def revive_interview_session():
    """
    Revive a paused interview session by re-broadcasting the current question.

    Called by the browser when the user clicks the Revive button after a soft
    timeout has fired.  Re-sends the active question to all SSE subscribers so
    the browser can transition back to the active state.

    Returns 404 if no question is currently active (e.g. the hard timeout has
    already fired and cleared session state).
    """
    session = get_interview_session()
    question = await session.revive()

    if question is None:
        raise HTTPException(
            status_code=404,
            detail="No active question to revive. The session may have timed out.",
        )

    return {"status": "revived", "question": question}


@app.get("/api/interview/debug")
async def get_interview_debug():
    """
    Return the session event log for debugging.

    Returns the full structured log for the active session, or the last
    session's log if it ended within the past 60 seconds.

    Returns 404 if no session is active and no recent log is available.
    """
    result = get_debug_log()
    if result is None:
        raise HTTPException(status_code=404, detail="No active or recent interview session.")
    return result


# ---------------------------------------------------------------------------
# Interview process launcher — description-driven dynamic interview
# ---------------------------------------------------------------------------

# Appended to the plan-tasks template to redirect all interaction to the browser.
_INTERVIEW_API_SUFFIX = """
## IMPORTANT: Use the Browser Interview API for All Interaction

You MUST NOT ask questions or await input in the terminal. The user is waiting
in their browser at /interview. All conversation must happen through the
following API.

### API Quick Reference

| Action | Command |
|--------|---------|
| Post question (first) | See "Safe JSON Pattern" below — NEVER use inline `-d '{...}'` |
| Post question (subsequent) | Add `-H "X-Interview-Token: $SESSION_TOKEN"` to every POST |
| Poll for answer | `curl -s --max-time 610 http://localhost:8000/api/interview/answer` |
| End session | `curl -s -X DELETE "http://localhost:8000/api/interview/session?features_created=<N>"` |

Always use `--max-time 610` on the answer poll — the server long-polls up to 600 s total
(soft pause at 5 min, hard kill at 10 min).

### CRITICAL: Always Use Python to Build the JSON Body

**NEVER** construct the curl body with inline `-d '{"text":"..."}'. Question text
may contain backslashes, quotes, or other characters that break shell JSON strings.
Always generate the body with Python:

```bash
# First question — captures SESSION_TOKEN from response
BODY=$(python -c "import json; print(json.dumps({'text': 'Your question here', 'options': ['Option A', 'Option B']}))")
RESPONSE=$(curl -s -X POST http://localhost:8000/api/interview/question \\
  -H "Content-Type: application/json" \\
  -d "$BODY")
SESSION_TOKEN=$(echo "$RESPONSE" | python -c "import sys,json; d=json.load(sys.stdin); print(d.get('session_token',''))")

# Subsequent questions — include the session token header
BODY=$(python -c "import json; print(json.dumps({'text': 'Next question', 'options': ['A', 'B']}))")
RESPONSE=$(curl -s -X POST http://localhost:8000/api/interview/question \\
  -H "Content-Type: application/json" \\
  -H "X-Interview-Token: $SESSION_TOKEN" \\
  -d "$BODY")
```

**Key rules:**
- Always use `python -c "import json; print(json.dumps({...}))"` to build the body
- Use `d.get('session_token', '')` — never use direct key access, which raises KeyError if the key is absent
- `session_token` is only present in the **first** POST response; subsequent responses omit it

### Option Types

- **Multiple choice**: `"options": ["Option A", "Option B"]`
- **Free text**: `"options": ["(type in browser)"]` — renders a text input in the browser

### Conversation Flow

**Phase 1 — Clarify**: Post your first question greeting the user, summarising
your understanding of their request, and asking one focused clarifying question.
Continue asking follow-up questions until you have enough detail.

**Phase 2 — Present Breakdown**: Post a question listing planned features
grouped by category. Options: `["Approve and Create", "Revise"]`.
If "Revise", ask what to change.

**Phase 3 — Create Features**: Call `feature_create_bulk` with ALL features at once.
Then post a final confirmation with options `["Done"]`.

**Phase 4 — End**: Call `DELETE /api/interview/session?features_created=<N>`.
Always call this on completion OR on error.

### Error Handling

| Error | Action |
|-------|--------|
| POST → 409 (answer pending) | Wait 1 s, retry with `$SESSION_TOKEN` |
| GET answer → 408 | Re-post same question, poll again |
| Any unrecoverable error | Call DELETE /api/interview/session, stop |
"""


class InterviewStartRequest(BaseModel):
    description: str


@app.post("/api/interview/start")
async def start_interview(request: InterviewStartRequest):
    """Launch a dynamic interview session driven by a user-supplied description.

    Combines the plan-tasks prompt template (with the user's description) with
    browser interview API instructions, then launches Claude as a hidden background
    process (no terminal window, stdout/stderr captured via pipes). Claude uses the
    interview API to conduct a dynamic conversation in the browser and creates
    features via feature_create_bulk.
    """
    if not request.description.strip():
        raise HTTPException(status_code=400, detail="Description cannot be empty")

    settings = load_settings()
    plan_template = settings.get("plan_tasks_prompt_template", PLAN_TASKS_PROMPT_TEMPLATE)
    prompt = plan_template.format(description=request.description.strip())
    prompt += _INTERVIEW_API_SUFFIX

    working_dir = str(_current_db_path.parent)

    try:
        if sys.platform == "win32":
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, encoding="utf-8"
            ) as f:
                f.write(prompt)
                prompt_file = f.name

            ps_cmd = (
                f'claude --dangerously-skip-permissions --print '
                f'(Get-Content -LiteralPath "{prompt_file}" -Raw)'
            )
            launched = False
            for ps_exe in ["pwsh", "powershell"]:
                try:
                    subprocess.Popen(
                        [ps_exe, "-Command", ps_cmd],
                        cwd=working_dir,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                    launched = True
                    break
                except FileNotFoundError:
                    continue
            if not launched:
                raise HTTPException(
                    status_code=500,
                    detail="No PowerShell found. Install PowerShell 7 (pwsh) or ensure powershell.exe is available.",
                )
        else:
            try:
                subprocess.Popen(
                    ["claude", "--dangerously-skip-permissions", "--print", prompt],
                    cwd=working_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
            except FileNotFoundError:
                raise HTTPException(
                    status_code=500,
                    detail="Claude CLI not found. Make sure 'claude' is in your PATH.",
                )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to launch Claude: {str(e)}")

    return {"launched": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


 


 

