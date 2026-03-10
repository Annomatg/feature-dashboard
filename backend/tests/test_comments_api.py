import subprocess
import sys
import tempfile
import shutil
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.main import app
from api.database import CategoryToken, create_database, DescriptionBigram, DescriptionToken, Feature, NameBigram, NameToken


class TestCommentEndpoints:
    """Integration tests for GET/POST/DELETE /api/features/{id}/comments."""

    def test_get_comments_empty(self, client):
        """GET returns empty list when feature has no comments."""
        response = client.get("/api/features/1/comments")
        assert response.status_code == 200
        assert response.json() == []

    def test_get_comments_feature_not_found(self, client):
        """GET returns 404 for unknown feature."""
        response = client.get("/api/features/999/comments")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_add_comment_success(self, client):
        """POST creates a comment and returns 201 with CommentResponse."""
        response = client.post("/api/features/1/comments", json={"content": "Hello world"})
        assert response.status_code == 201
        data = response.json()
        assert data["content"] == "Hello world"
        assert data["feature_id"] == 1
        assert "id" in data
        assert "created_at" in data

    def test_add_comment_strips_whitespace(self, client):
        """POST strips leading/trailing whitespace from content."""
        response = client.post("/api/features/1/comments", json={"content": "  trimmed  "})
        assert response.status_code == 201
        assert response.json()["content"] == "trimmed"

    def test_add_comment_empty_content_rejected(self, client):
        """POST returns 400 when content is blank."""
        response = client.post("/api/features/1/comments", json={"content": "   "})
        assert response.status_code == 400
        assert "empty" in response.json()["detail"].lower()

    def test_add_comment_feature_not_found(self, client):
        """POST returns 404 for unknown feature."""
        response = client.post("/api/features/999/comments", json={"content": "orphan"})
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_comments_ordered_by_created_at(self, client):
        """GET returns comments ordered oldest-first."""
        client.post("/api/features/2/comments", json={"content": "first"})
        client.post("/api/features/2/comments", json={"content": "second"})
        client.post("/api/features/2/comments", json={"content": "third"})

        response = client.get("/api/features/2/comments")
        assert response.status_code == 200
        contents = [c["content"] for c in response.json()]
        assert contents == ["first", "second", "third"]

    def test_delete_comment_success(self, client):
        """DELETE removes the comment and returns 204."""
        post = client.post("/api/features/1/comments", json={"content": "to delete"})
        comment_id = post.json()["id"]

        response = client.delete(f"/api/features/1/comments/{comment_id}")
        assert response.status_code == 204

        # Verify it's gone
        comments = client.get("/api/features/1/comments").json()
        assert all(c["id"] != comment_id for c in comments)

    def test_delete_comment_not_found(self, client):
        """DELETE returns 404 for unknown comment."""
        response = client.delete("/api/features/1/comments/99999")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_delete_comment_wrong_feature(self, client):
        """DELETE returns 404 when comment_id exists but belongs to different feature."""
        post = client.post("/api/features/1/comments", json={"content": "on feature 1"})
        comment_id = post.json()["id"]

        response = client.delete(f"/api/features/2/comments/{comment_id}")
        assert response.status_code == 404

    def test_comments_isolated_per_feature(self, client):
        """Comments added to one feature do not appear on another."""
        client.post("/api/features/1/comments", json={"content": "for feature 1"})
        client.post("/api/features/2/comments", json={"content": "for feature 2"})

        f1_comments = [c["content"] for c in client.get("/api/features/1/comments").json()]
        f2_comments = [c["content"] for c in client.get("/api/features/2/comments").json()]

        assert f1_comments == ["for feature 1"]
        assert f2_comments == ["for feature 2"]


