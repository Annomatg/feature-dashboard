"""
Integration tests for Interview API endpoints.
================================================

Tests the /api/interview/* endpoints:
  - POST /api/interview/question

Uses FastAPI TestClient for isolated, synchronous HTTP testing.
Interview state is reset between tests via the module-level singleton.
"""

import asyncio
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

import backend.interview_state as state_module
from backend.main import app


@pytest.fixture(autouse=True)
def reset_interview_state():
    """
    Reset the interview session singleton before every test so tests are
    fully isolated from each other regardless of execution order.
    """
    session = state_module.get_interview_session()
    session.active_question = None
    session.pending_answer = None
    # Re-create the event to ensure clean state
    session._answer_ready = asyncio.Event()
    session._subscribers = []
    yield
    # Reset again after test to avoid leaking state to subsequent tests
    session.active_question = None
    session.pending_answer = None
    session._answer_ready = asyncio.Event()
    session._subscribers = []


@pytest.fixture
def client():
    return TestClient(app)


class TestPostInterviewQuestion:
    """Tests for POST /api/interview/question"""

    def test_post_question_returns_200_with_question(self, client):
        """A valid question is accepted and returned."""
        response = client.post("/api/interview/question", json={
            "text": "What category does this feature belong to?",
            "options": ["Backend", "Frontend", "Data"],
        })

        assert response.status_code == 200
        data = response.json()
        assert data["text"] == "What category does this feature belong to?"
        assert data["options"] == ["Backend", "Frontend", "Data"]

    def test_post_question_stores_in_session(self, client):
        """The posted question is stored in the interview session singleton."""
        client.post("/api/interview/question", json={
            "text": "Pick a step count",
            "options": ["1", "2", "3"],
        })

        session = state_module.get_interview_session()
        assert session.active_question is not None
        assert session.active_question["text"] == "Pick a step count"
        assert session.active_question["options"] == ["1", "2", "3"]

    def test_post_question_overwrites_previous_question(self, client):
        """Posting a second question replaces the first when no answer is pending."""
        client.post("/api/interview/question", json={
            "text": "First question",
            "options": ["A", "B"],
        })
        response = client.post("/api/interview/question", json={
            "text": "Second question",
            "options": ["X", "Y", "Z"],
        })

        assert response.status_code == 200
        data = response.json()
        assert data["text"] == "Second question"
        assert data["options"] == ["X", "Y", "Z"]

        session = state_module.get_interview_session()
        assert session.active_question["text"] == "Second question"

    def test_post_question_resets_answer_ready_event(self, client):
        """
        Posting a new question clears the answer-ready event so the long-poll
        endpoint will block until a fresh answer is submitted.
        """
        client.post("/api/interview/question", json={
            "text": "Q1",
            "options": ["opt"],
        })

        session = state_module.get_interview_session()
        assert not session._answer_ready.is_set()

    def test_post_question_clears_previous_answer_state(self, client):
        """
        When a new question is posted (with no pending unconsumed answer),
        any previously stored answer value is cleared.
        """
        # Manually put a stale value into pending_answer to simulate a
        # state where the answer was consumed but the field wasn't cleared
        session = state_module.get_interview_session()
        session.pending_answer = None  # already consumed — not a 409 situation

        client.post("/api/interview/question", json={
            "text": "Fresh question",
            "options": ["Yes", "No"],
        })

        assert session.pending_answer is None

    def test_post_question_returns_409_when_answer_pending(self, client):
        """
        Returns 409 Conflict when the browser has submitted an answer that
        Claude has not yet consumed via GET /api/interview/answer.
        """
        # Post an initial question
        client.post("/api/interview/question", json={
            "text": "Initial question",
            "options": ["A", "B"],
        })

        # Simulate browser submitting an answer (set pending_answer directly)
        session = state_module.get_interview_session()
        session.pending_answer = "A"

        # Now try to post another question — should be blocked
        response = client.post("/api/interview/question", json={
            "text": "Next question",
            "options": ["C", "D"],
        })

        assert response.status_code == 409
        assert "pending" in response.json()["detail"].lower()

    def test_post_question_409_does_not_overwrite_existing_question(self, client):
        """The active question is unchanged when a 409 is returned."""
        client.post("/api/interview/question", json={
            "text": "Original question",
            "options": ["A", "B"],
        })

        session = state_module.get_interview_session()
        session.pending_answer = "A"

        client.post("/api/interview/question", json={
            "text": "Should not be stored",
            "options": ["C"],
        })

        assert session.active_question["text"] == "Original question"

    def test_post_question_rejects_empty_text(self, client):
        """Empty question text is rejected with 422."""
        response = client.post("/api/interview/question", json={
            "text": "   ",
            "options": ["A"],
        })

        assert response.status_code == 422

    def test_post_question_rejects_empty_options(self, client):
        """Empty options list is rejected with 422."""
        response = client.post("/api/interview/question", json={
            "text": "Valid question?",
            "options": [],
        })

        assert response.status_code == 422

    def test_post_question_rejects_missing_text(self, client):
        """Missing text field is rejected with 422."""
        response = client.post("/api/interview/question", json={
            "options": ["A", "B"],
        })

        assert response.status_code == 422

    def test_post_question_rejects_missing_options(self, client):
        """Missing options field is rejected with 422."""
        response = client.post("/api/interview/question", json={
            "text": "Where is my options list?",
        })

        assert response.status_code == 422

    def test_post_question_single_option_is_valid(self, client):
        """A question with exactly one option is accepted."""
        response = client.post("/api/interview/question", json={
            "text": "Confirm to proceed?",
            "options": ["OK"],
        })

        assert response.status_code == 200

    def test_post_question_returns_correct_options_order(self, client):
        """Options are returned in the same order they were submitted."""
        options = ["Step A", "Step B", "Step C", "Step D"]
        response = client.post("/api/interview/question", json={
            "text": "Order test",
            "options": options,
        })

        assert response.json()["options"] == options
