"""
Tests for push notification endpoints
======================================

Endpoints tested:
  GET  /api/push/vapid-public-key   – returns VAPID public key
  GET  /api/push/status             – returns system status
  POST /api/push/subscribe          – registers a push subscription
  DELETE /api/push/subscribe        – removes a push subscription
  POST /api/push/send-test          – queues a test notification

All pywebpush.webpush calls are mocked to avoid real network requests.
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.main import app
import backend.routers.push as push_module

client = TestClient(app)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_SUBSCRIPTION = {
    "endpoint": "https://fcm.googleapis.com/fcm/send/test-endpoint-abc123",
    "keys": {
        "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlTiXWtuCGvOTBPJ1hjtzxnC3MiJdWomKBFRgXUI0",
        "auth": "tBHItJI5svbpez7KI4CCXg",
    },
}

SAMPLE_SUBSCRIPTION_2 = {
    "endpoint": "https://fcm.googleapis.com/fcm/send/another-endpoint-xyz789",
    "keys": {
        "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlTiXWtuCGvOTBPJ1hjtzxnC3MiJdWomKBFRgXUI1",
        "auth": "tBHItJI5svbpez7KI4CCXh",
    },
}


@pytest.fixture(autouse=True)
def clear_subscriptions():
    """Clear the in-memory subscription store before and after each test."""
    push_module._subscriptions.clear()
    yield
    push_module._subscriptions.clear()


# ---------------------------------------------------------------------------
# GET /api/push/status
# ---------------------------------------------------------------------------

class TestPushStatus:
    def test_returns_status_fields(self):
        resp = client.get("/api/push/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "vapid_configured" in data
        assert "subscriber_count" in data
        assert "persistent" in data

    def test_subscriber_count_starts_at_zero(self):
        resp = client.get("/api/push/status")
        assert resp.json()["subscriber_count"] == 0

    def test_persistent_is_false(self):
        resp = client.get("/api/push/status")
        assert resp.json()["persistent"] is False

    def test_vapid_configured_false_when_keys_missing(self):
        with patch.object(push_module, "_VAPID_PUBLIC_KEY", None), \
             patch.object(push_module, "_VAPID_PRIVATE_KEY", None):
            resp = client.get("/api/push/status")
        assert resp.json()["vapid_configured"] is False

    def test_vapid_configured_true_when_keys_present(self):
        with patch.object(push_module, "_VAPID_PUBLIC_KEY", "fake-pub-key"), \
             patch.object(push_module, "_VAPID_PRIVATE_KEY", "fake-priv-key"):
            resp = client.get("/api/push/status")
        assert resp.json()["vapid_configured"] is True

    def test_subscriber_count_reflects_subscriptions(self):
        push_module._subscriptions["ep1"] = SAMPLE_SUBSCRIPTION
        push_module._subscriptions["ep2"] = SAMPLE_SUBSCRIPTION_2
        resp = client.get("/api/push/status")
        assert resp.json()["subscriber_count"] == 2


# ---------------------------------------------------------------------------
# GET /api/push/vapid-public-key
# ---------------------------------------------------------------------------

class TestVapidPublicKey:
    def test_returns_503_when_keys_not_configured(self):
        with patch.object(push_module, "_VAPID_PUBLIC_KEY", None):
            resp = client.get("/api/push/vapid-public-key")
        assert resp.status_code == 503

    def test_returns_public_key_when_configured(self):
        fake_key = "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlTiXWtuCGvOTBPJ1hjtzxnC3MiJdWomKBFRgXUI0"
        with patch.object(push_module, "_VAPID_PUBLIC_KEY", fake_key):
            resp = client.get("/api/push/vapid-public-key")
        assert resp.status_code == 200
        assert resp.json()["publicKey"] == fake_key

    def test_response_has_public_key_field(self):
        with patch.object(push_module, "_VAPID_PUBLIC_KEY", "some-key"):
            resp = client.get("/api/push/vapid-public-key")
        assert "publicKey" in resp.json()


# ---------------------------------------------------------------------------
# POST /api/push/subscribe
# ---------------------------------------------------------------------------

class TestSubscribe:
    def test_subscribe_returns_201(self):
        resp = client.post("/api/push/subscribe", json=SAMPLE_SUBSCRIPTION)
        assert resp.status_code == 201

    def test_subscribe_stores_subscription(self):
        client.post("/api/push/subscribe", json=SAMPLE_SUBSCRIPTION)
        assert SAMPLE_SUBSCRIPTION["endpoint"] in push_module._subscriptions

    def test_subscribe_returns_subscribed_status(self):
        resp = client.post("/api/push/subscribe", json=SAMPLE_SUBSCRIPTION)
        data = resp.json()
        assert data["status"] == "subscribed"
        assert data["total"] == 1

    def test_subscribe_multiple_increments_total(self):
        client.post("/api/push/subscribe", json=SAMPLE_SUBSCRIPTION)
        resp = client.post("/api/push/subscribe", json=SAMPLE_SUBSCRIPTION_2)
        assert resp.json()["total"] == 2

    def test_subscribe_validates_missing_endpoint(self):
        bad = {"keys": {"p256dh": "x", "auth": "y"}}
        resp = client.post("/api/push/subscribe", json=bad)
        assert resp.status_code == 422

    def test_subscribe_validates_missing_keys(self):
        bad = {"endpoint": "https://example.com/push/test"}
        resp = client.post("/api/push/subscribe", json=bad)
        assert resp.status_code == 422

    def test_subscribe_rejects_non_https_endpoint(self):
        bad = {**SAMPLE_SUBSCRIPTION, "endpoint": "http://insecure.example.com/push"}
        resp = client.post("/api/push/subscribe", json=bad)
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /api/push/subscribe
# ---------------------------------------------------------------------------

class TestUnsubscribe:
    def test_unsubscribe_removes_subscription(self):
        client.post("/api/push/subscribe", json=SAMPLE_SUBSCRIPTION)
        resp = client.request("DELETE", "/api/push/subscribe", json=SAMPLE_SUBSCRIPTION)
        assert resp.status_code == 200
        assert SAMPLE_SUBSCRIPTION["endpoint"] not in push_module._subscriptions

    def test_unsubscribe_returns_unsubscribed_status(self):
        client.post("/api/push/subscribe", json=SAMPLE_SUBSCRIPTION)
        resp = client.request("DELETE", "/api/push/subscribe", json=SAMPLE_SUBSCRIPTION)
        data = resp.json()
        assert data["status"] == "unsubscribed"
        assert data["total"] == 0

    def test_unsubscribe_not_found_returns_404(self):
        resp = client.request("DELETE", "/api/push/subscribe", json=SAMPLE_SUBSCRIPTION)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/push/send-test
# ---------------------------------------------------------------------------

class TestSendTest:
    PAYLOAD = {"title": "Test", "body": "Hello from Feature Dashboard"}

    def test_send_returns_503_when_vapid_not_configured(self):
        with patch.object(push_module, "_VAPID_PUBLIC_KEY", None), \
             patch.object(push_module, "_VAPID_PRIVATE_KEY", None):
            resp = client.post("/api/push/send-test", json=self.PAYLOAD)
        assert resp.status_code == 503

    def test_send_returns_no_subscribers_when_empty(self):
        with patch.object(push_module, "_VAPID_PUBLIC_KEY", "pub"), \
             patch.object(push_module, "_VAPID_PRIVATE_KEY", "priv"):
            resp = client.post("/api/push/send-test", json=self.PAYLOAD)
        assert resp.status_code == 200
        assert resp.json()["status"] == "no_subscribers"

    def test_send_queues_notification_when_subscribers_present(self):
        client.post("/api/push/subscribe", json=SAMPLE_SUBSCRIPTION)
        with patch.object(push_module, "_VAPID_PUBLIC_KEY", "pub"), \
             patch.object(push_module, "_VAPID_PRIVATE_KEY", "priv"), \
             patch.object(push_module, "send_push_to_all") as _mock_send:
            resp = client.post("/api/push/send-test", json=self.PAYLOAD)
        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"
        assert resp.json()["total_subscribers"] == 1

    def test_send_test_requires_body_field(self):
        resp = client.post("/api/push/send-test", json={"title": "No body"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# _send_push_sync helper
# ---------------------------------------------------------------------------

class TestSendPushSync:
    def test_returns_zero_without_vapid_key_object(self):
        push_module._subscriptions["https://ep1.example.com"] = SAMPLE_SUBSCRIPTION
        with patch.object(push_module, "_VAPID_PRIVATE_KEY_OBJECT", None):
            result = push_module._send_push_sync({"title": "T", "body": "B"})
        assert result == 0

    def test_removes_stale_410_subscriptions(self):
        pywebpush = pytest.importorskip("pywebpush")
        WebPushException = pywebpush.WebPushException

        stale_ep = "https://stale-ep.example.com/push"
        push_module._subscriptions[stale_ep] = SAMPLE_SUBSCRIPTION

        mock_response = MagicMock()
        mock_response.status_code = 410
        mock_exc = WebPushException("Gone", response=mock_response)

        with patch.object(push_module, "_VAPID_PUBLIC_KEY", "pub"), \
             patch.object(push_module, "_VAPID_PRIVATE_KEY_OBJECT", MagicMock()), \
             patch("pywebpush.webpush", side_effect=mock_exc):
            result = push_module._send_push_sync({"title": "T", "body": "B"})

        assert result == 0
        assert stale_ep not in push_module._subscriptions
