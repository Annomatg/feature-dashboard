"""
Unit tests for backend/deps.py shared helpers.
================================================

Tests all public functions exported from deps.py:
- get_session()
- get_comment_counts()
- get_recent_logs()
- feature_to_response()
- load_settings()
- save_settings()
- load_dashboards_config()
- validate_db_path()
- switch_database()
"""

import json
import sqlite3
import sys
import tempfile
import shutil
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import backend.deps as deps
from api.database import Comment, Feature, create_database


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db(tmp_path):
    """Create an isolated in-memory SQLite database and return (engine, session_maker, db_path)."""
    engine, session_maker = create_database(tmp_path)
    session = session_maker()
    try:
        session.add_all([
            Feature(id=1, priority=100, category="Backend", name="Alpha",
                    description="Desc A", steps=["S1"], passes=False, in_progress=False),
            Feature(id=2, priority=200, category="Frontend", name="Beta",
                    description="Desc B", steps=["S1"], passes=True, in_progress=False),
        ])
        session.commit()
    finally:
        session.close()

    db_path = tmp_path / "features.db"
    yield engine, session_maker, db_path

    engine.dispose()


@pytest.fixture
def session(tmp_db):
    """Return a SQLAlchemy session for the isolated test database."""
    engine, session_maker, db_path = tmp_db
    s = session_maker()
    yield s
    s.close()


# ── get_session ───────────────────────────────────────────────────────────────

def test_get_session_returns_working_session(monkeypatch, tmp_db):
    """get_session() returns a session that can query features."""
    engine, session_maker, db_path = tmp_db
    monkeypatch.setattr(deps, '_session_maker', session_maker)

    s = deps.get_session()
    try:
        count = s.query(Feature).count()
        assert count == 2
    finally:
        s.close()


# ── get_comment_counts ────────────────────────────────────────────────────────

def test_get_comment_counts_empty_ids(session):
    """Returns empty dict when feature_ids is empty."""
    result = deps.get_comment_counts(session, [])
    assert result == {}


def test_get_comment_counts_no_comments(session):
    """Returns zero counts when features have no comments."""
    result = deps.get_comment_counts(session, [1, 2])
    assert result == {}


def test_get_comment_counts_with_comments(session):
    """Returns correct comment count per feature."""
    session.add_all([
        Comment(feature_id=1, content="comment 1a", ),
        Comment(feature_id=1, content="comment 1b", ),
        Comment(feature_id=2, content="comment 2a", ),
    ])
    session.commit()

    result = deps.get_comment_counts(session, [1, 2])
    assert result[1] == 2
    assert result[2] == 1


def test_get_comment_counts_ignores_unknown_ids(session):
    """Returns only entries for IDs that actually exist."""
    result = deps.get_comment_counts(session, [999])
    assert result == {}


# ── get_recent_logs ───────────────────────────────────────────────────────────

def test_get_recent_logs_empty_ids(session):
    """Returns empty dict when feature_ids is empty."""
    result = deps.get_recent_logs(session, [])
    assert result == {}


def test_get_recent_logs_no_comments(session):
    """Returns empty dict when features have no comments."""
    result = deps.get_recent_logs(session, [1, 2])
    assert result == {}


def test_get_recent_logs_returns_latest(session):
    """Returns the content of the most recent (highest id) comment per feature."""
    session.add_all([
        Comment(feature_id=1, content="first", ),
        Comment(feature_id=1, content="second", ),
    ])
    session.commit()

    result = deps.get_recent_logs(session, [1])
    assert result[1] == "second"


# ── feature_to_response ───────────────────────────────────────────────────────

def test_feature_to_response_includes_comment_count(session):
    """feature_to_response populates comment_count from the provided counts dict."""
    feature = session.query(Feature).filter(Feature.id == 1).first()
    response = deps.feature_to_response(feature, {1: 5})
    assert response.comment_count == 5


def test_feature_to_response_defaults_comment_count_to_zero(session):
    """comment_count defaults to 0 when the feature ID is absent from counts."""
    feature = session.query(Feature).filter(Feature.id == 1).first()
    response = deps.feature_to_response(feature, {})
    assert response.comment_count == 0


def test_feature_to_response_includes_recent_log(session):
    """recent_log is populated from the provided recent_logs dict."""
    feature = session.query(Feature).filter(Feature.id == 1).first()
    response = deps.feature_to_response(feature, {}, {1: "last note"})
    assert response.recent_log == "last note"


def test_feature_to_response_recent_log_none_when_missing(session):
    """recent_log is None when the feature ID is absent from recent_logs."""
    feature = session.query(Feature).filter(Feature.id == 1).first()
    response = deps.feature_to_response(feature, {})
    assert response.recent_log is None


# ── load_settings ─────────────────────────────────────────────────────────────

def test_load_settings_returns_defaults_when_file_missing(monkeypatch, tmp_path):
    """Returns default settings when settings.json does not exist."""
    monkeypatch.setattr(deps, 'SETTINGS_FILE', tmp_path / "nonexistent.json")
    settings = deps.load_settings()
    assert "claude_prompt_template" in settings
    assert "autopilot_budget_limit" in settings
    assert settings["autopilot_budget_limit"] == 0


