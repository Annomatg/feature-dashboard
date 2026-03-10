"""
Unit tests for the tasks API endpoints.

Tests the GET /api/tasks/{id}/graph endpoint.
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.main import app
from api.database import Feature


class TestGetTaskGraph:
    """Unit tests for GET /api/tasks/{id}/graph."""

    def test_task_not_found_returns_404(self, client):
        """Returns 404 when task ID doesn't exist."""
        response = client.get("/api/tasks/999/graph")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_task_without_session_returns_404(self, client):
        """Returns 404 when task has no claude_session_id."""
        # Feature 1 exists but has no session (claude_session_id is None)
        response = client.get("/api/tasks/1/graph")
        assert response.status_code == 404
        assert "no session" in response.json()["detail"].lower()

    def test_task_graph_success(self, client, monkeypatch):
        """Returns graph with nodes and edges when session file exists."""
        # Set up a feature with a session ID
        import backend.deps as deps_module
        session = deps_module._session_maker()
        try:
            feature = session.query(Feature).filter(Feature.id == 1).first()
            feature.claude_session_id = "test-session.jsonl"
            session.commit()
        finally:
            session.close()

        # Create a mock session file path that exists
        mock_session_file = MagicMock(spec=Path)
        mock_session_file.exists.return_value = True

        # Create a mock projects directory that returns our session file
        mock_projects_dir = MagicMock(spec=Path)
        mock_projects_dir.__truediv__ = MagicMock(return_value=mock_session_file)

        # Mock _get_claude_projects_dir to return our mock directory
        monkeypatch.setattr(
            "backend.routers.tasks._get_claude_projects_dir",
            lambda working_dir: mock_projects_dir
        )

        # Mock _parse_agent_graph to return a test graph
        test_graph = {
            "nodes": [
                {"id": "main", "label": "Main Agent", "type": "main"},
                {"id": "agent_1", "label": "Explore codebase", "type": "Explore"},
            ],
            "edges": [
                {"source": "main", "target": "agent_1"},
            ],
        }
        monkeypatch.setattr(
            "backend.routers.tasks._parse_agent_graph",
            lambda path: test_graph
        )

        response = client.get("/api/tasks/1/graph")

        assert response.status_code == 200
        data = response.json()
        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) == 2
        assert len(data["edges"]) == 1
        assert data["nodes"][0]["id"] == "main"
        assert data["nodes"][0]["label"] == "Main Agent"
        assert data["nodes"][0]["type"] == "main"
        assert data["edges"][0]["source"] == "main"
        assert data["edges"][0]["target"] == "agent_1"

    def test_task_graph_projects_dir_not_found(self, client, monkeypatch):
        """Returns 404 when Claude projects directory doesn't exist."""
        # Set up a feature with a session ID
        import backend.deps as deps_module
        session = deps_module._session_maker()
        try:
            feature = session.query(Feature).filter(Feature.id == 1).first()
            feature.claude_session_id = "test-session.jsonl"
            session.commit()
        finally:
            session.close()

        # Mock _get_claude_projects_dir to return None
        monkeypatch.setattr(
            "backend.routers.tasks._get_claude_projects_dir",
            lambda working_dir: None
        )

        response = client.get("/api/tasks/1/graph")

        assert response.status_code == 404
        assert "projects directory not found" in response.json()["detail"].lower()

    def test_task_graph_session_file_not_found(self, client, monkeypatch):
        """Returns 404 when the session file doesn't exist on disk."""
        # Set up a feature with a session ID
        import backend.deps as deps_module
        session = deps_module._session_maker()
        try:
            feature = session.query(Feature).filter(Feature.id == 1).first()
            feature.claude_session_id = "missing-session.jsonl"
            session.commit()
        finally:
            session.close()

        # Create a mock session file path that does NOT exist
        mock_session_file = MagicMock(spec=Path)
        mock_session_file.exists.return_value = False

        # Create a mock projects directory that returns our session file
        mock_projects_dir = MagicMock(spec=Path)
        mock_projects_dir.__truediv__ = MagicMock(return_value=mock_session_file)

        monkeypatch.setattr(
            "backend.routers.tasks._get_claude_projects_dir",
            lambda working_dir: mock_projects_dir
        )

        response = client.get("/api/tasks/1/graph")

        assert response.status_code == 404
        assert "session file not found" in response.json()["detail"].lower()

    def test_task_graph_empty_graph(self, client, monkeypatch):
        """Returns empty graph when session has no agent tool calls."""
        # Set up a feature with a session ID
        import backend.deps as deps_module
        session = deps_module._session_maker()
        try:
            feature = session.query(Feature).filter(Feature.id == 1).first()
            feature.claude_session_id = "empty-session.jsonl"
            session.commit()
        finally:
            session.close()

        # Create a mock session file path that exists
        mock_session_file = MagicMock(spec=Path)
        mock_session_file.exists.return_value = True

        # Create a mock projects directory that returns our session file
        mock_projects_dir = MagicMock(spec=Path)
        mock_projects_dir.__truediv__ = MagicMock(return_value=mock_session_file)

        # Mock _get_claude_projects_dir to return our mock directory
        monkeypatch.setattr(
            "backend.routers.tasks._get_claude_projects_dir",
            lambda working_dir: mock_projects_dir
        )

        # Mock _parse_agent_graph to return an empty graph (only main node)
        empty_graph = {
            "nodes": [{"id": "main", "label": "Main Agent", "type": "main"}],
            "edges": [],
        }
        monkeypatch.setattr(
            "backend.routers.tasks._parse_agent_graph",
            lambda path: empty_graph
        )

        response = client.get("/api/tasks/1/graph")

        assert response.status_code == 200
        data = response.json()
        assert len(data["nodes"]) == 1
        assert data["nodes"][0]["id"] == "main"
        assert len(data["edges"]) == 0

    def test_task_graph_parse_error_returns_500(self, client, monkeypatch):
        """Returns 500 when session file cannot be parsed."""
        # Set up a feature with a session ID
        import backend.deps as deps_module
        session = deps_module._session_maker()
        try:
            feature = session.query(Feature).filter(Feature.id == 1).first()
            feature.claude_session_id = "corrupted-session.jsonl"
            session.commit()
        finally:
            session.close()

        # Create a mock session file path that exists
        mock_session_file = MagicMock(spec=Path)
        mock_session_file.exists.return_value = True

        # Create a mock projects directory that returns our session file
        mock_projects_dir = MagicMock(spec=Path)
        mock_projects_dir.__truediv__ = MagicMock(return_value=mock_session_file)

        # Mock _get_claude_projects_dir to return our mock directory
        monkeypatch.setattr(
            "backend.routers.tasks._get_claude_projects_dir",
            lambda working_dir: mock_projects_dir
        )

        # Mock _parse_agent_graph to raise an exception
        def raise_parse_error(path):
            raise ValueError("Invalid JSON in session file")

        monkeypatch.setattr(
            "backend.routers.tasks._parse_agent_graph",
            raise_parse_error
        )

        response = client.get("/api/tasks/1/graph")

        assert response.status_code == 500
        assert "failed to parse" in response.json()["detail"].lower()

    def test_task_graph_invalid_session_id_path_traversal(self, client, monkeypatch):
        """Returns 400 when session ID contains path traversal characters."""
        # Set up a feature with a malicious session ID
        import backend.deps as deps_module
        session = deps_module._session_maker()
        try:
            feature = session.query(Feature).filter(Feature.id == 1).first()
            feature.claude_session_id = "../../../etc/passwd"
            session.commit()
        finally:
            session.close()

        response = client.get("/api/tasks/1/graph")

        assert response.status_code == 400
        assert "invalid session id" in response.json()["detail"].lower()

    def test_task_graph_invalid_session_id_wrong_extension(self, client, monkeypatch):
        """Returns 400 when session ID doesn't have .jsonl extension."""
        # Set up a feature with a wrong extension
        import backend.deps as deps_module
        session = deps_module._session_maker()
        try:
            feature = session.query(Feature).filter(Feature.id == 1).first()
            feature.claude_session_id = "session.txt"
            session.commit()
        finally:
            session.close()

        response = client.get("/api/tasks/1/graph")

        assert response.status_code == 400
        assert "invalid session id" in response.json()["detail"].lower()

    def test_task_id_zero_returns_404(self, client):
        """Returns 404 for task_id=0 (invalid ID)."""
        response = client.get("/api/tasks/0/graph")
        assert response.status_code == 404

    def test_task_id_negative_returns_404(self, client):
        """Returns 404 for negative task_id."""
        response = client.get("/api/tasks/-1/graph")
        assert response.status_code == 404


