"""
Integration tests for CRUD REST endpoints
==========================================

Tests all feature CRUD operations including:
- POST /api/features (create)
- PUT /api/features/{id} (update)
- DELETE /api/features/{id} (delete)
- PATCH /api/features/{id}/state (state transitions)
- PATCH /api/features/{id}/priority (reordering)
- PATCH /api/features/{id}/move (up/down movement)

Uses dependency injection to override get_session() with isolated test databases.
DOES NOT modify production database.
"""

import subprocess
import sys
from pathlib import Path
import tempfile
import shutil
import pytest
from fastapi.testclient import TestClient

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.main import app, get_session
from api.database import create_database, Feature


@pytest.fixture
def test_db():
    """Create an isolated test database."""
    temp_dir = tempfile.mkdtemp()
    temp_db_path = Path(temp_dir) / "features.db"

    # Create isolated database
    engine, session_maker = create_database(Path(temp_dir))

    # Seed with test data
    session = session_maker()
    try:
        features = [
            Feature(id=1, priority=100, category="Backend", name="Feature 1",
                   description="Test feature 1", steps=["Step 1"], passes=False, in_progress=False),
            Feature(id=2, priority=200, category="Backend", name="Feature 2",
                   description="Test feature 2", steps=["Step 1"], passes=False, in_progress=False),
            Feature(id=3, priority=300, category="Frontend", name="Feature 3",
                   description="Test feature 3", steps=["Step 1"], passes=True, in_progress=False),
            Feature(id=4, priority=400, category="Frontend", name="Feature 4",
                   description="Test feature 4", steps=["Step 1"], passes=False, in_progress=True),
        ]
        for feature in features:
            session.add(feature)
        session.commit()
    finally:
        session.close()

    yield session_maker

    # Cleanup - dispose engine to release file locks
    engine.dispose()

    # Remove temp directory
    try:
        shutil.rmtree(temp_dir)
    except PermissionError:
        # Windows file locking issue - ignore
        pass


@pytest.fixture
def client(test_db, monkeypatch):
    """Create a test client with session monkeypatch."""
    import backend.main as main_module

    # Monkeypatch the global _session_maker to use our test database
    monkeypatch.setattr(main_module, '_session_maker', test_db)

    yield TestClient(app)


class TestCreateFeature:
    """Tests for POST /api/features"""

    def test_create_feature_success(self, client):
        """Test creating a new feature."""
        response = client.post("/api/features", json={
            "category": "Testing",
            "name": "New Test Feature",
            "description": "A new test feature",
            "steps": ["Step 1", "Step 2"]
        })

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == 5  # Next available ID
        assert data["priority"] == 500  # max(400) + 100
        assert data["category"] == "Testing"
        assert data["name"] == "New Test Feature"
        assert data["passes"] is False
        assert data["in_progress"] is False
        assert data["created_at"] is not None
        assert data["completed_at"] is None

    def test_create_feature_validation_error(self, client):
        """Test creating feature with missing required fields."""
        response = client.post("/api/features", json={
            "category": "Testing",
            "name": "Incomplete Feature"
            # Missing description and steps
        })

        assert response.status_code == 422  # Validation error


class TestUpdateFeature:
    """Tests for PUT /api/features/{id}"""

    def test_update_feature_success(self, client):
        """Test updating feature fields."""
        response = client.put("/api/features/1", json={
            "name": "Updated Feature Name",
            "description": "Updated description"
        })

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["name"] == "Updated Feature Name"
        assert data["description"] == "Updated description"
        assert data["category"] == "Backend"  # Unchanged
        assert data["modified_at"] is not None

    def test_update_feature_partial(self, client):
        """Test updating only some fields."""
        response = client.put("/api/features/1", json={
            "name": "Only Name Changed"
        })

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Only Name Changed"
        assert data["description"] == "Test feature 1"  # Unchanged

    def test_update_feature_not_found(self, client):
        """Test updating non-existent feature."""
        response = client.put("/api/features/999", json={
            "name": "Doesn't exist"
        })

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestDeleteFeature:
    """Tests for DELETE /api/features/{id}"""

    def test_delete_feature_success(self, client):
        """Test deleting a feature."""
        response = client.delete("/api/features/1")

        assert response.status_code == 204

        # Verify it's actually deleted
        get_response = client.get("/api/features/1")
        assert get_response.status_code == 404

    def test_delete_feature_not_found(self, client):
        """Test deleting non-existent feature."""
        response = client.delete("/api/features/999")

        assert response.status_code == 404


class TestUpdateFeatureState:
    """Tests for PATCH /api/features/{id}/state"""

    def test_move_to_in_progress(self, client):
        """Test moving feature to in-progress."""
        response = client.patch("/api/features/1/state", json={
            "in_progress": True
        })

        assert response.status_code == 200
        data = response.json()
        assert data["in_progress"] is True
        assert data["passes"] is False
        assert data["completed_at"] is None

    def test_move_to_done_sets_completed_at(self, client):
        """Test that moving to done sets completed_at timestamp."""
        response = client.patch("/api/features/1/state", json={
            "passes": True,
            "in_progress": False
        })

        assert response.status_code == 200
        data = response.json()
        assert data["passes"] is True
        assert data["in_progress"] is False
        assert data["completed_at"] is not None

    def test_move_from_done_clears_completed_at(self, client):
        """Test that moving from done clears completed_at timestamp."""
        # First move to done
        client.patch("/api/features/1/state", json={"passes": True})

        # Then move back to todo
        response = client.patch("/api/features/1/state", json={
            "passes": False
        })

        assert response.status_code == 200
        data = response.json()
        assert data["passes"] is False
        assert data["completed_at"] is None

    def test_update_state_not_found(self, client):
        """Test updating state of non-existent feature."""
        response = client.patch("/api/features/999/state", json={
            "passes": True
        })

        assert response.status_code == 404


class TestUpdateFeaturePriority:
    """Tests for PATCH /api/features/{id}/priority"""

    def test_update_priority_success(self, client):
        """Test updating feature priority."""
        response = client.patch("/api/features/1/priority", json={
            "priority": 10
        })

        assert response.status_code == 200
        data = response.json()
        assert data["priority"] == 10

    def test_update_priority_invalid(self, client):
        """Test updating priority to invalid value."""
        response = client.patch("/api/features/1/priority", json={
            "priority": 0
        })

        assert response.status_code == 400
        assert "must be >= 1" in response.json()["detail"].lower()

    def test_update_priority_not_found(self, client):
        """Test updating priority of non-existent feature."""
        response = client.patch("/api/features/999/priority", json={
            "priority": 5
        })

        assert response.status_code == 404