def test_load_settings_reads_file(monkeypatch, tmp_path):
    """Returns values from settings.json when the file exists."""
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({"autopilot_budget_limit": 5}), encoding='utf-8')
    monkeypatch.setattr(deps, 'SETTINGS_FILE', settings_file)

    result = deps.load_settings()
    assert result["autopilot_budget_limit"] == 5


def test_load_settings_fills_missing_keys_with_defaults(monkeypatch, tmp_path):
    """Missing keys are filled in from defaults when the file exists but is incomplete."""
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({"autopilot_budget_limit": 3}), encoding='utf-8')
    monkeypatch.setattr(deps, 'SETTINGS_FILE', settings_file)

    result = deps.load_settings()
    assert "claude_prompt_template" in result
    assert result["autopilot_budget_limit"] == 3


def test_load_settings_returns_defaults_on_corrupt_file(monkeypatch, tmp_path):
    """Returns defaults when settings.json contains invalid JSON."""
    settings_file = tmp_path / "settings.json"
    settings_file.write_text("not json", encoding='utf-8')
    monkeypatch.setattr(deps, 'SETTINGS_FILE', settings_file)

    result = deps.load_settings()
    assert result["autopilot_budget_limit"] == 0


# ── save_settings ─────────────────────────────────────────────────────────────

def test_save_settings_writes_json(monkeypatch, tmp_path):
    """save_settings writes valid JSON to settings.json."""
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(deps, 'SETTINGS_FILE', settings_file)

    deps.save_settings({"autopilot_budget_limit": 7})

    with open(settings_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    assert data["autopilot_budget_limit"] == 7


def test_save_then_load_roundtrip(monkeypatch, tmp_path):
    """Data saved via save_settings can be loaded back via load_settings."""
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(deps, 'SETTINGS_FILE', settings_file)

    original = {"autopilot_budget_limit": 10, "provider": "claude"}
    deps.save_settings(original)
    result = deps.load_settings()

    assert result["autopilot_budget_limit"] == 10
    assert result["provider"] == "claude"


# ── load_dashboards_config ────────────────────────────────────────────────────

def test_load_dashboards_config_returns_default_when_missing(monkeypatch, tmp_path):
    """Returns default single-entry list when dashboards.json does not exist."""
    monkeypatch.setattr(deps, 'CONFIG_FILE', tmp_path / "nonexistent.json")
    result = deps.load_dashboards_config()
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["path"] == "features.db"


def test_load_dashboards_config_reads_file(monkeypatch, tmp_path):
    """Returns parsed contents of dashboards.json when the file exists."""
    config = [{"name": "MyDB", "path": "mydb.db"}]
    config_file = tmp_path / "dashboards.json"
    config_file.write_text(json.dumps(config), encoding='utf-8')
    monkeypatch.setattr(deps, 'CONFIG_FILE', config_file)

    result = deps.load_dashboards_config()
    assert result == config


# ── validate_db_path ──────────────────────────────────────────────────────────

def test_validate_db_path_returns_false_for_nonexistent(tmp_path):
    """Returns False for a path that does not exist."""
    assert deps.validate_db_path(tmp_path / "missing.db") is False


def test_validate_db_path_returns_true_for_valid_db(tmp_db):
    """Returns True for a valid SQLite database with a features table."""
    engine, session_maker, db_path = tmp_db
    assert deps.validate_db_path(db_path) is True


def test_validate_db_path_returns_false_for_no_features_table(tmp_path):
    """Returns False for a SQLite file without a features table."""
    db_path = tmp_path / "empty.db"
    conn = sqlite3.connect(str(db_path))
    conn.close()
    assert deps.validate_db_path(db_path) is False


def test_validate_db_path_returns_false_for_non_sqlite(tmp_path):
    """Returns False for a file that is not a valid SQLite database."""
    bad_file = tmp_path / "bad.db"
    bad_file.write_bytes(b"this is not sqlite")
    assert deps.validate_db_path(bad_file) is False


# ── switch_database ───────────────────────────────────────────────────────────

def test_switch_database_updates_current_db_path(monkeypatch, tmp_db):
    """switch_database updates deps._current_db_path to the new path."""
    engine, session_maker, db_path = tmp_db
    original_path = deps._current_db_path

    try:
        deps.switch_database(db_path)
        assert deps._current_db_path == db_path
    finally:
        # Restore original path and engine
        monkeypatch.setattr(deps, '_current_db_path', original_path)


def test_switch_database_updates_session_maker(monkeypatch, tmp_db):
    """After switch_database, get_session() returns sessions for the new database."""
    engine, session_maker, db_path = tmp_db
    original_sm = deps._session_maker

    try:
        deps.switch_database(db_path)
        s = deps.get_session()
        try:
            count = s.query(Feature).count()
            assert count == 2
        finally:
            s.close()
    finally:
        monkeypatch.setattr(deps, '_session_maker', original_sm)
        monkeypatch.setattr(deps, '_current_db_path', deps.PROJECT_DIR / "features.db")


def test_switch_database_raises_for_invalid_path(tmp_path):
    """switch_database raises HTTPException(400) for an invalid database path."""
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        deps.switch_database(tmp_path / "nonexistent.db")
    assert exc_info.value.status_code == 400
