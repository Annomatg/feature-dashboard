"""
Unit/integration tests for database schema and migrations.

Covers:
- name_tokens table creation (migration v6)
- NameToken model CRUD via SQLAlchemy
- Schema correctness (column names, types, constraints)
"""

import shutil
import sys
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import inspect, text

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.database import (
    Base,
    NameToken,
    create_database,
)


@pytest.fixture
def temp_db():
    """Create an isolated temporary database and yield (engine, session_maker)."""
    temp_dir = tempfile.mkdtemp()
    engine, session_maker = create_database(Path(temp_dir))

    yield engine, session_maker

    engine.dispose()
    try:
        shutil.rmtree(temp_dir)
    except PermissionError:
        pass


# ---------------------------------------------------------------------------
# Table existence & schema
# ---------------------------------------------------------------------------


def test_name_tokens_table_exists(temp_db):
    """name_tokens table must be created on database initialisation."""
    engine, _ = temp_db
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='name_tokens'")
        )
        assert result.fetchone() is not None, "name_tokens table was not created"


def test_name_tokens_schema(temp_db):
    """name_tokens must have exactly: token TEXT PK, usage_count INTEGER NOT NULL DEFAULT 0."""
    engine, _ = temp_db
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA table_info(name_tokens)"))
        columns = {row[1]: row for row in result.fetchall()}

    assert "token" in columns, "token column missing"
    assert "usage_count" in columns, "usage_count column missing"
    assert len(columns) == 2, f"Expected 2 columns, got {len(columns)}: {list(columns)}"

    # token column: pk=1
    token_col = columns["token"]
    assert token_col[5] == 1, "token should be the primary key (pk=1)"

    # usage_count: notnull=1, default=0
    # SQLite PRAGMA dflt_value may be "0" (raw SQL DDL) or "'0'" (SQLAlchemy server_default)
    usage_col = columns["usage_count"]
    assert usage_col[3] == 1, "usage_count should be NOT NULL"
    raw_default = usage_col[4]
    assert raw_default is not None, "usage_count must have a DEFAULT"
    assert raw_default.strip("'") == "0", f"usage_count default should resolve to 0, got {raw_default!r}"


# ---------------------------------------------------------------------------
# ORM CRUD via NameToken model
# ---------------------------------------------------------------------------


def test_name_token_insert_and_query(temp_db):
    """Can insert a NameToken record and retrieve it."""
    _, session_maker = temp_db
    session = session_maker()
    try:
        token = NameToken(token="dashboard", usage_count=3)
        session.add(token)
        session.commit()

        fetched = session.query(NameToken).filter_by(token="dashboard").first()
        assert fetched is not None
        assert fetched.token == "dashboard"
        assert fetched.usage_count == 3
    finally:
        session.close()


def test_name_token_default_usage_count(temp_db):
    """usage_count defaults to 0 when not provided."""
    _, session_maker = temp_db
    session = session_maker()
    try:
        token = NameToken(token="feature")
        session.add(token)
        session.commit()

        fetched = session.query(NameToken).filter_by(token="feature").first()
        assert fetched is not None
        assert fetched.usage_count == 0
    finally:
        session.close()


def test_name_token_primary_key_uniqueness(temp_db):
    """Inserting a duplicate token must raise an integrity error."""
    from sqlalchemy.exc import IntegrityError

    _, session_maker = temp_db
    session = session_maker()
    try:
        session.add(NameToken(token="duplicate", usage_count=1))
        session.commit()

        session.add(NameToken(token="duplicate", usage_count=2))
        with pytest.raises(IntegrityError):
            session.commit()
    finally:
        session.rollback()
        session.close()


def test_name_token_update(temp_db):
    """Can update usage_count for an existing token."""
    _, session_maker = temp_db
    session = session_maker()
    try:
        session.add(NameToken(token="update_me", usage_count=1))
        session.commit()

        token = session.query(NameToken).filter_by(token="update_me").first()
        token.usage_count = 5
        session.commit()

        refreshed = session.query(NameToken).filter_by(token="update_me").first()
        assert refreshed.usage_count == 5
    finally:
        session.close()


def test_name_token_delete(temp_db):
    """Can delete a NameToken record."""
    _, session_maker = temp_db
    session = session_maker()
    try:
        session.add(NameToken(token="delete_me", usage_count=1))
        session.commit()

        token = session.query(NameToken).filter_by(token="delete_me").first()
        session.delete(token)
        session.commit()

        assert session.query(NameToken).filter_by(token="delete_me").first() is None
    finally:
        session.close()


def test_name_token_to_dict(temp_db):
    """to_dict() returns the expected structure."""
    _, session_maker = temp_db
    session = session_maker()
    try:
        session.add(NameToken(token="serialise", usage_count=7))
        session.commit()

        token = session.query(NameToken).filter_by(token="serialise").first()
        d = token.to_dict()
        assert d == {"token": "serialise", "usage_count": 7}
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Migration idempotency
# ---------------------------------------------------------------------------


def test_migration_v6_idempotent(temp_db):
    """Running migration v6 again on an existing DB must not raise."""
    from api.database import _migration_v6

    engine, _ = temp_db
    # Should not raise even though table already exists
    _migration_v6(engine)

    # Table still present and intact
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='name_tokens'")
        )
        assert result.fetchone() is not None


def test_schema_version_updated_to_6(temp_db):
    """After create_database(), schema_version in db_meta must be 6 (or higher)."""
    engine, _ = temp_db
    with engine.connect() as conn:
        result = conn.execute(text("SELECT schema_version FROM db_meta"))
        version = result.fetchone()[0]
    assert version >= 6, f"Expected schema_version >= 6, got {version}"
