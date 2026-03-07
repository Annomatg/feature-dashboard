"""
Tests for GET /api/budget endpoint
====================================

Tests:
- Returns error field when credentials file is missing
- Returns error field when credentials file lacks OAuth token
- Returns error field when Anthropic API call fails
- Returns five_hour and seven_day data when API succeeds
- Utilization values are rounded to one decimal
- resets_formatted is 'HH:MM' when reset is today
- resets_formatted is 'ddd HH:MM' when reset is another day
- Provider field defaults to 'anthropic'
- Returns empty periods when API response has no matching keys
"""

import json
import sys
import urllib.error
from datetime import datetime, timezone, timedelta
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.main import app

client = TestClient(app)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_cred_file(tmp_path, token="test-oauth-token"):
    """Write a minimal .credentials.json and return its Path."""
    cred = {"claudeAiOauth": {"accessToken": token}}
    p = tmp_path / ".credentials.json"
    p.write_text(json.dumps(cred), encoding="utf-8")
    return p


def _make_api_response(five_hour_util=45.0, seven_day_util=30.0, resets_at=None):
    """Return a dict mimicking the Anthropic usage API response."""
    if resets_at is None:
        # Default: resets tomorrow
        resets_at = (datetime.now(timezone.utc) + timedelta(hours=5)).isoformat()
    return {
        "five_hour": {"utilization": five_hour_util, "resets_at": resets_at},
        "seven_day": {"utilization": seven_day_util, "resets_at": resets_at},
    }


def _mock_urlopen(api_data: dict):
    """Return a context manager mock that yields api_data as JSON."""
    body = json.dumps(api_data).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = body
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


# ── Missing / invalid credentials ─────────────────────────────────────────────

def test_budget_no_credentials_file(tmp_path):
    """Returns error when ~/.claude/.credentials.json is absent."""
    missing = tmp_path / "no_such_file.json"
    with patch("backend.routers.settings.Path.home", return_value=tmp_path / "home_no_creds"):
        resp = client.get("/api/budget")
    assert resp.status_code == 200
    data = resp.json()
    assert data["error"] is not None
    assert data["five_hour"] is None
    assert data["seven_day"] is None


def test_budget_no_oauth_token(tmp_path):
    """Returns error when credentials file has no accessToken."""
    home = tmp_path / "home"
    claude_dir = home / ".claude"
    claude_dir.mkdir(parents=True)
    cred_path = claude_dir / ".credentials.json"
    cred_path.write_text(json.dumps({"claudeAiOauth": {}}), encoding="utf-8")

    with patch("backend.routers.settings.Path.home", return_value=home):
        resp = client.get("/api/budget")
    assert resp.status_code == 200
    data = resp.json()
    assert data["error"] is not None
    assert "token" in data["error"].lower()


def test_budget_api_http_error(tmp_path):
    """Returns error when the Anthropic API returns an HTTP error."""
    home = tmp_path / "home"
    claude_dir = home / ".claude"
    claude_dir.mkdir(parents=True)
    _make_cred_file(claude_dir)

    http_err = urllib.error.HTTPError(
        url="https://api.anthropic.com/api/oauth/usage",
        code=401,
        msg="Unauthorized",
        hdrs=None,
        fp=None,
    )

    with (
        patch("backend.routers.settings.Path.home", return_value=home),
        patch("backend.routers.settings.urllib.request.urlopen", side_effect=http_err),
    ):
        resp = client.get("/api/budget")

    assert resp.status_code == 200
    data = resp.json()
    assert data["error"] is not None
    assert "401" in data["error"]


def test_budget_api_network_error(tmp_path):
    """Returns error when the network request fails."""
    home = tmp_path / "home"
    claude_dir = home / ".claude"
    claude_dir.mkdir(parents=True)
    _make_cred_file(claude_dir)

    with (
        patch("backend.routers.settings.Path.home", return_value=home),
        patch("backend.routers.settings.urllib.request.urlopen", side_effect=OSError("Network unreachable")),
    ):
        resp = client.get("/api/budget")

    assert resp.status_code == 200
    data = resp.json()
    assert data["error"] is not None


# ── Successful responses ───────────────────────────────────────────────────────

def test_budget_returns_five_hour_and_seven_day(tmp_path):
    """Returns both periods when API succeeds."""
    home = tmp_path / "home"
    claude_dir = home / ".claude"
    claude_dir.mkdir(parents=True)
    _make_cred_file(claude_dir)

    api_data = _make_api_response(five_hour_util=45.0, seven_day_util=30.0)
    mock_resp = _mock_urlopen(api_data)

    with (
        patch("backend.routers.settings.Path.home", return_value=home),
        patch("backend.routers.settings.urllib.request.urlopen", return_value=mock_resp),
    ):
        resp = client.get("/api/budget")

    assert resp.status_code == 200
    data = resp.json()
    assert data["error"] is None
    assert data["five_hour"] is not None
    assert data["seven_day"] is not None
    assert data["five_hour"]["utilization"] == 45.0
    assert data["seven_day"]["utilization"] == 30.0


