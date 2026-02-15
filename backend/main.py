"""
Feature Dashboard Backend API
==============================

FastAPI server exposing feature data from SQLite database.
"""

import json
import sqlite3
import sys
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
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database setup
PROJECT_DIR = Path(__file__).parent.parent
CONFIG_FILE = PROJECT_DIR / "dashboards.json"

# Global state for active database
_current_db_path = PROJECT_DIR / "features.db"
_engine, _session_maker = create_database(PROJECT_DIR)


def get_session():
    """Get a database session."""
    return _session_maker()


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
    created_at: Optional[str] = None
    modified_at: Optional[str] = None
    completed_at: Optional[str] = None


class StatsResponse(BaseModel):
    """Statistics response."""
    passing: int
    in_progress: int
    total: int
    percentage: float


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


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Feature Dashboard API",
        "version": "1.0.0",
        "endpoints": {
            "features": "/api/features",
            "stats": "/api/features/stats",
            "feature_by_id": "/api/features/{id}",
            "databases": "/api/databases",
            "databases_active": "/api/databases/active",
            "databases_select": "/api/databases/select"
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


@app.get("/api/features", response_model=list[FeatureResponse], response_model_exclude_none=False)
async def get_features(
    passes: Optional[bool] = None,
    in_progress: Optional[bool] = None,
    category: Optional[str] = None
):
    """
    Get all features with optional filters.

    Query parameters:
    - passes: Filter by passing status (true/false)
    - in_progress: Filter by in-progress status (true/false)
    - category: Filter by category name
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

        features = query.order_by(Feature.priority.asc()).all()
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

 


 

