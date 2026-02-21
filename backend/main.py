"""
Feature Dashboard Backend API
==============================

FastAPI server exposing feature data from SQLite database.
"""

import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.database import Feature, create_database

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


@app.on_event("startup")
async def startup_migrate_all():
    """Run schema migrations on all configured databases at startup."""
    from api.migration import migrate_all_dashboards
    migrate_all_dashboards()


def get_session():
    """Get a database session."""
    return _session_maker()


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


class LaunchClaudeResponse(BaseModel):
    """Response for launching a Claude Code session."""
    launched: bool
    feature_id: int
    prompt: str
    working_directory: str
    model: str


class SettingsResponse(BaseModel):
    """Application settings response."""
    claude_prompt_template: str


class UpdateSettingsRequest(BaseModel):
    """Request to update application settings."""
    claude_prompt_template: str


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

            return PaginatedFeaturesResponse(
                features=[FeatureResponse(**f.to_dict()) for f in features],
                total=total,
                limit=actual_limit,
                offset=actual_offset
            )

        # Otherwise return simple list (backward compatible)
        features = query.all()
        return [FeatureResponse(**f.to_dict()) for f in features]
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

        return FeatureResponse(**feature.to_dict())
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
        # Get the maximum priority and add 1
        max_priority = session.query(Feature.priority).order_by(Feature.priority.desc()).first()
        next_priority = (max_priority[0] + 1) if max_priority else 1

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

        return FeatureResponse(**new_feature.to_dict())
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

        return FeatureResponse(**feature.to_dict())
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

        return FeatureResponse(**feature.to_dict())
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

        return FeatureResponse(**feature.to_dict())
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update feature priority: {str(e)}")
    finally:
        session.close()


@app.patch("/api/features/{feature_id}/move", response_model=FeatureResponse)
async def move_feature(feature_id: int, request: MoveFeatureRequest):
    """
    Move a feature up or down within its current lane.

    Swaps priorities with the adjacent feature in the specified direction.
    Direction must be "up" or "down".
    """
    if request.direction not in ["up", "down"]:
        raise HTTPException(status_code=400, detail="Direction must be 'up' or 'down'")

    session = get_session()
    try:
        feature = session.query(Feature).filter(Feature.id == feature_id).first()

        if feature is None:
            raise HTTPException(status_code=404, detail=f"Feature {feature_id} not found")

        # Find adjacent feature in the same lane (same passes/in_progress state)
        if request.direction == "up":
            # Find feature with next lower priority (smaller number = higher priority)
            adjacent = session.query(Feature).filter(
                Feature.passes == feature.passes,
                Feature.in_progress == feature.in_progress,
                Feature.priority < feature.priority
            ).order_by(Feature.priority.desc()).first()
        else:  # down
            # Find feature with next higher priority (larger number = lower priority)
            adjacent = session.query(Feature).filter(
                Feature.passes == feature.passes,
                Feature.in_progress == feature.in_progress,
                Feature.priority > feature.priority
            ).order_by(Feature.priority.asc()).first()

        if adjacent is None:
            raise HTTPException(status_code=400, detail=f"Cannot move feature {request.direction}: already at the edge")

        # Swap priorities
        feature.priority, adjacent.priority = adjacent.priority, feature.priority

        session.commit()
        session.refresh(feature)

        return FeatureResponse(**feature.to_dict())
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

        # Get all features in the lane sorted by current priority
        lane_features = session.query(Feature).filter(
            Feature.passes == feature.passes,
            Feature.in_progress == feature.in_progress,
        ).order_by(Feature.priority.asc()).all()

        # Collect current priority values to reuse (preserves cross-lane priority values)
        priorities = [f.priority for f in lane_features]

        # Build new order: remove dragged feature, insert at target position
        ordered = [f for f in lane_features if f.id != feature_id]
        target_idx = next((i for i, f in enumerate(ordered) if f.id == request.target_id), None)

        if target_idx is None:
            raise HTTPException(status_code=400, detail="Target feature not found in the same lane")

        insert_idx = target_idx if request.insert_before else target_idx + 1
        ordered.insert(insert_idx, feature)

        # Reassign priorities in new order
        for f, p in zip(ordered, priorities):
            f.priority = p

        session.commit()
        session.refresh(feature)

        return FeatureResponse(**feature.to_dict())
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
async def launch_claude_for_feature(feature_id: int):
    """
    Launch a Claude Code session to work on a specific feature.

    Opens Claude in a new terminal window with the feature context as the initial prompt.
    The working directory is the folder containing the active features.db, so Claude
    operates in the correct project context.

    Only works for TODO and IN PROGRESS features (not completed features).
    """
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
                ps_cmd = f'claude --model {feature_model} --dangerously-skip-permissions (Get-Content -LiteralPath "{prompt_file}" -Raw)'
                # Try pwsh (PowerShell 7) first, fall back to powershell (Windows PS 5)
                ps_executables = ["pwsh", "powershell"]
                launched = False
                for ps_exe in ps_executables:
                    try:
                        subprocess.Popen(
                            [ps_exe, "-NoExit", "-Command", ps_cmd],
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
                subprocess.Popen(["claude", "--model", feature_model, "--dangerously-skip-permissions", prompt], cwd=working_dir)
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
        )
    finally:
        session.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

 


 

