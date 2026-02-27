"""
Interview session state manager.
=================================

All state is in-memory only — intentionally ephemeral.
Restarting the backend clears all interview state. This is by design:
interviews are short, real-time sessions, not long-lived persisted data.
"""

import asyncio
import secrets
import time
from collections import deque
from datetime import datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Structured event logger
# ---------------------------------------------------------------------------

def _log_event(session: "InterviewSession", event_type: str, detail: Optional[dict] = None) -> None:
    """Append a timestamped log entry to the session's event log."""
    session.log.append({
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "event_type": event_type,
        "detail": detail if detail is not None else {},
    })


class InterviewSession:
    """
    Tracks the state of a single in-flight interview session.

    Lifecycle:
        1. Claude POSTs a question  → active_question set, answer_ready cleared
        2. Browser GETs SSE stream  → subscribes to question broadcasts
        3. Browser POSTs an answer  → pending_answer set, answer_ready signalled
        4. Claude GETs /answer      → consumes pending_answer, clears it
        5. Repeat from 1, or DELETE /session to end
    """

    def __init__(self) -> None:
        self.active_question: Optional[dict] = None   # {text, options}
        self.pending_answer: Optional[str] = None     # set by browser, consumed by Claude
        self.started_at: Optional[datetime] = None    # set on first question, cleared on reset
        self.owner_token: Optional[str] = None        # set on first question, cleared on reset
        self._answer_ready: asyncio.Event = asyncio.Event()
        self._lock: asyncio.Lock = asyncio.Lock()
        self._subscribers: list[asyncio.Queue] = []
        self.log: deque = deque(maxlen=200)           # structured event log for this session

    # ------------------------------------------------------------------
    # Session token (duplicate-session guard)
    # ------------------------------------------------------------------

    def claim_session(self) -> str:
        """
        Claim ownership of this session and return a new token.

        Called when the first question is posted with no existing owner.
        Generates a random token, stores it, and returns it to the caller
        so it can be included in the API response.
        """
        token = secrets.token_urlsafe(32)
        self.owner_token = token
        return token

    # ------------------------------------------------------------------
    # Question management
    # ------------------------------------------------------------------

    async def set_question(self, text: str, options: list[str]) -> None:
        """
        Store a new active question and reset answer state.

        Callers must check has_unconsumed_answer() BEFORE calling this and
        raise 409 if True — this method does NOT enforce that guard itself.
        """
        async with self._lock:
            is_first = self.started_at is None
            if is_first:
                self.started_at = datetime.utcnow()
            self.active_question = {"text": text, "options": options}
            self.pending_answer = None
            self._answer_ready.clear()

        if is_first:
            _log_event(self, "session_start", {"started_at": self.started_at.isoformat() + "Z"})
        _log_event(self, "question_posted", {"text": text, "options": options})
        await self.broadcast({"type": "question", "text": text, "options": options})

    # ------------------------------------------------------------------
    # Answer management
    # ------------------------------------------------------------------

    def has_unconsumed_answer(self) -> bool:
        """Return True when the browser has submitted an answer that Claude has not yet read."""
        return self.pending_answer is not None

    async def submit_answer(self, value: str) -> None:
        """Store the user's answer and wake any waiting GET /answer poller."""
        async with self._lock:
            self.pending_answer = value
            self._answer_ready.set()

        _log_event(self, "answer_submitted", {"value": value})
        await self.broadcast({"type": "answer_received"})

    async def wait_for_answer(self, timeout: float = 300.0) -> Optional[str]:
        """
        Block until an answer is available or *timeout* seconds elapse.

        Returns the answer string, or None on timeout.
        Clears the answer from state (consume-once semantics).
        """
        try:
            await asyncio.wait_for(self._answer_ready.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

        async with self._lock:
            answer = self.pending_answer
            self.pending_answer = None
            self._answer_ready.clear()
            return answer

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    async def timeout(self) -> None:
        """Called when the answer wait times out. Clears state and notifies SSE subscribers."""
        global _last_session_log, _last_session_log_time
        _log_event(self, "answer_timeout", {})
        _last_session_log = list(self.log)
        _last_session_log_time = time.monotonic()

        async with self._lock:
            self.active_question = None
            self.pending_answer = None
            self.started_at = None
            self.owner_token = None
            self._answer_ready.clear()

        self.log.clear()
        await self.broadcast({"type": "session_timeout"})

    async def reset(self, features_created: int = 0) -> None:
        """Clear all session state and notify SSE subscribers that the session ended."""
        global _last_session_log, _last_session_log_time
        _log_event(self, "session_end", {"features_created": features_created})
        _last_session_log = list(self.log)
        _last_session_log_time = time.monotonic()

        async with self._lock:
            self.active_question = None
            self.pending_answer = None
            self.started_at = None
            self.owner_token = None
            self._answer_ready.clear()

        self.log.clear()
        await self.broadcast({"type": "session_ended", "features_created": features_created})

    # ------------------------------------------------------------------
    # SSE subscriber management (used by GET /api/interview/question/stream)
    # ------------------------------------------------------------------

    def subscribe(self) -> asyncio.Queue:
        """Register a new SSE subscriber and return its queue."""
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        """Remove an SSE subscriber queue."""
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass

    async def broadcast(self, event: dict) -> None:
        """Push an event to all registered SSE subscribers."""
        for q in list(self._subscribers):
            await q.put(event)


# ---------------------------------------------------------------------------
# Module-level singleton — one session for the whole backend process
# ---------------------------------------------------------------------------

_interview_session = InterviewSession()

# Post-session log: kept for 60 s after a session ends so the debug endpoint
# can still serve it even though the session object has been cleared.
_last_session_log: Optional[list] = None
_last_session_log_time: Optional[float] = None  # time.monotonic() timestamp


def get_interview_session() -> InterviewSession:
    """Return the global interview session singleton."""
    return _interview_session


def get_debug_log() -> Optional[dict]:
    """
    Return the session event log for the debug endpoint.

    Returns:
      - {"active": True,  "log": [...]}  if a session is currently active
      - {"active": False, "log": [...]}  if a session ended within the last 60 s
      - None if no session is active and no recent session log is available
    """
    session = _interview_session
    if session.owner_token is not None:
        return {"active": True, "log": list(session.log)}
    if (
        _last_session_log is not None
        and _last_session_log_time is not None
        and time.monotonic() - _last_session_log_time < 60.0
    ):
        return {"active": False, "log": _last_session_log}
    return None
