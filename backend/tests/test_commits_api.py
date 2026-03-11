"""
Integration tests for feature commits endpoints.

Tests GET/POST/DELETE /api/features/{id}/commits.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.main import app


class TestGetCommits:
    """GET /api/features/{id}/commits"""

    def test_returns_empty_list_when_no_commits(self, client):
        """Feature with no commits returns an empty list."""
        response = client.get("/api/features/1/commits")
        assert response.status_code == 200
        assert response.json() == []

    def test_returns_404_for_unknown_feature(self, client):
        """Returns 404 when the feature does not exist."""
        response = client.get("/api/features/999/commits")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_returns_commits_after_adding(self, client):
        """Commits added to a feature appear in the list."""
        client.post("/api/features/1/commits", json={"commit_hash": "abc1234"})
        response = client.get("/api/features/1/commits")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["commit_hash"] == "abc1234"
        assert data[0]["feature_id"] == 1

    def test_returns_commits_ordered_by_created_at(self, client):
        """Commits are returned oldest-first."""
        client.post("/api/features/1/commits", json={"commit_hash": "aaaaaaa"})
        client.post("/api/features/1/commits", json={"commit_hash": "bbbbbbb"})
        client.post("/api/features/1/commits", json={"commit_hash": "ccccccc"})

        response = client.get("/api/features/1/commits")
        assert response.status_code == 200
        hashes = [c["commit_hash"] for c in response.json()]
        assert hashes == ["aaaaaaa", "bbbbbbb", "ccccccc"]


class TestAddCommit:
    """POST /api/features/{id}/commits"""

    def test_adds_commit_and_returns_201(self, client):
        """POST creates a commit record and returns 201 with FeatureCommitResponse."""
        response = client.post("/api/features/1/commits", json={"commit_hash": "deadbeef"})
        assert response.status_code == 201
        data = response.json()
        assert data["commit_hash"] == "deadbeef"
        assert data["feature_id"] == 1
        assert "id" in data
        assert "created_at" in data

    def test_strips_whitespace_from_hash(self, client):
        """Leading/trailing whitespace is stripped from the commit hash."""
        response = client.post("/api/features/1/commits", json={"commit_hash": "  abc123  "})
        assert response.status_code == 201
        assert response.json()["commit_hash"] == "abc123"

    def test_rejects_empty_hash(self, client):
        """Empty or whitespace-only commit hash returns 400."""
        response = client.post("/api/features/1/commits", json={"commit_hash": "   "})
        assert response.status_code == 400
        assert "empty" in response.json()["detail"].lower()

    def test_returns_404_for_unknown_feature(self, client):
        """POST returns 404 when the feature does not exist."""
        response = client.post("/api/features/999/commits", json={"commit_hash": "abc1234"})
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_accepts_full_40_char_hash(self, client):
        """Full 40-character SHA1 hashes are accepted."""
        full_hash = "a" * 40
        response = client.post("/api/features/1/commits", json={"commit_hash": full_hash})
        assert response.status_code == 201
        assert response.json()["commit_hash"] == full_hash

    def test_commits_isolated_per_feature(self, client):
        """Commits added to one feature do not appear on another."""
        client.post("/api/features/1/commits", json={"commit_hash": "for-feature-1"})
        client.post("/api/features/2/commits", json={"commit_hash": "for-feature-2"})

        f1 = [c["commit_hash"] for c in client.get("/api/features/1/commits").json()]
        f2 = [c["commit_hash"] for c in client.get("/api/features/2/commits").json()]

        assert f1 == ["for-feature-1"]
        assert f2 == ["for-feature-2"]


class TestDeleteCommit:
    """DELETE /api/features/{id}/commits/{commit_id}"""

    def test_deletes_commit_and_returns_204(self, client):
        """DELETE removes the commit and returns 204."""
        post = client.post("/api/features/1/commits", json={"commit_hash": "to-delete"})
        commit_id = post.json()["id"]

        response = client.delete(f"/api/features/1/commits/{commit_id}")
        assert response.status_code == 204

        remaining = [c["id"] for c in client.get("/api/features/1/commits").json()]
        assert commit_id not in remaining

    def test_returns_404_for_unknown_commit(self, client):
        """DELETE returns 404 when the commit ID does not exist."""
        response = client.delete("/api/features/1/commits/99999")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_returns_404_when_commit_belongs_to_different_feature(self, client):
        """DELETE returns 404 when the commit exists but on a different feature."""
        post = client.post("/api/features/1/commits", json={"commit_hash": "on-feature-1"})
        commit_id = post.json()["id"]

        response = client.delete(f"/api/features/2/commits/{commit_id}")
        assert response.status_code == 404


class TestCommitCountInFeatureResponse:
    """commit_count field is populated in FeatureResponse."""

    def test_commit_count_zero_by_default(self, client):
        """Features with no commits report commit_count=0."""
        response = client.get("/api/features/1")
        assert response.status_code == 200
        assert response.json()["commit_count"] == 0

    def test_commit_count_increments_after_adding(self, client):
        """commit_count increases after attaching commits to the feature."""
        client.post("/api/features/1/commits", json={"commit_hash": "hash1"})
        client.post("/api/features/1/commits", json={"commit_hash": "hash2"})

        response = client.get("/api/features/1")
        assert response.status_code == 200
        assert response.json()["commit_count"] == 2

    def test_commit_count_in_features_list(self, client):
        """commit_count is included when listing all features."""
        client.post("/api/features/1/commits", json={"commit_hash": "list-test"})

        response = client.get("/api/features")
        assert response.status_code == 200
        feature_1 = next(f for f in response.json() if f["id"] == 1)
        assert feature_1["commit_count"] == 1