class TestMoveFeature:
    """Tests for PATCH /api/features/{id}/move"""

    def test_move_up_success(self, client):
        """Test moving feature up within its lane."""
        # Feature 2 (priority 200) should swap with Feature 1 (priority 100)
        response = client.patch("/api/features/2/move", json={
            "direction": "up"
        })

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 2
        assert data["priority"] == 100

        # Verify the other feature was also updated
        feature_1 = client.get("/api/features/1").json()
        assert feature_1["priority"] == 200

    def test_move_down_success(self, client):
        """Test moving feature down within its lane."""
        # Feature 1 (priority 100) should swap with Feature 2 (priority 200)
        response = client.patch("/api/features/1/move", json={
            "direction": "down"
        })

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["priority"] == 200

        # Verify the other feature was also updated
        feature_2 = client.get("/api/features/2").json()
        assert feature_2["priority"] == 100

    def test_move_up_at_top(self, client):
        """Test that moving up from top position fails gracefully."""
        # Feature 1 is at priority 1 (top of todo lane)
        response = client.patch("/api/features/1/move", json={
            "direction": "up"
        })

        assert response.status_code == 400
        assert "already at the edge" in response.json()["detail"].lower()

    def test_move_down_at_bottom(self, client):
        """Test that moving down from bottom position fails gracefully."""
        # Feature 4 is the only in-progress feature, so it's at the bottom
        response = client.patch("/api/features/4/move", json={
            "direction": "down"
        })

        assert response.status_code == 400
        assert "already at the edge" in response.json()["detail"].lower()

    def test_move_respects_lanes(self, client):
        """Test that move only swaps with features in the same lane."""
        # Feature 1 is todo, Feature 3 is done, Feature 4 is in-progress
        # Moving Feature 1 down should swap with Feature 2 (also todo), not Feature 3/4
        response = client.patch("/api/features/1/move", json={
            "direction": "down"
        })

        assert response.status_code == 200
        # Should swap with feature 2 (the other todo feature)
        assert response.json()["priority"] == 200

    def test_move_invalid_direction(self, client):
        """Test moving with invalid direction."""
        response = client.patch("/api/features/1/move", json={
            "direction": "sideways"
        })

        assert response.status_code == 400
        assert "must be 'up' or 'down'" in response.json()["detail"].lower()

    def test_move_not_found(self, client):
        """Test moving non-existent feature."""
        response = client.patch("/api/features/999/move", json={
            "direction": "up"
        })

        assert response.status_code == 404


class TestMoveFeatureWithDuplicatePriorities:
    """Regression tests for move/reorder with duplicate priorities (Feature #35)."""

    def test_move_down_when_both_features_share_same_priority(self, client):
        """Bug: moving top-prio task down fails when another task shares the same priority.

        When features 1 and 2 both have priority=1, moving feature 1 down should
        give it a higher priority number (lower display rank), not fail or stay at 1.
        """
        # Force both TODO features to have priority 1 (duplicate)
        client.patch("/api/features/1/priority", json={"priority": 1})
        client.patch("/api/features/2/priority", json={"priority": 1})

        response = client.patch("/api/features/1/move", json={"direction": "down"})

        assert response.status_code == 200
        f1_data = response.json()
        f2_data = client.get("/api/features/2").json()

        # Feature 1 must now sort AFTER feature 2 (higher priority number = lower rank)
        assert f1_data["priority"] > f2_data["priority"]

    def test_move_up_when_both_features_share_same_priority(self, client):
        """Moving the second of two equal-priority features up should place it first."""
        client.patch("/api/features/1/priority", json={"priority": 1})
        client.patch("/api/features/2/priority", json={"priority": 1})

        response = client.patch("/api/features/2/move", json={"direction": "up"})

        assert response.status_code == 200
        f2_data = response.json()
        f1_data = client.get("/api/features/1").json()

        # Feature 2 must now sort BEFORE feature 1
        assert f2_data["priority"] < f1_data["priority"]

    def test_reorder_high_prio_task_into_duplicate_group_keeps_distinct_priorities(self, client):
        """Bug: reordering a prio-27 task between two prio-1 tasks collapses it to prio 1.

        Expected: all three features end up with distinct priorities in the correct order.
        """
        # Set both TODO features to priority 1 (duplicate)
        client.patch("/api/features/1/priority", json={"priority": 1})
        client.patch("/api/features/2/priority", json={"priority": 1})

        # Create a third TODO feature — gets auto-assigned a high priority
        new_resp = client.post("/api/features", json={
            "category": "Testing",
            "name": "High Priority Task",
            "description": "Should not collapse to prio 1 when reordered",
            "steps": ["Verify priority stays distinct"],
        })
        assert new_resp.status_code == 201
        new_id = new_resp.json()["id"]

        # Reorder: insert the new feature between feature 1 and feature 2
        response = client.patch(f"/api/features/{new_id}/reorder", json={
            "target_id": 2,
            "insert_before": True,
        })

        assert response.status_code == 200

        f1 = client.get("/api/features/1").json()
        f2 = client.get("/api/features/2").json()
        fn = client.get(f"/api/features/{new_id}").json()

        # All three must have distinct priorities
        priorities = [f1["priority"], f2["priority"], fn["priority"]]
        assert len(priorities) == len(set(priorities)), (
            f"Priorities must be distinct, got: {priorities}"
        )

        # Ordering must be: feature 1 < new feature < feature 2
        assert f1["priority"] < fn["priority"] < f2["priority"], (
            f"Expected f1({f1['priority']}) < fn({fn['priority']}) < f2({f2['priority']})"
        )

    def test_reorder_preserves_ordering_with_unique_priorities(self, client):
        """Existing reorder behavior must still work correctly with unique priorities."""
        # Features 1 (prio 1) and 2 (prio 2) are both TODO, move 2 to before 1
        response = client.patch("/api/features/2/reorder", json={
            "target_id": 1,
            "insert_before": True,
        })

        assert response.status_code == 200
        f1 = client.get("/api/features/1").json()
        f2 = client.get("/api/features/2").json()

        # Feature 2 should now come before feature 1
        assert f2["priority"] < f1["priority"]


