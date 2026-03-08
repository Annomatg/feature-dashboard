"""
Autopilot HTTP endpoints router.

Handles enable/disable, status polling, log management, and session-log streaming
for the auto-pilot feature. Process-kill helpers live in autopilot_engine.py.
"""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import backend.deps as _deps
from backend.deps import get_session, load_settings
from backend.autopilot_engine import (
    get_autopilot_state,
    _append_log,
    _disable_autopilot_state,
    get_next_autopilot_feature,
    _spawn_and_monitor,
    _write_autopilot_to_config,
    _get_child_procs,
    _any_proc_running,
    _wait_for_stopping_process,
)
from backend.claude_process import (
    _find_session_jsonl,
    _get_claude_projects_dir,
    _parse_jsonl_log,
)
from backend.schemas import (
    AutoPilotStatusResponse,
    SessionLogEntry,
    SessionLogResponse,
)

router = APIRouter(prefix="/api", tags=["autopilot"])


@router.get("/autopilot/session-log", response_model=SessionLogResponse)
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

    # Determine which feature is being processed (for frontend filtering)
    feature_id = None
    if state.manual_active:
        feature_id = state.manual_feature_id
    elif state.enabled or state.stopping:
        feature_id = state.current_feature_id

    if not active or state.session_start_time is None:
        return SessionLogResponse(
            active=active,
            feature_id=feature_id,
            session_file=None,
            entries=[],
            total_entries=0,
        )

    working_dir = str(_deps._current_db_path.parent)
    projects_dir = _get_claude_projects_dir(working_dir)

    if projects_dir is None:
        return SessionLogResponse(
            active=active,
            feature_id=feature_id,
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
            feature_id=feature_id,
            session_file=None,
            entries=[],
            total_entries=0,
        )

    clamped_limit = max(1, min(limit, 200))
    entries = _parse_jsonl_log(session_file, limit=clamped_limit)

    return SessionLogResponse(
        active=active,
        feature_id=feature_id,
        session_file=session_file.name,
        entries=[SessionLogEntry(**e) for e in entries],
        total_entries=len(entries),
    )


@router.post("/autopilot/enable", response_model=AutoPilotStatusResponse)
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
        # Attempt to kill the old orphaned process so it does not interfere with
        # the new Claude run (especially on Windows where the child may outlive
        # the PowerShell wrapper).
        if state.active_process is not None:
            try:
                state.active_process.terminate()
            except Exception:
                pass
        _disable_autopilot_state(state)
        state.stopping = False

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
        _append_log(state, 'info', f"Auto-pilot enabled for database: {_deps._current_db_path.name}")
        _append_log(state, 'info', f"Starting feature #{feature.id}: {feature.name}")

        settings = load_settings()
        feature_model = feature.model or "sonnet"

        await _spawn_and_monitor(feature, state, _deps._current_db_path, settings, raise_on_error=True)
        _append_log(state, 'info', f"Claude launched for feature #{feature.id} with model {feature_model}")
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


@router.post("/autopilot/disable", response_model=AutoPilotStatusResponse)
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


@router.post("/autopilot/log/clear")
async def clear_autopilot_log():
    """
    Clear all auto-pilot log entries for the active database.

    Empties the in-memory log deque without affecting the enabled/running state.
    Always returns 200 — idempotent even if the log is already empty.
    """
    state = get_autopilot_state()
    state.log.clear()
    return {"cleared": True}


@router.post("/autopilot/clear-error")
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


@router.get("/autopilot/status", response_model=AutoPilotStatusResponse)
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
