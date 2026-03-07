import subprocess
import sys
import tempfile
import shutil
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.main import app
from api.database import CategoryToken, create_database, DescriptionBigram, DescriptionToken, Feature, NameBigram, NameToken


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

    def test_create_feature_populates_name_tokens(self, client):
        """Creating a feature inserts tokens from its name into name_tokens."""
        import backend.main as main_module
        import backend.deps as deps_module

        response = client.post("/api/features", json={
            "category": "Testing",
            "name": "Token Alpha Beta",
            "description": "Token test",
            "steps": ["Step 1"],
        })
        assert response.status_code == 201

        session = main_module.get_session()
        try:
            tokens = {row.token: row.usage_count for row in session.query(NameToken).all()}
        finally:
            session.close()

        assert "token" in tokens
        assert "alpha" in tokens
        assert "beta" in tokens
        assert tokens["token"] >= 1
        assert tokens["alpha"] >= 1
        assert tokens["beta"] >= 1

    def test_create_feature_increments_name_tokens_on_repeated_create(self, client):
        """Creating two features with a shared token increments usage_count for that token."""
        import backend.main as main_module
        import backend.deps as deps_module

        client.post("/api/features", json={
            "category": "Testing",
            "name": "Shared Token First",
            "description": "d",
            "steps": ["s"],
        })
        client.post("/api/features", json={
            "category": "Testing",
            "name": "Shared Token Second",
            "description": "d",
            "steps": ["s"],
        })

        session = main_module.get_session()
        try:
            row = session.query(NameToken).filter(NameToken.token == "shared").first()
        finally:
            session.close()

        assert row is not None
        assert row.usage_count == 2


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

    def test_update_feature_name_populates_name_tokens(self, client):
        """Updating a feature's name inserts tokens from the new name into name_tokens."""
        import backend.main as main_module
        import backend.deps as deps_module

        response = client.put("/api/features/1", json={
            "name": "Updated Gamma Delta"
        })
        assert response.status_code == 200

        session = main_module.get_session()
        try:
            tokens = {row.token: row.usage_count for row in session.query(NameToken).all()}
        finally:
            session.close()

        assert "updated" in tokens
        assert "gamma" in tokens
        assert "delta" in tokens
        assert tokens["updated"] >= 1
        assert tokens["gamma"] >= 1
        assert tokens["delta"] >= 1

    def test_update_feature_name_does_not_decrement_old_tokens(self, client):
        """Old tokens from the previous name are not decremented when name is updated (append-only)."""
        import backend.main as main_module
        import backend.deps as deps_module

        # Seed a known token by creating a feature with a unique name
        client.post("/api/features", json={
            "category": "Testing",
            "name": "Unique OldToken Name",
            "description": "Token retention test",
            "steps": ["s"],
        })

        session = main_module.get_session()
        try:
            old_row = session.query(NameToken).filter(NameToken.token == "oldtoken").first()
            old_count = old_row.usage_count if old_row else 0
        finally:
            session.close()

        assert old_count >= 1

        # Now update that feature's name to something without "oldtoken"
        response = client.get("/api/features")
        feature_id = response.json()[-1]["id"]

        client.put(f"/api/features/{feature_id}", json={"name": "Brand New Different Name"})

        session = main_module.get_session()
        try:
            updated_row = session.query(NameToken).filter(NameToken.token == "oldtoken").first()
            new_count = updated_row.usage_count if updated_row else 0
        finally:
            session.close()

        # usage_count must not have decreased
        assert new_count == old_count

    def test_update_feature_without_name_does_not_touch_name_tokens(self, client):
        """Updating fields other than name does not modify name_tokens."""
        import backend.main as main_module
        import backend.deps as deps_module

        # Capture current token state
        session = main_module.get_session()
        try:
            before = {row.token: row.usage_count for row in session.query(NameToken).all()}
        finally:
            session.close()

        # Update description only (no name change)
        response = client.put("/api/features/1", json={"description": "Updated description only"})
        assert response.status_code == 200

        session = main_module.get_session()
        try:
            after = {row.token: row.usage_count for row in session.query(NameToken).all()}
        finally:
            session.close()

        assert before == after

    def test_update_feature_description_populates_description_tokens(self, client):
        """Updating a feature's description inserts tokens from the new description into description_tokens."""
        import backend.main as main_module
        import backend.deps as deps_module

        response = client.put("/api/features/1", json={
            "description": "Zephyr Quartz Vortex updated description"
        })
        assert response.status_code == 200

        session = main_module.get_session()
        try:
            tokens = {row.token: row.usage_count for row in session.query(DescriptionToken).all()}
        finally:
            session.close()

        assert "zephyr" in tokens
        assert "quartz" in tokens
        assert "vortex" in tokens
        assert tokens["zephyr"] >= 1
        assert tokens["quartz"] >= 1
        assert tokens["vortex"] >= 1

    def test_update_feature_description_does_not_decrement_old_tokens(self, client):
        """Old tokens from the previous description are not decremented when description is updated (append-only)."""
        import backend.main as main_module
        import backend.deps as deps_module

        # Seed a known token by creating a feature with a unique description
        client.post("/api/features", json={
            "category": "Testing",
            "name": "Retention Test Feature",
            "description": "Unique OldDescToken retention test",
            "steps": ["s"],
        })

        session = main_module.get_session()
        try:
            old_row = session.query(DescriptionToken).filter(DescriptionToken.token == "olddesctoken").first()
            old_count = old_row.usage_count if old_row else 0
        finally:
            session.close()

        assert old_count >= 1

        # Now update that feature's description to something without "olddesctoken"
        response = client.get("/api/features")
        feature_id = response.json()[-1]["id"]

        client.put(f"/api/features/{feature_id}", json={"description": "Brand new different description text"})

        session = main_module.get_session()
        try:
            updated_row = session.query(DescriptionToken).filter(DescriptionToken.token == "olddesctoken").first()
            new_count = updated_row.usage_count if updated_row else 0
        finally:
            session.close()

        # usage_count must not have decreased
        assert new_count == old_count

    def test_update_feature_without_description_does_not_touch_description_tokens(self, client):
        """Updating fields other than description does not modify description_tokens."""
        import backend.main as main_module
        import backend.deps as deps_module

        # Capture current description_tokens state
        session = main_module.get_session()
        try:
            before = {row.token: row.usage_count for row in session.query(DescriptionToken).all()}
        finally:
            session.close()

        # Update name only (no description change)
        response = client.put("/api/features/1", json={"name": "Only Name Updated Here"})
        assert response.status_code == 200

        session = main_module.get_session()
        try:
            after = {row.token: row.usage_count for row in session.query(DescriptionToken).all()}
        finally:
            session.close()

        assert before == after

    def test_create_feature_populates_description_tokens(self, client):
        """Creating a feature inserts tokens from its description into description_tokens."""
        import backend.main as main_module
        import backend.deps as deps_module

        response = client.post("/api/features", json={
            "category": "Testing",
            "name": "Desc Token Feature",
            "description": "unique descriptor phrase here",
            "steps": ["step"],
        })

        assert response.status_code == 201

        session = main_module.get_session()
        try:
            tokens = {row.token: row.usage_count for row in session.query(DescriptionToken).all()}
        finally:
            session.close()

        assert "unique" in tokens
        assert "descriptor" in tokens
        assert "phrase" in tokens
        assert tokens["unique"] >= 1
        assert tokens["descriptor"] >= 1
        assert tokens["phrase"] >= 1

    def test_create_feature_increments_description_tokens_on_repeated_create(self, client):
        """Creating two features with a shared description token increments usage_count."""
        import backend.main as main_module
        import backend.deps as deps_module

        client.post("/api/features", json={
            "category": "Testing",
            "name": "First Feature",
            "description": "sharedword in this description",
            "steps": ["step"],
        })
        client.post("/api/features", json={
            "category": "Testing",
            "name": "Second Feature",
            "description": "sharedword appears again here",
            "steps": ["step"],
        })

        session = main_module.get_session()
        try:
            row = session.query(DescriptionToken).filter(DescriptionToken.token == "sharedword").first()
        finally:
            session.close()

        assert row is not None
        assert row.usage_count >= 2

    def test_create_feature_with_duplicate_words_in_description_succeeds(self, client):
        """Creating a feature whose description contains a repeated word must not raise a
        UNIQUE constraint error. Regression test for the autoflush=False + duplicate token bug."""
        response = client.post("/api/features", json={
            "category": "Testing",
            "name": "Duplicate Word Feature",
            "description": "above and somehow above it reacts very above somehow",
            "steps": ["step"],
        })
        assert response.status_code == 201

    def test_create_feature_with_duplicate_words_in_name_succeeds(self, client):
        """Creating a feature whose name contains a repeated word must not raise a
        UNIQUE constraint error. Regression test for the same autoflush=False issue."""
        response = client.post("/api/features", json={
            "category": "Testing",
            "name": "test test feature",
            "description": "Some description",
            "steps": ["step"],
        })
        assert response.status_code == 201

    def test_update_feature_with_duplicate_words_in_description_succeeds(self, client):
        """Updating a feature description with repeated words must not raise UNIQUE constraint."""
        response = client.put("/api/features/1", json={
            "description": "very very complicated issue above above the normal range",
        })
        assert response.status_code == 200


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
        """Test that new features get auto-assigned priority based on active (non-passing) features."""
        # Get max priority among active (passes=False) features only
        features = client.get("/api/features").json()
        active_features = [f for f in features if not f["passes"]]
        max_active_priority = max(f["priority"] for f in active_features)

        # Create new feature
        response = client.post("/api/features", json={
            "category": "Testing",
            "name": "Priority Test",
            "description": "Test priority assignment",
            "steps": ["Test"]
        })

        assert response.status_code == 201
        assert response.json()["priority"] == max_active_priority + 100

    def test_priority_ignores_completed_features(self, client):
        """Test that completed features with high priorities don't affect new feature priority."""
        # Mark the highest-priority active feature (priority=400) as passing
        client.patch("/api/features/4/state", json={"passes": True})

        # Now mark Feature 3 (priority=300, currently passing) - highest active is Feature 2 (200)
        # Active features: Feature 1 (100), Feature 2 (200), (Feature 4 is now passing at 400)
        # Max active priority should now be 200
        features = client.get("/api/features").json()
        active_features = [f for f in features if not f["passes"]]
        max_active_priority = max(f["priority"] for f in active_features)
        assert max_active_priority == 200  # Feature 4 is now passing, so max active is 200

        # Create a new feature - it should be based on active max (200), not the passing max (400)
        response = client.post("/api/features", json={
            "category": "Testing",
            "name": "Priority Ignores Completed",
            "description": "Verify completed features don't inflate new feature priority",
            "steps": ["Test"]
        })

        assert response.status_code == 201
        # Should be 200 + 100 = 300, not 400 + 100 = 500
        assert response.json()["priority"] == 300

    def test_isolation_from_production(self, client):
        """Verify test database is isolated from production."""
        # Test database should only have 4 seeded features
        response = client.get("/api/features")
        assert response.status_code == 200

        # Should only see our test data
        features = response.json()
        assert len(features) == 4
        assert all(f["name"].startswith("Feature ") for f in features)



