"""
Unit/integration tests for MCP feature tools
=============================================

Tests the MCP tool functions directly by patching the global _session_maker
with an in-memory SQLite database. Does NOT start the MCP server process.
"""

import json
import sys
import tempfile
import shutil
from pathlib import Path

import pytest

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.database import create_database, Feature
import mcp_server.feature_mcp as mcp_module


@pytest.fixture
def test_db():
    """Create an isolated test database seeded with known features."""
    temp_dir = tempfile.mkdtemp()

    engine, session_maker = create_database(Path(temp_dir))

    session = session_maker()
    try:
        features = [
            Feature(id=1, priority=1, category="Backend", name="Feature 1",
                    description="Test feature 1", steps=["Step 1"],
                    passes=False, in_progress=False),
            Feature(id=2, priority=2, category="Backend", name="Feature 2",
                    description="Test feature 2", steps=["Step 1"],
                    passes=False, in_progress=False),
            Feature(id=3, priority=3, category="Frontend", name="Feature 3",
                    description="Test feature 3", steps=["Step 1"],
                    passes=True, in_progress=False),
            Feature(id=4, priority=4, category="Frontend", name="Feature 4",
                    description="Test feature 4", steps=["Step 1"],
                    passes=False, in_progress=True),
        ]
        for f in features:
            session.add(f)
        session.commit()
    finally:
        session.close()

    yield session_maker

    engine.dispose()
    try:
        shutil.rmtree(temp_dir)
    except PermissionError:
        pass


@pytest.fixture(autouse=True)
def patch_session_maker(test_db, monkeypatch):
    """Patch the global _session_maker used by all MCP tools."""
    monkeypatch.setattr(mcp_module, "_session_maker", test_db)


# ===========================================================================
# feature_get_by_id
# ===========================================================================

class TestFeatureGetById:
    """Tests for feature_get_by_id()."""

    def test_returns_existing_feature(self):
        result = json.loads(mcp_module.feature_get_by_id(feature_id=1))
        assert result["id"] == 1
        assert result["name"] == "Feature 1"
        assert result["category"] == "Backend"
        assert result["passes"] is False
        assert result["in_progress"] is False

    def test_returns_passing_feature(self):
        """Should return a feature even if it is already passing."""
        result = json.loads(mcp_module.feature_get_by_id(feature_id=3))
        assert result["id"] == 3
        assert result["passes"] is True

    def test_returns_in_progress_feature(self):
        """Should return a feature even if it is already in-progress."""
        result = json.loads(mcp_module.feature_get_by_id(feature_id=4))
        assert result["id"] == 4
        assert result["in_progress"] is True

    def test_returns_error_for_missing_feature(self):
        result = json.loads(mcp_module.feature_get_by_id(feature_id=999))
        assert "error" in result
        assert "999" in result["error"]

    def test_returns_all_expected_fields(self):
        result = json.loads(mcp_module.feature_get_by_id(feature_id=1))
        for field in ("id", "priority", "category", "name", "description",
                      "steps", "passes", "in_progress"):
            assert field in result, f"Missing field: {field}"

    def test_returns_last_feature(self):
        result = json.loads(mcp_module.feature_get_by_id(feature_id=4))
        assert result["id"] == 4
        assert result["name"] == "Feature 4"


# ===========================================================================
# feature_get_next (regression — make sure it still works)
# ===========================================================================

class TestFeatureGetNext:
    def test_returns_lowest_priority_pending(self):
        result = json.loads(mcp_module.feature_get_next())
        assert result["id"] == 1
        assert result["passes"] is False

    def test_ignores_in_progress_and_passing(self):
        result = json.loads(mcp_module.feature_get_next())
        # Features 3 (passing) and 4 (in-progress) should not be returned first
        assert result["id"] in (1, 2)


# ===========================================================================
# feature_mark_in_progress (ensure it works independently of feature_get_next)
# ===========================================================================

class TestFeatureMarkInProgress:
    def test_mark_any_pending_feature_in_progress(self):
        """Can mark any pending feature, not only the 'next' one."""
        result = json.loads(mcp_module.feature_mark_in_progress(feature_id=2))
        assert result["id"] == 2
        assert result["in_progress"] is True

    def test_mark_first_feature_in_progress(self):
        result = json.loads(mcp_module.feature_mark_in_progress(feature_id=1))
        assert result["in_progress"] is True
        assert result["passes"] is False

    def test_error_when_already_in_progress(self):
        # Feature 4 is already in-progress
        result = json.loads(mcp_module.feature_mark_in_progress(feature_id=4))
        assert "error" in result
        assert "already in-progress" in result["error"]

    def test_error_when_already_passing(self):
        # Feature 3 is already passing
        result = json.loads(mcp_module.feature_mark_in_progress(feature_id=3))
        assert "error" in result
        assert "already passing" in result["error"]

    def test_error_for_missing_feature(self):
        result = json.loads(mcp_module.feature_mark_in_progress(feature_id=999))
        assert "error" in result
        assert "999" in result["error"]


# ===========================================================================
# Workflow: get by ID then mark in progress
# ===========================================================================

class TestGetByIdThenMarkInProgress:
    """Tests the workflow of retrieving a specific feature and starting work on it."""

    def test_full_workflow_get_then_mark(self):
        """An agent can look up feature 2 by ID and start working on it."""
        # Step 1: retrieve the feature by ID
        feature = json.loads(mcp_module.feature_get_by_id(feature_id=2))
        assert feature["id"] == 2
        assert feature["in_progress"] is False

        # Step 2: mark it as in-progress
        updated = json.loads(mcp_module.feature_mark_in_progress(feature_id=2))
        assert updated["id"] == 2
        assert updated["in_progress"] is True

    def test_get_next_and_get_by_id_return_same_data(self):
        """feature_get_next() and feature_get_by_id(1) return the same feature data."""
        by_next = json.loads(mcp_module.feature_get_next())
        by_id = json.loads(mcp_module.feature_get_by_id(feature_id=by_next["id"]))

        assert by_next["id"] == by_id["id"]
        assert by_next["name"] == by_id["name"]
        assert by_next["category"] == by_id["category"]


# ===========================================================================
# feature_get_stats (regression)
# ===========================================================================

class TestFeatureGetStats:
    def test_stats_counts(self):
        result = json.loads(mcp_module.feature_get_stats())
        assert result["total"] == 4
        assert result["passing"] == 1
        assert result["in_progress"] == 1
        assert isinstance(result["percentage"], float)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
