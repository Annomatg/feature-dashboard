"""
Integration tests for feature stream and notify endpoints.
===========================================================

Tests the following endpoints:
  - GET  /api/features/stream   (SSE, feature_created + heartbeat events)
  - POST /api/features/notify   (broadcasts feature_created event)

SSE tests require a real uvicorn server (httpx.ASGITransport buffers
the full response, so it cannot test infinite streaming endpoints).
Non-SSE tests use FastAPI TestClient.
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

import backend.main as main_module
from backend.main import app


@pytest.fixture(autouse=True)
def reset_feature_subscribers():
    """Clear the feature subscriber list before and after every test."""
    main_module._feature_subscribers.clear()
    yield
    main_module._feature_subscribers.clear()


@pytest.fixture
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# Live uvicorn server fixture (reused from test_interview_api.py pattern)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def live_server():
    """
    Start a real uvicorn server in a background thread.

    Yields (base_url, server_loop) so tests can schedule coroutines on the
    server's event loop via asyncio.run_coroutine_threadsafe().
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="critical")
    server = uvicorn.Server(config)

    loop_holder: list[asyncio.AbstractEventLoop] = []

    def run_server():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop_holder.append(loop)
        loop.run_until_complete(server.serve())

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()

    deadline = time.monotonic() + 5.0
    while not loop_holder and time.monotonic() < deadline:
        time.sleep(0.01)
    if not loop_holder:
        raise RuntimeError("Server event loop did not start")
    server_loop = loop_holder[0]

    base_url = f"http://127.0.0.1:{port}"

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
# POST /api/features/notify — synchronous tests
# ---------------------------------------------------------------------------

class TestPostFeaturesNotify:
    """Tests for POST /api/features/notify"""

    def test_notify_returns_200_with_status(self, client):
        """A valid notify call returns 200 with status=notified."""
        response = client.post("/api/features/notify?feature_id=42&name=My+Feature")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "notified"

    def test_notify_returns_subscriber_count(self, client):
        """The response includes the current subscriber count."""
        response = client.post("/api/features/notify?feature_id=1&name=Test")

        assert response.status_code == 200
        assert "subscribers" in response.json()
        assert response.json()["subscribers"] == 0  # no active SSE clients in sync tests

    def test_notify_with_zero_subscribers_does_not_error(self, client):
        """Notifying with no connected SSE clients returns 200 without error."""
        assert len(main_module._feature_subscribers) == 0

        response = client.post("/api/features/notify?feature_id=99&name=Solo")

        assert response.status_code == 200

    def test_notify_with_subscriber_puts_event_on_queue(self, client):
        """When a subscriber queue is registered, notify puts an event on it."""
        q: asyncio.Queue = asyncio.Queue()
        main_module._feature_subscribers.append(q)

        try:
            client.post("/api/features/notify?feature_id=7&name=New+Feature")

            assert not q.empty()
        finally:
            main_module._feature_subscribers.remove(q)

    def test_notify_missing_feature_id_returns_422(self, client):
        """Missing feature_id query parameter returns 422."""
        response = client.post("/api/features/notify?name=Test")

        assert response.status_code == 422

    def test_notify_missing_name_returns_422(self, client):
        """Missing name query parameter returns 422."""
        response = client.post("/api/features/notify?feature_id=1")

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/features/stream — SSE tests (live server)
# ---------------------------------------------------------------------------