class TestRecentLog:
    """Tests for recent_log field in feature responses (Feature #148)."""

    def test_feature_without_comments_has_null_recent_log(self, client):
        """A feature with no comments should return recent_log=null."""
        response = client.get("/api/features/1")
        assert response.status_code == 200
        data = response.json()
        assert "recent_log" in data
        assert data["recent_log"] is None

    def test_feature_with_comment_returns_recent_log(self, client):
        """A feature with at least one comment should return its content as recent_log."""
        # Add a comment to feature 1
        comment_res = client.post("/api/features/1/comments", json={"content": "First log entry"})
        assert comment_res.status_code == 201

        response = client.get("/api/features/1")
        assert response.status_code == 200
        data = response.json()
        assert data["recent_log"] == "First log entry"

    def test_recent_log_is_the_latest_comment(self, client):
        """When multiple comments exist, recent_log should be the most recent one."""
        client.post("/api/features/2/comments", json={"content": "Older entry"})
        client.post("/api/features/2/comments", json={"content": "Newer entry"})

        response = client.get("/api/features/2")
        assert response.status_code == 200
        data = response.json()
        assert data["recent_log"] == "Newer entry"

    def test_list_endpoint_includes_recent_log(self, client):
        """GET /api/features should include recent_log for each feature."""
        # Add a comment to feature 3
        client.post("/api/features/3/comments", json={"content": "Progress note"})

        response = client.get("/api/features")
        assert response.status_code == 200
        features = response.json()

        feature3 = next(f for f in features if f["id"] == 3)
        assert feature3["recent_log"] == "Progress note"

        # Features without comments should have null recent_log
        feature4 = next(f for f in features if f["id"] == 4)
        assert feature4["recent_log"] is None

    def test_recent_log_updates_after_new_comment(self, client):
        """Adding a new comment should update recent_log on next fetch."""
        client.post("/api/features/1/comments", json={"content": "Initial log"})
        r1 = client.get("/api/features/1")
        assert r1.json()["recent_log"] == "Initial log"

        client.post("/api/features/1/comments", json={"content": "Updated log"})
        r2 = client.get("/api/features/1")
        assert r2.json()["recent_log"] == "Updated log"

