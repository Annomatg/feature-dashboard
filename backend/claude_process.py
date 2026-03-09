"""
Claude process utilities for Feature Dashboard.
=================================================

Pure utility classes and functions for spawning and monitoring Claude
subprocesses, parsing JSONL session logs, and reading stdout/stderr buffers.
No FastAPI coupling except _launch_claude_terminal which raises HTTPException.
"""

import asyncio
import json
import subprocess
import sys
import tempfile
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Log buffer classes
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Stream reader
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Claude projects directory helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# JSONL session file helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# JSONL log parsing
# ---------------------------------------------------------------------------

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
            elif item_type == 'thinking':
                # Handle "thinking" content type from extended thinking models
                thinking_text = item.get('thinking', '').strip()
                if thinking_text:
                    thinking_text = thinking_text.replace('\n', ' ').replace('\r', '')
                    entries.append({
                        'timestamp': timestamp,
                        'entry_type': 'thinking',
                        'tool_name': None,
                        'text': thinking_text[:200],
                    })

    return entries[-limit:] if len(entries) > limit else entries


def _parse_main_agent_metadata(jsonl_file: Path) -> dict:
    """Parse a Claude JSONL session file and extract main agent metadata.

    Returns a dict with:
    - turn_count: number of turns (user + assistant messages)
    - token_estimate: rough token count estimated from character lengths
    - last_tool_used: name of the last tool_use block, or None
    - agent_type: extracted from filename or first system message

    Token estimation uses ~4 characters per token as a rough approximation.
    """
    turn_count = 0
    token_estimate = 0
    last_tool_used = None
    agent_type = None
    char_count = 0

    try:
        file_size = jsonl_file.stat().st_size
    except OSError:
        return {
            "turn_count": 0,
            "token_estimate": 0,
            "last_tool_used": None,
            "agent_type": None,
        }

    # Extract agent type from filename (e.g., "session-abc123--sonnet.jsonl" -> "sonnet")
    filename = jsonl_file.stem
    if '--' in filename:
        parts = filename.split('--')
        if len(parts) >= 2:
            potential_type = parts[-1].lower()
            # Common model identifiers
            if potential_type in ('sonnet', 'opus', 'haiku', 'claude-sonnet', 'claude-opus', 'claude-haiku'):
                agent_type = potential_type

    try:
        with open(jsonl_file, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
    except (IOError, OSError):
        return {
            "turn_count": 0,
            "token_estimate": 0,
            "last_tool_used": None,
            "agent_type": agent_type,
        }

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        obj_type = obj.get('type', '')

        # Count turns (user and assistant messages)
        if obj_type in ('user', 'assistant'):
            turn_count += 1

        # Extract agent type from first system message if not found in filename
        if agent_type is None and obj_type == 'system':
            msg = obj.get('message', {})
            if isinstance(msg, dict):
                # Look for model info in system message
                model = msg.get('model', '')
                if model:
                    if 'sonnet' in model.lower():
                        agent_type = 'sonnet'
                    elif 'opus' in model.lower():
                        agent_type = 'opus'
                    elif 'haiku' in model.lower():
                        agent_type = 'haiku'
                    else:
                        agent_type = model

        # Count characters for token estimation
        msg = obj.get('message', {})
        if isinstance(msg, dict):
            content = msg.get('content', '')
            if isinstance(content, str):
                char_count += len(content)
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        # Count text content
                        text = item.get('text', '') or item.get('thinking', '') or ''
                        char_count += len(text)
                        # Count tool inputs (JSON serialized)
                        tool_input = item.get('input', {})
                        if tool_input:
                            char_count += len(json.dumps(tool_input))
                    elif isinstance(item, str):
                        char_count += len(item)

        # Track last tool used from assistant messages
        if obj_type == 'assistant':
            msg = obj.get('message', {})
            if isinstance(msg, dict):
                content = msg.get('content', [])
                if isinstance(content, list):
                    # Iterate in reverse to find the last tool_use
                    for item in reversed(content):
                        if isinstance(item, dict) and item.get('type') == 'tool_use':
                            last_tool_used = item.get('name', None)
                            break

    # Estimate tokens (~4 characters per token is a rough approximation)
    token_estimate = char_count // 4 if char_count > 0 else 0

    return {
        "turn_count": turn_count,
        "token_estimate": token_estimate,
        "last_tool_used": last_tool_used,
        "agent_type": agent_type,
    }


# ---------------------------------------------------------------------------
# Agent graph parsing
# ---------------------------------------------------------------------------

def _parse_agent_graph(jsonl_file: Path) -> dict:
    """Parse a Claude JSONL session file and extract an agent graph.

    Returns a dict with:
    - nodes: list of {id, label, type} - main agent + all subagents
    - edges: list of {source, target} - parent-child relationships

    The main agent is always node "main". Each Agent tool call creates a
    subagent node with a unique ID and an edge from the caller to the subagent.
    """
    nodes: list[dict] = [{"id": "main", "label": "Main Agent", "type": "main"}]
    edges: list[dict] = []
    agent_counter = 0
    # Track which agent we're currently in (stack for nested agents)
    agent_stack: list[str] = ["main"]

    try:
        file_size = jsonl_file.stat().st_size
    except OSError:
        return {"nodes": nodes, "edges": edges}

    try:
        with open(jsonl_file, 'r', encoding='utf-8', errors='replace') as f:
            if file_size > 500_000:
                f.seek(max(0, file_size - 100_000))
                f.readline()  # Skip partial first line
            lines = f.readlines()
    except (IOError, OSError):
        return {"nodes": nodes, "edges": edges}

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

        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get('type') != 'tool_use':
                continue

            tool_name = item.get('name', '')
            tool_input = item.get('input', {}) or {}

            # Handle Agent tool calls (subagent spawning)
            if tool_name == 'Agent':
                agent_counter += 1
                subagent_type = tool_input.get('subagent_type', 'general-purpose')
                description = tool_input.get('description', 'Subagent')

                # Create a unique ID for this agent
                agent_id = f"agent_{agent_counter}"

                # Create node for the subagent
                nodes.append({
                    "id": agent_id,
                    "label": description[:50] if description else f"Agent {agent_counter}",
                    "type": subagent_type,
                })

                # Create edge from current agent to this subagent
                current_agent = agent_stack[-1] if agent_stack else "main"
                edges.append({
                    "source": current_agent,
                    "target": agent_id,
                })

                # Push this agent onto the stack (it may spawn more agents)
                agent_stack.append(agent_id)

    return {"nodes": nodes, "edges": edges}


# ---------------------------------------------------------------------------
# Terminal launcher
# ---------------------------------------------------------------------------

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
    model_flag = f"--model '{model}' " if model else ""

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