class TestGetFeaturesStream:
    """Tests for GET /api/features/stream (uses live uvicorn server)."""

    def test_stream_returns_200_with_event_stream_content_type(self, live_server):
        """The SSE endpoint returns 200 with text/event-stream Content-Type."""
        base_url, _ = live_server
        with httpx.Client() as client:
            with client.stream("GET", f"{base_url}/api/features/stream") as response:
                assert response.status_code == 200
                assert "text/event-stream" in response.headers["content-type"]

    def test_stream_sends_heartbeat_when_idle(self, live_server):
        """A heartbeat event is emitted when no events arrive within the timeout."""
        import backend.routers.features as features_router_module
        base_url, _ = live_server
        original = features_router_module._FEATURE_SSE_HEARTBEAT_SECONDS
        features_router_module._FEATURE_SSE_HEARTBEAT_SECONDS = 0.05

        try:
            with httpx.Client(timeout=5.0) as client:
                with client.stream("GET", f"{base_url}/api/features/stream") as resp:
                    events = _read_sse_events(resp, stop_after=1)

            assert len(events) == 1
            assert events[0][0] == "heartbeat"
        finally:
            features_router_module._FEATURE_SSE_HEARTBEAT_SECONDS = original

    def test_stream_receives_feature_created_event_on_notify(self, live_server):
        """
        A feature_created event posted via /api/features/notify is broadcast to
        all active /api/features/stream subscribers.
        """
        import backend.routers.features as features_router_module
        base_url, _ = live_server
        features_router_module._FEATURE_SSE_HEARTBEAT_SECONDS = 15.0

        received: list[tuple[str, dict]] = []
        ready = threading.Event()
        done = threading.Event()

        def read_stream():
            with httpx.Client(timeout=10.0) as client:
                with client.stream("GET", f"{base_url}/api/features/stream") as resp:
                    ready.set()
                    events = _read_sse_events(resp, stop_after=1)
                    received.extend(events)
            done.set()

        t = threading.Thread(target=read_stream, daemon=True)
        t.start()

        assert ready.wait(timeout=5.0), "SSE stream did not connect in time"
        time.sleep(0.1)  # give the generator a moment to register

        with httpx.Client() as client:
            client.post(f"{base_url}/api/features/notify?feature_id=42&name=Auto+Created")

        assert done.wait(timeout=5.0), "SSE stream did not receive feature_created event"
        t.join(timeout=2.0)

        assert len(received) == 1
        event_type, data = received[0]
        assert event_type == "feature_created"
        assert data["id"] == 42
        assert data["name"] == "Auto Created"

    def test_stream_broadcasts_to_multiple_subscribers(self, live_server):
        """
        Multiple subscribers all receive the feature_created event.
        """
        import backend.routers.features as features_router_module
        base_url, _ = live_server
        features_router_module._FEATURE_SSE_HEARTBEAT_SECONDS = 15.0

        received_1: list = []
        received_2: list = []
        ready_1, ready_2 = threading.Event(), threading.Event()
        done_1, done_2 = threading.Event(), threading.Event()

        def read_stream(ready, received, done):
            with httpx.Client(timeout=10.0) as client:
                with client.stream("GET", f"{base_url}/api/features/stream") as resp:
                    ready.set()
                    events = _read_sse_events(resp, stop_after=1)
                    received.extend(events)
            done.set()

        t1 = threading.Thread(target=read_stream, args=(ready_1, received_1, done_1), daemon=True)
        t2 = threading.Thread(target=read_stream, args=(ready_2, received_2, done_2), daemon=True)
        t1.start()
        t2.start()

        assert ready_1.wait(timeout=5.0) and ready_2.wait(timeout=5.0)
        time.sleep(0.1)

        with httpx.Client() as client:
            client.post(f"{base_url}/api/features/notify?feature_id=5&name=Shared+Feature")

        assert done_1.wait(timeout=5.0) and done_2.wait(timeout=5.0)

        assert received_1[0][0] == "feature_created"
        assert received_2[0][0] == "feature_created"

    def test_stream_unsubscribes_on_disconnect(self, live_server):
        """
        The subscriber queue is removed when the TCP connection closes,
        preventing memory leaks.
        """
        import backend.routers.features as features_router_module
        base_url, _ = live_server
        original = features_router_module._FEATURE_SSE_HEARTBEAT_SECONDS
        features_router_module._FEATURE_SSE_HEARTBEAT_SECONDS = 0.05

        try:
            initial_count = len(main_module._feature_subscribers)

            with httpx.Client() as client:
                with client.stream("GET", f"{base_url}/api/features/stream") as resp:
                    _read_sse_events(resp, stop_after=1)
                # TCP connection closes here

            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                if len(main_module._feature_subscribers) == initial_count:
                    break
                time.sleep(0.05)

            assert len(main_module._feature_subscribers) == initial_count
        finally:
            features_router_module._FEATURE_SSE_HEARTBEAT_SECONDS = original