class TestPagination:
    """Tests for pagination support in GET /api/features"""

    def test_pagination_basic(self, client):
        """Test basic pagination with limit and offset."""
        # Get first 2 features
        response = client.get("/api/features?limit=2&offset=0")

        assert response.status_code == 200
        data = response.json()

        # Should return paginated response format
        assert "features" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data

        assert len(data["features"]) == 2
        assert data["total"] == 4  # Total seeded features
        assert data["limit"] == 2
        assert data["offset"] == 0

    def test_pagination_offset(self, client):
        """Test pagination with offset."""
        # Get next 2 features
        response = client.get("/api/features?limit=2&offset=2")

        assert response.status_code == 200
        data = response.json()

        assert len(data["features"]) == 2
        assert data["total"] == 4
        assert data["offset"] == 2

    def test_pagination_with_filter(self, client):
        """Test pagination combined with filtering."""
        # There are 2 features with passes=False and in_progress=False (todo lane)
        response = client.get("/api/features?passes=false&in_progress=false&limit=10&offset=0")

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 2
        assert len(data["features"]) == 2
        assert all(not f["passes"] and not f["in_progress"] for f in data["features"])

    def test_pagination_done_features_ordered_by_completed_at(self, client):
        """Test that done features are ordered by completed_at DESC."""
        from datetime import datetime, timedelta

        # Mark multiple features as done with different completion times
        # Feature 1 - completed first
        client.patch("/api/features/1/state", json={"passes": True})

        # Wait a bit and complete feature 2
        import time
        time.sleep(0.1)
        client.patch("/api/features/2/state", json={"passes": True})

        # Fetch done features with pagination
        response = client.get("/api/features?passes=true&limit=10&offset=0")

        assert response.status_code == 200
        data = response.json()

        # Feature 2 should come first (most recent completion)
        # Feature 3 was already done in seed, Feature 1 was done first above
        features = data["features"]

        # The order should be: most recently completed first
        # Feature 2 (just completed), then Feature 1 (completed earlier), then Feature 3 (seed data)
        assert features[0]["id"] == 2
        assert features[1]["id"] == 1

    def test_pagination_large_dataset(self, client):
        """Test pagination with a larger dataset."""
        # Create 30 done features
        for i in range(30):
            create_response = client.post("/api/features", json={
                "category": "Testing",
                "name": f"Done Feature {i}",
                "description": f"Test feature {i}",
                "steps": ["Test"]
            })
            feature_id = create_response.json()["id"]

            # Mark as done
            client.patch(f"/api/features/{feature_id}/state", json={"passes": True})

            # Small delay to ensure different timestamps
            if i % 5 == 0:
                import time
                time.sleep(0.01)

        # Fetch first page of done features (limit=20)
        response = client.get("/api/features?passes=true&limit=20&offset=0")

        assert response.status_code == 200
        data = response.json()

        assert len(data["features"]) == 20
        assert data["total"] >= 30  # At least 30 (plus Feature 3 from seed)
        assert data["limit"] == 20
        assert data["offset"] == 0

        # Fetch second page
        response2 = client.get("/api/features?passes=true&limit=20&offset=20")

        assert response2.status_code == 200
        data2 = response2.json()

        # Should have remaining features
        assert len(data2["features"]) >= 10
        assert data2["offset"] == 20

    def test_backward_compatibility_without_pagination(self, client):
        """Test that endpoint still returns list when limit is not provided."""
        response = client.get("/api/features")

        assert response.status_code == 200
        data = response.json()

        # Should return a list (backward compatible), not paginated response
        assert isinstance(data, list)
        assert len(data) == 4


class TestIntegrationScenarios:
    """Integration tests for complex scenarios"""

    def test_full_lifecycle(self, client):
        """Test complete feature lifecycle: create -> update -> move states -> delete."""
        # Create
        create_response = client.post("/api/features", json={
            "category": "Testing",
            "name": "Lifecycle Test",
            "description": "Full lifecycle test",
            "steps": ["Create", "Update", "Move", "Delete"]
        })
        assert create_response.status_code == 201
        feature_id = create_response.json()["id"]

        # Update fields
        update_response = client.put(f"/api/features/{feature_id}", json={
            "name": "Updated Lifecycle Test"
        })
        assert update_response.status_code == 200
        assert update_response.json()["name"] == "Updated Lifecycle Test"

        # Move to in-progress
        in_progress_response = client.patch(f"/api/features/{feature_id}/state", json={
            "in_progress": True
        })
        assert in_progress_response.status_code == 200
        assert in_progress_response.json()["in_progress"] is True

        # Move to done
        done_response = client.patch(f"/api/features/{feature_id}/state", json={
            "passes": True,
            "in_progress": False
        })
        assert done_response.status_code == 200
        assert done_response.json()["passes"] is True
        assert done_response.json()["completed_at"] is not None

        # Delete
        delete_response = client.delete(f"/api/features/{feature_id}")
        assert delete_response.status_code == 204

        # Verify deleted
        get_response = client.get(f"/api/features/{feature_id}")
        assert get_response.status_code == 404

    def test_priority_auto_assignment(self, client):
        """Test that new features get auto-assigned the next priority."""
        # Get current max priority
        features = client.get("/api/features").json()
        max_priority = max(f["priority"] for f in features)

        # Create new feature
        response = client.post("/api/features", json={
            "category": "Testing",
            "name": "Priority Test",
            "description": "Test priority assignment",
            "steps": ["Test"]
        })

        assert response.status_code == 201
        assert response.json()["priority"] == max_priority + 100

    def test_isolation_from_production(self, client):
        """Verify test database is isolated from production."""
        # Test database should only have 4 seeded features
        response = client.get("/api/features")
        assert response.status_code == 200

        # Should only see our test data
        features = response.json()
        assert len(features) == 4
        assert all(f["name"].startswith("Feature ") for f in features)


class TestLaunchClaude:
    """Tests for POST /api/features/{id}/launch-claude"""

    def test_launch_todo_feature(self, client, monkeypatch):
        """Test launching Claude for a TODO feature succeeds."""
        popen_calls = []

        def mock_popen(*args, **kwargs):
            popen_calls.append({"args": args, "kwargs": kwargs})

            class MockProcess:
                pid = 12345

            return MockProcess()

        monkeypatch.setattr(subprocess, "Popen", mock_popen)

        response = client.post("/api/features/1/launch-claude")

        assert response.status_code == 200
        data = response.json()
        assert data["launched"] is True
        assert data["feature_id"] == 1
        assert "Feature #1" in data["prompt"]
        assert "Feature 1" in data["prompt"]
        assert "Backend" in data["prompt"]
        assert "working_directory" in data
        assert len(popen_calls) == 1

    def test_launch_in_progress_feature(self, client, monkeypatch):
        """Test launching Claude for an IN PROGRESS feature succeeds."""
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1})())

        # Feature 4 is in_progress=True, passes=False
        response = client.post("/api/features/4/launch-claude")

        assert response.status_code == 200
        data = response.json()
        assert data["launched"] is True
        assert data["feature_id"] == 4
        assert "Feature #4" in data["prompt"]

    def test_launch_done_feature_fails(self, client, monkeypatch):
        """Test that launching Claude for a completed feature returns 400."""
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1})())

        # Feature 3 is passes=True (done)
        response = client.post("/api/features/3/launch-claude")

        assert response.status_code == 400
        assert "completed" in response.json()["detail"].lower()

    def test_launch_not_found(self, client, monkeypatch):
        """Test launching Claude for a non-existent feature returns 404."""
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1})())

        response = client.post("/api/features/999/launch-claude")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_launch_claude_not_in_path(self, client, monkeypatch):
        """Test that missing claude CLI returns 500 with helpful message."""

        def mock_popen_not_found(*args, **kwargs):
            raise FileNotFoundError("claude not found")

        monkeypatch.setattr(subprocess, "Popen", mock_popen_not_found)

        response = client.post("/api/features/1/launch-claude")

        assert response.status_code == 500
        assert "No PowerShell found" in response.json()["detail"]

    def test_launch_uses_full_access_mode(self, client, monkeypatch):
        """Test that Claude is launched with --dangerously-skip-permissions for full access mode."""
        popen_calls = []

        def mock_popen(*args, **kwargs):
            popen_calls.append({"args": args, "kwargs": kwargs})

            class MockProcess:
                pid = 12345

            return MockProcess()

        monkeypatch.setattr(subprocess, "Popen", mock_popen)

        response = client.post("/api/features/1/launch-claude")

        assert response.status_code == 200
        assert len(popen_calls) == 1

        # Verify --dangerously-skip-permissions is included in the command.
        # On Windows, the command is a list like ['pwsh', '-Command', 'claude --model ... --dangerously-skip-permissions ...']
        # so we check that the flag appears somewhere in the full command string.
        call_args = popen_calls[0]["args"][0]  # First positional arg is the command list/string
        full_command = " ".join(call_args) if isinstance(call_args, list) else str(call_args)
        assert "--dangerously-skip-permissions" in full_command

    def test_prompt_contains_feature_details(self, client, monkeypatch, tmp_path):
        """Test that the generated prompt includes all key feature details."""
        import backend.main as main_module

        # Use a fresh settings file with the default template so description is included
        monkeypatch.setattr(main_module, 'SETTINGS_FILE', tmp_path / "settings.json")
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1})())

        response = client.post("/api/features/1/launch-claude")

        assert response.status_code == 200
        prompt = response.json()["prompt"]
        # Prompt should contain id, category, name, description, and steps
        assert "Feature #1" in prompt
        assert "Backend" in prompt
        assert "Feature 1" in prompt
        assert "Test feature 1" in prompt
        assert "Step 1" in prompt

    def test_launch_uses_print_flag_for_auto_close(self, client, monkeypatch):
        """Test that Claude is launched with --print so the session closes automatically when done."""
        popen_calls = []

        def mock_popen(*args, **kwargs):
            popen_calls.append({"args": args, "kwargs": kwargs})

            class MockProcess:
                pid = 12345

            return MockProcess()

        monkeypatch.setattr(subprocess, "Popen", mock_popen)

        response = client.post("/api/features/1/launch-claude")

        assert response.status_code == 200
        assert len(popen_calls) == 1

        # Verify --print is included so Claude runs non-interactively and exits when done.
        call_args = popen_calls[0]["args"][0]
        full_command = " ".join(call_args) if isinstance(call_args, list) else str(call_args)
        assert "--print" in full_command

    def test_launch_does_not_use_no_exit(self, client, monkeypatch):
        """Test that the PowerShell command does NOT use -NoExit so the window closes when done."""
        popen_calls = []

        def mock_popen(*args, **kwargs):
            popen_calls.append({"args": args, "kwargs": kwargs})

            class MockProcess:
                pid = 12345

            return MockProcess()

        monkeypatch.setattr(subprocess, "Popen", mock_popen)

        response = client.post("/api/features/1/launch-claude")

        assert response.status_code == 200
        assert len(popen_calls) == 1

        # Verify -NoExit is NOT in the command — the window should close automatically.
        call_args = popen_calls[0]["args"][0]
        full_command = " ".join(call_args) if isinstance(call_args, list) else str(call_args)
        assert "-NoExit" not in full_command


