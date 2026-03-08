"""
Feature Dashboard Backend API
==============================

FastAPI server exposing feature data from SQLite database.
"""

# Load environment variables from .env file FIRST (before other imports)
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).parent.parent / ".env")

import asyncio
import subprocess
import sys
import tempfile
import urllib.request
import urllib.error
from datetime import datetime, timezone

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.database import Feature
import backend.deps as _deps
from backend.deps import (
    CONFIG_FILE,  # re-exported for tests that patch via main_module.CONFIG_FILE
    DEFAULT_PROMPT_TEMPLATE, PLAN_TASKS_PROMPT_TEMPLATE,
    get_session,
    load_settings,
    _autopilot_states,
    _feature_subscribers,  # re-exported so tests can clear via main_module._feature_subscribers
)
from backend.claude_process import (
    ClaudeProcessLog,  # re-exported for tests that import from backend.main
    _find_session_jsonl,
    _get_claude_projects_dir,
    _launch_claude_terminal,
    _parse_jsonl_log,
)
from backend.autopilot_engine import (
    _AutoPilotState,  # re-exported for tests that import from backend.main
    _claude_process_logs,  # re-exported for tests that patch via main_module._claude_process_logs
    CLAUDE_RATE_LIMIT_PATTERNS,  # re-exported for tests
    CLAUDE_SESSION_LIMIT_EXIT_CODES,  # re-exported for tests
    get_autopilot_state,
    _append_log,
    monitor_manual_process,
    _disable_autopilot_state,
    handle_all_complete,  # re-exported for tests
    get_next_autopilot_feature,
    spawn_claude_for_autopilot,  # re-exported for tests
    _spawn_and_monitor,
    handle_budget_exhausted,  # re-exported for tests
    handle_autopilot_success,  # re-exported for tests
    _extract_output_snippet,  # re-exported for tests
    handle_autopilot_failure,  # re-exported for tests
    monitor_claude_process,  # re-exported for tests
    _reset_autopilot_in_config,
    _read_autopilot_from_config,  # re-exported for tests
    _write_autopilot_to_config,
    _get_child_procs,
    _any_proc_running,
    _wait_for_process_and_children,  # re-exported for tests
    _wait_for_stopping_process,
)
from backend.schemas import (  # noqa: E402
    AutoPilotStatusResponse,
    LaunchClaudeRequest,
    LaunchClaudeResponse,
    PlanTasksRequest,
    PlanTasksResponse,
    SessionLogEntry,
    SessionLogResponse,
)

# Initialize FastAPI app
app = FastAPI(
    title="Feature Dashboard API",
    description="API for managing project features and backlog",
    version="1.0.0"
)

from backend.routers import comments as comments_router  # noqa: E402
app.include_router(comments_router.router)
from backend.routers import databases as databases_router  # noqa: E402
app.include_router(databases_router.router)
from backend.routers import settings as settings_router  # noqa: E402
app.include_router(settings_router.router)
from backend.routers import interview as interview_router  # noqa: E402
app.include_router(interview_router.router)
from backend.routers import features as features_router  # noqa: E402
app.include_router(features_router.router)


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


# CORS middleware for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174", "http://127.0.0.1:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_migrate_all():
    """Run schema migrations on all configured databases at startup."""
    from api.migration import migrate_all_dashboards
    migrate_all_dashboards()


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
        working_dir = str(_deps._current_db_path.parent)

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
    working_dir = str(_deps._current_db_path.parent)

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


# Interview endpoints are registered via backend/routers/interview.py above.


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


 


 

