"""
End-to-end integration tests for the full interview flow.
==========================================================

Simulates both sides of the interview protocol concurrently against a real
uvicorn server started in a background thread:

  Claude side:   POST /api/interview/question
                 GET  /api/interview/answer       (long-poll, blocks until browser responds)
                 DELETE /api/interview/session    (when done)

  Browser side:  GET  /api/interview/question/stream  (SSE, receives questions)
                 POST /api/interview/answer            (submits user answers)

These tests validate the *transport layer* of the interview protocol:
  - Questions are broadcast to SSE subscribers
  - Answers are reliably delivered via the long-poll endpoint
  - Multi-round Q&A cycles work correctly
  - Session lifecycle (start, complete, timeout) behaves correctly
  - Duplicate-session guard prevents multiple simultaneous owners

httpx.ASGITransport buffers the full response body before returning, so it
cannot be used for SSE or long-poll endpoints. A real uvicorn server with
genuine TCP connections is required for those tests.
"""

import asyncio
import json
import socket
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn

sys.path.insert(0, str(Path(__file__).parent.parent))

import backend.interview_state as state_module
import backend.main as main_module
from backend.main import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_interview_state():
    """Reset the interview session singleton before and after every test."""
    session = state_module.get_interview_session()
    session.active_question = None
    session.pending_answer = None
    session.owner_token = None
    session.started_at = None
    session._answer_ready = asyncio.Event()
    session._subscribers = []
    session.log.clear()
    state_module._last_session_log = None
    state_module._last_session_log_time = None
    yield
    session.active_question = None
    session.pending_answer = None
    session.owner_token = None
    session.started_at = None
    session._answer_ready = asyncio.Event()
    session._subscribers = []
    session.log.clear()
    state_module._last_session_log = None
    state_module._last_session_log_time = None