class TestLaunchClaudeHiddenExecution:
    """Tests for the hidden_execution option in launch-claude."""

    def _get_full_command(self, popen_calls):
        call_args = popen_calls[0]["args"][0]
        return " ".join(call_args) if isinstance(call_args, list) else str(call_args)

    def test_hidden_execution_true_uses_print_flag(self, client, monkeypatch):
        """Test that hidden_execution=true includes --print flag."""
        popen_calls = []

        def mock_popen(*args, **kwargs):
            popen_calls.append({"args": args, "kwargs": kwargs})
            return type("P", (), {"pid": 1})()

        monkeypatch.setattr(subprocess, "Popen", mock_popen)

        response = client.post("/api/features/1/launch-claude", json={"hidden_execution": True})

        assert response.status_code == 200
        assert response.json()["hidden_execution"] is True
        assert "--print" in self._get_full_command(popen_calls)

    def test_hidden_execution_false_omits_print_flag(self, client, monkeypatch):
        """Test that hidden_execution=false omits the --print flag (interactive mode)."""
        popen_calls = []

        def mock_popen(*args, **kwargs):
            popen_calls.append({"args": args, "kwargs": kwargs})
            return type("P", (), {"pid": 1})()

        monkeypatch.setattr(subprocess, "Popen", mock_popen)

        response = client.post("/api/features/1/launch-claude", json={"hidden_execution": False})

        assert response.status_code == 200
        assert response.json()["hidden_execution"] is False
        assert "--print" not in self._get_full_command(popen_calls)

    def test_hidden_execution_defaults_to_true(self, client, monkeypatch):
        """Test that omitting hidden_execution defaults to True (hidden mode)."""
        popen_calls = []

        def mock_popen(*args, **kwargs):
            popen_calls.append({"args": args, "kwargs": kwargs})
            return type("P", (), {"pid": 1})()

        monkeypatch.setattr(subprocess, "Popen", mock_popen)

        # No request body — should default to hidden_execution=True
        response = client.post("/api/features/1/launch-claude")

        assert response.status_code == 200
        assert response.json()["hidden_execution"] is True
        assert "--print" in self._get_full_command(popen_calls)

    def test_hidden_execution_response_field_present(self, client, monkeypatch):
        """Test that the response always includes hidden_execution field."""
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1})())

        response = client.post("/api/features/1/launch-claude")

        assert response.status_code == 200
        assert "hidden_execution" in response.json()

    def test_interactive_mode_still_uses_dangerously_skip_permissions(self, client, monkeypatch):
        """Test that interactive mode (hidden_execution=false) still uses --dangerously-skip-permissions."""
        popen_calls = []

        def mock_popen(*args, **kwargs):
            popen_calls.append({"args": args, "kwargs": kwargs})
            return type("P", (), {"pid": 1})()

        monkeypatch.setattr(subprocess, "Popen", mock_popen)

        response = client.post("/api/features/1/launch-claude", json={"hidden_execution": False})

        assert response.status_code == 200
        assert "--dangerously-skip-permissions" in self._get_full_command(popen_calls)


# ==============================================================================
# Settings endpoints
# ==============================================================================

def test_get_settings_returns_defaults(client, tmp_path, monkeypatch):
    """GET /api/settings returns default template when no settings.json exists."""
    import backend.main as main_module
    # Point SETTINGS_FILE to a non-existent file in tmp_path
    monkeypatch.setattr(main_module, 'SETTINGS_FILE', tmp_path / "settings_nonexistent.json")

    response = client.get("/api/settings")
    assert response.status_code == 200
    data = response.json()
    assert "claude_prompt_template" in data
    assert len(data["claude_prompt_template"]) > 0


def test_put_settings_saves_and_returns(client, tmp_path, monkeypatch):
    """PUT /api/settings saves settings and returns them."""
    import backend.main as main_module
    settings_file = tmp_path / "test_settings.json"
    monkeypatch.setattr(main_module, 'SETTINGS_FILE', settings_file)

    new_template = "Custom prompt: {name} - {description}"
    response = client.put("/api/settings", json={"claude_prompt_template": new_template})
    assert response.status_code == 200
    data = response.json()
    assert data["claude_prompt_template"] == new_template

    # Verify it was saved to disk
    assert settings_file.exists()
    import json
    saved = json.loads(settings_file.read_text())
    assert saved["claude_prompt_template"] == new_template


