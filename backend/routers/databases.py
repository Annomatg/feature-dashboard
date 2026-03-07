"""
Database management endpoints router.
"""

import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import module to access _current_db_path by reference (not by value) —
# switch_database() mutates this attribute at runtime.
import backend.deps as _deps
from backend.deps import PROJECT_DIR, load_dashboards_config, validate_db_path, switch_database
from backend.schemas import DatabaseInfo, SelectDatabaseRequest

router = APIRouter(prefix="/api/databases", tags=["databases"])


@router.get("", response_model=list[DatabaseInfo])
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
            is_active=db_path.resolve() == _deps._current_db_path.resolve()
        ))

    return result


@router.get("/active", response_model=DatabaseInfo)
async def get_active_database():
    """Get the currently active database."""
    config = load_dashboards_config()

    # Find the matching config entry
    for db_config in config:
        db_path = PROJECT_DIR / db_config["path"]
        if db_path.resolve() == _deps._current_db_path.resolve():
            return DatabaseInfo(
                name=db_config["name"],
                path=db_config["path"],
                exists=True,
                is_active=True
            )

    # If not in config, return current path info
    return DatabaseInfo(
        name="Current Database",
        path=str(_deps._current_db_path.relative_to(PROJECT_DIR)),
        exists=_deps._current_db_path.exists(),
        is_active=True
    )


@router.post("/select")
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