class TestGetTaskMetadata:
    """Unit tests for GET /api/tasks/{id}/metadata."""

    def test_metadata_task_not_found_returns_404(self, client):
        """Returns 404 when task ID doesn't exist."""
        response = client.get("/api/tasks/999/metadata")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_metadata_task_without_session_returns_404(self, client):
        """Returns 404 when task has no claude_session_id."""
        # Feature 1 exists but has no session (claude_session_id is None)
        response = client.get("/api/tasks/1/metadata")
        assert response.status_code == 404
        assert "no session" in response.json()["detail"].lower()

    def test_metadata_success(self, client, monkeypatch, tmp_path):
        """Returns metadata when session file exists."""
        import backend.deps as deps_module
        session = deps_module._session_maker()
        try:
            feature = session.query(Feature).filter(Feature.id == 1).first()
            feature.claude_session_id = "test-session--sonnet.jsonl"
            session.commit()
        finally:
            session.close()

        # Create a real JSONL file for parsing
        import json
        session_file = tmp_path / "test-session--sonnet.jsonl"
        content = (
            json.dumps({'type': 'user', 'message': {'content': 'Fix bug'}}) + '\n' +
            json.dumps({
                'type': 'assistant',
                'message': {
                    'content': [{'type': 'tool_use', 'name': 'Bash', 'input': {'command': 'ls'}}]
                }
            }) + '\n'
        )
        session_file.write_text(content)

        # Create a mock projects directory that returns our session file
        mock_projects_dir = MagicMock(spec=Path)
        mock_projects_dir.__truediv__ = MagicMock(return_value=session_file)

        monkeypatch.setattr(
            "backend.routers.tasks._get_claude_projects_dir",
            lambda working_dir: mock_projects_dir
        )

        response = client.get("/api/tasks/1/metadata")

        assert response.status_code == 200
        data = response.json()
        assert "turn_count" in data
        assert "token_estimate" in data
        assert "last_tool_used" in data
        assert "agent_type" in data
        assert data["turn_count"] == 2  # 1 user + 1 assistant
        assert data["last_tool_used"] == "Bash"
        assert data["agent_type"] == "sonnet"

    def test_metadata_projects_dir_not_found(self, client, monkeypatch):
        """Returns 404 when Claude projects directory doesn't exist."""
        import backend.deps as deps_module
        session = deps_module._session_maker()
        try:
            feature = session.query(Feature).filter(Feature.id == 1).first()
            feature.claude_session_id = "test-session.jsonl"
            session.commit()
        finally:
            session.close()

        monkeypatch.setattr(
            "backend.routers.tasks._get_claude_projects_dir",
            lambda working_dir: None
        )

        response = client.get("/api/tasks/1/metadata")

        assert response.status_code == 404
        assert "projects directory not found" in response.json()["detail"].lower()

    def test_metadata_session_file_not_found(self, client, monkeypatch):
        """Returns 404 when the session file doesn't exist on disk."""
        import backend.deps as deps_module
        session = deps_module._session_maker()
        try:
            feature = session.query(Feature).filter(Feature.id == 1).first()
            feature.claude_session_id = "missing-session.jsonl"
            session.commit()
        finally:
            session.close()

        # Create a mock session file path that does NOT exist
        mock_session_file = MagicMock(spec=Path)
        mock_session_file.exists.return_value = False

        # Create a mock projects directory that returns our session file
        mock_projects_dir = MagicMock(spec=Path)
        mock_projects_dir.__truediv__ = MagicMock(return_value=mock_session_file)

        monkeypatch.setattr(
            "backend.routers.tasks._get_claude_projects_dir",
            lambda working_dir: mock_projects_dir
        )

        response = client.get("/api/tasks/1/metadata")

        assert response.status_code == 404
        assert "session file not found" in response.json()["detail"].lower()

    def test_metadata_invalid_session_id_path_traversal(self, client, monkeypatch):
        """Returns 400 when session ID contains path traversal characters."""
        import backend.deps as deps_module
        session = deps_module._session_maker()
        try:
            feature = session.query(Feature).filter(Feature.id == 1).first()
            feature.claude_session_id = "../../../etc/passwd"
            session.commit()
        finally:
            session.close()

        response = client.get("/api/tasks/1/metadata")

        assert response.status_code == 400
        assert "invalid session id" in response.json()["detail"].lower()

    def test_metadata_invalid_session_id_wrong_extension(self, client, monkeypatch):
        """Returns 400 when session ID doesn't have .jsonl extension."""
        import backend.deps as deps_module
        session = deps_module._session_maker()
        try:
            feature = session.query(Feature).filter(Feature.id == 1).first()
            feature.claude_session_id = "session.txt"
            session.commit()
        finally:
            session.close()

        response = client.get("/api/tasks/1/metadata")

        assert response.status_code == 400
        assert "invalid session id" in response.json()["detail"].lower()

    def test_metadata_id_zero_returns_404(self, client):
        """Returns 404 for task_id=0 (invalid ID)."""
        response = client.get("/api/tasks/0/metadata")
        assert response.status_code == 404

    def test_metadata_id_negative_returns_404(self, client):
        """Returns 404 for negative task_id."""
        response = client.get("/api/tasks/-1/metadata")
        assert response.status_code == 404

    def test_metadata_parse_error_returns_500(self, client, monkeypatch, tmp_path):
        """Returns 500 when session file cannot be parsed."""
        import backend.deps as deps_module
        session = deps_module._session_maker()
        try:
            feature = session.query(Feature).filter(Feature.id == 1).first()
            feature.claude_session_id = "corrupted-session.jsonl"
            session.commit()
        finally:
            session.close()

        # Create a mock session file that exists
        mock_session_file = MagicMock(spec=Path)
        mock_session_file.exists.return_value = True

        # Create a mock projects directory that returns our session file
        mock_projects_dir = MagicMock(spec=Path)
        mock_projects_dir.__truediv__ = MagicMock(return_value=mock_session_file)

        monkeypatch.setattr(
            "backend.routers.tasks._get_claude_projects_dir",
            lambda working_dir: mock_projects_dir
        )

        # Mock _parse_main_agent_metadata to raise an exception
        def raise_parse_error(path):
            raise ValueError("Invalid JSON in session file")

        monkeypatch.setattr(
            "backend.routers.tasks._parse_main_agent_metadata",
            raise_parse_error
        )

        response = client.get("/api/tasks/1/metadata")

        assert response.status_code == 500
        assert "failed to parse" in response.json()["detail"].lower()


