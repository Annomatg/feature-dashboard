"""
Web Push notification endpoints.

Provides VAPID key distribution, push subscription management,
and notification delivery for the Feature Dashboard PWA.

Setup:
  1. Generate VAPID keys: python scripts/generate_vapid_keys.py
  2. Add VAPID_PRIVATE_KEY, VAPID_PUBLIC_KEY, VAPID_SUBJECT to .env
  3. pywebpush is installed automatically via requirements.txt

Note: subscriptions are stored in-memory and are lost on backend restart.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/push", tags=["push"])

_executor = ThreadPoolExecutor(max_workers=2)

# ---------------------------------------------------------------------------
# VAPID configuration – loaded once at import time
# ---------------------------------------------------------------------------

_VAPID_PUBLIC_KEY: str | None = os.environ.get("VAPID_PUBLIC_KEY")
_VAPID_PRIVATE_KEY: str | None = os.environ.get("VAPID_PRIVATE_KEY")
_VAPID_SUBJECT: str = os.environ.get("VAPID_SUBJECT", "mailto:dev@localhost")

# Decode private key once at startup so it is not decoded on every send
_VAPID_PRIVATE_KEY_OBJECT: Any = None

if not _VAPID_PUBLIC_KEY or not _VAPID_PRIVATE_KEY:
    logger.warning(
        "VAPID keys not configured. "
        "Run `python scripts/generate_vapid_keys.py` and add the keys to .env. "
        "Push notifications will return 503 until keys are set."
    )
else:
    try:
        from cryptography.hazmat.primitives.serialization import load_der_private_key as _load_der

        _padded = _VAPID_PRIVATE_KEY + "=" * (-len(_VAPID_PRIVATE_KEY) % 4)
        _VAPID_PRIVATE_KEY_OBJECT = _load_der(
            base64.urlsafe_b64decode(_padded), password=None
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to decode VAPID_PRIVATE_KEY: %s", exc)

# ---------------------------------------------------------------------------
# In-memory subscription store  {endpoint: subscription_dict}
# NOTE: subscriptions are lost on backend restart (in-memory only).
# ---------------------------------------------------------------------------

_subscriptions: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class PushSubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscription(BaseModel):
    endpoint: str
    keys: PushSubscriptionKeys

    @field_validator("endpoint")
    @classmethod
    def endpoint_must_be_https(cls, v: str) -> str:
        if not v.startswith("https://"):
            raise ValueError("endpoint must start with https://")
        return v


class PushPayload(BaseModel):
    title: str = "Feature Dashboard"
    body: str
    tag: str = "feature-notification"
    url: str = "/"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _send_push_sync(payload: dict[str, Any]) -> int:
    """Synchronously send push to all subscribers (intended for the thread pool).

    Returns the number of successfully notified clients.
    Silently removes subscriptions that have gone stale (410 Gone).
    """
    if not _VAPID_PUBLIC_KEY or not _VAPID_PRIVATE_KEY_OBJECT:
        logger.warning("_send_push_sync: VAPID keys not configured, skipping.")
        return 0

    from pywebpush import webpush, WebPushException

    stale: list[str] = []
    sent = 0

    for endpoint, sub in list(_subscriptions.items()):
        try:
            webpush(
                subscription_info=sub,
                data=json.dumps(payload),
                vapid_private_key=_VAPID_PRIVATE_KEY_OBJECT,
                vapid_claims={"sub": _VAPID_SUBJECT},
                content_encoding="aes128gcm",
            )
            sent += 1
        except WebPushException as exc:
            if exc.response is not None and exc.response.status_code == 410:
                stale.append(endpoint)
            else:
                logger.error("WebPush send failed for %s: %s", endpoint, exc)

    for ep in stale:
        _subscriptions.pop(ep, None)
        logger.info("Removed stale push subscription: %s", ep)

    return sent


async def send_push_to_all(payload: dict[str, Any]) -> int:
    """Async wrapper: send push notifications in a thread pool to avoid blocking the event loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _send_push_sync, payload)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/vapid-public-key")
async def get_vapid_public_key():
    """Return the VAPID public key for use in PushManager.subscribe()."""
    if not _VAPID_PUBLIC_KEY:
        raise HTTPException(
            status_code=503,
            detail="VAPID keys not configured. Run scripts/generate_vapid_keys.py and add to .env.",
        )
    return {"publicKey": _VAPID_PUBLIC_KEY}


@router.post("/subscribe", status_code=201)
async def subscribe(subscription: PushSubscription):
    """Register a push subscription from the browser."""
    _subscriptions[subscription.endpoint] = subscription.model_dump()
    logger.info(
        "Push subscription registered: %s (total: %d)",
        subscription.endpoint[:60],
        len(_subscriptions),
    )
    return {"status": "subscribed", "total": len(_subscriptions)}


@router.delete("/subscribe")
async def unsubscribe(subscription: PushSubscription):
    """Remove a push subscription."""
    removed = _subscriptions.pop(subscription.endpoint, None)
    if removed is None:
        raise HTTPException(status_code=404, detail="Subscription not found.")
    logger.info("Push subscription removed: %s", subscription.endpoint[:60])
    return {"status": "unsubscribed", "total": len(_subscriptions)}


@router.post("/send-test")
async def send_test_notification(payload: PushPayload, background_tasks: BackgroundTasks):
    """Queue a test push notification to all subscribed clients (runs in background)."""
    if not _VAPID_PUBLIC_KEY or not _VAPID_PRIVATE_KEY:
        raise HTTPException(
            status_code=503,
            detail="VAPID keys not configured. Run scripts/generate_vapid_keys.py and add to .env.",
        )
    if not _subscriptions:
        return {"status": "no_subscribers", "sent": 0}

    background_tasks.add_task(send_push_to_all, payload.model_dump())
    return {"status": "queued", "total_subscribers": len(_subscriptions)}


@router.get("/status")
async def push_status():
    """Return push notification system status."""
    return {
        "vapid_configured": bool(_VAPID_PUBLIC_KEY and _VAPID_PRIVATE_KEY),
        "subscriber_count": len(_subscriptions),
        "persistent": False,  # subscriptions are in-memory; lost on backend restart
    }
