"""
Autopilot engine for Feature Dashboard.
==========================================

Manages the auto-pilot state machine and process monitoring logic.
Extracted from main.py so that the route handlers in main.py remain thin.

Public API
----------
State class / container:
- _AutoPilotState          dataclass tracking per-DB autopilot state
- _claude_process_logs     per-feature stdout/stderr capture buffers

State accessors:
- get_autopilot_state()    get/create state for the active DB
- _append_log(state, ...)  append a structured log entry

Process lifecycle:
- monitor_manual_process(state)                         monitor a manually launched process
- monitor_claude_process(feature_id, proc, db, state)   monitor an autopilot process
- spawn_claude_for_autopilot(feature, settings, dir)    spawn a Claude process

Autopilot flow handlers:
- get_next_autopilot_feature(session)                   pick the next feature to work on
- handle_all_complete(state)                            stop when no features remain
- handle_budget_exhausted(state)                        stop when budget limit reached
- handle_autopilot_success(feature_id, state, db_path)  handle successful feature completion
- handle_autopilot_failure(feature_id, exit_code, state, output_text)  handle failure

Process-tree helpers (for disable):
- _get_child_procs(proc)                               collect child psutil processes
- _any_proc_running(procs)                             check if any procs still alive
- _wait_for_stopping_process(proc, state, children)    wait for process exit async

Config persistence:
- _reset_autopilot_in_config()                         clear autopilot flag on restart
- _read_autopilot_from_config()                        read persisted autopilot toggle
- _write_autopilot_to_config(enabled)                  persist autopilot toggle
"""

import asyncio
import json
import subprocess
import sys
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import create_engine as _create_engine
from sqlalchemy.orm import sessionmaker as _sessionmaker

# Add parent directory to path for api/ package imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.database import Feature
import backend.deps as _deps
from backend.deps import PROJECT_DIR, CONFIG_FILE, _autopilot_states, load_settings
from backend.claude_process import ClaudeProcessLog, _read_stream_to_buffer
from backend.schemas import LogEntry
from backend.providers import get_provider


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Per-feature stdout/stderr capture buffers
# ---------------------------------------------------------------------------

# Per-feature stdout/stderr capture buffers, keyed by feature_id.
# Created when a Claude process starts, removed when monitoring ends.
_claude_process_logs: dict[int, ClaudeProcessLog] = {}


# ---------------------------------------------------------------------------
# AutoPilot state
# ---------------------------------------------------------------------------

class _AutoPilotState:
    """Tracks auto-pilot mode for a single database."""
    def __init__(self):
        self.enabled: bool = False
        self.stopping: bool = False  # True when disabled but Claude process still running
        self.current_feature_id: Optional[int] = None
        self.current_feature_name: Optional[str] = None
        self.current_feature_model: Optional[str] = None
        self.last_error: Optional[str] = None
        self.log: deque = deque()  # LogEntry items, unbounded (user wants to keep all entries)
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


def get_autopilot_state() -> _AutoPilotState:
    """Get or create the autopilot state for the currently active database.

    When creating a new state entry, initialises the ``enabled`` flag from the
    persisted value in dashboards.json so that the UI toggle is restored
    correctly after a frontend reload (without a backend restart).
    """
    db_key = str(_deps._current_db_path)
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


# ---------------------------------------------------------------------------
# Internal state helpers
# ---------------------------------------------------------------------------

def _disable_autopilot_state(state: _AutoPilotState) -> None:
    """Reset the 6 shared fields that mark an active auto-pilot run as inactive.

    Sets enabled=False and clears current_feature_id, current_feature_name,
    current_feature_model, active_process, and monitor_task.  Callers that
    need additional teardown (last_error, budget_exhausted, …) do so after
    calling this helper.
    """
    state.enabled = False
    state.current_feature_id = None
    state.current_feature_name = None
    state.current_feature_model = None
    state.active_process = None
    state.monitor_task = None


# ---------------------------------------------------------------------------
# Autopilot flow handlers
# ---------------------------------------------------------------------------

def handle_all_complete(state: _AutoPilotState) -> None:
    """Cleanly stop auto-pilot when no features remain.

    Sets enabled=False, clears current_feature_id, current_feature_name,
    last_error, active_process, and monitor_task, then appends an info log
    entry indicating all tasks are done.
    """
    _disable_autopilot_state(state)
    state.last_error = None
    _append_log(state, 'info', "All tasks complete \u2014 auto-pilot disabled")


def get_next_autopilot_feature(session) -> Optional[Feature]:
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


