"""
Tests for GET /api/settings and PUT /api/settings endpoints
============================================================

Tests:
- GET returns current settings with available_providers list
- GET returns defaults when settings.json does not exist
- PUT saves valid settings and returns updated values
- PUT returns 400 for unknown provider
- PUT preserves plan_tasks_prompt_template when not supplied
- PUT updates plan_tasks_prompt_template when supplied
- PUT saves autopilot_budget_limit correctly
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.main import app

client = TestClient(app)

VALID_TEMPLATE = "Work on Feature #{feature_id}: {name}"
DEFAULT_PROVIDER = "claude"


# ── GET /api/settings ──────────────────────────────────────────────────────────

def test_get_settings_returns_defaults_when_no_file(tmp_path):
    """Returns default settings when settings.json does not exist."""
    missing = tmp_path / "settings.json"
    with patch("backend.deps.SETTINGS_FILE", missing):
        resp = client.get("/api/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert "claude_prompt_template" in data
    assert "plan_tasks_prompt_template" in data
    assert "autopilot_budget_limit" in data
    assert "provider" in data
    assert "available_providers" in data
    assert isinstance(data["available_providers"], list)
    assert len(data["available_providers"]) > 0


def test_get_settings_returns_available_providers():
    """available_providers is a sorted non-empty list."""
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    providers = resp.json()["available_providers"]
    assert isinstance(providers, list)
    assert providers == sorted(providers)
    assert "claude" in providers


def test_get_settings_reads_saved_file(tmp_path):
    """Returns the settings stored in settings.json."""
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({
        "claude_prompt_template": "Custom template {feature_id}",
        "plan_tasks_prompt_template": "Plan: {description}",
        "autopilot_budget_limit": 5,
        "provider": "claude",
    }), encoding="utf-8")

    with patch("backend.deps.SETTINGS_FILE", settings_file):
        resp = client.get("/api/settings")

    assert resp.status_code == 200
    data = resp.json()
    assert data["claude_prompt_template"] == "Custom template {feature_id}"
    assert data["autopilot_budget_limit"] == 5


# ── PUT /api/settings ──────────────────────────────────────────────────────────

def test_put_settings_saves_and_returns(tmp_path):
    """PUT saves valid settings and returns the updated response."""
    settings_file = tmp_path / "settings.json"
    payload = {
        "claude_prompt_template": VALID_TEMPLATE,
        "plan_tasks_prompt_template": "Plan: {description}",
        "autopilot_budget_limit": 3,
        "provider": DEFAULT_PROVIDER,
    }

    with patch("backend.deps.SETTINGS_FILE", settings_file):
        resp = client.put("/api/settings", json=payload)

    assert resp.status_code == 200
    data = resp.json()
    assert data["claude_prompt_template"] == VALID_TEMPLATE
    assert data["autopilot_budget_limit"] == 3
    assert data["provider"] == DEFAULT_PROVIDER
    assert "available_providers" in data


def test_put_settings_persists_to_file(tmp_path):
    """PUT actually writes the settings to disk."""
    settings_file = tmp_path / "settings.json"
    payload = {
        "claude_prompt_template": VALID_TEMPLATE,
        "autopilot_budget_limit": 7,
        "provider": DEFAULT_PROVIDER,
    }

    with patch("backend.deps.SETTINGS_FILE", settings_file):
        client.put("/api/settings", json=payload)
        saved = json.loads(settings_file.read_text(encoding="utf-8"))

    assert saved["claude_prompt_template"] == VALID_TEMPLATE
    assert saved["autopilot_budget_limit"] == 7


def test_put_settings_invalid_provider_returns_400():
    """PUT returns 400 when an unknown provider is specified."""
    payload = {
        "claude_prompt_template": VALID_TEMPLATE,
        "autopilot_budget_limit": 0,
        "provider": "nonexistent_provider_xyz",
    }
    resp = client.put("/api/settings", json=payload)
    assert resp.status_code == 400


def test_put_settings_preserves_plan_template_when_omitted(tmp_path):
    """When plan_tasks_prompt_template is None, the existing value is kept."""
    settings_file = tmp_path / "settings.json"
    existing = {
        "claude_prompt_template": "old",
        "plan_tasks_prompt_template": "Existing plan template",
        "autopilot_budget_limit": 0,
        "provider": "claude",
    }
    settings_file.write_text(json.dumps(existing), encoding="utf-8")

    payload = {
        "claude_prompt_template": VALID_TEMPLATE,
        "plan_tasks_prompt_template": None,
        "autopilot_budget_limit": 0,
        "provider": DEFAULT_PROVIDER,
    }

    with patch("backend.deps.SETTINGS_FILE", settings_file):
        resp = client.put("/api/settings", json=payload)

    assert resp.status_code == 200
    assert resp.json()["plan_tasks_prompt_template"] == "Existing plan template"


def test_put_settings_updates_plan_template_when_supplied(tmp_path):
    """When plan_tasks_prompt_template is provided, it is saved."""
    settings_file = tmp_path / "settings.json"
    payload = {
        "claude_prompt_template": VALID_TEMPLATE,
        "plan_tasks_prompt_template": "New plan template",
        "autopilot_budget_limit": 0,
        "provider": DEFAULT_PROVIDER,
    }

    with patch("backend.deps.SETTINGS_FILE", settings_file):
        resp = client.put("/api/settings", json=payload)

    assert resp.status_code == 200
    assert resp.json()["plan_tasks_prompt_template"] == "New plan template"
