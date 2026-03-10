"""
Tests for POST /api/git/update endpoint
=========================================

Tests:
- Returns push result when no runner_path configured
- Returns 200 with push+pull when runner_path is set and push succeeds
- Pull is skipped when push fails
- Pull returns error when runner directory does not exist
- Uses actual PROJECT_DIR for push (mocked git subprocess)
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.main import app
from backend.schemas import GitOperationResult


# ── helpers ─────────────────────────────────────────────────────────────────

def _make_git_result(success: bool, stdout: str = "", stderr: str = "") -> GitOperationResult:
    return GitOperationResult(
        success=success,
        returncode=0 if success else 1,
        stdout=stdout,
        stderr=stderr,
    )


# ── test classes ─────────────────────────────────────────────────────────────

class TestGitUpdateNoRunnerPath:
    """POST /api/git/update with no runner_path configured."""

    def test_returns_push_only_when_no_runner_path(self, client, tmp_path):
        push_ok = _make_git_result(True, stdout="Everything up-to-date")
        with patch("backend.routers.git._run_git", new=AsyncMock(return_value=push_ok)), \
             patch("backend.routers.git.load_settings", return_value={"runner_path": ""}):
            resp = client.post("/api/git/update")

        assert resp.status_code == 200
        data = resp.json()
        assert data["push"]["success"] is True
        assert data["push"]["stdout"] == "Everything up-to-date"
        assert data["pull"] is None

    def test_returns_push_only_when_runner_path_missing_from_settings(self, client):
        push_ok = _make_git_result(True)
        with patch("backend.routers.git._run_git", new=AsyncMock(return_value=push_ok)), \
             patch("backend.routers.git.load_settings", return_value={}):
            resp = client.post("/api/git/update")

        assert resp.status_code == 200
        data = resp.json()
        assert data["push"]["success"] is True
        assert data["pull"] is None


class TestGitUpdateWithRunnerPath:
    """POST /api/git/update with runner_path configured."""

    def test_push_and_pull_both_succeed(self, client, tmp_path):
        runner_dir = tmp_path / "runner"
        runner_dir.mkdir()

        push_ok = _make_git_result(True, stdout="master -> origin/master")
        pull_ok = _make_git_result(True, stdout="Already up to date.")

        results = [push_ok, pull_ok]
        call_idx = 0

        async def mock_run_git(args, cwd):
            nonlocal call_idx
            r = results[call_idx]
            call_idx += 1
            return r

        with patch("backend.routers.git._run_git", side_effect=mock_run_git), \
             patch("backend.routers.git.load_settings", return_value={"runner_path": str(runner_dir)}):
            resp = client.post("/api/git/update")

        assert resp.status_code == 200
        data = resp.json()
        assert data["push"]["success"] is True
        assert data["pull"]["success"] is True
        assert data["pull"]["stdout"] == "Already up to date."

    def test_pull_skipped_when_push_fails(self, client, tmp_path):
        runner_dir = tmp_path / "runner"
        runner_dir.mkdir()

        push_fail = _make_git_result(False, stderr="rejected")

        with patch("backend.routers.git._run_git", new=AsyncMock(return_value=push_fail)), \
             patch("backend.routers.git.load_settings", return_value={"runner_path": str(runner_dir)}):
            resp = client.post("/api/git/update")

        assert resp.status_code == 200
        data = resp.json()
        assert data["push"]["success"] is False
        assert data["push"]["stderr"] == "rejected"
        assert data["pull"] is None

    def test_pull_error_when_runner_dir_missing(self, client, tmp_path):
        missing_dir = tmp_path / "does_not_exist"
        push_ok = _make_git_result(True)

        with patch("backend.routers.git._run_git", new=AsyncMock(return_value=push_ok)), \
             patch("backend.routers.git.load_settings", return_value={"runner_path": str(missing_dir)}):
            resp = client.post("/api/git/update")

        assert resp.status_code == 200
        data = resp.json()
        assert data["push"]["success"] is True
        assert data["pull"]["success"] is False
        assert data["pull"]["returncode"] == -1
        assert "not found" in data["pull"]["stderr"].lower()

    def test_pull_error_contains_runner_path_in_message(self, client, tmp_path):
        missing_dir = tmp_path / "nonexistent_runner"
        push_ok = _make_git_result(True)

        with patch("backend.routers.git._run_git", new=AsyncMock(return_value=push_ok)), \
             patch("backend.routers.git.load_settings", return_value={"runner_path": str(missing_dir)}):
            resp = client.post("/api/git/update")

        data = resp.json()
        assert str(missing_dir) in data["pull"]["stderr"]


class TestGitUpdateResponseShape:
    """Verify the response shape matches the schema."""

    def test_push_result_has_all_fields(self, client):
        push_ok = _make_git_result(True, stdout="ok", stderr="")
        with patch("backend.routers.git._run_git", new=AsyncMock(return_value=push_ok)), \
             patch("backend.routers.git.load_settings", return_value={"runner_path": ""}):
            resp = client.post("/api/git/update")

        push = resp.json()["push"]
        assert "success" in push
        assert "returncode" in push
        assert "stdout" in push
        assert "stderr" in push

    def test_pull_result_has_all_fields_when_present(self, client, tmp_path):
        runner_dir = tmp_path / "runner"
        runner_dir.mkdir()
        push_ok = _make_git_result(True)
        pull_ok = _make_git_result(True, stdout="pulled", stderr="")

        results = [push_ok, pull_ok]
        idx = 0

        async def mock_run_git(args, cwd):
            nonlocal idx
            r = results[idx]
            idx += 1
            return r

        with patch("backend.routers.git._run_git", side_effect=mock_run_git), \
             patch("backend.routers.git.load_settings", return_value={"runner_path": str(runner_dir)}):
            resp = client.post("/api/git/update")

        pull = resp.json()["pull"]
        assert "success" in pull
        assert "returncode" in pull
        assert "stdout" in pull
        assert "stderr" in pull