def handle_budget_exhausted(state: _AutoPilotState) -> None:
    """Stop auto-pilot because the session budget limit has been reached."""
    limit = state.features_completed
    msg = f"Session budget reached: {limit} feature{'s' if limit != 1 else ''} completed"
    _append_log(state, 'info', msg)
    _disable_autopilot_state(state)
    state.budget_exhausted = True


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
    feature_id: int, exit_code: int, state: _AutoPilotState, output_text: str = ""
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

    _disable_autopilot_state(state)


async def handle_autopilot_success(
    feature_id: int, state: _AutoPilotState, db_path: Path
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
            _disable_autopilot_state(state)
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
    _append_log(state, 'info', f"Starting feature #{next_feature.id}: {next_feature.name}")
    await _spawn_and_monitor(next_feature, state, db_path, settings)


async def _spawn_and_monitor(
    feature,
    state: _AutoPilotState,
    db_path: Path,
    settings: dict,
    raise_on_error: bool = False,
) -> bool:
    """Spawn a Claude process for *feature*, store it in *state*, and start the monitor task.

    This helper owns the full spawn → store → error-reset → create-monitor-task sequence
    that was previously duplicated between enable_autopilot() and handle_autopilot_success().

    Args:
        feature:       Feature ORM object with id, name, category, model attributes.
        state:         Shared _AutoPilotState instance to update.
        db_path:       Path to the active SQLite database (parent dir used as working_dir).
        settings:      Settings dict passed to spawn_claude_for_autopilot.
        raise_on_error: When True (HTTP context), raises HTTPException(500) on spawn failure
                        so the caller receives a proper error response.

    Returns:
        True when the process was spawned and the monitor task was created.
        False when spawning failed and raise_on_error is False.
    """
    working_dir = str(db_path.parent)
    try:
        proc = spawn_claude_for_autopilot(feature, settings, working_dir)
        state.active_process = proc
        state.monitor_task = asyncio.create_task(
            monitor_claude_process(feature.id, proc, db_path, state)
        )
        return True
    except (FileNotFoundError, RuntimeError) as e:
        _disable_autopilot_state(state)
        err = str(e)
        state.last_error = err
        _append_log(state, 'error', f"Failed to spawn Claude: {err}")
        if raise_on_error:
            raise HTTPException(status_code=500, detail=err)
        return False
    except Exception as e:
        _disable_autopilot_state(state)
        err = f"Failed to launch Claude: {str(e)}"
        state.last_error = err
        _append_log(state, 'error', err)
        if raise_on_error:
            raise HTTPException(status_code=500, detail=err)
        return False


async def monitor_manual_process(state: _AutoPilotState) -> None:
    """Wait for a manually launched Claude process to finish and update the log.

    Runs in the background as an asyncio task. When the process exits it appends a
    success or info log entry and clears all ``manual_*`` state fields.

    If the process has stdout/stderr pipes (hidden-execution mode) the output is
    captured into ``_claude_process_logs`` keyed by feature_id.

    When ``process`` is None (interactive terminal launch), there is no handle to
    wait on.  The function returns immediately so that ``manual_active`` stays True
    and the JSONL session-log remains readable while Claude works in the terminal.
    """
    process = state.manual_process
    feature_id = state.manual_feature_id
    feature_name = state.manual_feature_name

    # Interactive mode: Claude opened in a terminal; no process handle to wait on.
    # Leave manual_active=True so the session log stays readable.
    if process is None:
        return

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


async def monitor_claude_process(
    feature_id: int,
    process: "subprocess.Popen",
    db_path: Path,
    state: _AutoPilotState,
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
            _disable_autopilot_state(state)
            return

        # Open a fresh DB session — the process may have updated the DB while running
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


# ---------------------------------------------------------------------------
# Process-tree helpers (used by disable_autopilot)
# ---------------------------------------------------------------------------

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
    state: _AutoPilotState,
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


# ---------------------------------------------------------------------------
# Config persistence helpers
# ---------------------------------------------------------------------------

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
    whose path matches ``_deps._current_db_path``.  Returns False if the config file
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
                    if entry_path.resolve() == _deps._current_db_path.resolve():
                        return bool(entry.get('autopilot', False))
    except Exception:
        pass
    return False


def _write_autopilot_to_config(enabled: bool) -> None:
    """Persist the autopilot toggle state for the currently active database.

    Finds the dashboards.json entry whose path matches ``_deps._current_db_path`` and
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
                    if entry_path.resolve() == _deps._current_db_path.resolve():
                        entry['autopilot'] = enabled
                        break
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
    except Exception:
        pass  # Never fail an API call due to config file issues