@pytest.fixture(scope="module")
def live_server():
    """
    Start a real uvicorn server in a background thread for SSE and long-poll tests.

    Yields the base URL string so tests can open genuine HTTP connections.
    Uses an ephemeral port to avoid conflicts with DevServer or other test modules.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="critical",
    )
    server = uvicorn.Server(config)

    loop_holder: list[asyncio.AbstractEventLoop] = []

    def run_server():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop_holder.append(loop)
        loop.run_until_complete(server.serve())

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()

    # Wait for the event loop to be created
    deadline = time.monotonic() + 5.0
    while not loop_holder and time.monotonic() < deadline:
        time.sleep(0.01)
    if not loop_holder:
        raise RuntimeError("Server event loop did not start within 5 s")

    base_url = f"http://127.0.0.1:{port}"

    # Wait until the server is accepting connections
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        try:
            with httpx.Client(timeout=0.5) as probe:
                probe.get(f"{base_url}/api/features")
            break
        except Exception:
            time.sleep(0.05)
    else:
        raise RuntimeError("Live test server did not start within 10 s")

    yield base_url

    server.should_exit = True
    thread.join(timeout=5)


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------


def _read_sse_events(
    response: httpx.Response,
    *,
    stop_after: int = 1,
) -> list[tuple[str, dict]]:
    """
    Read lines from an open SSE streaming response until ``stop_after`` events
    have been collected, then return them as (event_type, data_dict) tuples.
    """
    events: list[tuple[str, dict]] = []
    current_event_type: str | None = None
    for line in response.iter_lines():
        if line.startswith("event:"):
            current_event_type = line[len("event:"):].strip()
        elif line.startswith("data:") and current_event_type is not None:
            events.append((current_event_type, json.loads(line[len("data:"):].strip())))
            current_event_type = None
            if len(events) >= stop_after:
                break
    return events


# ---------------------------------------------------------------------------
# Interview flow helpers (simulate Claude side and Browser side)
# ---------------------------------------------------------------------------


def _claude_post_question(
    base_url: str,
    text: str,
    options: list[str],
    token: str | None = None,
) -> tuple[dict, str | None]:
    """
    Claude side: post a question to the interview session.

    Returns (response_json, active_token).
    On the first POST, response_json contains ``session_token``.
    Subsequent POSTs return the same token passed in.
    """
    headers = {}
    if token:
        headers["X-Interview-Token"] = token
    with httpx.Client() as client:
        resp = client.post(
            f"{base_url}/api/interview/question",
            json={"text": text, "options": options},
            headers=headers,
        )
    resp.raise_for_status()
    data = resp.json()
    active_token = data.get("session_token") or token
    return data, active_token


def _claude_get_answer(base_url: str, http_timeout: float = 30.0) -> str | None:
    """
    Claude side: long-poll for the browser's answer.

    Returns the answer string, or None if the server responded with 408 (timeout).
    The http_timeout controls how long the httpx client waits before giving up.
    The server-side poll timeout is controlled by main_module._ANSWER_POLL_TIMEOUT_SECONDS.
    """
    with httpx.Client(timeout=http_timeout) as client:
        resp = client.get(f"{base_url}/api/interview/answer")
    if resp.status_code == 408:
        return None
    resp.raise_for_status()
    return resp.json()["value"]


def _browser_post_answer(base_url: str, value: str) -> dict:
    """Browser side: submit an answer to the current question."""
    with httpx.Client() as client:
        resp = client.post(f"{base_url}/api/interview/answer", json={"value": value})
    resp.raise_for_status()
    return resp.json()


def _claude_end_session(base_url: str, features_created: int = 0) -> dict:
    """Claude side: end the current interview session."""
    with httpx.Client() as client:
        resp = client.delete(
            f"{base_url}/api/interview/session",
            params={"features_created": features_created},
        )
    resp.raise_for_status()
    return resp.json()


def _run_one_round(
    base_url: str,
    question: str,
    options: list[str],
    answer: str,
    token: str | None,
) -> str | None:
    """
    Complete one interview round end-to-end:
    1. Claude posts the question.
    2. Claude starts long-polling for the answer in a background thread.
    3. Browser submits the answer.
    4. Verify Claude received the correct answer.

    Returns the active session token.
    """
    data, token = _claude_post_question(base_url, question, options, token=token)

    answer_result: list[str | None] = []

    def poll():
        answer_result.append(_claude_get_answer(base_url))

    poll_thread = threading.Thread(target=poll, daemon=True)
    poll_thread.start()

    time.sleep(0.05)  # give the server time to enter wait_for_answer()
    _browser_post_answer(base_url, answer)

    poll_thread.join(timeout=10.0)
    assert answer_result == [answer], f"Expected {answer!r}, got {answer_result!r}"
    return token


# ---------------------------------------------------------------------------
# Single-round tests (basic Q&A cycle)
# ---------------------------------------------------------------------------


class TestSingleRound:
    """Verify the fundamental request-response cycle works end-to-end."""

    def test_claude_posts_question_browser_answers_claude_receives(self, live_server):
        """Claude posts a question, browser answers, Claude receives the correct value."""
        base_url = live_server
        _claude_post_question(base_url, "Which category?", ["Backend", "Frontend"])

        answer_result: list[str | None] = []

        def poll():
            answer_result.append(_claude_get_answer(base_url))

        poll_thread = threading.Thread(target=poll, daemon=True)
        poll_thread.start()

        time.sleep(0.05)
        _browser_post_answer(base_url, "Backend")

        poll_thread.join(timeout=10.0)
        assert answer_result == ["Backend"]

    def test_session_token_returned_on_first_post(self, live_server):
        """The first question response includes a non-empty session_token."""
        data, token = _claude_post_question(live_server, "Category?", ["A", "B"])
        assert "session_token" in data
        assert token is not None and len(token) > 10

    def test_subsequent_question_does_not_return_token(self, live_server):
        """Subsequent questions (with valid token) do not include session_token."""
        base_url = live_server
        _, token = _claude_post_question(base_url, "Category?", ["A", "B"])

        # Consume the answer so the next question can be posted
        _browser_post_answer(base_url, "A")
        _claude_get_answer(base_url)

        data2, _ = _claude_post_question(base_url, "Name?", ["foo", "bar"], token=token)
        assert "session_token" not in data2

    def test_answer_is_cleared_after_claude_consumes_it(self, live_server):
        """After Claude consumes the answer via GET /answer, pending_answer is None."""
        base_url = live_server
        _claude_post_question(base_url, "Q?", ["Yes", "No"])
        _browser_post_answer(base_url, "Yes")
        answer = _claude_get_answer(base_url)

        assert answer == "Yes"
        session = state_module.get_interview_session()
        assert session.pending_answer is None

    def test_session_active_after_one_round(self, live_server):
        """The session remains active (owner_token set) after one complete round."""
        base_url = live_server
        _run_one_round(base_url, "Category?", ["Backend"], "Backend", None)

        session = state_module.get_interview_session()
        assert session.owner_token is not None


# ---------------------------------------------------------------------------
# Multi-round tests (simulate full interview)
# ---------------------------------------------------------------------------


class TestMultiRound:
    """Simulate a complete multi-question interview session."""

    def test_four_question_interview_completes_successfully(self, live_server):
        """
        Simulate a 4-question interview (category, name, description, steps).
        Each round: Claude posts → browser answers → Claude receives.
        """
        base_url = live_server

        SCRIPT = [
            ("What category?", ["Backend", "Frontend", "Data"], "Backend"),
            ("Feature name?",  ["My Feature", "New Feature"],   "My Feature"),
            ("Description?",   ["Short", "Long"],               "Short"),
            ("How many steps?", ["1", "2", "3", "4"],           "3"),
        ]

        token = None
        for question, options, answer in SCRIPT:
            token = _run_one_round(base_url, question, options, answer, token)

        # Session still alive — token is set
        session = state_module.get_interview_session()
        assert session.owner_token is not None

    def test_summary_and_end_session_sends_sse_end_event(self, live_server):
        """
        After Q&A rounds, ending the session broadcasts an 'end' event with
        features_created count to SSE subscribers.
        """
        base_url = live_server

        # Complete one round first
        token = _run_one_round(base_url, "Category?", ["Backend"], "Backend", None)

        # Subscribe to SSE to capture the end event
        sse_events: list[tuple[str, dict]] = []
        sse_ready = threading.Event()
        sse_done = threading.Event()

        def read_stream():
            with httpx.Client(timeout=10.0) as client:
                with client.stream("GET", f"{base_url}/api/interview/question/stream") as resp:
                    sse_ready.set()
                    # The stale active_question is sent immediately on connect, so we
                    # read up to 2 events: the existing question + the end event.
                    events = _read_sse_events(resp, stop_after=2)
                    sse_events.extend(events)
            sse_done.set()

        t = threading.Thread(target=read_stream, daemon=True)
        t.start()
        assert sse_ready.wait(timeout=5.0), "SSE stream did not connect"

        _claude_end_session(base_url, features_created=1)

        assert sse_done.wait(timeout=5.0), "SSE stream did not receive 'end' event"
        t.join(timeout=2.0)

        end_events = [e for e in sse_events if e[0] == "end"]
        assert len(end_events) == 1
        assert end_events[0][1].get("features_created") == 1

    def test_session_state_cleared_after_end(self, live_server):
        """After DELETE /session, all session state is cleared."""
        base_url = live_server
        token = _run_one_round(base_url, "Q?", ["A"], "A", None)
        _claude_end_session(base_url)

        session = state_module.get_interview_session()
        assert session.owner_token is None
        assert session.active_question is None
        assert session.pending_answer is None

    def test_three_rounds_all_answers_delivered(self, live_server):
        """All answers in a 3-round session are delivered correctly to Claude."""
        base_url = live_server

        ROUNDS = [
            ("Category?",    ["Backend"], "Backend"),
            ("Name?",        ["Feature X"], "Feature X"),
            ("Description?", ["A short desc"], "A short desc"),
        ]

        token = None
        for question, options, expected_answer in ROUNDS:
            token = _run_one_round(base_url, question, options, expected_answer, token)


# ---------------------------------------------------------------------------
# SSE broadcast tests
# ---------------------------------------------------------------------------


class TestSSEBroadcasts:
    """Verify SSE broadcasts questions and events to the browser in real time."""

    def test_sse_receives_question_broadcast_when_subscribed_first(self, live_server):
        """
        Browser subscribes before Claude posts a question.
        The SSE stream receives the question event.
        """
        base_url = live_server

        sse_events: list[tuple[str, dict]] = []
        sse_ready = threading.Event()
        sse_done = threading.Event()

        def read_stream():
            with httpx.Client(timeout=10.0) as client:
                with client.stream("GET", f"{base_url}/api/interview/question/stream") as resp:
                    sse_ready.set()
                    events = _read_sse_events(resp, stop_after=1)
                    sse_events.extend(events)
            sse_done.set()

        t = threading.Thread(target=read_stream, daemon=True)
        t.start()
        assert sse_ready.wait(timeout=5.0), "SSE stream did not connect"

        _claude_post_question(base_url, "What category?", ["Backend", "Frontend"])

        assert sse_done.wait(timeout=5.0), "SSE did not receive question event"
        t.join(timeout=2.0)

        assert len(sse_events) == 1
        event_type, data = sse_events[0]
        assert event_type == "question"
        assert data["text"] == "What category?"
        assert "Backend" in data["options"]
        assert "Frontend" in data["options"]

    def test_sse_receives_existing_question_on_late_connect(self, live_server):
        """
        Browser connects *after* Claude has already posted a question.
        The SSE stream immediately receives the existing question.
        """
        base_url = live_server

        _claude_post_question(base_url, "Pre-existing question", ["A", "B"])

        with httpx.Client() as client:
            with client.stream("GET", f"{base_url}/api/interview/question/stream") as resp:
                events = _read_sse_events(resp, stop_after=1)

        assert len(events) == 1
        assert events[0][0] == "question"
        assert events[0][1]["text"] == "Pre-existing question"

    def test_sse_receives_answer_received_event(self, live_server):
        """Browser SSE receives 'answer_received' when an answer is submitted."""
        base_url = live_server

        _claude_post_question(base_url, "Pick one:", ["A", "B"])

        sse_events: list[tuple[str, dict]] = []
        sse_ready = threading.Event()
        sse_done = threading.Event()

        def read_stream():
            with httpx.Client(timeout=10.0) as client:
                with client.stream("GET", f"{base_url}/api/interview/question/stream") as resp:
                    sse_ready.set()
                    # Expect existing question event + answer_received event
                    events = _read_sse_events(resp, stop_after=2)
                    sse_events.extend(events)
            sse_done.set()

        t = threading.Thread(target=read_stream, daemon=True)
        t.start()
        assert sse_ready.wait(timeout=5.0)

        time.sleep(0.05)
        _browser_post_answer(base_url, "A")

        assert sse_done.wait(timeout=5.0), "SSE did not receive answer_received event"
        t.join(timeout=2.0)

        event_types = [e[0] for e in sse_events]
        assert "answer_received" in event_types

    def test_sse_receives_all_questions_in_multi_round_session(self, live_server):
        """SSE subscriber receives a question event for each round of the interview."""
        base_url = live_server

        ROUNDS = [
            ("Category?", ["Backend", "Frontend"], "Backend"),
            ("Name?",     ["My Feature"],          "My Feature"),
            ("Done?",     ["Yes", "No"],            "Yes"),
        ]

        sse_events: list[tuple[str, dict]] = []
        sse_ready = threading.Event()
        sse_done = threading.Event()

        def read_stream():
            with httpx.Client(timeout=20.0) as client:
                with client.stream("GET", f"{base_url}/api/interview/question/stream") as resp:
                    sse_ready.set()
                    # 1 question event + 1 answer_received event per round
                    events = _read_sse_events(resp, stop_after=len(ROUNDS) * 2)
                    sse_events.extend(events)
            sse_done.set()

        t = threading.Thread(target=read_stream, daemon=True)
        t.start()
        assert sse_ready.wait(timeout=5.0), "SSE stream did not connect"

        token = None
        for question, options, answer in ROUNDS:
            _, token = _claude_post_question(base_url, question, options, token=token)
            time.sleep(0.05)
            _browser_post_answer(base_url, answer)
            _claude_get_answer(base_url)
            time.sleep(0.05)

        # SSE reader has already collected all events (6 events = 3 questions + 3 answer_received)
        # End session cleanly
        _claude_end_session(base_url)
        sse_done.wait(timeout=5.0)
        t.join(timeout=2.0)

        question_events = [e for e in sse_events if e[0] == "question"]
        assert len(question_events) == len(ROUNDS)
        for i, (expected_text, _, _) in enumerate(ROUNDS):
            assert question_events[i][1]["text"] == expected_text

    def test_sse_end_event_carries_features_created_count(self, live_server):
        """The 'end' SSE event includes the features_created count from DELETE /session."""
        base_url = live_server

        sse_events: list[tuple[str, dict]] = []
        sse_ready = threading.Event()
        sse_done = threading.Event()

        def read_stream():
            with httpx.Client(timeout=10.0) as client:
                with client.stream("GET", f"{base_url}/api/interview/question/stream") as resp:
                    sse_ready.set()
                    events = _read_sse_events(resp, stop_after=1)
                    sse_events.extend(events)
            sse_done.set()

        t = threading.Thread(target=read_stream, daemon=True)
        t.start()
        assert sse_ready.wait(timeout=5.0)

        _claude_end_session(base_url, features_created=3)

        assert sse_done.wait(timeout=5.0), "SSE did not receive 'end' event"
        t.join(timeout=2.0)

        assert sse_events[0][0] == "end"
        assert sse_events[0][1]["features_created"] == 3


# ---------------------------------------------------------------------------
# Error case tests
# ---------------------------------------------------------------------------


class TestErrorCases:
    """Verify the interview API enforces its protocol constraints."""

    def test_duplicate_session_returns_409(self, live_server):
        """Second Claude instance trying to start a session while one is active gets 409."""
        base_url = live_server

        _claude_post_question(base_url, "First question?", ["A"])

        # Second caller has no token — must be rejected
        with httpx.Client() as client:
            resp = client.post(
                f"{base_url}/api/interview/question",
                json={"text": "Hijack attempt?", "options": ["B"]},
            )
        assert resp.status_code == 409

    def test_wrong_token_returns_409(self, live_server):
        """POST with the wrong session token is rejected with 409."""
        base_url = live_server

        _claude_post_question(base_url, "First question?", ["A"])

        with httpx.Client() as client:
            resp = client.post(
                f"{base_url}/api/interview/question",
                json={"text": "Wrong token?", "options": ["B"]},
                headers={"X-Interview-Token": "wrong-token-xyz"},
            )
        assert resp.status_code == 409

    def test_answer_timeout_returns_408(self, live_server):
        """GET /answer returns 408 when no answer arrives within the poll timeout."""
        base_url = live_server
        original = main_module._ANSWER_POLL_TIMEOUT_SECONDS
        main_module._ANSWER_POLL_TIMEOUT_SECONDS = 0.05
        try:
            _claude_post_question(base_url, "Q?", ["A"])

            with httpx.Client(timeout=10.0) as client:
                resp = client.get(f"{base_url}/api/interview/answer")
            assert resp.status_code == 408
        finally:
            main_module._ANSWER_POLL_TIMEOUT_SECONDS = original

    def test_answer_timeout_clears_session_state(self, live_server):
        """After a timeout, owner_token and active_question are cleared."""
        base_url = live_server
        original = main_module._ANSWER_POLL_TIMEOUT_SECONDS
        main_module._ANSWER_POLL_TIMEOUT_SECONDS = 0.05
        try:
            _claude_post_question(base_url, "Q?", ["A"])

            with httpx.Client(timeout=10.0) as client:
                client.get(f"{base_url}/api/interview/answer")  # triggers timeout

            session = state_module.get_interview_session()
            assert session.owner_token is None
            assert session.active_question is None
        finally:
            main_module._ANSWER_POLL_TIMEOUT_SECONDS = original

    def test_answer_timeout_broadcasts_session_timeout_sse_event(self, live_server):
        """A timeout broadcasts 'session-timeout' to SSE subscribers."""
        base_url = live_server
        original = main_module._ANSWER_POLL_TIMEOUT_SECONDS
        main_module._ANSWER_POLL_TIMEOUT_SECONDS = 0.05

        try:
            _claude_post_question(base_url, "Q?", ["A"])

            sse_events: list[tuple[str, dict]] = []
            sse_ready = threading.Event()
            sse_done = threading.Event()

            def read_stream():
                with httpx.Client(timeout=10.0) as client:
                    with client.stream("GET", f"{base_url}/api/interview/question/stream") as resp:
                        sse_ready.set()
                        # We'll get the pre-existing question + the session-timeout
                        events = _read_sse_events(resp, stop_after=2)
                        sse_events.extend(events)
                sse_done.set()

            t = threading.Thread(target=read_stream, daemon=True)
            t.start()
            assert sse_ready.wait(timeout=5.0)

            # Trigger the timeout
            with httpx.Client(timeout=10.0) as client:
                client.get(f"{base_url}/api/interview/answer")

            assert sse_done.wait(timeout=5.0), "SSE did not receive timeout event"
            t.join(timeout=2.0)

            event_types = [e[0] for e in sse_events]
            assert "session-timeout" in event_types
        finally:
            main_module._ANSWER_POLL_TIMEOUT_SECONDS = original

    def test_post_answer_without_active_question_returns_400(self, live_server):
        """Submitting an answer when no question is active returns 400."""
        with httpx.Client() as client:
            resp = client.post(
                f"{live_server}/api/interview/answer",
                json={"value": "orphan answer"},
            )
        assert resp.status_code == 400

    def test_concurrent_answer_submissions_rejected(self, live_server):
        """Second answer while the first is still pending returns 400."""
        base_url = live_server
        _claude_post_question(base_url, "Pick one:", ["A", "B"])
        _browser_post_answer(base_url, "A")

        # Second answer before Claude consumed the first
        with httpx.Client() as client:
            resp = client.post(
                f"{base_url}/api/interview/answer",
                json={"value": "B"},
            )
        assert resp.status_code == 400

    def test_new_question_before_consuming_answer_returns_409(self, live_server):
        """Claude cannot post a new question while the browser's answer is unconsumed."""
        base_url = live_server
        _, token = _claude_post_question(base_url, "Q1?", ["A", "B"])
        _browser_post_answer(base_url, "A")
        # Do NOT call _claude_get_answer — answer is still pending

        with httpx.Client() as client:
            resp = client.post(
                f"{base_url}/api/interview/question",
                json={"text": "Q2?", "options": ["C"]},
                headers={"X-Interview-Token": token},
            )
        assert resp.status_code == 409

    def test_end_session_is_idempotent(self, live_server):
        """DELETE /session can be called multiple times without error."""
        base_url = live_server
        _claude_end_session(base_url)   # no active session
        _claude_end_session(base_url)   # still safe

    def test_new_session_can_start_after_previous_ends(self, live_server):
        """After one session ends, a fresh session starts with a new token."""
        base_url = live_server

        data1, token1 = _claude_post_question(base_url, "Q1?", ["A"])
        _browser_post_answer(base_url, "A")
        _claude_get_answer(base_url)
        _claude_end_session(base_url)

        data2, token2 = _claude_post_question(base_url, "Q2?", ["B"])
        assert "session_token" in data2
        assert token2 != token1


