"""
Database Models and Connection
==============================

SQLite database schema for feature storage using SQLAlchemy.
"""

from pathlib import Path
from typing import Optional

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.sql import func
from sqlalchemy.types import JSON

Base = declarative_base()


class Feature(Base):
    """Feature model representing a test case/feature to implement."""

    __tablename__ = "features"

    id = Column(Integer, primary_key=True, index=True)
    priority = Column(Integer, nullable=False, default=999, index=True)
    category = Column(String(100), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    steps = Column(JSON, nullable=False)  # Stored as JSON array
    passes = Column(Boolean, nullable=False, default=False, index=True)
    in_progress = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime, default=func.now())
    modified_at = Column(DateTime, default=func.now(), onupdate=func.now())
    completed_at = Column(DateTime, nullable=True)

    def to_dict(self) -> dict:
        """Convert feature to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "priority": self.priority,
            "category": self.category,
            "name": self.name,
            "description": self.description,
            "steps": self.steps,
            # Handle legacy NULL values gracefully - treat as False
            "passes": self.passes if self.passes is not None else False,
            "in_progress": self.in_progress if self.in_progress is not None else False,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "modified_at": self.modified_at.isoformat() if self.modified_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


def get_database_path(project_dir: Path, db_filename: str = "features.db") -> Path:
    """Return the path to the SQLite database for a project."""
    return project_dir / db_filename


def get_database_url(project_dir: Path, db_filename: str = "features.db") -> str:
    """Return the SQLAlchemy database URL for a project.

    Uses POSIX-style paths (forward slashes) for cross-platform compatibility.
    """
    db_path = get_database_path(project_dir, db_filename)
    return f"sqlite:///{db_path.as_posix()}"


# ---------------------------------------------------------------------------
# Numbered migrations
# ---------------------------------------------------------------------------

LATEST_SCHEMA_VERSION = 3


def _migration_v1(engine) -> None:
    """v1: Add in_progress column to features table."""
    from sqlalchemy import text

    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA table_info(features)"))
        columns = [row[1] for row in result.fetchall()]
        if "in_progress" not in columns:
            conn.execute(text("ALTER TABLE features ADD COLUMN in_progress BOOLEAN DEFAULT 0"))
            conn.commit()


def _migration_v2(engine) -> None:
    """v2: Fix NULL values in passes and in_progress columns."""
    from sqlalchemy import text

    with engine.connect() as conn:
        conn.execute(text("UPDATE features SET passes = 0 WHERE passes IS NULL"))
        conn.execute(text("UPDATE features SET in_progress = 0 WHERE in_progress IS NULL"))
        conn.commit()


def _migration_v3(engine) -> None:
    """v3: Add created_at, modified_at, completed_at timestamp columns."""
    from datetime import datetime
    from sqlalchemy import text

    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA table_info(features)"))
        columns = [row[1] for row in result.fetchall()]
        current_time = datetime.now().isoformat()

        if "created_at" not in columns:
            conn.execute(text("ALTER TABLE features ADD COLUMN created_at DATETIME"))
            conn.execute(text(f"UPDATE features SET created_at = '{current_time}' WHERE created_at IS NULL"))
            conn.commit()

        if "modified_at" not in columns:
            conn.execute(text("ALTER TABLE features ADD COLUMN modified_at DATETIME"))
            conn.execute(text(f"UPDATE features SET modified_at = '{current_time}' WHERE modified_at IS NULL"))
            conn.commit()

        if "completed_at" not in columns:
            conn.execute(text("ALTER TABLE features ADD COLUMN completed_at DATETIME"))
            conn.commit()


_MIGRATIONS = [
    (1, _migration_v1),
    (2, _migration_v2),
    (3, _migration_v3),
]


def run_migrations(engine) -> None:
    """Run any missing schema migrations sequentially and update db_meta."""
    from sqlalchemy import text

    with engine.connect() as conn:
        # Ensure db_meta table exists (raw SQL — no SQLAlchemy model needed)
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS db_meta (schema_version INTEGER NOT NULL)"
        ))

        # Get current version; 0 means pre-versioning or brand-new DB
        result = conn.execute(text("SELECT schema_version FROM db_meta"))
        row = result.fetchone()
        current_version = row[0] if row else 0

        if row is None:
            conn.execute(text("INSERT INTO db_meta (schema_version) VALUES (0)"))
            conn.commit()

    for version, migration_fn in _MIGRATIONS:
        if version > current_version:
            migration_fn(engine)
            with engine.connect() as conn:
                conn.execute(text(f"UPDATE db_meta SET schema_version = {version}"))
                conn.commit()
            current_version = version


def create_database(project_dir: Path, db_filename: str = "features.db") -> tuple:
    """
    Create database and return engine + session maker.

    Args:
        project_dir: Directory containing the project
        db_filename: Database filename (default: "features.db")

    Returns:
        Tuple of (engine, SessionLocal)
    """
    db_url = get_database_url(project_dir, db_filename)
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    run_migrations(engine)

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return engine, SessionLocal


# Global session maker - will be set when server starts
_session_maker: Optional[sessionmaker] = None


def set_session_maker(session_maker: sessionmaker) -> None:
    """Set the global session maker."""
    global _session_maker
    _session_maker = session_maker


def get_db() -> Session:
    """
    Dependency for FastAPI to get database session.

    Yields a database session and ensures it's closed after use.
    """
    if _session_maker is None:
        raise RuntimeError("Database not initialized. Call set_session_maker first.")

    db = _session_maker()
    try:
        yield db
    finally:
        db.close()