def test_budget_provider_field(tmp_path):
    """Provider defaults to 'anthropic'."""
    home = tmp_path / "home"
    claude_dir = home / ".claude"
    claude_dir.mkdir(parents=True)
    _make_cred_file(claude_dir)

    api_data = _make_api_response()
    mock_resp = _mock_urlopen(api_data)

    with (
        patch("backend.routers.settings.Path.home", return_value=home),
        patch("backend.routers.settings.urllib.request.urlopen", return_value=mock_resp),
    ):
        resp = client.get("/api/budget")

    assert resp.json()["provider"] == "anthropic"


def test_budget_utilization_rounded(tmp_path):
    """Utilization is rounded to one decimal place."""
    home = tmp_path / "home"
    claude_dir = home / ".claude"
    claude_dir.mkdir(parents=True)
    _make_cred_file(claude_dir)

    api_data = _make_api_response(five_hour_util=45.678, seven_day_util=99.999)
    mock_resp = _mock_urlopen(api_data)

    with (
        patch("backend.routers.settings.Path.home", return_value=home),
        patch("backend.routers.settings.urllib.request.urlopen", return_value=mock_resp),
    ):
        resp = client.get("/api/budget")

    data = resp.json()
    assert data["five_hour"]["utilization"] == 45.7
    assert data["seven_day"]["utilization"] == 100.0


def test_budget_resets_formatted_today(tmp_path):
    """resets_formatted shows 'HH:MM' when the reset is today."""
    home = tmp_path / "home"
    claude_dir = home / ".claude"
    claude_dir.mkdir(parents=True)
    _make_cred_file(claude_dir)

    # Use a reset time that is the same UTC day as now
    now_utc = datetime.now(timezone.utc)
    resets_at = now_utc.strftime("%Y-%m-%dT%H:%M:%S")

    api_data = _make_api_response(resets_at=resets_at)
    mock_resp = _mock_urlopen(api_data)

    with (
        patch("backend.routers.settings.Path.home", return_value=home),
        patch("backend.routers.settings.urllib.request.urlopen", return_value=mock_resp),
    ):
        resp = client.get("/api/budget")

    data = resp.json()
    fmt = data["five_hour"]["resets_formatted"]
    # Should be HH:MM — two digits, colon, two digits
    assert len(fmt) == 5 and fmt[2] == ":", f"Expected HH:MM, got {fmt!r}"


def test_budget_resets_formatted_other_day(tmp_path):
    """resets_formatted shows 'ddd HH:MM' when the reset is on another day."""
    home = tmp_path / "home"
    claude_dir = home / ".claude"
    claude_dir.mkdir(parents=True)
    _make_cred_file(claude_dir)

    # Use a reset time far in the future (different day)
    future = datetime.now(timezone.utc) + timedelta(days=3)
    resets_at = future.strftime("%Y-%m-%dT%H:%M:%S")

    api_data = _make_api_response(resets_at=resets_at)
    mock_resp = _mock_urlopen(api_data)

    with (
        patch("backend.routers.settings.Path.home", return_value=home),
        patch("backend.routers.settings.urllib.request.urlopen", return_value=mock_resp),
    ):
        resp = client.get("/api/budget")

    data = resp.json()
    fmt = data["five_hour"]["resets_formatted"]
    # Should be "ddd HH:MM" — at least "Mon 14:30" (10 chars)
    assert len(fmt) >= 9, f"Expected 'ddd HH:MM', got {fmt!r}"
    assert " " in fmt, f"Expected space between day and time, got {fmt!r}"


def test_budget_empty_when_api_returns_no_periods(tmp_path):
    """Both periods are None when the API response has no matching keys."""
    home = tmp_path / "home"
    claude_dir = home / ".claude"
    claude_dir.mkdir(parents=True)
    _make_cred_file(claude_dir)

    api_data = {}   # Empty response
    mock_resp = _mock_urlopen(api_data)

    with (
        patch("backend.routers.settings.Path.home", return_value=home),
        patch("backend.routers.settings.urllib.request.urlopen", return_value=mock_resp),
    ):
        resp = client.get("/api/budget")

    data = resp.json()
    assert data["error"] is None
    assert data["five_hour"] is None
    assert data["seven_day"] is None
