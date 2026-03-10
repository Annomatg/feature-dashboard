"""
Tests for interview session logging and GET /api/interview/debug endpoint.
===========================================================================

Covers:
  - _log_event helper appends structured entries to session.log
  - Automatic logging in set_question, submit_answer, timeout, reset
  - get_debug_log() returns active/post-session log correctly
  - GET /api/interview/debug HTTP endpoint
"""

import asyncio
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import backend.interview_state as state_module
from backend.interview_state import (
    InterviewSession,
    _log_event,
    get_debug_log,
    get_interview_session,
)
from backend.main import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def session():
    """Fresh InterviewSession for each test (does not use the singleton)."""
    return InterviewSession()


@pytest.fixture(autouse=True)
def reset_singleton_state():
    """Reset the module singleton and post-session log before/after each test."""
    s = get_interview_session()
    s.active_question = None
    s.pending_answer = None
    s.owner_token = None
    s.started_at = None
    s._answer_ready = asyncio.Event()
    s._subscribers = []
    s.log.clear()
    state_module._last_session_log = None
    state_module._last_session_log_time = None
    yield
    s.active_question = None
    s.pending_answer = None
    s.owner_token = None
    s.started_at = None
    s._answer_ready = asyncio.Event()
    s._subscribers = []
    s.log.clear()
    state_module._last_session_log = None
    state_module._last_session_log_time = None


@pytest.fixture
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# _log_event helper
# ---------------------------------------------------------------------------

class TestLogEventHelper:
    def test_appends_entry_to_log(self, session):
        _log_event(session, "test_event", {"key": "value"})
        assert len(session.log) == 1

    def test_entry_has_timestamp(self, session):
        _log_event(session, "test_event", {})
        entry = session.log[0]
        assert "timestamp" in entry
        assert entry["timestamp"].endswith("Z")

    def test_entry_has_event_type(self, session):
        _log_event(session, "my_event", {})
        assert session.log[0]["event_type"] == "my_event"

    def test_entry_has_detail(self, session):
        _log_event(session, "x", {"foo": "bar"})
        assert session.log[0]["detail"] == {"foo": "bar"}

    def test_none_detail_becomes_empty_dict(self, session):
        _log_event(session, "x", None)
        assert session.log[0]["detail"] == {}

    def test_multiple_entries_accumulate(self, session):
        _log_event(session, "a", {})
        _log_event(session, "b", {})
        _log_event(session, "c", {})
        assert len(session.log) == 3
        types = [e["event_type"] for e in session.log]
        assert types == ["a", "b", "c"]

    def test_maxlen_enforced(self, session):
        for i in range(250):
            _log_event(session, "flood", {"i": i})
        assert len(session.log) == 200


# ---------------------------------------------------------------------------
# Automatic logging in session methods
# ---------------------------------------------------------------------------

class TestSessionStartLogging:
    def test_session_start_logged_on_first_question(self, session):
        run(session.set_question("Q?", ["A", "B"]))
        types = [e["event_type"] for e in session.log]
        assert "session_start" in types

    def test_session_start_not_logged_on_second_question(self, session):
        run(session.set_question("Q1?", ["A"]))
        run(session.set_question("Q2?", ["B"]))
        start_events = [e for e in session.log if e["event_type"] == "session_start"]
        assert len(start_events) == 1

    def test_session_start_detail_has_started_at(self, session):
        run(session.set_question("Q?", ["A"]))
        entry = next(e for e in session.log if e["event_type"] == "session_start")
        assert "started_at" in entry["detail"]


class TestQuestionPostedLogging:
    def test_question_posted_logged(self, session):
        run(session.set_question("What colour?", ["red", "blue"]))
        types = [e["event_type"] for e in session.log]
        assert "question_posted" in types

    def test_question_posted_detail_has_text_and_options(self, session):
        run(session.set_question("What?", ["X", "Y"]))
        entry = next(e for e in session.log if e["event_type"] == "question_posted")
        assert entry["detail"]["text"] == "What?"
        assert entry["detail"]["options"] == ["X", "Y"]

    def test_question_posted_logged_each_time(self, session):
        run(session.set_question("Q1?", ["A"]))
        run(session.set_question("Q2?", ["B"]))
        posted = [e for e in session.log if e["event_type"] == "question_posted"]
        assert len(posted) == 2


class TestAnswerSubmittedLogging:
    def test_answer_submitted_logged(self, session):
        run(session.set_question("Q?", ["Yes", "No"]))
        run(session.submit_answer("Yes"))
        types = [e["event_type"] for e in session.log]
        assert "answer_submitted" in types

    def test_answer_submitted_detail_has_value(self, session):
        run(session.set_question("Q?", ["A", "B"]))
        run(session.submit_answer("A"))
        entry = next(e for e in session.log if e["event_type"] == "answer_submitted")
        assert entry["detail"]["value"] == "A"


class TestSessionEndLogging:
    def test_session_end_logged_on_reset(self, session):
        run(session.set_question("Q?", ["A"]))
        run(session.reset(features_created=2))
        # Log was saved to _last_session_log, session.log is cleared
        log = state_module._last_session_log
        types = [e["event_type"] for e in log]
        assert "session_end" in types

    def test_session_end_detail_has_features_created(self, session):
        # We test via the module-level singleton since reset() uses 'global'
        s = get_interview_session()
        run(s.set_question("Q?", ["A"]))
        s.owner_token = "tok"
        run(s.reset(features_created=3))
        log = state_module._last_session_log
        entry = next(e for e in log if e["event_type"] == "session_end")
        assert entry["detail"]["features_created"] == 3

    def test_answer_timeout_logged_on_timeout(self, session):
        run(session.set_question("Q?", ["A"]))
        run(session.timeout())
        log = state_module._last_session_log
        types = [e["event_type"] for e in log]
        assert "answer_timeout" in types