class TestGetTaskSubagents:
    """Unit tests for GET /api/tasks/{id}/subagents."""

    def test_task_not_found_returns_404(self, client):
        """Returns 404 when task ID doesn't exist."""
        response = client.get("/api/tasks/999/subagents")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_task_without_session_returns_404(self, client):
        """Returns 404 when task has no claude_session_id."""
        response = client.get("/api/tasks/1/subagents")
        assert response.status_code == 404
        assert "no session" in response.json()["detail"].lower()

    def test_invalid_session_id_path_traversal_returns_400(self, client):
        """Returns 400 when session ID contains path traversal characters."""
        import backend.deps as deps_module
        session = deps_module._session_maker()
        try:
            feature = session.query(Feature).filter(Feature.id == 1).first()
            feature.claude_session_id = "../../../etc/passwd"
            session.commit()
        finally:
            session.close()

        response = client.get("/api/tasks/1/subagents")
        assert response.status_code == 400
        assert "invalid session id" in response.json()["detail"].lower()

    def test_invalid_session_id_wrong_extension_returns_400(self, client):
        """Returns 400 when session ID doesn't have .jsonl extension."""
        import backend.deps as deps_module
        session = deps_module._session_maker()
        try:
            feature = session.query(Feature).filter(Feature.id == 1).first()
            feature.claude_session_id = "session.txt"
            session.commit()
        finally:
            session.close()

        response = client.get("/api/tasks/1/subagents")
        assert response.status_code == 400
        assert "invalid session id" in response.json()["detail"].lower()

    def test_projects_dir_not_found_returns_404(self, client, monkeypatch):
        """Returns 404 when Claude projects directory doesn't exist."""
        import backend.deps as deps_module
        session = deps_module._session_maker()
        try:
            feature = session.query(Feature).filter(Feature.id == 1).first()
            feature.claude_session_id = "test-session.jsonl"
            session.commit()
        finally:
            session.close()

        monkeypatch.setattr(
            "backend.routers.tasks._get_claude_projects_dir",
            lambda working_dir: None
        )

        response = client.get("/api/tasks/1/subagents")
        assert response.status_code == 404
        assert "projects directory not found" in response.json()["detail"].lower()

    def test_returns_empty_list_when_no_subagents(self, client, monkeypatch):
        """Returns empty subagents list when no subagent directory exists."""
        import backend.deps as deps_module
        session = deps_module._session_maker()
        try:
            feature = session.query(Feature).filter(Feature.id == 1).first()
            feature.claude_session_id = "test-session.jsonl"
            session.commit()
        finally:
            session.close()

        mock_projects_dir = MagicMock(spec=Path)

        monkeypatch.setattr(
            "backend.routers.tasks._get_claude_projects_dir",
            lambda working_dir: mock_projects_dir
        )
        monkeypatch.setattr(
            "backend.routers.tasks._discover_subagent_logs",
            lambda projects_dir, session_id: []
        )

        response = client.get("/api/tasks/1/subagents")

        assert response.status_code == 200
        data = response.json()
        assert "subagents" in data
        assert data["subagents"] == []

    def test_returns_subagent_list(self, client, monkeypatch):
        """Returns list of subagent records when subagents exist."""
        import backend.deps as deps_module
        session = deps_module._session_maker()
        try:
            feature = session.query(Feature).filter(Feature.id == 1).first()
            feature.claude_session_id = "test-session.jsonl"
            session.commit()
        finally:
            session.close()

        mock_projects_dir = MagicMock(spec=Path)
        monkeypatch.setattr(
            "backend.routers.tasks._get_claude_projects_dir",
            lambda working_dir: mock_projects_dir
        )

        fake_subagents = [
            {"agent_id": "abc123", "file_path": "/path/to/agent-abc123.jsonl"},
            {"agent_id": "def456", "file_path": "/path/to/agent-def456.jsonl"},
        ]
        monkeypatch.setattr(
            "backend.routers.tasks._discover_subagent_logs",
            lambda projects_dir, session_id: fake_subagents
        )

        response = client.get("/api/tasks/1/subagents")

        assert response.status_code == 200
        data = response.json()
        assert len(data["subagents"]) == 2
        assert data["subagents"][0]["agent_id"] == "abc123"
        assert data["subagents"][0]["file_path"] == "/path/to/agent-abc123.jsonl"
        assert data["subagents"][1]["agent_id"] == "def456"

    def test_task_id_zero_returns_404(self, client):
        """Returns 404 for task_id=0."""
        response = client.get("/api/tasks/0/subagents")
        assert response.status_code == 404

    def test_task_id_negative_returns_404(self, client):
        """Returns 404 for negative task_id."""
        response = client.get("/api/tasks/-1/subagents")
        assert response.status_code == 404