def test_get_settings_after_save(client, tmp_path, monkeypatch):
    """GET /api/settings returns previously saved settings."""
    import backend.main as main_module
    settings_file = tmp_path / "test_settings.json"
    monkeypatch.setattr(main_module, 'SETTINGS_FILE', settings_file)

    # Save a custom template
    custom_template = "My custom template {feature_id}"
    client.put("/api/settings", json={"claude_prompt_template": custom_template})

    # Now get and verify
    response = client.get("/api/settings")
    assert response.status_code == 200
    data = response.json()
    assert data["claude_prompt_template"] == custom_template


# ==============================================================================
# Model field tests
# ==============================================================================

class TestModelField:
    """Tests for the optional model field on features."""

    def test_feature_default_model_is_sonnet(self, client):
        """New features default to 'sonnet' model."""
        response = client.get("/api/features/1")
        assert response.status_code == 200
        data = response.json()
        assert data["model"] == "sonnet"

    def test_update_model_to_opus(self, client):
        """Test updating model to opus."""
        response = client.put("/api/features/1", json={"model": "opus"})
        assert response.status_code == 200
        data = response.json()
        assert data["model"] == "opus"

    def test_update_model_to_haiku(self, client):
        """Test updating model to haiku."""
        response = client.put("/api/features/1", json={"model": "haiku"})
        assert response.status_code == 200
        data = response.json()
        assert data["model"] == "haiku"

    def test_update_model_to_sonnet(self, client):
        """Test updating model back to sonnet."""
        # First set to opus
        client.put("/api/features/1", json={"model": "opus"})
        # Then back to sonnet
        response = client.put("/api/features/1", json={"model": "sonnet"})
        assert response.status_code == 200
        data = response.json()
        assert data["model"] == "sonnet"

    def test_update_invalid_model_returns_400(self, client):
        """Test that invalid model value returns 400."""
        response = client.put("/api/features/1", json={"model": "gpt-4"})
        assert response.status_code == 400
        assert "invalid model" in response.json()["detail"].lower()

    def test_update_model_does_not_change_other_fields(self, client):
        """Test that updating model leaves other fields unchanged."""
        response = client.put("/api/features/1", json={"model": "haiku"})
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Feature 1"
        assert data["category"] == "Backend"
        assert data["model"] == "haiku"

    def test_create_feature_has_default_model(self, client):
        """Test that newly created features get 'sonnet' model when not specified."""
        response = client.post("/api/features", json={
            "category": "Testing",
            "name": "Model Test Feature",
            "description": "Test model default",
            "steps": ["Step 1"]
        })
        assert response.status_code == 201
        data = response.json()
        assert data["model"] == "sonnet"

    def test_create_feature_with_opus_model(self, client):
        """Test creating a feature with opus model specified."""
        response = client.post("/api/features", json={
            "category": "Testing",
            "name": "Opus Feature",
            "description": "Test opus model on create",
            "steps": ["Step 1"],
            "model": "opus"
        })
        assert response.status_code == 201
        data = response.json()
        assert data["model"] == "opus"

    def test_create_feature_with_haiku_model(self, client):
        """Test creating a feature with haiku model specified."""
        response = client.post("/api/features", json={
            "category": "Testing",
            "name": "Haiku Feature",
            "description": "Test haiku model on create",
            "steps": ["Step 1"],
            "model": "haiku"
        })
        assert response.status_code == 201
        data = response.json()
        assert data["model"] == "haiku"

    def test_create_feature_invalid_model_returns_400(self, client):
        """Test that creating a feature with an invalid model returns 400."""
        response = client.post("/api/features", json={
            "category": "Testing",
            "name": "Bad Model Feature",
            "description": "Test invalid model on create",
            "steps": ["Step 1"],
            "model": "gpt-4"
        })
        assert response.status_code == 400
        assert "invalid model" in response.json()["detail"].lower()

    def test_model_persists_across_requests(self, client):
        """Test that model value persists after being saved."""
        # Set model to opus
        client.put("/api/features/2", json={"model": "opus"})
        # Fetch and verify
        response = client.get("/api/features/2")
        assert response.status_code == 200
        assert response.json()["model"] == "opus"

    def test_model_included_in_features_list(self, client):
        """Test that model field is included in the features list."""
        response = client.get("/api/features")
        assert response.status_code == 200
        features = response.json()
        for feature in features:
            assert "model" in feature
            assert feature["model"] in ("sonnet", "opus", "haiku")


class TestLaunchClaudeWithModel:
    """Tests for launch-claude respecting the feature model."""

    def test_launch_uses_feature_model_sonnet(self, client, monkeypatch):
        """Test that launch uses the feature's model (sonnet default)."""
        popen_calls = []

        def mock_popen(*args, **kwargs):
            popen_calls.append({"args": args, "kwargs": kwargs})
            return type("P", (), {"pid": 1})()

        monkeypatch.setattr(subprocess, "Popen", mock_popen)

        response = client.post("/api/features/1/launch-claude")
        assert response.status_code == 200
        data = response.json()
        assert data["model"] == "sonnet"
        assert len(popen_calls) == 1

    def test_launch_uses_feature_model_opus(self, client, monkeypatch):
        """Test that launch uses opus when feature model is set to opus."""
        # Set feature model to opus
        client.put("/api/features/1", json={"model": "opus"})

        popen_calls = []

        def mock_popen(*args, **kwargs):
            popen_calls.append({"args": args, "kwargs": kwargs})
            return type("P", (), {"pid": 1})()

        monkeypatch.setattr(subprocess, "Popen", mock_popen)

        response = client.post("/api/features/1/launch-claude")
        assert response.status_code == 200
        data = response.json()
        assert data["model"] == "opus"
        assert len(popen_calls) == 1
        # Verify --model flag is in the command
        call_args = str(popen_calls[0])
        assert "opus" in call_args

    def test_launch_uses_feature_model_haiku(self, client, monkeypatch):
        """Test that launch uses haiku when feature model is set to haiku."""
        client.put("/api/features/1", json={"model": "haiku"})

        popen_calls = []

        def mock_popen(*args, **kwargs):
            popen_calls.append({"args": args, "kwargs": kwargs})
            return type("P", (), {"pid": 1})()

        monkeypatch.setattr(subprocess, "Popen", mock_popen)

        response = client.post("/api/features/1/launch-claude")
        assert response.status_code == 200
        data = response.json()
        assert data["model"] == "haiku"

    def test_launch_response_includes_model(self, client, monkeypatch):
        """Test that launch response always includes the model field."""
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1})())

        response = client.post("/api/features/1/launch-claude")
        assert response.status_code == 200
        data = response.json()
        assert "model" in data