# ---------------------------------------------------------------------------
# Log cleared after session end, saved to _last_session_log
# ---------------------------------------------------------------------------

class TestLogSavedAfterSessionEnd:
    def test_session_log_cleared_after_reset(self, session):
        run(session.set_question("Q?", ["A"]))
        run(session.reset())
        assert len(session.log) == 0

    def test_last_session_log_set_after_reset(self, session):
        run(session.set_question("Q?", ["A"]))
        run(session.reset())
        assert state_module._last_session_log is not None

    def test_last_session_log_time_set_after_reset(self, session):
        run(session.set_question("Q?", ["A"]))
        run(session.reset())
        assert state_module._last_session_log_time is not None

    def test_last_session_log_set_after_timeout(self, session):
        run(session.set_question("Q?", ["A"]))
        run(session.timeout())
        assert state_module._last_session_log is not None

    def test_session_log_cleared_after_timeout(self, session):
        run(session.set_question("Q?", ["A"]))
        run(session.timeout())
        assert len(session.log) == 0


# ---------------------------------------------------------------------------
# get_debug_log()
# ---------------------------------------------------------------------------

class TestGetDebugLog:
    def test_returns_none_when_no_active_session_and_no_history(self):
        result = get_debug_log()
        assert result is None

    def test_returns_active_true_when_session_active(self):
        s = get_interview_session()
        s.owner_token = "active-token"
        result = get_debug_log()
        assert result is not None
        assert result["active"] is True

    def test_returns_session_log_when_active(self):
        s = get_interview_session()
        s.owner_token = "tok"
        _log_event(s, "test_event", {"x": 1})
        result = get_debug_log()
        assert len(result["log"]) == 1
        assert result["log"][0]["event_type"] == "test_event"

    def test_returns_active_false_for_recent_ended_session(self):
        state_module._last_session_log = [{"event_type": "session_end", "detail": {}, "timestamp": "t"}]
        state_module._last_session_log_time = time.monotonic()
        result = get_debug_log()
        assert result is not None
        assert result["active"] is False

    def test_returns_last_log_for_recent_ended_session(self):
        state_module._last_session_log = [{"event_type": "session_end", "detail": {}, "timestamp": "t"}]
        state_module._last_session_log_time = time.monotonic()
        result = get_debug_log()
        assert result["log"][0]["event_type"] == "session_end"

    def test_returns_none_when_last_session_log_expired(self):
        state_module._last_session_log = [{"event_type": "session_end", "detail": {}, "timestamp": "t"}]
        state_module._last_session_log_time = time.monotonic() - 61.0  # expired
        result = get_debug_log()
        assert result is None

    def test_active_session_takes_priority_over_last_log(self):
        # Both active session and last session log exist
        state_module._last_session_log = [{"event_type": "session_end", "detail": {}, "timestamp": "t"}]
        state_module._last_session_log_time = time.monotonic()
        s = get_interview_session()
        s.owner_token = "tok"
        result = get_debug_log()
        assert result["active"] is True


# ---------------------------------------------------------------------------
# HTTP: GET /api/interview/debug
# ---------------------------------------------------------------------------

class TestDebugEndpoint:
    def test_returns_404_when_no_session(self, client):
        resp = client.get("/api/interview/debug")
        assert resp.status_code == 404

    def test_returns_200_when_session_active(self, client):
        s = get_interview_session()
        s.owner_token = "tok"
        resp = client.get("/api/interview/debug")
        assert resp.status_code == 200

    def test_response_has_active_field(self, client):
        s = get_interview_session()
        s.owner_token = "tok"
        data = client.get("/api/interview/debug").json()
        assert "active" in data

    def test_response_has_log_field(self, client):
        s = get_interview_session()
        s.owner_token = "tok"
        data = client.get("/api/interview/debug").json()
        assert "log" in data
        assert isinstance(data["log"], list)

    def test_returns_200_within_60s_of_session_end(self, client):
        state_module._last_session_log = [{"event_type": "session_end", "detail": {}, "timestamp": "t"}]
        state_module._last_session_log_time = time.monotonic()
        resp = client.get("/api/interview/debug")
        assert resp.status_code == 200

    def test_returns_404_after_60s_window_expired(self, client):
        state_module._last_session_log = [{"event_type": "session_end", "detail": {}, "timestamp": "t"}]
        state_module._last_session_log_time = time.monotonic() - 61.0
        resp = client.get("/api/interview/debug")
        assert resp.status_code == 404

    def test_full_flow_logs_question_and_answer(self, client):
        """Full session: post question, submit answer, delete session → debug log has expected events."""
        # Post question (starts session)
        resp = client.post(
            "/api/interview/question",
            json={"text": "Favourite colour?", "options": ["red", "blue"]},
        )
        assert resp.status_code == 200
        token = resp.json()["session_token"]

        # Submit answer
        client.post("/api/interview/answer", json={"value": "red"})

        # Check debug while session is active
        data = client.get("/api/interview/debug").json()
        assert data["active"] is True
        event_types = [e["event_type"] for e in data["log"]]
        assert "session_start" in event_types
        assert "question_posted" in event_types
        assert "answer_submitted" in event_types

        # End session
        client.delete("/api/interview/session")

        # Check debug after session ended (within 60s window)
        data = client.get("/api/interview/debug").json()
        assert data["active"] is False
        event_types = [e["event_type"] for e in data["log"]]
        assert "session_end" in event_types
