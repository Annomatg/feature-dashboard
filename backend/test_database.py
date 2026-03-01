"""
Unit/integration tests for database schema and migrations.

Covers:
- name_tokens table creation (migration v6)
- NameToken model CRUD via SQLAlchemy
- description_tokens table creation (migration v7)
- DescriptionToken model CRUD via SQLAlchemy
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
    DescriptionToken,
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


# ---------------------------------------------------------------------------
# description_tokens table existence & schema
# ---------------------------------------------------------------------------


def test_description_tokens_table_exists(temp_db):
    """description_tokens table must be created on database initialisation."""
    engine, _ = temp_db
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='description_tokens'")
        )
        assert result.fetchone() is not None, "description_tokens table was not created"


def test_description_tokens_schema(temp_db):
    """description_tokens must have exactly: token TEXT PK, usage_count INTEGER NOT NULL DEFAULT 0."""
    engine, _ = temp_db
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA table_info(description_tokens)"))
        columns = {row[1]: row for row in result.fetchall()}

    assert "token" in columns, "token column missing"
    assert "usage_count" in columns, "usage_count column missing"
    assert len(columns) == 2, f"Expected 2 columns, got {len(columns)}: {list(columns)}"

    # token column: pk=1
    token_col = columns["token"]
    assert token_col[5] == 1, "token should be the primary key (pk=1)"

    # usage_count: notnull=1, default=0
    usage_col = columns["usage_count"]
    assert usage_col[3] == 1, "usage_count should be NOT NULL"
    raw_default = usage_col[4]
    assert raw_default is not None, "usage_count must have a DEFAULT"
    assert raw_default.strip("'") == "0", f"usage_count default should resolve to 0, got {raw_default!r}"


# ---------------------------------------------------------------------------
# ORM CRUD via DescriptionToken model
# ---------------------------------------------------------------------------


def test_description_token_insert_and_query(temp_db):
    """Can insert a DescriptionToken record and retrieve it."""
    _, session_maker = temp_db
    session = session_maker()
    try:
        token = DescriptionToken(token="authentication", usage_count=5)
        session.add(token)
        session.commit()

        fetched = session.query(DescriptionToken).filter_by(token="authentication").first()
        assert fetched is not None
        assert fetched.token == "authentication"
        assert fetched.usage_count == 5
    finally:
        session.close()


def test_description_token_default_usage_count(temp_db):
    """usage_count defaults to 0 when not provided."""
    _, session_maker = temp_db
    session = session_maker()
    try:
        token = DescriptionToken(token="migration")
        session.add(token)
        session.commit()

        fetched = session.query(DescriptionToken).filter_by(token="migration").first()
        assert fetched is not None
        assert fetched.usage_count == 0
    finally:
        session.close()


def test_description_token_primary_key_uniqueness(temp_db):
    """Inserting a duplicate token must raise an integrity error."""
    from sqlalchemy.exc import IntegrityError

    _, session_maker = temp_db
    session = session_maker()
    try:
        session.add(DescriptionToken(token="duplicate", usage_count=1))
        session.commit()

        session.add(DescriptionToken(token="duplicate", usage_count=2))
        with pytest.raises(IntegrityError):
            session.commit()
    finally:
        session.rollback()
        session.close()


def test_description_token_update(temp_db):
    """Can update usage_count for an existing token."""
    _, session_maker = temp_db
    session = session_maker()
    try:
        session.add(DescriptionToken(token="update_me", usage_count=1))
        session.commit()

        token = session.query(DescriptionToken).filter_by(token="update_me").first()
        token.usage_count = 10
        session.commit()

        refreshed = session.query(DescriptionToken).filter_by(token="update_me").first()
        assert refreshed.usage_count == 10
    finally:
        session.close()


def test_description_token_delete(temp_db):
    """Can delete a DescriptionToken record."""
    _, session_maker = temp_db
    session = session_maker()
    try:
        session.add(DescriptionToken(token="delete_me", usage_count=1))
        session.commit()

        token = session.query(DescriptionToken).filter_by(token="delete_me").first()
        session.delete(token)
        session.commit()

        assert session.query(DescriptionToken).filter_by(token="delete_me").first() is None
    finally:
        session.close()


def test_description_token_to_dict(temp_db):
    """to_dict() returns the expected structure."""
    _, session_maker = temp_db
    session = session_maker()
    try:
        session.add(DescriptionToken(token="serialise", usage_count=4))
        session.commit()

        token = session.query(DescriptionToken).filter_by(token="serialise").first()
        d = token.to_dict()
        assert d == {"token": "serialise", "usage_count": 4}
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Migration v7 idempotency & schema version
# ---------------------------------------------------------------------------


def test_migration_v7_idempotent(temp_db):
    """Running migration v7 again on an existing DB must not raise."""
    from api.database import _migration_v7

    engine, _ = temp_db
    # Should not raise even though table already exists
    _migration_v7(engine)

    # Table still present and intact
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='description_tokens'")
        )
        assert result.fetchone() is not None


def test_schema_version_updated_to_7(temp_db):
    """After create_database(), schema_version in db_meta must be 7 (or higher)."""
    engine, _ = temp_db
    with engine.connect() as conn:
        result = conn.execute(text("SELECT schema_version FROM db_meta"))
        version = result.fetchone()[0]
    assert version >= 7, f"Expected schema_version >= 7, got {version}"


# ---------------------------------------------------------------------------
# tokenize_name unit tests
# ---------------------------------------------------------------------------


def test_tokenize_name_basic():
    """Simple multi-word name produces expected tokens."""
    from api.migration import tokenize_name

    assert tokenize_name("Add login button") == ["add", "login", "button"]


def test_tokenize_name_lowercase():
    """Output tokens are always lowercase."""
    from api.migration import tokenize_name

    tokens = tokenize_name("FastAPI Backend")
    assert tokens == ["fastapi", "backend"]


def test_tokenize_name_strips_punctuation():
    """Punctuation is removed and does not merge adjacent words."""
    from api.migration import tokenize_name

    tokens = tokenize_name("auto-reload: on startup")
    assert "auto" in tokens
    assert "reload" in tokens
    assert "on" in tokens
    assert "startup" in tokens
    # No colons or hyphens remain
    assert all(":" not in t and "-" not in t for t in tokens)


def test_tokenize_name_drops_short_tokens():
    """Tokens of length 1 are dropped; length 2 tokens are kept."""
    from api.migration import tokenize_name

    tokens = tokenize_name("a is ok go")
    assert "a" not in tokens
    assert "is" in tokens
    assert "ok" in tokens
    assert "go" in tokens


def test_tokenize_name_empty_string():
    """Empty name returns empty list."""
    from api.migration import tokenize_name

    assert tokenize_name("") == []


def test_tokenize_name_only_punctuation():
    """Name containing only punctuation returns empty list."""
    from api.migration import tokenize_name

    assert tokenize_name("---!!!") == []


def test_tokenize_name_numbers_kept():
    """Numeric tokens of length >= 2 are kept."""
    from api.migration import tokenize_name

    tokens = tokenize_name("v2 api endpoint")
    assert "v2" in tokens
    assert "api" in tokens


# ---------------------------------------------------------------------------
# backfill_name_tokens integration tests
# ---------------------------------------------------------------------------


@pytest.fixture
def seeded_db():
    """Create an isolated DB seeded with known features for backfill tests."""
    import shutil
    import tempfile

    from api.database import Feature, create_database

    temp_dir = tempfile.mkdtemp()
    engine, session_maker = create_database(Path(temp_dir))

    session = session_maker()
    try:
        features = [
            Feature(id=1, priority=1, category="Backend", name="Add login button",
                    description="desc", steps=["step"], passes=False, in_progress=False),
            Feature(id=2, priority=2, category="Backend", name="Add logout button",
                    description="desc", steps=["step"], passes=False, in_progress=False),
            Feature(id=3, priority=3, category="Frontend", name="Create dashboard",
                    description="desc", steps=["step"], passes=False, in_progress=False),
        ]
        for f in features:
            session.add(f)
        session.commit()
    finally:
        session.close()

    yield engine, session_maker

    engine.dispose()
    try:
        shutil.rmtree(temp_dir)
    except PermissionError:
        pass


def test_backfill_name_tokens_populates_table(seeded_db):
    """backfill_name_tokens inserts tokens from all feature names."""
    from api.database import NameToken
    from api.migration import backfill_name_tokens

    _, session_maker = seeded_db
    count = backfill_name_tokens(session_maker)
    assert count > 0

    session = session_maker()
    try:
        tokens = {row.token: row.usage_count for row in session.query(NameToken).all()}
    finally:
        session.close()

    # "add" appears in "Add login button" and "Add logout button"
    assert tokens.get("add") == 2
    # "button" appears twice
    assert tokens.get("button") == 2
    # "login" appears once
    assert tokens.get("login") == 1
    # "logout" appears once
    assert tokens.get("logout") == 1
    # "create" and "dashboard" appear once each
    assert tokens.get("create") == 1
    assert tokens.get("dashboard") == 1


def test_backfill_name_tokens_returns_distinct_count(seeded_db):
    """Return value equals the number of distinct tokens inserted."""
    from api.database import NameToken
    from api.migration import backfill_name_tokens

    _, session_maker = seeded_db
    returned = backfill_name_tokens(session_maker)

    session = session_maker()
    try:
        db_count = session.query(NameToken).count()
    finally:
        session.close()

    assert returned == db_count


def test_backfill_name_tokens_idempotent_guard(seeded_db):
    """Second call returns -1 and does not alter existing tokens."""
    from api.database import NameToken
    from api.migration import backfill_name_tokens

    _, session_maker = seeded_db
    first = backfill_name_tokens(session_maker)
    assert first > 0

    second = backfill_name_tokens(session_maker)
    assert second == -1

    session = session_maker()
    try:
        count_after = session.query(NameToken).count()
    finally:
        session.close()

    assert count_after == first  # unchanged


def test_backfill_name_tokens_empty_features():
    """Backfill on a DB with no features inserts 0 tokens and returns 0."""
    import shutil
    import tempfile

    from api.database import NameToken, create_database
    from api.migration import backfill_name_tokens

    temp_dir = tempfile.mkdtemp()
    try:
        engine, session_maker = create_database(Path(temp_dir))
        try:
            result = backfill_name_tokens(session_maker)
            assert result == 0

            session = session_maker()
            try:
                assert session.query(NameToken).count() == 0
            finally:
                session.close()
        finally:
            engine.dispose()
    finally:
        try:
            shutil.rmtree(temp_dir)
        except PermissionError:
            pass


# ---------------------------------------------------------------------------
# tokenize_description unit tests
# ---------------------------------------------------------------------------


def test_tokenize_description_basic():
    """Simple description produces expected tokens."""
    from api.migration import tokenize_description

    assert tokenize_description("Populate tokens from description") == [
        "populate", "tokens", "from", "description"
    ]


def test_tokenize_description_lowercase():
    """Output tokens are always lowercase."""
    from api.migration import tokenize_description

    tokens = tokenize_description("FastAPI Backend Server")
    assert tokens == ["fastapi", "backend", "server"]


def test_tokenize_description_strips_punctuation():
    """Punctuation is removed and does not merge adjacent words."""
    from api.migration import tokenize_description

    tokens = tokenize_description("reads all rows from features.description")
    assert "reads" in tokens
    assert "all" in tokens
    assert "rows" in tokens
    assert "from" in tokens
    assert "features" in tokens
    assert "description" in tokens
    assert all("." not in t for t in tokens)


def test_tokenize_description_drops_short_tokens():
    """Tokens of length 1 are dropped; length 2 tokens are kept."""
    from api.migration import tokenize_description

    tokens = tokenize_description("a is ok to do")
    assert "a" not in tokens
    assert "is" in tokens
    assert "ok" in tokens
    assert "to" in tokens
    assert "do" in tokens


def test_tokenize_description_empty_string():
    """Empty description returns empty list."""
    from api.migration import tokenize_description

    assert tokenize_description("") == []


def test_tokenize_description_only_punctuation():
    """Description containing only punctuation returns empty list."""
    from api.migration import tokenize_description

    assert tokenize_description("---!!!...") == []


def test_tokenize_description_numbers_kept():
    """Numeric tokens of length >= 2 are kept."""
    from api.migration import tokenize_description

    tokens = tokenize_description("schema version v2 migration step")
    assert "v2" in tokens
    assert "migration" in tokens


def test_tokenize_description_long_text():
    """Longer multi-sentence description is tokenized correctly."""
    from api.migration import tokenize_description

    desc = "One-time migration that tokenizes all existing features."
    tokens = tokenize_description(desc)
    assert "one" in tokens
    assert "time" in tokens
    assert "migration" in tokens
    assert "tokenizes" in tokens
    assert "all" in tokens
    assert "existing" in tokens
    assert "features" in tokens


# ---------------------------------------------------------------------------
# backfill_description_tokens integration tests
# ---------------------------------------------------------------------------


@pytest.fixture
def seeded_desc_db():
    """Create an isolated DB seeded with features having meaningful descriptions."""
    import shutil
    import tempfile

    from api.database import Feature, create_database

    temp_dir = tempfile.mkdtemp()
    engine, session_maker = create_database(Path(temp_dir))

    session = session_maker()
    try:
        features = [
            Feature(id=1, priority=1, category="Backend", name="Feature A",
                    description="Populate tokens from feature description",
                    steps=["step"], passes=False, in_progress=False),
            Feature(id=2, priority=2, category="Backend", name="Feature B",
                    description="Populate tokens from feature name field",
                    steps=["step"], passes=False, in_progress=False),
            Feature(id=3, priority=3, category="Frontend", name="Feature C",
                    description="Run migration on startup",
                    steps=["step"], passes=False, in_progress=False),
        ]
        for f in features:
            session.add(f)
        session.commit()
    finally:
        session.close()

    yield engine, session_maker

    engine.dispose()
    try:
        shutil.rmtree(temp_dir)
    except PermissionError:
        pass


def test_backfill_description_tokens_populates_table(seeded_desc_db):
    """backfill_description_tokens inserts tokens from all feature descriptions."""
    from api.database import DescriptionToken
    from api.migration import backfill_description_tokens

    _, session_maker = seeded_desc_db
    count = backfill_description_tokens(session_maker)
    assert count > 0

    session = session_maker()
    try:
        tokens = {row.token: row.usage_count for row in session.query(DescriptionToken).all()}
    finally:
        session.close()

    # "populate" appears in descriptions 1 and 2
    assert tokens.get("populate") == 2
    # "tokens" appears in descriptions 1 and 2
    assert tokens.get("tokens") == 2
    # "from" appears in descriptions 1 and 2
    assert tokens.get("from") == 2
    # "feature" appears in descriptions 1 and 2 (not in "Run migration on startup")
    assert tokens.get("feature") == 2
    # "description" appears once (feature A)
    assert tokens.get("description") == 1
    # "migration" appears once (feature C)
    assert tokens.get("migration") == 1


def test_backfill_description_tokens_returns_distinct_count(seeded_desc_db):
    """Return value equals the number of distinct tokens inserted."""
    from api.database import DescriptionToken
    from api.migration import backfill_description_tokens

    _, session_maker = seeded_desc_db
    returned = backfill_description_tokens(session_maker)

    session = session_maker()
    try:
        db_count = session.query(DescriptionToken).count()
    finally:
        session.close()

    assert returned == db_count


def test_backfill_description_tokens_idempotent_guard(seeded_desc_db):
    """Second call returns -1 and does not alter existing tokens."""
    from api.database import DescriptionToken
    from api.migration import backfill_description_tokens

    _, session_maker = seeded_desc_db
    first = backfill_description_tokens(session_maker)
    assert first > 0

    second = backfill_description_tokens(session_maker)
    assert second == -1

    session = session_maker()
    try:
        count_after = session.query(DescriptionToken).count()
    finally:
        session.close()

    assert count_after == first  # unchanged


def test_backfill_description_tokens_empty_features():
    """Backfill on a DB with no features inserts 0 tokens and returns 0."""
    import shutil
    import tempfile

    from api.database import DescriptionToken, create_database
    from api.migration import backfill_description_tokens

    temp_dir = tempfile.mkdtemp()
    try:
        engine, session_maker = create_database(Path(temp_dir))
        try:
            result = backfill_description_tokens(session_maker)
            assert result == 0

            session = session_maker()
            try:
                assert session.query(DescriptionToken).count() == 0
            finally:
                session.close()
        finally:
            engine.dispose()
    finally:
        try:
            shutil.rmtree(temp_dir)
        except PermissionError:
            pass


def test_backfill_description_tokens_aggregates_counts():
    """Tokens shared across multiple descriptions have summed usage_count."""
    import shutil
    import tempfile

    from api.database import DescriptionToken, Feature, create_database
    from api.migration import backfill_description_tokens

    temp_dir = tempfile.mkdtemp()
    try:
        engine, session_maker = create_database(Path(temp_dir))
        session = session_maker()
        try:
            # "migration" appears in all three descriptions
            features = [
                Feature(id=1, priority=1, category="X", name="A",
                        description="run migration step",
                        steps=["s"], passes=False, in_progress=False),
                Feature(id=2, priority=2, category="X", name="B",
                        description="migration runs on startup",
                        steps=["s"], passes=False, in_progress=False),
                Feature(id=3, priority=3, category="X", name="C",
                        description="apply migration to database",
                        steps=["s"], passes=False, in_progress=False),
            ]
            for f in features:
                session.add(f)
            session.commit()
        finally:
            session.close()

        backfill_description_tokens(session_maker)

        session = session_maker()
        try:
            token = session.query(DescriptionToken).filter_by(token="migration").first()
            assert token is not None
            assert token.usage_count == 3
        finally:
            session.close()
    finally:
        engine.dispose()
        try:
            shutil.rmtree(temp_dir)
        except PermissionError:
            pass
