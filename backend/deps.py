"""
Shared dependencies for Feature Dashboard backend.
====================================================

Contains shared database session helpers, config utilities, and mutable server
state that all routers import from.  Extracted from main.py so that future
router modules have a single, stable import target.

Public API
----------
- get_session()                           SQLAlchemy session factory
- get_comment_counts(session, ids)        batch comment-count query
- get_commit_counts(session, ids)         batch commit-count query
- get_recent_logs(session, ids)           batch most-recent-log query
- feature_to_response(feature, c, l, cc) ORM → FeatureResponse conversion
- load_settings() / save_settings(s)     settings.json I/O
- load_dashboards_config()               dashboards.json I/O
- validate_db_path(path)                 DB path validation
- switch_database(path)                  active-DB switching

Mutable state (importable by routers)
--------------------------------------
- _current_db_path   active database Path
- _autopilot_states  per-DB autopilot state dict
- _feature_subscribers  SSE subscriber queue list
"""

import asyncio
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import create_engine, func as sa_func
from sqlalchemy.orm import sessionmaker

# Add parent directory to path for api/ package imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.database import Comment, Feature, FeatureCommit, create_database

# ── Constants ──────────────────────────────────────────────────────────────────

PROJECT_DIR = Path(__file__).parent.parent
CONFIG_FILE = PROJECT_DIR / "dashboards.json"
SETTINGS_FILE = PROJECT_DIR / "settings.json"

PLANNING_MODEL = "claude-opus-4-6"

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

# ── Database state ─────────────────────────────────────────────────────────────
# Support test database via environment variable

_TEST_DB_PATH = os.environ.get("TEST_DB_PATH")
if _TEST_DB_PATH:
    _test_db_path = Path(_TEST_DB_PATH)
    _current_db_path: Path = _test_db_path
    _engine, _session_maker = create_database(
        _test_db_path.parent, db_filename=_test_db_path.name
    )
else:
    _current_db_path = PROJECT_DIR / "features.db"
    _engine, _session_maker = create_database(PROJECT_DIR)

# ── Autopilot state ────────────────────────────────────────────────────────────
# Keyed by database path string.  The _AutoPilotState class lives in main.py;
# we use a plain dict here to avoid importing it (which would be circular).
_autopilot_states: dict = {}

# ── SSE subscriber list ────────────────────────────────────────────────────────
# Each subscriber is an asyncio.Queue; the broadcast helper in main.py puts
# events onto every queue.
_feature_subscribers: list = []


# ── Session helper ─────────────────────────────────────────────────────────────

def get_session():
    """Get a SQLAlchemy database session from the current session factory."""
    return _session_maker()


# ── Query helpers ──────────────────────────────────────────────────────────────

def get_comment_counts(session, feature_ids: list) -> dict:
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


def get_recent_logs(session, feature_ids: list) -> dict:
    """Return a mapping of feature_id -> most recent comment content for the given feature IDs."""
    if not feature_ids:
        return {}
    subq = (
        session.query(
            Comment.feature_id,
            sa_func.max(Comment.id).label("max_id"),
        )
        .filter(Comment.feature_id.in_(feature_ids))
        .group_by(Comment.feature_id)
        .subquery()
    )
    rows = (
        session.query(Comment.feature_id, Comment.content)
        .join(subq, Comment.id == subq.c.max_id)
        .all()
    )
    return {fid: content for fid, content in rows}


def get_commit_counts(session, feature_ids: list) -> dict:
    """Return a mapping of feature_id -> commit_count for the given feature IDs."""
    if not feature_ids:
        return {}
    rows = (
        session.query(FeatureCommit.feature_id, sa_func.count(FeatureCommit.id))
        .filter(FeatureCommit.feature_id.in_(feature_ids))
        .group_by(FeatureCommit.feature_id)
        .all()
    )
    return {fid: count for fid, count in rows}


def feature_to_response(feature, comment_counts: dict, recent_logs: Optional[dict] = None, commit_counts: Optional[dict] = None):
    """Convert a Feature ORM object to FeatureResponse including comment_count, commit_count, and recent_log."""
    # Import here to avoid potential circular imports at module load time
    from backend.schemas import FeatureResponse
    d = feature.to_dict()
    d["comment_count"] = comment_counts.get(feature.id, 0)
    d["commit_count"] = (commit_counts or {}).get(feature.id, 0)
    d["recent_log"] = (recent_logs or {}).get(feature.id)
    return FeatureResponse(**d)


# ── Settings I/O ───────────────────────────────────────────────────────────────

def load_settings() -> dict:
    """Load settings from settings.json, returning defaults if not found."""
    defaults = {
        "claude_prompt_template": DEFAULT_PROMPT_TEMPLATE,
        "plan_tasks_prompt_template": PLAN_TASKS_PROMPT_TEMPLATE,
        "autopilot_budget_limit": 0,
        "provider": "claude",
        "planning_model": PLANNING_MODEL,
    }
    if not SETTINGS_FILE.exists():
        return defaults
    try:
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for key, default in defaults.items():
            if key not in data:
                data[key] = default
        return data
    except Exception:
        return defaults


def save_settings(settings: dict) -> None:
    """Save settings to settings.json."""
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)


# ── Dashboard config I/O ───────────────────────────────────────────────────────

def load_dashboards_config() -> list:
    """Load dashboards configuration from dashboards.json."""
    if not CONFIG_FILE.exists():
        return [{"name": "Feature Dashboard", "path": "features.db"}]
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load dashboards config: {str(e)}")


# ── Database switching ─────────────────────────────────────────────────────────

def validate_db_path(db_path: Path) -> bool:
    """Validate that the path is a valid SQLite database with a features table."""
    if not db_path.exists():
        return False
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='features'")
        result = cursor.fetchone()
        conn.close()
        return result is not None
    except sqlite3.DatabaseError:
        return False


def switch_database(db_path: Path) -> None:
    """Switch the active database connection to *db_path*."""
    global _current_db_path, _engine, _session_maker

    if not validate_db_path(db_path):
        raise HTTPException(status_code=400, detail=f"Invalid database path: {db_path}")

    db_url = f"sqlite:///{db_path.as_posix()}"
    _engine = create_engine(db_url, connect_args={"check_same_thread": False})
    _session_maker = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    _current_db_path = db_path
