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


class TestLaunchClaude:
    """Tests for POST /api/features/{id}/launch-claude"""

    def test_launch_todo_feature(self, client, monkeypatch, tmp_path):
        """Test launching Claude for a TODO feature succeeds."""
        import backend.main as main_module
        import backend.deps as deps_module
        # Isolate from production settings.json so prompt assertions are stable
        monkeypatch.setattr(deps_module, 'SETTINGS_FILE', tmp_path / "settings.json")

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

    def test_launch_in_progress_feature(self, client, monkeypatch, tmp_path):
        """Test launching Claude for an IN PROGRESS feature succeeds."""
        import backend.main as main_module
        import backend.deps as deps_module
        # Isolate from production settings.json so prompt assertions are stable
        monkeypatch.setattr(deps_module, 'SETTINGS_FILE', tmp_path / "settings.json")

        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1, "wait": lambda self: 0})())

        # Feature 4 is in_progress=True, passes=False
        response = client.post("/api/features/4/launch-claude")

        assert response.status_code == 200
        data = response.json()
        assert data["launched"] is True
        assert data["feature_id"] == 4
        assert "Feature #4" in data["prompt"]

    def test_launch_done_feature_fails(self, client, monkeypatch):
        """Test that launching Claude for a completed feature returns 400."""
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1, "wait": lambda self: 0})())

        # Feature 3 is passes=True (done)
        response = client.post("/api/features/3/launch-claude")

        assert response.status_code == 400
        assert "completed" in response.json()["detail"].lower()

    def test_launch_not_found(self, client, monkeypatch):
        """Test launching Claude for a non-existent feature returns 404."""
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1, "wait": lambda self: 0})())

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
        import backend.deps as deps_module

        # Use a fresh settings file with the default template so description is included
        monkeypatch.setattr(deps_module, 'SETTINGS_FILE', tmp_path / "settings.json")
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1, "wait": lambda self: 0})())

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
            return type("P", (), {"pid": 1, "wait": lambda self: 0})()

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
            return type("P", (), {"pid": 1, "wait": lambda self: 0})()

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
            return type("P", (), {"pid": 1, "wait": lambda self: 0})()

        monkeypatch.setattr(subprocess, "Popen", mock_popen)

        # No request body — should default to hidden_execution=True
        response = client.post("/api/features/1/launch-claude")

        assert response.status_code == 200
        assert response.json()["hidden_execution"] is True
        assert "--print" in self._get_full_command(popen_calls)

    def test_hidden_execution_response_field_present(self, client, monkeypatch):
        """Test that the response always includes hidden_execution field."""
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1, "wait": lambda self: 0})())

        response = client.post("/api/features/1/launch-claude")

        assert response.status_code == 200
        assert "hidden_execution" in response.json()

    def test_interactive_mode_still_uses_dangerously_skip_permissions(self, client, monkeypatch):
        """Test that interactive mode (hidden_execution=false) still uses --dangerously-skip-permissions."""
        popen_calls = []

        def mock_popen(*args, **kwargs):
            popen_calls.append({"args": args, "kwargs": kwargs})
            return type("P", (), {"pid": 1, "wait": lambda self: 0})()

        monkeypatch.setattr(subprocess, "Popen", mock_popen)

        response = client.post("/api/features/1/launch-claude", json={"hidden_execution": False})

        assert response.status_code == 200
        assert "--dangerously-skip-permissions" in self._get_full_command(popen_calls)



# ==============================================================================
# Settings endpoints
# ==============================================================================

def test_get_settings_returns_defaults(client, tmp_path, monkeypatch):
    """GET /api/settings returns default templates when no settings.json exists."""
    import backend.main as main_module
    import backend.deps as deps_module
    # Point SETTINGS_FILE to a non-existent file in tmp_path
    monkeypatch.setattr(deps_module, 'SETTINGS_FILE', tmp_path / "settings_nonexistent.json")

    response = client.get("/api/settings")
    assert response.status_code == 200
    data = response.json()
    assert "claude_prompt_template" in data
    assert len(data["claude_prompt_template"]) > 0
    assert "plan_tasks_prompt_template" in data
    assert len(data["plan_tasks_prompt_template"]) > 0


