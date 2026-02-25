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
from collections import deque
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

from api.database import Comment, Feature, create_database

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


# Auto-pilot in-memory state, keyed by database path string
class _AutoPilotState:
    """Tracks auto-pilot mode for a single database."""
    def __init__(self):
        self.enabled: bool = False
        self.current_feature_id: Optional[int] = None
        self.current_feature_name: Optional[str] = None
        self.current_feature_model: Optional[str] = None
        self.last_error: Optional[str] = None
        self.log: deque = deque(maxlen=100)  # LogEntry items, circular buffer
        self.active_process = None  # subprocess.Popen handle, if any
        self.monitor_task = None  # asyncio.Task handle, if monitoring
        self.consecutive_skip_count: int = 0  # incremented when same feature is returned consecutively
        self.last_skipped_feature_id: Optional[int] = None  # last feature id given to the sequencer


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
    """Spawn a background Claude process for auto-pilot mode and return the Popen handle.

    Differences from the interactive launch-claude endpoint:
    - No CREATE_NEW_CONSOLE — runs silently in the background.
    - Always uses --print (non-interactive, exits when done).
    - Raises RuntimeError when no PowerShell executable is found (Windows).
    - Raises FileNotFoundError when the Claude CLI is not in PATH (Linux/Mac).

    Args:
        feature:     Feature ORM object (must have id, category, name, description, steps, model).
        settings:    Settings dict containing 'claude_prompt_template'.
        working_dir: Working directory string for the spawned process.

    Returns:
        subprocess.Popen handle for the spawned process.
    """
    template = settings.get("claude_prompt_template", DEFAULT_PROMPT_TEMPLATE)
    steps_text = "\n".join(f"{i + 1}. {step}" for i, step in enumerate(feature.steps))
    prompt = template.format(
        feature_id=feature.id,
        category=feature.category,
        name=feature.name,
        description=feature.description,
        steps=steps_text,
    )

    feature_model = feature.model or "sonnet"

    if sys.platform == "win32":
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write(prompt)
            prompt_file = f.name

        ps_cmd = (
            f'claude --model {feature_model} --dangerously-skip-permissions '
            f'--print (Get-Content -LiteralPath "{prompt_file}" -Raw)'
        )
        for ps_exe in ["pwsh", "powershell"]:
            try:
                return subprocess.Popen(
                    [ps_exe, "-Command", ps_cmd],
                    cwd=working_dir,
                    # No CREATE_NEW_CONSOLE — background execution
                )
            except FileNotFoundError:
                continue

        raise RuntimeError(
            "No PowerShell found. Install PowerShell 7 (pwsh) or ensure powershell.exe is available."
        )
    else:
        try:
            return subprocess.Popen(
                ["claude", "--model", feature_model, "--dangerously-skip-permissions", "--print", prompt],
                cwd=working_dir,
            )
        except FileNotFoundError:
            raise FileNotFoundError("Claude CLI not found. Make sure claude is in your PATH.")


async def handle_autopilot_success(
    feature_id: int, state: "_AutoPilotState", db_path: Path
) -> None:
    """Handle successful feature completion (feature.passes=True after process exits).

    Logs the success, then picks the next pending feature and spawns Claude for it.
    If no further work remains, disables auto-pilot and logs completion.
    """
    feature_name = state.current_feature_name or "unknown"
    _append_log(state, 'success', f"Feature #{feature_id} completed: {feature_name}")

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
    settings = load_settings()
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