# ---------------------------------------------------------------------------
# Continuation paths (Yes = loop, No = end)
# ---------------------------------------------------------------------------


class TestContinuationPaths:
    """Simulate the 'create another feature?' decision point."""

    def test_yes_answer_allows_session_to_continue(self, live_server):
        """
        After answering 'Yes', the session stays active and Claude can post
        more questions using the same token.
        """
        base_url = live_server

        data, token = _claude_post_question(
            base_url, "Create another feature?", ["Yes", "No"]
        )

        # Browser answers Yes
        _browser_post_answer(base_url, "Yes")
        answer = _claude_get_answer(base_url)
        assert answer == "Yes"

        # Session still alive — Claude can continue with same token
        data2, token2 = _claude_post_question(
            base_url, "Category for second feature?", ["Backend"], token=token
        )
        assert data2["text"] == "Category for second feature?"
        assert token2 == token  # token is unchanged

    def test_no_answer_allows_session_to_end_cleanly(self, live_server):
        """
        After answering 'No', Claude ends the session and SSE receives 'end'.
        """
        base_url = live_server

        _claude_post_question(
            base_url, "Create another feature?", ["Yes", "No"]
        )
        _browser_post_answer(base_url, "No")
        answer = _claude_get_answer(base_url)
        assert answer == "No"

        result = _claude_end_session(base_url, features_created=1)
        assert result["message"] == "Session ended"

        session = state_module.get_interview_session()
        assert session.owner_token is None

    def test_two_feature_loop_completes(self, live_server):
        """
        Simulate creating two features in one session (Yes loop, then No to end).
        """
        base_url = live_server

        # Feature 1
        token = _run_one_round(base_url, "Category?", ["Backend"], "Backend", None)
        token = _run_one_round(base_url, "Name?", ["Feature A"], "Feature A", token)

        # Loop: create another?
        _, token = _claude_post_question(base_url, "Another?", ["Yes", "No"], token=token)
        _browser_post_answer(base_url, "Yes")
        loop_answer = _claude_get_answer(base_url)
        assert loop_answer == "Yes"

        # Feature 2 (same session, same token)
        token = _run_one_round(base_url, "Category?", ["Frontend"], "Frontend", token)
        token = _run_one_round(base_url, "Name?", ["Feature B"], "Feature B", token)

        # End: create another?
        _, token = _claude_post_question(base_url, "Another?", ["Yes", "No"], token=token)
        _browser_post_answer(base_url, "No")
        end_answer = _claude_get_answer(base_url)
        assert end_answer == "No"

        _claude_end_session(base_url, features_created=2)

        session = state_module.get_interview_session()
        assert session.owner_token is None