def test_put_settings_saves_and_returns(client, tmp_path, monkeypatch):
    """PUT /api/settings saves settings and returns them."""
    import backend.main as main_module
    import backend.deps as deps_module
    settings_file = tmp_path / "test_settings.json"
    monkeypatch.setattr(deps_module, 'SETTINGS_FILE', settings_file)

    new_template = "Custom prompt: {name} - {description}"
    new_plan_template = "Custom plan: {description}"
    response = client.put("/api/settings", json={
        "claude_prompt_template": new_template,
        "plan_tasks_prompt_template": new_plan_template,
    })
    assert response.status_code == 200
    data = response.json()
    assert data["claude_prompt_template"] == new_template
    assert data["plan_tasks_prompt_template"] == new_plan_template

    # Verify it was saved to disk
    assert settings_file.exists()
    import json
    saved = json.loads(settings_file.read_text())
    assert saved["claude_prompt_template"] == new_template
    assert saved["plan_tasks_prompt_template"] == new_plan_template


def test_put_settings_preserves_plan_template_when_omitted(client, tmp_path, monkeypatch):
    """PUT /api/settings preserves plan_tasks_prompt_template when not provided."""
    import backend.main as main_module
    import backend.deps as deps_module
    settings_file = tmp_path / "test_settings.json"
    monkeypatch.setattr(deps_module, 'SETTINGS_FILE', settings_file)

    # Save a custom plan template first
    custom_plan = "My custom plan: {description}"
    client.put("/api/settings", json={
        "claude_prompt_template": "original",
        "plan_tasks_prompt_template": custom_plan,
    })

    # Update only the autopilot template (omit plan_tasks_prompt_template)
    response = client.put("/api/settings", json={"claude_prompt_template": "updated"})
    assert response.status_code == 200
    data = response.json()
    assert data["claude_prompt_template"] == "updated"
    assert data["plan_tasks_prompt_template"] == custom_plan


def test_get_settings_after_save(client, tmp_path, monkeypatch):
    """GET /api/settings returns previously saved settings."""
    import backend.main as main_module
    import backend.deps as deps_module
    settings_file = tmp_path / "test_settings.json"
    monkeypatch.setattr(deps_module, 'SETTINGS_FILE', settings_file)

    # Save a custom template
    custom_template = "My custom template {feature_id}"
    custom_plan = "My plan template {description}"
    client.put("/api/settings", json={
        "claude_prompt_template": custom_template,
        "plan_tasks_prompt_template": custom_plan,
    })

    # Now get and verify
    response = client.get("/api/settings")
    assert response.status_code == 200
    data = response.json()
    assert data["claude_prompt_template"] == custom_template
    assert data["plan_tasks_prompt_template"] == custom_plan


def test_get_settings_returns_planning_model(client, tmp_path, monkeypatch):
    """GET /api/settings returns planning_model field."""
    import backend.deps as deps_module
    monkeypatch.setattr(deps_module, 'SETTINGS_FILE', tmp_path / "settings_nonexistent.json")

    response = client.get("/api/settings")
    assert response.status_code == 200
    data = response.json()
    assert "planning_model" in data
    assert data["planning_model"] == deps_module.PLANNING_MODEL


