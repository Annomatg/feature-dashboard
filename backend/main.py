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
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.database import Feature
import backend.deps as _deps
from backend.deps import (
    CONFIG_FILE,  # re-exported for tests that patch via main_module.CONFIG_FILE
    DEFAULT_PROMPT_TEMPLATE, PLAN_TASKS_PROMPT_TEMPLATE, PLANNING_MODEL,
    get_session,
    load_settings,
    _autopilot_states,
    _feature_subscribers,  # re-exported so tests can clear via main_module._feature_subscribers
)
from backend.claude_process import (
    ClaudeProcessLog,  # re-exported for tests that import from backend.main
    _launch_claude_terminal,
)
from backend.autopilot_engine import (
    _AutoPilotState,  # re-exported for tests that import from backend.main
    _claude_process_logs,  # re-exported for tests that patch via main_module._claude_process_logs
    CLAUDE_RATE_LIMIT_PATTERNS,  # re-exported for tests
    CLAUDE_SESSION_LIMIT_EXIT_CODES,  # re-exported for tests
    get_autopilot_state,
    _append_log,
    monitor_manual_process,
    _disable_autopilot_state,  # re-exported for tests
    handle_all_complete,  # re-exported for tests
    get_next_autopilot_feature,  # re-exported for tests
    spawn_claude_for_autopilot,  # re-exported for tests
    _spawn_and_monitor,  # re-exported for tests
    handle_budget_exhausted,  # re-exported for tests
    handle_autopilot_success,  # re-exported for tests
    _extract_output_snippet,  # re-exported for tests
    handle_autopilot_failure,  # re-exported for tests
    monitor_claude_process,  # re-exported for tests
    _reset_autopilot_in_config,
    _read_autopilot_from_config,  # re-exported for tests
    _write_autopilot_to_config,  # re-exported for tests
    _get_child_procs,  # re-exported for tests
    _any_proc_running,  # re-exported for tests
    _wait_for_process_and_children,  # re-exported for tests
    _wait_for_stopping_process,  # re-exported for tests
)
from backend.schemas import (  # noqa: E402
    LaunchClaudeRequest,
    LaunchClaudeResponse,
    PlanTasksRequest,
    PlanTasksResponse,
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
from backend.routers import autopilot as autopilot_router  # noqa: E402
app.include_router(autopilot_router.router)
from backend.routers import push as push_router  # noqa: E402
app.include_router(push_router.router)
from backend.routers import tasks as tasks_router  # noqa: E402
app.include_router(tasks_router.router)
from backend.routers import git as git_router  # noqa: E402
app.include_router(git_router.router)
from backend.routers import feature_commits as feature_commits_router  # noqa: E402
app.include_router(feature_commits_router.router)


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
            "update_settings": "PUT /api/settings",
            "task_graph": "GET /api/tasks/{id}/graph",
            "git_update": "POST /api/git/update",
        }
    }


# CORS middleware for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173",
        "https://localhost:5173", "https://127.0.0.1:5173",
        "http://localhost:5174", "http://127.0.0.1:5174",
        "https://localhost:5174", "https://127.0.0.1:5174",
    ],
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
                    ps_cmd = f"claude --model '{feature_model}' --dangerously-skip-permissions --print (Get-Content -LiteralPath \"{prompt_file}\" -Raw)"
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
    planning_model = settings.get("planning_model", PLANNING_MODEL)

    try:
        _launch_claude_terminal(prompt, working_dir, model=planning_model)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to launch Claude: {str(e)}")

    return PlanTasksResponse(
        launched=True,
        prompt=prompt,
        working_directory=working_dir,
        model=planning_model,
    )


# Interview endpoints are registered via backend/routers/interview.py above.
# Autopilot endpoints are registered via backend/routers/autopilot.py above.


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