# ---------------------------------------------------------------------------
# Debug log tests
# ---------------------------------------------------------------------------


class TestDebugLog:
    """Verify the debug log captures key lifecycle events from the full session."""

    def test_debug_log_active_true_during_session(self, live_server):
        """GET /api/interview/debug returns active=True while a session is in progress."""
        base_url = live_server

        _claude_post_question(base_url, "Category?", ["Backend"])

        with httpx.Client() as client:
            resp = client.get(f"{base_url}/api/interview/debug")

        assert resp.status_code == 200
        assert resp.json()["active"] is True

    def test_debug_log_contains_expected_events_after_full_session(self, live_server):
        """The debug log records session_start, question_posted, answer_submitted, session_end."""
        base_url = live_server

        token = _run_one_round(base_url, "Category?", ["Backend"], "Backend", None)
        _claude_end_session(base_url, features_created=1)

        with httpx.Client() as client:
            resp = client.get(f"{base_url}/api/interview/debug")

        assert resp.status_code == 200
        data = resp.json()
        event_types = [e["event_type"] for e in data["log"]]

        assert "session_start" in event_types
        assert "question_posted" in event_types
        assert "answer_submitted" in event_types
        assert "session_end" in event_types

    def test_debug_log_active_false_after_session_ends(self, live_server):
        """GET /api/interview/debug returns active=False within 60 s of session end."""
        base_url = live_server

        _run_one_round(base_url, "Q?", ["A"], "A", None)
        _claude_end_session(base_url)

        with httpx.Client() as client:
            resp = client.get(f"{base_url}/api/interview/debug")

        assert resp.status_code == 200
        assert resp.json()["active"] is False

    def test_debug_log_question_posted_detail_correct(self, live_server):
        """The question_posted log entry includes the question text and options."""
        base_url = live_server

        _claude_post_question(base_url, "My question?", ["Option A", "Option B"])

        with httpx.Client() as client:
            resp = client.get(f"{base_url}/api/interview/debug")

        data = resp.json()
        posted = next(
            (e for e in data["log"] if e["event_type"] == "question_posted"), None
        )
        assert posted is not None
        assert posted["detail"]["text"] == "My question?"
        assert "Option A" in posted["detail"]["options"]

    def test_debug_log_multi_round_session_has_multiple_question_posted_events(self, live_server):
        """A multi-round session has one question_posted entry per round."""
        base_url = live_server

        token = _run_one_round(base_url, "Q1?", ["A"], "A", None)
        token = _run_one_round(base_url, "Q2?", ["B"], "B", token)
        _run_one_round(base_url, "Q3?", ["C"], "C", token)

        session = state_module.get_interview_session()
        posted_events = [e for e in session.log if e["event_type"] == "question_posted"]
        assert len(posted_events) == 3
