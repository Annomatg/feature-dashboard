"""
Unit tests for InterviewSession state manager.
===============================================

Tests the InterviewSession class in backend/interview_state.py directly,
without going through HTTP endpoints.  All async tests use pytest-anyio or
plain asyncio.run() via a sync wrapper.
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.interview_state import InterviewSession


# ---------------------------------------------------------------------------
# Helper: run a coroutine synchronously inside tests
# ---------------------------------------------------------------------------

def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def session():
    """Fresh InterviewSession for each test."""
    return InterviewSession()


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------

class TestInitialState:
    def test_active_question_is_none(self, session):
        assert session.active_question is None

    def test_pending_answer_is_none(self, session):
        assert session.pending_answer is None

    def test_started_at_is_none(self, session):
        assert session.started_at is None

    def test_subscribers_is_empty(self, session):
        assert session._subscribers == []

    def test_answer_ready_not_set(self, session):
        assert not session._answer_ready.is_set()


# ---------------------------------------------------------------------------
# set_question
# ---------------------------------------------------------------------------

class TestSetQuestion:
    def test_stores_question(self, session):
        run(session.set_question("What is 2+2?", ["3", "4", "5"]))
        assert session.active_question == {"text": "What is 2+2?", "options": ["3", "4", "5"]}

    def test_sets_started_at_on_first_question(self, session):
        before = datetime.utcnow()
        run(session.set_question("First?", ["A"]))
        after = datetime.utcnow()

        assert session.started_at is not None
        assert before <= session.started_at <= after

    def test_started_at_not_updated_on_subsequent_questions(self, session):
        run(session.set_question("Q1", ["A"]))
        first_started_at = session.started_at

        run(session.set_question("Q2", ["B"]))
        assert session.started_at == first_started_at

    def test_clears_pending_answer(self, session):
        session.pending_answer = "old_answer"
        run(session.set_question("New Q", ["X"]))
        assert session.pending_answer is None

    def test_clears_answer_ready_event(self, session):
        session._answer_ready.set()
        run(session.set_question("New Q", ["X"]))
        assert not session._answer_ready.is_set()

    def test_broadcasts_question_event_to_subscribers(self, session):
        q = session.subscribe()
        run(session.set_question("Broadcast?", ["Yes", "No"]))

        assert not q.empty()
        event = q.get_nowait()
        assert event == {"type": "question", "text": "Broadcast?", "options": ["Yes", "No"]}

    def test_broadcasts_to_multiple_subscribers(self, session):
        queues = [session.subscribe() for _ in range(3)]
        run(session.set_question("Multi?", ["1", "2"]))

        for q in queues:
            assert not q.empty()


# ---------------------------------------------------------------------------
# has_unconsumed_answer
# ---------------------------------------------------------------------------

class TestHasUnconsumedAnswer:
    def test_false_when_no_answer(self, session):
        assert not session.has_unconsumed_answer()

    def test_true_when_answer_is_set(self, session):
        session.pending_answer = "X"
        assert session.has_unconsumed_answer()

    def test_false_after_answer_cleared(self, session):
        session.pending_answer = "X"
        session.pending_answer = None
        assert not session.has_unconsumed_answer()


# ---------------------------------------------------------------------------
# submit_answer
# ---------------------------------------------------------------------------

class TestSubmitAnswer:
    def test_stores_answer(self, session):
        run(session.submit_answer("42"))
        assert session.pending_answer == "42"

    def test_sets_answer_ready_event(self, session):
        run(session.submit_answer("yes"))
        assert session._answer_ready.is_set()

    def test_broadcasts_answer_received_event(self, session):
        q = session.subscribe()
        run(session.submit_answer("chosen"))

        assert not q.empty()
        event = q.get_nowait()
        assert event == {"type": "answer_received"}


# ---------------------------------------------------------------------------
# wait_for_answer
# ---------------------------------------------------------------------------

class TestWaitForAnswer:
    def test_returns_answer_when_already_set(self, session):
        session.pending_answer = "ready"
        session._answer_ready.set()

        result = run(session.wait_for_answer(timeout=1.0))
        assert result == "ready"

    def test_clears_pending_answer_after_return(self, session):
        session.pending_answer = "x"
        session._answer_ready.set()

        run(session.wait_for_answer(timeout=1.0))
        assert session.pending_answer is None

    def test_clears_answer_ready_event_after_return(self, session):
        session.pending_answer = "x"
        session._answer_ready.set()

        run(session.wait_for_answer(timeout=1.0))
        assert not session._answer_ready.is_set()

    def test_returns_none_on_timeout(self, session):
        result = run(session.wait_for_answer(timeout=0.05))
        assert result is None

    def test_consume_once_second_call_times_out(self, session):
        session.pending_answer = "x"
        session._answer_ready.set()

        run(session.wait_for_answer(timeout=1.0))          # consumes
        result = run(session.wait_for_answer(timeout=0.05))  # should time out
        assert result is None

    def test_unblocks_when_answer_submitted_concurrently(self, session):
        """wait_for_answer unblocks as soon as submit_answer is called."""

        async def delayed_submit():
            await asyncio.sleep(0.05)
            await session.submit_answer("concurrent")

        async def run_both():
            task = asyncio.create_task(delayed_submit())
            result = await session.wait_for_answer(timeout=2.0)
            await task
            return result

        result = asyncio.run(run_both())
        assert result == "concurrent"


# ---------------------------------------------------------------------------
# timeout
# ---------------------------------------------------------------------------

class TestSessionTimeout:
    def test_clears_active_question(self, session):
        session.active_question = {"text": "Q?", "options": ["A"]}
        run(session.timeout())
        assert session.active_question is None

    def test_clears_pending_answer(self, session):
        session.pending_answer = "A"
        run(session.timeout())
        assert session.pending_answer is None

    def test_clears_started_at(self, session):
        from datetime import datetime
        session.started_at = datetime.utcnow()
        run(session.timeout())
        assert session.started_at is None

    def test_clears_answer_ready_event(self, session):
        session._answer_ready.set()
        run(session.timeout())
        assert not session._answer_ready.is_set()

    def test_broadcasts_session_timeout_event(self, session):
        q = session.subscribe()
        run(session.timeout())

        assert not q.empty()
        event = q.get_nowait()
        assert event == {"type": "session_timeout"}

    def test_idempotent_when_no_active_session(self, session):
        run(session.timeout())  # nothing set — should not raise
        assert session.active_question is None
        assert session.pending_answer is None


# ---------------------------------------------------------------------------
# reset
# ---------------------------------------------------------------------------

class TestReset:
    def test_clears_active_question(self, session):
        session.active_question = {"text": "Q", "options": ["A"]}
        run(session.reset())
        assert session.active_question is None

    def test_clears_pending_answer(self, session):
        session.pending_answer = "A"
        run(session.reset())
        assert session.pending_answer is None

    def test_clears_started_at(self, session):
        session.started_at = datetime.utcnow()
        run(session.reset())
        assert session.started_at is None

    def test_clears_answer_ready_event(self, session):
        session._answer_ready.set()
        run(session.reset())
        assert not session._answer_ready.is_set()

    def test_broadcasts_session_ended_event(self, session):
        q = session.subscribe()
        run(session.reset())

        assert not q.empty()
        event = q.get_nowait()
        assert event == {"type": "session_ended", "features_created": 0}

    def test_broadcasts_session_ended_event_with_features_created(self, session):
        q = session.subscribe()
        run(session.reset(features_created=5))

        assert not q.empty()
        event = q.get_nowait()
        assert event == {"type": "session_ended", "features_created": 5}

    def test_idempotent_when_no_active_session(self, session):
        run(session.reset())  # nothing set — should not raise
        assert session.active_question is None
        assert session.pending_answer is None
        assert session.started_at is None


# ---------------------------------------------------------------------------
# subscribe / unsubscribe
# ---------------------------------------------------------------------------

class TestSubscribeUnsubscribe:
    def test_subscribe_returns_queue(self, session):
        q = session.subscribe()
        assert isinstance(q, asyncio.Queue)

    def test_subscribe_adds_to_subscribers(self, session):
        q = session.subscribe()
        assert q in session._subscribers

    def test_unsubscribe_removes_queue(self, session):
        q = session.subscribe()
        session.unsubscribe(q)
        assert q not in session._subscribers

    def test_unsubscribe_unknown_queue_does_not_raise(self, session):
        import asyncio
        unknown = asyncio.Queue()
        session.unsubscribe(unknown)  # should not raise

    def test_multiple_subscribers_independent(self, session):
        q1 = session.subscribe()
        q2 = session.subscribe()
        assert q1 is not q2
        assert len(session._subscribers) == 2


# ---------------------------------------------------------------------------
# broadcast
# ---------------------------------------------------------------------------

class TestBroadcast:
    def test_broadcast_delivers_to_all_subscribers(self, session):
        queues = [session.subscribe() for _ in range(4)]
        run(session.broadcast({"type": "test"}))

        for q in queues:
            assert q.get_nowait() == {"type": "test"}

    def test_broadcast_with_no_subscribers_does_not_raise(self, session):
        run(session.broadcast({"type": "test"}))  # should not raise

    def test_broadcast_does_not_modify_event(self, session):
        q = session.subscribe()
        event = {"type": "question", "text": "Q?", "options": ["A"]}
        run(session.broadcast(event))
        assert q.get_nowait() == event
