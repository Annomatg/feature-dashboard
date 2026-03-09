"""
Claude launch endpoints router.

Handles launching Claude Code sessions for individual features (manual launch)
and the plan-tasks planning flow. Process management helpers live in
claude_process.py and autopilot_engine.py.
"""

import asyncio
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import backend.deps as _deps
from backend.deps import (
    DEFAULT_PROMPT_TEMPLATE,
    PLAN_TASKS_PROMPT_TEMPLATE,
    PLANNING_MODEL,
    get_session,
    load_settings,
)
from backend.autopilot_engine import (
    get_autopilot_state,
    _append_log,
    monitor_manual_process,
)
from backend.claude_process import _launch_claude_terminal
from backend.schemas import (
    LaunchClaudeRequest,
    LaunchClaudeResponse,
    PlanTasksRequest,
    PlanTasksResponse,
)
from api.database import Feature

router = APIRouter(prefix="/api", tags=["claude"])


@router.post("/features/{feature_id}/launch-claude", response_model=LaunchClaudeResponse)
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


@router.post("/plan-tasks", response_model=PlanTasksResponse)
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
