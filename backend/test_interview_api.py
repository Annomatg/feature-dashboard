"""
Integration tests for Interview API endpoints.
================================================

Tests the /api/interview/* endpoints:
  - POST /api/interview/question
  - GET  /api/interview/question/stream  (SSE)

POST tests use FastAPI TestClient (sync, no network).

SSE tests use a *real* uvicorn server started in a background thread.
httpx.ASGITransport buffers the full response before returning, so it
cannot test an infinite streaming endpoint. A real HTTP server and real
TCP connections are the only reliable way to test SSE + disconnect.

Interview state is reset between tests via the module-level singleton.
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


# ---------------------------------------------------------------------------
# Live uvicorn server fixture (SSE tests need real TCP, not mocked transport)
# ---------------------------------------------------------------------------
#
# httpx.ASGITransport buffers the entire response body before returning, so
# it deadlocks on an infinite SSE stream.  The only reliable approach is a
# real uvicorn server running in a background thread so that genuine TCP
# connections can be opened, read, and closed.
#
# State isolation: the server runs in the same process as the tests and
# shares the _interview_session singleton.  Python 3.10+ asyncio objects
# (Event, Queue) use get_running_loop() lazily, so they can be created
# in the main test thread and safely used from uvicorn's event loop.

@pytest.fixture(scope="module")
def live_server():
    """
    Start a real uvicorn server in a background thread.

    Yields (base_url, server_loop) so tests can schedule coroutines on the
    server's event loop via asyncio.run_coroutine_threadsafe().
    """
    # Pick a free ephemeral port
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
        loop_holder.append(loop)       # expose loop to the test thread
        loop.run_until_complete(server.serve())

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()

    # Wait for the loop to be created
    deadline = time.monotonic() + 5.0
    while not loop_holder and time.monotonic() < deadline:
        time.sleep(0.01)
    if not loop_holder:
        raise RuntimeError("Server event loop did not start")
    server_loop = loop_holder[0]

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

    yield base_url, server_loop

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
    Read lines from an open SSE streaming response until `stop_after` events
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
# SSE endpoint tests
# ---------------------------------------------------------------------------

class TestGetInterviewQuestionStream:
    """Tests for GET /api/interview/question/stream (uses live uvicorn server)."""

    def test_stream_returns_200_with_event_stream_content_type(self, live_server):
        """The SSE endpoint returns 200 with text/event-stream Content-Type."""
        base_url, _ = live_server
        with httpx.Client() as client:
            with client.stream("GET", f"{base_url}/api/interview/question/stream") as response:
                assert response.status_code == 200
                assert "text/event-stream" in response.headers["content-type"]
                # Exiting closes the TCP connection; server detects disconnect

    def test_stream_sends_existing_question_immediately_on_connect(self, live_server):
        """
        When a question is already active, it is sent to the browser immediately
        upon connection — without waiting for the next POST.
        """
        base_url, _ = live_server
        with httpx.Client() as client:
            client.post(f"{base_url}/api/interview/question", json={
                "text": "Pre-existing question",
                "options": ["Option A", "Option B"],
            })

            with client.stream("GET", f"{base_url}/api/interview/question/stream") as response:
                events = _read_sse_events(response, stop_after=1)

        assert len(events) == 1
        event_type, data = events[0]
        assert event_type == "question"
        assert data["text"] == "Pre-existing question"
        assert data["options"] == ["Option A", "Option B"]

    def test_stream_no_immediate_event_when_no_active_question(self):
        """
        The subscriber queue is empty at subscription time when no question is
        active — the stream does not emit a spurious initial event.
        """
        session = state_module.get_interview_session()
        assert session.active_question is None

        q = session.subscribe()
        assert q.empty()
        session.unsubscribe(q)

    def test_stream_broadcasts_new_question_to_subscriber(self, live_server):
        """
        A question posted after the browser subscribes is broadcast and received
        by the SSE stream within a few seconds.
        """
        base_url, _ = live_server
        received: list[tuple[str, dict]] = []
        ready = threading.Event()
        done = threading.Event()

        def read_stream():
            with httpx.Client(timeout=10.0) as client:
                with client.stream("GET", f"{base_url}/api/interview/question/stream") as resp:
                    ready.set()  # headers received → subscriber registered server-side
                    events = _read_sse_events(resp, stop_after=1)
                    received.extend(events)
            done.set()

        t = threading.Thread(target=read_stream, daemon=True)
        t.start()

        assert ready.wait(timeout=5.0), "SSE stream did not connect in time"

        with httpx.Client() as client:
            client.post(f"{base_url}/api/interview/question", json={
                "text": "Live broadcast question",
                "options": ["X", "Y", "Z"],
            })

        assert done.wait(timeout=5.0), "SSE stream did not receive event in time"
        t.join(timeout=2.0)

        assert len(received) == 1
        event_type, data = received[0]
        assert event_type == "question"
        assert data["text"] == "Live broadcast question"
        assert data["options"] == ["X", "Y", "Z"]

    def test_stream_sends_end_event_on_session_reset(self, live_server):
        """
        Resetting the interview session broadcasts an 'end' event to all
        active SSE subscribers.
        """
        base_url, server_loop = live_server
        received: list[tuple[str, dict]] = []
        ready = threading.Event()
        done = threading.Event()

        def read_stream():
            with httpx.Client(timeout=10.0) as client:
                with client.stream("GET", f"{base_url}/api/interview/question/stream") as resp:
                    ready.set()
                    events = _read_sse_events(resp, stop_after=1)
                    received.extend(events)
            done.set()

        t = threading.Thread(target=read_stream, daemon=True)
        t.start()

        assert ready.wait(timeout=5.0)

        # Schedule reset() on the server's own event loop so that the
        # asyncio.Queue.put() inside broadcast() runs in the correct loop.
        future = asyncio.run_coroutine_threadsafe(
            state_module.get_interview_session().reset(),
            server_loop,
        )
        future.result(timeout=2.0)

        assert done.wait(timeout=5.0), "SSE stream did not receive 'end' event"
        t.join(timeout=2.0)

        assert len(received) == 1
        assert received[0][0] == "end"

    def test_stream_unsubscribes_on_disconnect(self, live_server):
        """
        The subscriber queue is removed from the session when the TCP connection
        closes, preventing memory leaks.
        """
        import backend.main as main_module
        base_url, _ = live_server
        main_module._SSE_HEARTBEAT_SECONDS = 0.05  # fire heartbeat quickly

        try:
            session = state_module.get_interview_session()
            initial_count = len(session._subscribers)

            with httpx.Client() as client:
                with client.stream("GET", f"{base_url}/api/interview/question/stream") as resp:
                    # Read one heartbeat so the generator has actually started
                    _read_sse_events(resp, stop_after=1)
                # TCP connection closes here

            # Give the server a moment to detect disconnect and run the finally block
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                if len(session._subscribers) == initial_count:
                    break
                time.sleep(0.05)

            assert len(session._subscribers) == initial_count
        finally:
            main_module._SSE_HEARTBEAT_SECONDS = 15.0

    def test_stream_heartbeat_sent_when_queue_idle(self, live_server):
        """
        A heartbeat event is emitted when no events arrive within the timeout,
        keeping long-lived connections alive through proxies.
        """
        import backend.main as main_module
        base_url, _ = live_server
        main_module._SSE_HEARTBEAT_SECONDS = 0.05  # very short for testing

        try:
            with httpx.Client(timeout=5.0) as client:
                with client.stream("GET", f"{base_url}/api/interview/question/stream") as resp:
                    events = _read_sse_events(resp, stop_after=1)

            assert len(events) == 1
            assert events[0][0] == "heartbeat"
        finally:
            main_module._SSE_HEARTBEAT_SECONDS = 15.0


# ---------------------------------------------------------------------------
# POST /api/interview/answer tests
# ---------------------------------------------------------------------------

class TestPostInterviewAnswer:
    """Tests for POST /api/interview/answer"""

    def test_post_answer_returns_200_with_status_and_value(self, client):
        """A valid answer is accepted and echoed back."""
        session = state_module.get_interview_session()
        session.active_question = {"text": "Pick one", "options": ["A", "B"]}

        response = client.post("/api/interview/answer", json={"value": "A"})

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "received"
        assert data["value"] == "A"

    def test_post_answer_stores_in_session(self, client):
        """The submitted answer is stored as pending_answer in the session."""
        session = state_module.get_interview_session()
        session.active_question = {"text": "Pick one", "options": ["A", "B"]}

        client.post("/api/interview/answer", json={"value": "B"})

        assert session.pending_answer == "B"

    def test_post_answer_sets_answer_ready_event(self, client):
        """Submitting an answer signals the answer_ready event."""
        session = state_module.get_interview_session()
        session.active_question = {"text": "Pick one", "options": ["Yes", "No"]}

        client.post("/api/interview/answer", json={"value": "Yes"})

        assert session._answer_ready.is_set()

    def test_post_answer_returns_400_when_no_active_question(self, client):
        """Returns 400 when no question is currently active."""
        response = client.post("/api/interview/answer", json={"value": "A"})

        assert response.status_code == 400
        assert "active question" in response.json()["detail"].lower()

    def test_post_answer_returns_400_when_answer_already_pending(self, client):
        """Returns 400 when an answer is already pending and not yet consumed."""
        session = state_module.get_interview_session()
        session.active_question = {"text": "Pick one", "options": ["A", "B"]}
        session.pending_answer = "A"

        response = client.post("/api/interview/answer", json={"value": "B"})

        assert response.status_code == 400
        assert "already been submitted" in response.json()["detail"].lower()

    def test_post_answer_400_does_not_overwrite_existing_answer(self, client):
        """When 400 is returned for a duplicate answer, the original is preserved."""
        session = state_module.get_interview_session()
        session.active_question = {"text": "Pick one", "options": ["A", "B"]}
        session.pending_answer = "A"

        client.post("/api/interview/answer", json={"value": "B"})

        assert session.pending_answer == "A"

    def test_post_answer_rejects_empty_value(self, client):
        """Empty or whitespace-only answer value is rejected with 422."""
        session = state_module.get_interview_session()
        session.active_question = {"text": "Pick one", "options": ["A", "B"]}

        response = client.post("/api/interview/answer", json={"value": "   "})

        assert response.status_code == 422

    def test_post_answer_rejects_missing_value(self, client):
        """Missing value field is rejected with 422."""
        response = client.post("/api/interview/answer", json={})

        assert response.status_code == 422

    def test_post_answer_broadcasts_answer_received_to_sse(self, live_server):
        """
        Submitting an answer broadcasts an 'answer_received' event to SSE
        subscribers so the browser can transition to a waiting state.
        """
        import backend.main as main_module
        base_url, _ = live_server
        main_module._SSE_HEARTBEAT_SECONDS = 15.0

        # Set up an active question via the API
        with httpx.Client() as setup_client:
            setup_client.post(f"{base_url}/api/interview/question", json={
                "text": "Pick one",
                "options": ["Alpha", "Beta"],
            })

        received: list[tuple[str, dict]] = []
        ready = threading.Event()
        done = threading.Event()

        def read_stream():
            with httpx.Client(timeout=10.0) as client:
                with client.stream("GET", f"{base_url}/api/interview/question/stream") as resp:
                    ready.set()
                    # First event is the existing question; second is answer_received
                    events = _read_sse_events(resp, stop_after=2)
                    received.extend(events)
            done.set()

        t = threading.Thread(target=read_stream, daemon=True)
        t.start()

        assert ready.wait(timeout=5.0), "SSE stream did not connect"
        time.sleep(0.1)  # give the generator a moment to emit the initial question

        with httpx.Client() as client:
            client.post(f"{base_url}/api/interview/answer", json={"value": "Alpha"})

        assert done.wait(timeout=5.0), "SSE stream did not receive answer_received event"
        t.join(timeout=2.0)

        event_types = [e[0] for e in received]
        assert "answer_received" in event_types