class TestPlanTasks:
    """Tests for POST /api/plan-tasks"""

    def test_valid_description_returns_200_and_launched(self, client, monkeypatch):
        """Test that a valid description returns 200 with launched=True."""
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1})())

        response = client.post("/api/plan-tasks", json={
            "description": "Add dark mode support to the dashboard"
        })

        assert response.status_code == 200
        data = response.json()
        assert data["launched"] is True

    def test_empty_description_returns_400(self, client, monkeypatch):
        """Test that an empty description returns 400."""
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1})())

        response = client.post("/api/plan-tasks", json={"description": ""})

        assert response.status_code == 400
        assert "empty" in response.json()["detail"].lower()

    def test_whitespace_description_returns_400(self, client, monkeypatch):
        """Test that a whitespace-only description is also rejected."""
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1})())

        response = client.post("/api/plan-tasks", json={"description": "   "})

        assert response.status_code == 400

    def test_prompt_contains_user_description(self, client, monkeypatch):
        """Test that the generated prompt embeds the user's description."""
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1})())

        description = "Add user authentication with OAuth"
        response = client.post("/api/plan-tasks", json={"description": description})

        assert response.status_code == 200
        assert description in response.json()["prompt"]

    def test_does_not_use_print_flag(self, client, monkeypatch):
        """Test that plan-tasks launches Claude without --print (interactive mode)."""
        popen_calls = []

        def mock_popen(*args, **kwargs):
            popen_calls.append({"args": args, "kwargs": kwargs})
            return type("P", (), {"pid": 1})()

        monkeypatch.setattr(subprocess, "Popen", mock_popen)

        response = client.post("/api/plan-tasks", json={"description": "Add reporting features"})

        assert response.status_code == 200
        assert len(popen_calls) == 1

        call_args = popen_calls[0]["args"][0]
        full_command = " ".join(call_args) if isinstance(call_args, list) else str(call_args)
        assert "--print" not in full_command

    def test_uses_dangerously_skip_permissions(self, client, monkeypatch):
        """Test that plan-tasks includes --dangerously-skip-permissions."""
        popen_calls = []

        def mock_popen(*args, **kwargs):
            popen_calls.append({"args": args, "kwargs": kwargs})
            return type("P", (), {"pid": 1})()

        monkeypatch.setattr(subprocess, "Popen", mock_popen)

        response = client.post("/api/plan-tasks", json={"description": "Add reporting features"})

        assert response.status_code == 200
        assert len(popen_calls) == 1

        call_args = popen_calls[0]["args"][0]
        full_command = " ".join(call_args) if isinstance(call_args, list) else str(call_args)
        assert "--dangerously-skip-permissions" in full_command

    def test_claude_not_found_returns_500(self, client, monkeypatch):
        """Test that a missing Claude CLI (or PowerShell) returns 500."""
        def mock_popen_not_found(*args, **kwargs):
            raise FileNotFoundError("not found")

        monkeypatch.setattr(subprocess, "Popen", mock_popen_not_found)

        response = client.post("/api/plan-tasks", json={"description": "Add reporting features"})

        assert response.status_code == 500

    def test_response_includes_prompt_and_working_directory(self, client, monkeypatch):
        """Test that the response always includes prompt and working_directory."""
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1})())

        response = client.post("/api/plan-tasks", json={"description": "Add dark mode"})

        assert response.status_code == 200
        data = response.json()
        assert "prompt" in data
        assert len(data["prompt"]) > 0
        assert "working_directory" in data
        assert len(data["working_directory"]) > 0

    def test_missing_description_field_returns_422(self, client, monkeypatch):
        """Test that omitting description entirely returns 422 validation error."""
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1})())

        response = client.post("/api/plan-tasks", json={})

        assert response.status_code == 422


class TestGetNextAutopilotFeature:
    """Unit tests for get_next_autopilot_feature(session) sequencer function."""

    def test_in_progress_returned_before_todo(self, test_db):
        """In-progress features are returned before TODO features regardless of priority."""
        from backend.main import get_next_autopilot_feature

        # Seed DB has: feature 1 (todo, prio 100), feature 2 (todo, prio 200),
        #              feature 3 (done, prio 300), feature 4 (in_progress, prio 400)
        # Feature 4 has higher priority number but is in_progress, so it wins
        session = test_db()
        try:
            result = get_next_autopilot_feature(session)
            assert result is not None
            assert result.id == 4
            assert result.in_progress is True
        finally:
            session.close()

    def test_todo_features_ordered_by_priority(self, test_db):
        """When no in-progress features exist, lowest priority number is returned first."""
        from backend.main import get_next_autopilot_feature
        from api.database import Feature

        # Clear in_progress on feature 4 so only TODO features remain
        session = test_db()
        try:
            f4 = session.query(Feature).filter(Feature.id == 4).first()
            f4.in_progress = False
            session.commit()

            result = get_next_autopilot_feature(session)
            assert result is not None
            # Feature 1 has priority 100, feature 2 has priority 200 — pick lowest
            assert result.id == 1
            assert result.priority == 100
        finally:
            session.close()

    def test_in_progress_features_ordered_by_priority_among_themselves(self, test_db):
        """When multiple in-progress features exist, the one with the lowest priority is picked."""
        from backend.main import get_next_autopilot_feature
        from api.database import Feature

        # Mark feature 1 (prio 100) as in_progress too — lower priority number than feature 4 (400)
        session = test_db()
        try:
            f1 = session.query(Feature).filter(Feature.id == 1).first()
            f1.in_progress = True
            session.commit()

            result = get_next_autopilot_feature(session)
            assert result is not None
            # Feature 1 has priority 100 < feature 4 priority 400
            assert result.id == 1
        finally:
            session.close()

    def test_returns_none_when_all_features_are_passing(self, test_db):
        """Returns None when no in-progress or TODO features remain."""
        from backend.main import get_next_autopilot_feature
        from api.database import Feature

        session = test_db()
        try:
            # Mark all non-done features as done
            for fid in [1, 2, 4]:
                f = session.query(Feature).filter(Feature.id == fid).first()
                f.passes = True
                f.in_progress = False
            session.commit()

            result = get_next_autopilot_feature(session)
            assert result is None
        finally:
            session.close()

    def test_returns_none_when_database_is_empty(self, test_db):
        """Returns None when there are no features at all."""
        from backend.main import get_next_autopilot_feature
        from api.database import Feature

        session = test_db()
        try:
            session.query(Feature).delete()
            session.commit()

            result = get_next_autopilot_feature(session)
            assert result is None
        finally:
            session.close()

    def test_skips_passing_in_progress_edge_case(self, test_db):
        """A feature with both passes=True and in_progress=True is not returned."""
        from backend.main import get_next_autopilot_feature
        from api.database import Feature

        session = test_db()
        try:
            # Force feature 4 into a passes=True, in_progress=True edge state
            f4 = session.query(Feature).filter(Feature.id == 4).first()
            f4.passes = True
            # in_progress stays True
            session.commit()

            result = get_next_autopilot_feature(session)
            assert result is not None
            # Should fall through to TODO features (1 or 2), not pick the passing feature 4
            assert result.passes is False
            assert result.id in (1, 2)
        finally:
            session.close()