def test_put_settings_saves_planning_model(client, tmp_path, monkeypatch):
    """PUT /api/settings saves and returns planning_model."""
    import backend.deps as deps_module
    settings_file = tmp_path / "test_settings.json"
    monkeypatch.setattr(deps_module, 'SETTINGS_FILE', settings_file)

    response = client.put("/api/settings", json={
        "claude_prompt_template": "template",
        "planning_model": "claude-sonnet-4-6",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["planning_model"] == "claude-sonnet-4-6"

    import json as json_mod
    saved = json_mod.loads(settings_file.read_text())
    assert saved["planning_model"] == "claude-sonnet-4-6"


def test_put_settings_preserves_planning_model_when_omitted(client, tmp_path, monkeypatch):
    """PUT /api/settings preserves planning_model when not provided."""
    import backend.deps as deps_module
    settings_file = tmp_path / "test_settings.json"
    monkeypatch.setattr(deps_module, 'SETTINGS_FILE', settings_file)

    # Save a custom planning model first
    client.put("/api/settings", json={
        "claude_prompt_template": "original",
        "planning_model": "claude-haiku-4-5-20251001",
    })

    # Update without planning_model
    response = client.put("/api/settings", json={"claude_prompt_template": "updated"})
    assert response.status_code == 200
    assert response.json()["planning_model"] == "claude-haiku-4-5-20251001"


def test_plan_tasks_uses_settings_template(client, tmp_path, monkeypatch):
    """POST /api/plan-tasks uses the plan_tasks_prompt_template from settings."""
    import backend.main as main_module
    import backend.deps as deps_module

    # Point settings file to temp dir
    settings_file = tmp_path / "test_settings.json"
    monkeypatch.setattr(deps_module, 'SETTINGS_FILE', settings_file)

    # Save a custom plan template
    custom_plan = "Custom plan for: {description}"
    client.put("/api/settings", json={
        "claude_prompt_template": "some autopilot template",
        "plan_tasks_prompt_template": custom_plan,
    })

    # Mock subprocess.Popen to avoid actually launching Claude
    import subprocess
    mock_calls = []

    class MockPopen:
        def __init__(self, *args, **kwargs):
            mock_calls.append(kwargs)

    monkeypatch.setattr(subprocess, 'Popen', MockPopen)

    response = client.post("/api/plan-tasks", json={"description": "Add login page"})
    assert response.status_code == 200
    data = response.json()
    assert data["launched"] is True
    assert "Custom plan for:" in data["prompt"]
    assert "Add login page" in data["prompt"]


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
            return type("P", (), {"pid": 1, "wait": lambda self: 0})()

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
            return type("P", (), {"pid": 1, "wait": lambda self: 0})()

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
            return type("P", (), {"pid": 1, "wait": lambda self: 0})()

        monkeypatch.setattr(subprocess, "Popen", mock_popen)

        response = client.post("/api/features/1/launch-claude")
        assert response.status_code == 200
        data = response.json()
        assert data["model"] == "haiku"

    def test_launch_response_includes_model(self, client, monkeypatch):
        """Test that launch response always includes the model field."""
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1, "wait": lambda self: 0})())

        response = client.post("/api/features/1/launch-claude")
        assert response.status_code == 200
        data = response.json()
        assert "model" in data


