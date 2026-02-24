"""
Interview session state manager.
=================================

All state is in-memory only — intentionally ephemeral.
Restarting the backend clears all interview state. This is by design:
interviews are short, real-time sessions, not long-lived persisted data.
"""

import asyncio
from typing import Optional


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
        self.active_question: Optional[dict] = None  # {text, options}
        self.pending_answer: Optional[str] = None    # set by browser, consumed by Claude
        self._answer_ready: asyncio.Event = asyncio.Event()
        self._lock: asyncio.Lock = asyncio.Lock()
        self._subscribers: list[asyncio.Queue] = []

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
            self.active_question = {"text": text, "options": options}
            self.pending_answer = None
            self._answer_ready.clear()

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

    async def reset(self) -> None:
        """Clear all session state and notify SSE subscribers that the session ended."""
        async with self._lock:
            self.active_question = None
            self.pending_answer = None
            self._answer_ready.clear()

        await self.broadcast({"type": "session_ended"})

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


def get_interview_session() -> InterviewSession:
    """Return the global interview session singleton."""
    return _interview_session