class TestAutoPilotEnable:
    """Tests for POST /api/autopilot/enable"""

    def _reset_autopilot_state(self, monkeypatch):
        """Reset autopilot state dict to isolate tests from each other."""
        import backend.main as main_module
        monkeypatch.setattr(main_module, '_autopilot_states', {})

    def _get_full_command(self, popen_calls):
        call_args = popen_calls[0]["args"][0]
        return " ".join(call_args) if isinstance(call_args, list) else str(call_args)

    def test_enable_returns_200_with_todo_feature(self, client, monkeypatch):
        """Test that enabling autopilot returns 200 with enabled=True when TODO features exist."""
        self._reset_autopilot_state(monkeypatch)
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1})())

        response = client.post("/api/autopilot/enable")

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True
        assert data["current_feature_id"] is not None

    def test_enable_picks_in_progress_feature_first(self, client, monkeypatch):
        """Test that autopilot picks in-progress features before TODO features."""
        self._reset_autopilot_state(monkeypatch)
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1})())

        # Test DB has feature 4 as in_progress=True, passes=False
        response = client.post("/api/autopilot/enable")

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True
        # Feature 4 is in_progress, so it should be selected over TODO features 1/2
        assert data["current_feature_id"] == 4

    def test_enable_picks_todo_by_priority_when_no_in_progress(self, client, monkeypatch):
        """Test that autopilot picks the highest priority TODO when no in-progress feature exists."""
        self._reset_autopilot_state(monkeypatch)
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1})())

        # Move feature 4 out of in_progress state
        client.patch("/api/features/4/state", json={"in_progress": False})

        response = client.post("/api/autopilot/enable")

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True
        # Feature 1 has priority 100 (lowest = highest priority), feature 2 has 200
        assert data["current_feature_id"] == 1

    def test_enable_spawns_claude_process(self, client, monkeypatch):
        """Test that enabling autopilot spawns exactly one Claude process."""
        self._reset_autopilot_state(monkeypatch)
        popen_calls = []

        def mock_popen(*args, **kwargs):
            popen_calls.append({"args": args, "kwargs": kwargs})
            return type("P", (), {"pid": 1})()

        monkeypatch.setattr(subprocess, "Popen", mock_popen)

        response = client.post("/api/autopilot/enable")

        assert response.status_code == 200
        assert len(popen_calls) == 1

    def test_enable_uses_print_flag_for_hidden_execution(self, client, monkeypatch):
        """Test that autopilot launches Claude with --print (hidden execution)."""
        self._reset_autopilot_state(monkeypatch)
        popen_calls = []

        def mock_popen(*args, **kwargs):
            popen_calls.append({"args": args, "kwargs": kwargs})
            return type("P", (), {"pid": 1})()

        monkeypatch.setattr(subprocess, "Popen", mock_popen)

        response = client.post("/api/autopilot/enable")

        assert response.status_code == 200
        assert len(popen_calls) == 1
        full_command = self._get_full_command(popen_calls)
        assert "--print" in full_command

    def test_enable_uses_dangerously_skip_permissions(self, client, monkeypatch):
        """Test that autopilot launches Claude with --dangerously-skip-permissions."""
        self._reset_autopilot_state(monkeypatch)
        popen_calls = []

        def mock_popen(*args, **kwargs):
            popen_calls.append({"args": args, "kwargs": kwargs})
            return type("P", (), {"pid": 1})()

        monkeypatch.setattr(subprocess, "Popen", mock_popen)

        response = client.post("/api/autopilot/enable")

        assert response.status_code == 200
        full_command = self._get_full_command(popen_calls)
        assert "--dangerously-skip-permissions" in full_command

    def test_enable_returns_log_entries(self, client, monkeypatch):
        """Test that the response includes non-empty log entries."""
        self._reset_autopilot_state(monkeypatch)
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1})())

        response = client.post("/api/autopilot/enable")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["log"], list)
        assert len(data["log"]) > 0

    def test_enable_when_already_enabled_returns_409(self, client, monkeypatch):
        """Test that enabling autopilot when already enabled returns 409."""
        self._reset_autopilot_state(monkeypatch)
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1})())

        # Enable once
        first = client.post("/api/autopilot/enable")
        assert first.status_code == 200

        # Try to enable again — should get 409
        second = client.post("/api/autopilot/enable")
        assert second.status_code == 409
        assert "already enabled" in second.json()["detail"].lower()

    def test_enable_with_no_tasks_returns_disabled(self, client, monkeypatch):
        """Test that autopilot returns enabled=False with message when no tasks available."""
        self._reset_autopilot_state(monkeypatch)
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1})())

        # Mark all non-done features as done so no tasks remain
        for fid in [1, 2, 4]:
            client.patch(f"/api/features/{fid}/state", json={"passes": True})

        response = client.post("/api/autopilot/enable")

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False
        assert data["current_feature_id"] is None
        assert any("no tasks" in entry["message"].lower() for entry in data["log"])

    def test_enable_with_no_tasks_does_not_spawn_process(self, client, monkeypatch):
        """Test that no Claude process is spawned when no tasks are available."""
        self._reset_autopilot_state(monkeypatch)
        popen_calls = []

        def mock_popen(*args, **kwargs):
            popen_calls.append({"args": args, "kwargs": kwargs})
            return type("P", (), {"pid": 1})()

        monkeypatch.setattr(subprocess, "Popen", mock_popen)

        # Mark all non-done features as done
        for fid in [1, 2, 4]:
            client.patch(f"/api/features/{fid}/state", json={"passes": True})

        response = client.post("/api/autopilot/enable")

        assert response.status_code == 200
        assert len(popen_calls) == 0

    def test_enable_claude_not_found_returns_500(self, client, monkeypatch):
        """Test that a missing Claude CLI returns 500 and disables autopilot."""
        self._reset_autopilot_state(monkeypatch)

        def mock_popen_not_found(*args, **kwargs):
            raise FileNotFoundError("claude not found")

        monkeypatch.setattr(subprocess, "Popen", mock_popen_not_found)

        response = client.post("/api/autopilot/enable")

        assert response.status_code == 500

    def test_enable_response_fields_present(self, client, monkeypatch):
        """Test that response always includes enabled, current_feature_id, and log."""
        self._reset_autopilot_state(monkeypatch)
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1})())

        response = client.post("/api/autopilot/enable")

        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data
        assert "current_feature_id" in data
        assert "log" in data

    def test_enable_log_contains_feature_name(self, client, monkeypatch):
        """Test that the log mentions the selected feature."""
        self._reset_autopilot_state(monkeypatch)
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1})())

        response = client.post("/api/autopilot/enable")

        assert response.status_code == 200
        data = response.json()
        log_text = " ".join(entry["message"] for entry in data["log"])
        # Should mention the feature ID
        assert str(data["current_feature_id"]) in log_text


