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
            Feature(id=1, priority=1, category="Backend", name="Feature 1",
                   description="Test feature 1", steps=["Step 1"], passes=False, in_progress=False),
            Feature(id=2, priority=2, category="Backend", name="Feature 2",
                   description="Test feature 2", steps=["Step 1"], passes=False, in_progress=False),
            Feature(id=3, priority=3, category="Frontend", name="Feature 3",
                   description="Test feature 3", steps=["Step 1"], passes=True, in_progress=False),
            Feature(id=4, priority=4, category="Frontend", name="Feature 4",
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
        assert data["priority"] == 5  # Next available priority
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
        # Feature 2 (priority 2) should swap with Feature 1 (priority 1)
        response = client.patch("/api/features/2/move", json={
            "direction": "up"
        })

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 2
        assert data["priority"] == 1

        # Verify the other feature was also updated
        feature_1 = client.get("/api/features/1").json()
        assert feature_1["priority"] == 2

    def test_move_down_success(self, client):
        """Test moving feature down within its lane."""
        # Feature 1 (priority 1) should swap with Feature 2 (priority 2)
        response = client.patch("/api/features/1/move", json={
            "direction": "down"
        })

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["priority"] == 2

        # Verify the other feature was also updated
        feature_2 = client.get("/api/features/2").json()
        assert feature_2["priority"] == 1

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
        assert response.json()["priority"] == 2

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
        assert response.json()["priority"] == max_priority + 1

    def test_isolation_from_production(self, client):
        """Verify test database is isolated from production."""
        # Test database should only have 4 seeded features
        response = client.get("/api/features")
        assert response.status_code == 200

        # Should only see our test data
        features = response.json()
        assert len(features) == 4
        assert all(f["name"].startswith("Feature ") for f in features)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