class TestPlanTasks:
    """Tests for POST /api/plan-tasks"""

    def test_valid_description_returns_200_and_launched(self, client, monkeypatch):
        """Test that a valid description returns 200 with launched=True."""
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1, "wait": lambda self: 0})())

        response = client.post("/api/plan-tasks", json={
            "description": "Add dark mode support to the dashboard"
        })

        assert response.status_code == 200
        data = response.json()
        assert data["launched"] is True

    def test_empty_description_returns_400(self, client, monkeypatch):
        """Test that an empty description returns 400."""
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1, "wait": lambda self: 0})())

        response = client.post("/api/plan-tasks", json={"description": ""})

        assert response.status_code == 400
        assert "empty" in response.json()["detail"].lower()

    def test_whitespace_description_returns_400(self, client, monkeypatch):
        """Test that a whitespace-only description is also rejected."""
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1, "wait": lambda self: 0})())

        response = client.post("/api/plan-tasks", json={"description": "   "})

        assert response.status_code == 400

    def test_prompt_contains_user_description(self, client, monkeypatch):
        """Test that the generated prompt embeds the user's description."""
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1, "wait": lambda self: 0})())

        description = "Add user authentication with OAuth"
        response = client.post("/api/plan-tasks", json={"description": description})

        assert response.status_code == 200
        assert description in response.json()["prompt"]

    def test_does_not_use_print_flag(self, client, monkeypatch):
        """Test that plan-tasks launches Claude without --print (interactive mode)."""
        popen_calls = []

        def mock_popen(*args, **kwargs):
            popen_calls.append({"args": args, "kwargs": kwargs})
            return type("P", (), {"pid": 1, "wait": lambda self: 0})()

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
            return type("P", (), {"pid": 1, "wait": lambda self: 0})()

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
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1, "wait": lambda self: 0})())

        response = client.post("/api/plan-tasks", json={"description": "Add dark mode"})

        assert response.status_code == 200
        data = response.json()
        assert "prompt" in data
        assert len(data["prompt"]) > 0
        assert "working_directory" in data
        assert len(data["working_directory"]) > 0

    def test_missing_description_field_returns_422(self, client, monkeypatch):
        """Test that omitting description entirely returns 422 validation error."""
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1, "wait": lambda self: 0})())

        response = client.post("/api/plan-tasks", json={})

        assert response.status_code == 422

    def test_working_directory_uses_active_db_parent(self, client, monkeypatch):
        """Regression test: plan-tasks must launch in the active database's parent directory.

        Bug: working_dir was hardcoded to PROJECT_DIR, so selecting a different
        database (e.g. code-similarity-mcp) still launched Claude in the
        feature-dashboard directory.  Fix: use _current_db_path.parent.
        """
        import backend.main as main_module
        import backend.deps as deps_module

        # Simulate switching to a different project's database
        other_dir = tempfile.mkdtemp()
        other_db_path = Path(other_dir) / "features.db"
        monkeypatch.setattr(deps_module, "_current_db_path", other_db_path)

        popen_calls = []

        def mock_popen(*args, **kwargs):
            popen_calls.append(kwargs)
            return type("P", (), {"pid": 1, "wait": lambda self: 0})()

        monkeypatch.setattr(subprocess, "Popen", mock_popen)

        response = client.post("/api/plan-tasks", json={"description": "Add search"})

        assert response.status_code == 200
        data = response.json()

        # The response working_directory should be the other project's dir
        assert data["working_directory"] == other_dir

        # The subprocess cwd must also match the other project's directory
        assert len(popen_calls) == 1
        assert popen_calls[0]["cwd"] == other_dir

        # Cleanup temp dir created in this test
        try:
            shutil.rmtree(other_dir)
        except PermissionError:
            pass

    def test_working_directory_uses_default_db_parent_without_switch(self, client, monkeypatch):
        """Plan-tasks uses the current active database's parent (not a hardcoded PROJECT_DIR)."""
        import backend.main as main_module
        import backend.deps as deps_module

        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1, "wait": lambda self: 0})())

        response = client.post("/api/plan-tasks", json={"description": "Add dark mode"})

        assert response.status_code == 200
        data = response.json()

        expected_dir = str(deps_module._current_db_path.parent)
        assert data["working_directory"] == expected_dir

    def test_uses_opus_model_by_default(self, client, monkeypatch, tmp_path):
        """Plan-tasks uses the planning model (opus) by default."""
        import backend.deps as deps_module

        monkeypatch.setattr(deps_module, "SETTINGS_FILE", tmp_path / "settings.json")

        popen_calls = []

        def mock_popen(*args, **kwargs):
            popen_calls.append({"args": args, "kwargs": kwargs})
            return type("P", (), {"pid": 1, "wait": lambda self: 0})()

        monkeypatch.setattr(subprocess, "Popen", mock_popen)

        response = client.post("/api/plan-tasks", json={"description": "Add analytics"})

        assert response.status_code == 200
        data = response.json()
        assert data["model"] == deps_module.PLANNING_MODEL

        assert len(popen_calls) == 1
        cmd_args = popen_calls[0]["args"][0]
        full_cmd = " ".join(cmd_args) if isinstance(cmd_args, list) else str(cmd_args)
        assert deps_module.PLANNING_MODEL in full_cmd

    def test_uses_custom_planning_model_from_settings(self, client, monkeypatch, tmp_path):
        """Plan-tasks respects planning_model override from settings."""
        import json as json_mod
        import backend.deps as deps_module

        settings_file = tmp_path / "settings.json"
        monkeypatch.setattr(deps_module, "SETTINGS_FILE", settings_file)

        # Save a custom planning model
        settings_file.write_text(json_mod.dumps({"planning_model": "claude-sonnet-4-6"}))

        popen_calls = []

        def mock_popen(*args, **kwargs):
            popen_calls.append({"args": args, "kwargs": kwargs})
            return type("P", (), {"pid": 1, "wait": lambda self: 0})()

        monkeypatch.setattr(subprocess, "Popen", mock_popen)

        response = client.post("/api/plan-tasks", json={"description": "Add analytics"})

        assert response.status_code == 200
        data = response.json()
        assert data["model"] == "claude-sonnet-4-6"

        assert len(popen_calls) == 1
        cmd_args = popen_calls[0]["args"][0]
        full_cmd = " ".join(cmd_args) if isinstance(cmd_args, list) else str(cmd_args)
        assert "claude-sonnet-4-6" in full_cmd

    def test_response_includes_model_field(self, client, monkeypatch, tmp_path):
        """Plan-tasks response includes the planning model value."""
        import backend.deps as deps_module

        monkeypatch.setattr(deps_module, "SETTINGS_FILE", tmp_path / "settings.json")
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1, "wait": lambda self: 0})())

        response = client.post("/api/plan-tasks", json={"description": "Add features"})

        assert response.status_code == 200
        assert response.json()["model"] == deps_module.PLANNING_MODEL