async def handle_autopilot_failure(
    feature_id: int, exit_code: int, state: "_AutoPilotState"
) -> None:
    """Handle failed feature (process exited but feature.passes=False).

    Sets last_error, logs the failure, and disables auto-pilot.
    The feature's DB state is left unchanged (not reverted).
    """
    msg = (
        f"Feature #{feature_id} failed: process exited with code {exit_code}"
        " and was not marked as passing"
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
    """
    try:
        loop = asyncio.get_event_loop()
        exit_code = await loop.run_in_executor(None, process.wait)

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
            await handle_autopilot_failure(feature_id, exit_code, state)
    except asyncio.CancelledError:
        # Auto-pilot was disabled externally — exit cleanly without propagating
        pass


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


def feature_to_response(feature, comment_counts: dict[int, int]) -> "FeatureResponse":
    """Convert a Feature ORM object to FeatureResponse including comment_count."""
    d = feature.to_dict()
    d["comment_count"] = comment_counts.get(feature.id, 0)
    return FeatureResponse(**d)


def load_settings() -> dict:
    """Load settings from settings.json, returning defaults if not found."""
    if not SETTINGS_FILE.exists():
        return {"claude_prompt_template": DEFAULT_PROMPT_TEMPLATE}
    try:
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if "claude_prompt_template" not in data:
            data["claude_prompt_template"] = DEFAULT_PROMPT_TEMPLATE
        return data
    except Exception:
        return {"claude_prompt_template": DEFAULT_PROMPT_TEMPLATE}


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


class UpdateSettingsRequest(BaseModel):
    """Request to update application settings."""
    claude_prompt_template: str


class CommentResponse(BaseModel):
    """Comment data response."""
    id: int
    feature_id: int
    content: str
    created_at: Optional[str] = None


class CreateCommentRequest(BaseModel):
    """Request to add a comment to a feature."""
    content: str


class AutoPilotStatusResponse(BaseModel):
    """Response for auto-pilot enable/status."""
    enabled: bool
    current_feature_id: Optional[int] = None
    current_feature_name: Optional[str] = None
    current_feature_model: Optional[str] = None
    last_error: Optional[str] = None
    log: list[LogEntry] = []


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
            counts = get_comment_counts(session, [f.id for f in features])

            return PaginatedFeaturesResponse(
                features=[feature_to_response(f, counts) for f in features],
                total=total,
                limit=actual_limit,
                offset=actual_offset
            )

        # Otherwise return simple list (backward compatible)
        features = query.all()
        counts = get_comment_counts(session, [f.id for f in features])
        return [feature_to_response(f, counts) for f in features]
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
        return feature_to_response(feature, counts)
    finally:
        session.close()


@app.post("/api/features", response_model=FeatureResponse, status_code=201)
async def create_feature(request: CreateFeatureRequest):
    """
    Create a new feature.

    Automatically assigns priority as max(existing_priorities) + 1.
    Sets passes=False and in_progress=False by default.
    """
    session = get_session()
    try:
        # Append after the current highest priority using the standard step size
        max_priority = session.query(Feature.priority).order_by(Feature.priority.desc()).first()
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

        return feature_to_response(feature, get_comment_counts(session, [feature.id]))
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

        return feature_to_response(feature, get_comment_counts(session, [feature.id]))
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

        return feature_to_response(feature, get_comment_counts(session, [feature.id]))
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

        return feature_to_response(feature, get_comment_counts(session, [feature.id]))
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

        return feature_to_response(feature, get_comment_counts(session, [feature.id]))
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
    return SettingsResponse(**settings)


@app.put("/api/settings", response_model=SettingsResponse)
async def update_settings(request: UpdateSettingsRequest):
    """Update application settings."""
    try:
        settings = {"claude_prompt_template": request.claude_prompt_template}
        save_settings(settings)
        return SettingsResponse(**settings)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save settings: {str(e)}")


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

        try:
            if sys.platform == "win32":
                # Write prompt to a temp file to avoid shell quoting issues
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".txt", delete=False, encoding="utf-8"
                ) as f:
                    f.write(prompt)
                    prompt_file = f.name

                # PowerShell reads the file and passes its content as the first message
                # --dangerously-skip-permissions enables full access mode (no permission prompts)
                # --print runs Claude non-interactively so the session closes automatically when done
                print_flag = "--print " if request.hidden_execution else ""
                ps_cmd = f'claude --model {feature_model} --dangerously-skip-permissions {print_flag}(Get-Content -LiteralPath "{prompt_file}" -Raw)'
                # Try pwsh (PowerShell 7) first, fall back to powershell (Windows PS 5)
                ps_executables = ["pwsh", "powershell"]
                launched = False
                for ps_exe in ps_executables:
                    try:
                        subprocess.Popen(
                            [ps_exe, "-Command", ps_cmd],
                            creationflags=subprocess.CREATE_NEW_CONSOLE,
                            cwd=working_dir,
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
                # --print runs Claude non-interactively so the session closes automatically when done
                cmd = ["claude", "--model", feature_model, "--dangerously-skip-permissions"]
                if request.hidden_execution:
                    cmd.append("--print")
                cmd.append(prompt)
                subprocess.Popen(cmd, cwd=working_dir)
        except FileNotFoundError:
            raise HTTPException(
                status_code=500,
                detail="Claude CLI not found. Make sure 'claude' is in your PATH.",
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to launch Claude: {str(e)}")

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

    prompt = PLAN_TASKS_PROMPT_TEMPLATE.format(description=request.description.strip())
    working_dir = str(_current_db_path.parent)

    try:
        if sys.platform == "win32":
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, encoding="utf-8"
            ) as f:
                f.write(prompt)
                prompt_file = f.name

            # Interactive mode: no --print flag so the terminal stays open
            ps_cmd = f'claude --dangerously-skip-permissions (Get-Content -LiteralPath "{prompt_file}" -Raw)'
            ps_executables = ["pwsh", "powershell"]
            launched = False
            for ps_exe in ps_executables:
                try:
                    subprocess.Popen(
                        [ps_exe, "-Command", ps_cmd],
                        creationflags=subprocess.CREATE_NEW_CONSOLE,
                        cwd=working_dir,
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
            # Interactive mode: no --print flag
            subprocess.Popen(
                ["claude", "--dangerously-skip-permissions", prompt],
                cwd=working_dir,
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

    session = get_session()
    try:
        feature = get_next_autopilot_feature(session)

        if feature is None:
            _append_log(state, 'info', 'No tasks available')
            return AutoPilotStatusResponse(
                enabled=False,
                current_feature_id=None,
                current_feature_name=None,
                last_error=None,
                log=list(state.log),
            )

        state.enabled = True
        state.current_feature_id = feature.id
        state.current_feature_name = feature.name
        state.current_feature_model = feature.model or "sonnet"
        state.last_error = None
        state.last_skipped_feature_id = feature.id
        state.consecutive_skip_count = 0
        state.log.clear()
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

    if state.monitor_task is not None:
        state.monitor_task.cancel()
        state.monitor_task = None

    if state.active_process is not None:
        try:
            state.active_process.terminate()
        except Exception:
            pass  # Process may have already exited
        state.active_process = None

    state.enabled = False
    state.current_feature_id = None
    state.current_feature_name = None
    state.current_feature_model = None
    state.last_error = None
    _append_log(state, 'info', "Auto-pilot manually disabled")
    _write_autopilot_to_config(False)

    return AutoPilotStatusResponse(
        enabled=False,
        current_feature_id=None,
        current_feature_name=None,
        current_feature_model=None,
        last_error=None,
        log=list(state.log),
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
    return AutoPilotStatusResponse(
        enabled=state.enabled,
        current_feature_id=state.current_feature_id,
        current_feature_name=state.current_feature_name,
        current_feature_model=state.current_feature_model,
        last_error=state.last_error,
        log=list(state.log),
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

from backend.interview_state import get_interview_session  # noqa: E402


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
                elif event["type"] == "session_timeout":
                    yield "event: session-timeout\ndata: {}\n\n"
                    break
                elif event["type"] == "session_ended":
                    features_created = event.get("features_created", 0)
                    yield f"event: end\ndata: {json.dumps({'features_created': features_created})}\n\n"
                    break
        finally:
            session.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# Timeout for GET /api/interview/answer long-poll (seconds).
# Override in tests to avoid multi-minute waits.
_ANSWER_POLL_TIMEOUT_SECONDS: float = 300.0


@app.get("/api/interview/answer")
async def get_interview_answer():
    """
    Long-polling endpoint that blocks until the user submits an answer.

    Called by Claude Code immediately after posting a question. Waits up to
    _ANSWER_POLL_TIMEOUT_SECONDS for the browser to submit an answer via
    POST /api/interview/answer, then returns the value and clears it from
    session state (consume-once semantics).

    Returns 408 Request Timeout if no answer arrives within the timeout period.
    """
    session = get_interview_session()
    answer = await session.wait_for_answer(timeout=_ANSWER_POLL_TIMEOUT_SECONDS)

    if answer is None:
        # Broadcast session-timeout to SSE subscribers and clear state
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


 


 

