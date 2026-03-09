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