# ==============================================================================
# Claude log tests
# ==============================================================================

class TestClaudeLog:
    """Tests for GET /api/features/{feature_id}/claude-log"""

    def test_no_log_returns_404(self, client, monkeypatch):
        """Returns 404 when no log buffer exists for the feature."""
        import backend.autopilot_engine as ae_module
        monkeypatch.setattr(ae_module, '_claude_process_logs', {})
        response = client.get("/api/features/1/claude-log")
        assert response.status_code == 404

    def test_empty_log_returns_200_with_no_lines(self, client, monkeypatch):
        """Returns 200 with empty lines list when log exists but has no output yet."""
        import backend.autopilot_engine as ae_module
        from backend.main import ClaudeProcessLog
        log = ClaudeProcessLog(feature_id=1)
        monkeypatch.setattr(ae_module, '_claude_process_logs', {1: log})
        response = client.get("/api/features/1/claude-log")
        assert response.status_code == 200
        data = response.json()
        assert data["feature_id"] == 1
        assert data["active"] is True
        assert data["lines"] == []
        assert data["total_lines"] == 0

    def test_log_with_data_returns_last_n_lines(self, client, monkeypatch):
        """Returns last N lines when limit is applied."""
        import backend.autopilot_engine as ae_module
        from backend.main import ClaudeProcessLog
        log = ClaudeProcessLog(feature_id=2)
        for i in range(20):
            log.append("stdout", f"line {i}")
        monkeypatch.setattr(ae_module, '_claude_process_logs', {2: log})

        response = client.get("/api/features/2/claude-log?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert data["total_lines"] == 20
        assert len(data["lines"]) == 5
        assert data["lines"][0]["text"] == "line 15"
        assert data["lines"][-1]["text"] == "line 19"

    def test_filter_by_stdout(self, client, monkeypatch):
        """Filters lines by stream=stdout."""
        import backend.autopilot_engine as ae_module
        from backend.main import ClaudeProcessLog
        log = ClaudeProcessLog(feature_id=3)
        log.append("stdout", "out line 1")
        log.append("stderr", "err line 1")
        log.append("stdout", "out line 2")
        monkeypatch.setattr(ae_module, '_claude_process_logs', {3: log})

        response = client.get("/api/features/3/claude-log?stream=stdout&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert data["total_lines"] == 2
        assert all(ln["stream"] == "stdout" for ln in data["lines"])

    def test_filter_by_stderr(self, client, monkeypatch):
        """Filters lines by stream=stderr."""
        import backend.autopilot_engine as ae_module
        from backend.main import ClaudeProcessLog
        log = ClaudeProcessLog(feature_id=3)
        log.append("stdout", "out line")
        log.append("stderr", "err line 1")
        log.append("stderr", "err line 2")
        monkeypatch.setattr(ae_module, '_claude_process_logs', {3: log})

        response = client.get("/api/features/3/claude-log?stream=stderr&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert data["total_lines"] == 2
        assert all(ln["stream"] == "stderr" for ln in data["lines"])

    def test_limit_clamped_to_500(self, client, monkeypatch):
        """Limit is clamped to a maximum of 500."""
        import backend.autopilot_engine as ae_module
        from backend.main import ClaudeProcessLog
        log = ClaudeProcessLog(feature_id=1)
        for i in range(10):
            log.append("stdout", f"line {i}")
        monkeypatch.setattr(ae_module, '_claude_process_logs', {1: log})

        response = client.get("/api/features/1/claude-log?limit=9999")
        assert response.status_code == 200
        data = response.json()
        assert len(data["lines"]) == 10  # only 10 exist, all returned

    def test_line_schema(self, client, monkeypatch):
        """Each line has timestamp, stream, and text fields."""
        import backend.autopilot_engine as ae_module
        from backend.main import ClaudeProcessLog
        log = ClaudeProcessLog(feature_id=1)
        log.append("stdout", "hello world")
        monkeypatch.setattr(ae_module, '_claude_process_logs', {1: log})

        response = client.get("/api/features/1/claude-log")
        assert response.status_code == 200
        data = response.json()
        assert len(data["lines"]) == 1
        line = data["lines"][0]
        assert "timestamp" in line
        assert line["stream"] == "stdout"
        assert line["text"] == "hello world"

    def test_active_flag_reflects_log_presence(self, client, monkeypatch):
        """active=True when the log key is present (process running)."""
        import backend.autopilot_engine as ae_module
        from backend.main import ClaudeProcessLog
        log = ClaudeProcessLog(feature_id=1)
        monkeypatch.setattr(ae_module, '_claude_process_logs', {1: log})

        response = client.get("/api/features/1/claude-log")
        assert response.status_code == 200
        assert response.json()["active"] is True



class TestGetBudget:
    """Tests for the GET /api/budget endpoint."""

    def test_budget_returns_error_when_credentials_missing(self, client, monkeypatch, tmp_path):
        """Returns error field when credentials file does not exist."""
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        response = client.get("/api/budget")
        assert response.status_code == 200
        data = response.json()
        assert data["error"] is not None
        assert "credentials" in data["error"].lower() or "not found" in data["error"].lower()

    def test_budget_returns_data_with_valid_api_response(self, client, monkeypatch, tmp_path):
        """Returns five_hour and seven_day data when API responds successfully."""
        import json

        # Create fake credentials
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        cred_file = claude_dir / ".credentials.json"
        cred_file.write_text(json.dumps({
            "claudeAiOauth": {"accessToken": "fake-token"}
        }))
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        fake_usage = {
            "five_hour": {"utilization": 42.5, "resets_at": "2025-01-01T12:00:00Z"},
            "seven_day": {"utilization": 75.0, "resets_at": "2025-01-07T00:00:00Z"},
        }

        def fake_fetch():
            import urllib.request
            import io
            payload = json.dumps(fake_usage).encode()
            class FakeResponse:
                def read(self): return payload
                def __enter__(self): return self
                def __exit__(self, *a): pass
            return FakeResponse()

        import unittest.mock as mock
        with mock.patch("urllib.request.urlopen", return_value=fake_fetch()):
            response = client.get("/api/budget")

        assert response.status_code == 200
        data = response.json()
        assert data["error"] is None
        assert data["five_hour"]["utilization"] == 42.5
        assert data["seven_day"]["utilization"] == 75.0

    def test_budget_handles_null_five_hour_in_api_response(self, client, monkeypatch, tmp_path):
        """Does not crash when API returns null for five_hour period."""
        import json

        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        cred_file = claude_dir / ".credentials.json"
        cred_file.write_text(json.dumps({
            "claudeAiOauth": {"accessToken": "fake-token"}
        }))
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        fake_usage = {
            "five_hour": None,
            "seven_day": {"utilization": 60.0, "resets_at": "2025-01-07T00:00:00Z"},
        }

        class FakeResponse:
            def read(self): return json.dumps(fake_usage).encode()
            def __enter__(self): return self
            def __exit__(self, *a): pass

        import unittest.mock as mock
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse()):
            response = client.get("/api/budget")

        assert response.status_code == 200
        data = response.json()
        assert data["five_hour"] is None
        assert data["seven_day"]["utilization"] == 60.0

    def test_budget_handles_null_seven_day_in_api_response(self, client, monkeypatch, tmp_path):
        """Does not crash when API returns null for seven_day period."""
        import json

        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        cred_file = claude_dir / ".credentials.json"
        cred_file.write_text(json.dumps({
            "claudeAiOauth": {"accessToken": "fake-token"}
        }))
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        fake_usage = {
            "five_hour": {"utilization": 30.0, "resets_at": "2025-01-01T12:00:00Z"},
            "seven_day": None,
        }

        class FakeResponse:
            def read(self): return json.dumps(fake_usage).encode()
            def __enter__(self): return self
            def __exit__(self, *a): pass

        import unittest.mock as mock
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse()):
            response = client.get("/api/budget")

        assert response.status_code == 200
        data = response.json()
        assert data["five_hour"]["utilization"] == 30.0
        assert data["seven_day"] is None

    def test_budget_handles_both_periods_null(self, client, monkeypatch, tmp_path):
        """Does not crash when API returns null for both periods."""
        import json

        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        cred_file = claude_dir / ".credentials.json"
        cred_file.write_text(json.dumps({
            "claudeAiOauth": {"accessToken": "fake-token"}
        }))
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        fake_usage = {"five_hour": None, "seven_day": None}

        class FakeResponse:
            def read(self): return json.dumps(fake_usage).encode()
            def __enter__(self): return self
            def __exit__(self, *a): pass

        import unittest.mock as mock
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse()):
            response = client.get("/api/budget")

        assert response.status_code == 200
        data = response.json()
        assert data["five_hour"] is None
        assert data["seven_day"] is None
        assert data["error"] is None

    def test_budget_returns_error_on_http_error(self, client, monkeypatch, tmp_path):
        """Returns error field when API returns an HTTP error."""
        import json
        import urllib.error

        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        cred_file = claude_dir / ".credentials.json"
        cred_file.write_text(json.dumps({
            "claudeAiOauth": {"accessToken": "fake-token"}
        }))
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        import unittest.mock as mock
        http_error = urllib.error.HTTPError(
            url="https://api.anthropic.com/api/oauth/usage",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=None,
        )
        with mock.patch("urllib.request.urlopen", side_effect=http_error):
            response = client.get("/api/budget")

        assert response.status_code == 200
        data = response.json()
        assert data["error"] is not None
        assert "401" in data["error"]

    def test_budget_returns_error_when_no_oauth_token(self, client, monkeypatch, tmp_path):
        """Returns error field when credentials have no OAuth access token."""
        import json

        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        cred_file = claude_dir / ".credentials.json"
        cred_file.write_text(json.dumps({"claudeAiOauth": {}}))
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        response = client.get("/api/budget")
        assert response.status_code == 200
        data = response.json()
        assert data["error"] is not None
        assert "token" in data["error"].lower()

    def test_budget_provider_is_anthropic(self, client, monkeypatch, tmp_path):
        """Response always includes provider=anthropic."""
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        response = client.get("/api/budget")
        assert response.status_code == 200
        assert response.json()["provider"] == "anthropic"


