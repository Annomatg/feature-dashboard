"""Tests for the AI provider abstraction layer.

Tests:
- ClaudeProvider.get_provider_name() returns 'claude'
- ClaudeProvider.spawn_process() produces correct command on win32
- ClaudeProvider.spawn_process() produces correct command on posix
- ClaudeProvider.spawn_process() falls back to powershell.exe when pwsh is missing (win32)
- ClaudeProvider.spawn_process() raises RuntimeError when no PowerShell found (win32)
- ClaudeProvider.spawn_process() raises FileNotFoundError when claude CLI missing (posix)
- get_provider() returns ClaudeProvider for 'claude'
- get_provider() raises ValueError for unknown provider names
- REGISTRY contains 'claude'
- GET /api/settings includes provider and available_providers fields
- PUT /api/settings with invalid provider returns 400
"""

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.providers import REGISTRY, get_provider
from backend.providers.claude import ClaudeProvider
from backend.main import app, get_session
from api.database import create_database, Feature
import tempfile
import shutil


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_feature(**kwargs):
    """Return a minimal feature-like namespace."""
    defaults = {
        "id": 42,
        "category": "Backend",
        "name": "Test Feature",
        "description": "A test feature description",
        "steps": ["Step one", "Step two"],
        "model": "sonnet",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


SETTINGS = {
    "claude_prompt_template": (
        "Feature #{feature_id} [{category}]: {name}\n{description}\n{steps}"
    ),
    "provider": "claude",
}


def _make_ntf_mock(name="/tmp/prompt123.txt"):
    """Create a mock for tempfile.NamedTemporaryFile context manager."""
    mock_file = MagicMock()
    mock_file.name = name
    mock_ntf_instance = MagicMock()
    mock_ntf_instance.__enter__ = MagicMock(return_value=mock_file)
    mock_ntf_instance.__exit__ = MagicMock(return_value=False)
    return mock_ntf_instance


# ── ClaudeProvider.get_provider_name ─────────────────────────────────────────

def test_claude_provider_name():
    assert ClaudeProvider().get_provider_name() == "claude"


# ── ClaudeProvider on win32 ───────────────────────────────────────────────────

class TestClaudeProviderWin32:
    def _spawn(self, feature, mock_popen, ntf_name="C:\\Temp\\prompt123.txt"):
        provider = ClaudeProvider()
        with (
            patch.object(sys, "platform", "win32"),
            patch("backend.providers.claude.subprocess.Popen", mock_popen),
            patch(
                "backend.providers.claude.tempfile.NamedTemporaryFile",
                return_value=_make_ntf_mock(ntf_name),
            ),
        ):
            return provider.spawn_process(feature, SETTINGS, "C:\\Projects\\test")

    def test_uses_pwsh_as_first_choice(self):
        mock_popen = MagicMock(return_value=MagicMock(spec=subprocess.Popen))
        self._spawn(make_feature(), mock_popen)

        cmd = mock_popen.call_args[0][0]
        assert cmd[0] == "pwsh"
        assert cmd[1] == "-Command"

    def test_command_contains_model(self):
        mock_popen = MagicMock(return_value=MagicMock(spec=subprocess.Popen))
        self._spawn(make_feature(model="opus"), mock_popen)

        ps_cmd = mock_popen.call_args[0][0][2]
        assert "opus" in ps_cmd

    def test_command_has_dangerously_skip_permissions(self):
        mock_popen = MagicMock(return_value=MagicMock(spec=subprocess.Popen))
        self._spawn(make_feature(), mock_popen)

        ps_cmd = mock_popen.call_args[0][0][2]
        assert "--dangerously-skip-permissions" in ps_cmd

    def test_command_has_print_flag(self):
        mock_popen = MagicMock(return_value=MagicMock(spec=subprocess.Popen))
        self._spawn(make_feature(), mock_popen)

        ps_cmd = mock_popen.call_args[0][0][2]
        assert "--print" in ps_cmd

    def test_stdout_and_stderr_are_pipes(self):
        mock_popen = MagicMock(return_value=MagicMock(spec=subprocess.Popen))
        self._spawn(make_feature(), mock_popen)

        kwargs = mock_popen.call_args[1]
        assert kwargs["stdout"] == subprocess.PIPE
        assert kwargs["stderr"] == subprocess.PIPE

    def test_falls_back_to_powershell_when_pwsh_missing(self):
        """When pwsh raises FileNotFoundError, falls back to powershell.exe."""
        calls = []

        def side_effect(cmd, **kwargs):
            calls.append(cmd[0])
            if cmd[0] == "pwsh":
                raise FileNotFoundError("pwsh not found")
            return MagicMock(spec=subprocess.Popen)

        provider = ClaudeProvider()
        with (
            patch.object(sys, "platform", "win32"),
            patch("backend.providers.claude.subprocess.Popen", side_effect=side_effect),
            patch(
                "backend.providers.claude.tempfile.NamedTemporaryFile",
                return_value=_make_ntf_mock(),
            ),
        ):
            provider.spawn_process(make_feature(), SETTINGS, "C:\\Projects\\test")

        assert "pwsh" in calls
        assert "powershell" in calls

    def test_raises_runtime_error_when_no_powershell(self):
        """Raises RuntimeError when neither pwsh nor powershell is found."""
        provider = ClaudeProvider()
        with (
            patch.object(sys, "platform", "win32"),
            patch(
                "backend.providers.claude.subprocess.Popen",
                side_effect=FileNotFoundError("not found"),
            ),
            patch(
                "backend.providers.claude.tempfile.NamedTemporaryFile",
                return_value=_make_ntf_mock(),
            ),
        ):
            with pytest.raises(RuntimeError, match="No PowerShell found"):
                provider.spawn_process(make_feature(), SETTINGS, "C:\\Projects\\test")

    def test_uses_feature_model_default_sonnet_when_none(self):
        """When feature.model is None, defaults to 'sonnet'."""
        mock_popen = MagicMock(return_value=MagicMock(spec=subprocess.Popen))
        self._spawn(make_feature(model=None), mock_popen)

        ps_cmd = mock_popen.call_args[0][0][2]
        assert "sonnet" in ps_cmd


# ── ClaudeProvider on posix ───────────────────────────────────────────────────

class TestClaudeProviderPosix:
    def _spawn(self, feature, mock_popen):
        provider = ClaudeProvider()
        with (
            patch.object(sys, "platform", "linux"),
            patch("backend.providers.claude.subprocess.Popen", mock_popen),
        ):
            return provider.spawn_process(feature, SETTINGS, "/home/user/project")

    def test_calls_claude_directly(self):
        mock_popen = MagicMock(return_value=MagicMock(spec=subprocess.Popen))
        self._spawn(make_feature(), mock_popen)

        cmd = mock_popen.call_args[0][0]
        assert cmd[0] == "claude"

    def test_command_contains_model_flag(self):
        mock_popen = MagicMock(return_value=MagicMock(spec=subprocess.Popen))
        self._spawn(make_feature(model="haiku"), mock_popen)

        cmd = mock_popen.call_args[0][0]
        assert "--model" in cmd
        idx = cmd.index("--model")
        assert cmd[idx + 1] == "haiku"

    def test_command_has_print_flag(self):
        mock_popen = MagicMock(return_value=MagicMock(spec=subprocess.Popen))
        self._spawn(make_feature(), mock_popen)

        cmd = mock_popen.call_args[0][0]
        assert "--print" in cmd

    def test_command_has_dangerously_skip_permissions(self):
        mock_popen = MagicMock(return_value=MagicMock(spec=subprocess.Popen))
        self._spawn(make_feature(), mock_popen)

        cmd = mock_popen.call_args[0][0]
        assert "--dangerously-skip-permissions" in cmd

    def test_stdout_and_stderr_are_pipes(self):
        mock_popen = MagicMock(return_value=MagicMock(spec=subprocess.Popen))
        self._spawn(make_feature(), mock_popen)

        kwargs = mock_popen.call_args[1]
        assert kwargs["stdout"] == subprocess.PIPE
        assert kwargs["stderr"] == subprocess.PIPE

    def test_raises_file_not_found_when_claude_missing(self):
        """Raises FileNotFoundError (with helpful message) when claude is not in PATH."""
        provider = ClaudeProvider()
        with (
            patch.object(sys, "platform", "linux"),
            patch(
                "backend.providers.claude.subprocess.Popen",
                side_effect=FileNotFoundError("not found"),
            ),
        ):
            with pytest.raises(FileNotFoundError, match="Claude CLI not found"):
                provider.spawn_process(make_feature(), SETTINGS, "/home/user/project")

    def test_uses_feature_model_default_sonnet_when_none(self):
        mock_popen = MagicMock(return_value=MagicMock(spec=subprocess.Popen))
        self._spawn(make_feature(model=None), mock_popen)

        cmd = mock_popen.call_args[0][0]
        idx = cmd.index("--model")
        assert cmd[idx + 1] == "sonnet"


# ── REGISTRY and get_provider ─────────────────────────────────────────────────

def test_registry_contains_claude():
    assert "claude" in REGISTRY


def test_get_provider_returns_claude_instance():
    provider = get_provider("claude")
    assert isinstance(provider, ClaudeProvider)


def test_get_provider_unknown_raises_value_error():
    with pytest.raises(ValueError, match="Unknown provider 'openai'"):
        get_provider("openai")


def test_get_provider_unknown_lists_available_providers():
    with pytest.raises(ValueError, match="Available providers:"):
        get_provider("gemini")


def test_get_provider_available_list_contains_claude():
    try:
        get_provider("nonexistent")
    except ValueError as e:
        assert "claude" in str(e)


# ── Settings API integration tests ────────────────────────────────────────────

@pytest.fixture
def api_client(monkeypatch, tmp_path):
    """TestClient with isolated database and settings file."""
    # Isolated DB
    engine, session_maker = create_database(tmp_path)
    session = session_maker()
    try:
        session.add(Feature(
            id=1, priority=100, category="Backend", name="Feature 1",
            description="Test", steps=["Step 1"], passes=False, in_progress=False,
        ))
        session.commit()
    finally:
        session.close()

    # Override DB session
    def override_get_session():
        s = session_maker()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_session] = override_get_session

    # Redirect settings file to tmp dir
    monkeypatch.setattr("backend.main.SETTINGS_FILE", tmp_path / "settings.json")

    yield TestClient(app)

    app.dependency_overrides.clear()
    engine.dispose()


def test_get_settings_includes_provider(api_client):
    resp = api_client.get("/api/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert "provider" in data
    assert data["provider"] == "claude"


def test_get_settings_includes_available_providers(api_client):
    resp = api_client.get("/api/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert "available_providers" in data
    assert "claude" in data["available_providers"]


def test_put_settings_saves_provider(api_client):
    resp = api_client.get("/api/settings")
    current = resp.json()

    payload = {
        "claude_prompt_template": current["claude_prompt_template"],
        "autopilot_budget_limit": 0,
        "provider": "claude",
    }
    resp = api_client.put("/api/settings", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "claude"
    assert "claude" in data["available_providers"]


def test_put_settings_invalid_provider_returns_400(api_client):
    resp = api_client.get("/api/settings")
    current = resp.json()

    payload = {
        "claude_prompt_template": current["claude_prompt_template"],
        "autopilot_budget_limit": 0,
        "provider": "openai",
    }
    resp = api_client.put("/api/settings", json=payload)
    assert resp.status_code == 400
    assert "openai" in resp.json()["detail"]