class TestAutoPilotDisable:
    """Tests for POST /api/autopilot/disable"""

    def _reset_autopilot_state(self, monkeypatch):
        """Reset autopilot state dict to isolate tests from each other."""
        import backend.main as main_module
        monkeypatch.setattr(main_module, '_autopilot_states', {})

    def test_disable_when_not_enabled_returns_200(self, client, monkeypatch):
        """Test that disabling when already disabled is idempotent and returns 200."""
        self._reset_autopilot_state(monkeypatch)

        response = client.post("/api/autopilot/disable")

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False

    def test_disable_after_enable_returns_200(self, client, monkeypatch):
        """Test that disabling after enabling returns 200 with enabled=False."""
        self._reset_autopilot_state(monkeypatch)
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1, "terminate": lambda self: None})())

        client.post("/api/autopilot/enable")

        response = client.post("/api/autopilot/disable")

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False

    def test_disable_sets_current_feature_id_to_none(self, client, monkeypatch):
        """Test that disabling clears current_feature_id."""
        self._reset_autopilot_state(monkeypatch)
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1, "terminate": lambda self: None})())

        enable_resp = client.post("/api/autopilot/enable")
        assert enable_resp.json()["current_feature_id"] is not None

        disable_resp = client.post("/api/autopilot/disable")
        assert disable_resp.json()["current_feature_id"] is None

    def test_disable_appends_manually_disabled_log_entry(self, client, monkeypatch):
        """Test that disable appends the 'manually disabled' log entry."""
        self._reset_autopilot_state(monkeypatch)

        response = client.post("/api/autopilot/disable")

        assert response.status_code == 200
        data = response.json()
        assert any("manually disabled" in entry["message"].lower() for entry in data["log"])

    def test_disable_terminates_active_process(self, client, monkeypatch):
        """Test that disable calls terminate() on the active process."""
        self._reset_autopilot_state(monkeypatch)
        terminate_calls = []

        class MockProcess:
            pid = 12345

            def terminate(self):
                terminate_calls.append(True)

        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: MockProcess())

        client.post("/api/autopilot/enable")
        assert len(terminate_calls) == 0

        client.post("/api/autopilot/disable")
        assert len(terminate_calls) == 1

    def test_disable_handles_already_exited_process_gracefully(self, client, monkeypatch):
        """Test that disable does not raise if process.terminate() fails (already exited)."""
        self._reset_autopilot_state(monkeypatch)

        class MockProcessAlreadyDead:
            pid = 99999

            def terminate(self):
                raise OSError("No such process")

        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: MockProcessAlreadyDead())

        client.post("/api/autopilot/enable")

        # Should not raise — disable handles the exception gracefully
        response = client.post("/api/autopilot/disable")
        assert response.status_code == 200
        assert response.json()["enabled"] is False

    def test_disable_when_no_process_does_not_terminate(self, client, monkeypatch):
        """Test that disabling when no process is running does not call terminate."""
        self._reset_autopilot_state(monkeypatch)
        terminate_calls = []

        class MockProcess:
            pid = 1

            def terminate(self):
                terminate_calls.append(True)

        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: MockProcess())

        # Disable without ever enabling — no process was spawned
        response = client.post("/api/autopilot/disable")
        assert response.status_code == 200
        assert len(terminate_calls) == 0

    def test_disable_is_idempotent_multiple_calls(self, client, monkeypatch):
        """Test that calling disable multiple times always returns 200 with enabled=False."""
        self._reset_autopilot_state(monkeypatch)
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1, "terminate": lambda self: None})())

        client.post("/api/autopilot/enable")

        for _ in range(3):
            response = client.post("/api/autopilot/disable")
            assert response.status_code == 200
            assert response.json()["enabled"] is False

    def test_disable_response_fields_present(self, client, monkeypatch):
        """Test that response always includes enabled, current_feature_id, and log."""
        self._reset_autopilot_state(monkeypatch)

        response = client.post("/api/autopilot/disable")

        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data
        assert "current_feature_id" in data
        assert "log" in data

    def test_re_enable_after_disable_works(self, client, monkeypatch):
        """Test that autopilot can be re-enabled after being disabled."""
        self._reset_autopilot_state(monkeypatch)
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1, "terminate": lambda self: None})())

        client.post("/api/autopilot/enable")
        client.post("/api/autopilot/disable")

        # Should be able to enable again
        response = client.post("/api/autopilot/enable")
        assert response.status_code == 200
        assert response.json()["enabled"] is True


class TestAutoPilotStatus:
    """Tests for GET /api/autopilot/status"""

    def _reset_autopilot_state(self, monkeypatch):
        """Reset autopilot state dict to isolate tests from each other."""
        import backend.main as main_module
        monkeypatch.setattr(main_module, '_autopilot_states', {})

    def test_status_returns_200_with_correct_shape_when_disabled(self, client, monkeypatch):
        """Test: GET returns 200 with correct shape when autopilot is disabled."""
        self._reset_autopilot_state(monkeypatch)

        response = client.get("/api/autopilot/status")

        assert response.status_code == 200
        data = response.json()

        # Required fields present
        assert "enabled" in data
        assert "current_feature_id" in data
        assert "current_feature_name" in data
        assert "last_error" in data
        assert "log" in data

        # Correct values when disabled
        assert data["enabled"] is False
        assert data["current_feature_id"] is None
        assert data["current_feature_name"] is None
        assert data["last_error"] is None
        assert isinstance(data["log"], list)

    def test_status_log_entries_have_correct_shape(self, client, monkeypatch):
        """Test that log entries contain timestamp, level, and message fields."""
        self._reset_autopilot_state(monkeypatch)

        # Trigger a disable so there's at least one log entry
        client.post("/api/autopilot/disable")

        response = client.get("/api/autopilot/status")

        assert response.status_code == 200
        data = response.json()
        assert len(data["log"]) > 0

        entry = data["log"][0]
        assert "timestamp" in entry
        assert "level" in entry
        assert "message" in entry
        # timestamp is a non-empty ISO string
        assert len(entry["timestamp"]) > 0
        # level is one of the valid values
        assert entry["level"] in ("info", "success", "error")
        # message is a non-empty string
        assert len(entry["message"]) > 0

    def test_status_returns_correct_current_feature_id_when_enabled_and_running(self, client, monkeypatch):
        """Test: GET returns correct current_feature_id when autopilot is enabled and running."""
        self._reset_autopilot_state(monkeypatch)
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1})())

        # Enable autopilot — test DB has feature 4 as in_progress so it's selected first
        enable_resp = client.post("/api/autopilot/enable")
        assert enable_resp.status_code == 200
        expected_feature_id = enable_resp.json()["current_feature_id"]
        expected_feature_name = enable_resp.json()["current_feature_name"]

        # Now poll status
        response = client.get("/api/autopilot/status")

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True
        assert data["current_feature_id"] == expected_feature_id
        assert data["current_feature_name"] == expected_feature_name
        assert data["last_error"] is None

    def test_status_returns_enabled_false_after_disable(self, client, monkeypatch):
        """Test that status reflects disabled state after calling disable."""
        self._reset_autopilot_state(monkeypatch)
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1, "terminate": lambda self: None})())

        client.post("/api/autopilot/enable")
        client.post("/api/autopilot/disable")

        response = client.get("/api/autopilot/status")

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False
        assert data["current_feature_id"] is None
        assert data["current_feature_name"] is None

    def test_status_log_accumulates_across_enable_disable(self, client, monkeypatch):
        """Test that the log accumulates entries across enable and disable calls."""
        self._reset_autopilot_state(monkeypatch)
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1, "terminate": lambda self: None})())

        client.post("/api/autopilot/enable")
        client.post("/api/autopilot/disable")

        response = client.get("/api/autopilot/status")

        assert response.status_code == 200
        data = response.json()
        # Should have entries from both enable (>= 3) and disable (1 more)
        assert len(data["log"]) >= 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
