"""
Tests verifying that InterviewSession state is intentionally ephemeral.

A backend restart is equivalent to creating a new InterviewSession() —
all prior session state is gone.  No database table is consulted on startup.
This is by design: interviews are short, real-time sessions, not long-lived
persisted data.
"""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.interview_state import InterviewSession, get_interview_session


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Ephemeral state: new instance starts completely clean
# ---------------------------------------------------------------------------

class TestEphemeralState:
    """
    A new InterviewSession() simulates a backend restart.
    Every field must be None / empty / unset — no state leaks across instances.
    """

    def test_no_active_question_on_fresh_instance(self):
        s = InterviewSession()
        assert s.active_question is None

    def test_no_pending_answer_on_fresh_instance(self):
        s = InterviewSession()
        assert s.pending_answer is None

    def test_no_started_at_on_fresh_instance(self):
        s = InterviewSession()
        assert s.started_at is None

    def test_no_owner_token_on_fresh_instance(self):
        s = InterviewSession()
        assert s.owner_token is None

    def test_no_subscribers_on_fresh_instance(self):
        s = InterviewSession()
        assert s._subscribers == []

    def test_answer_ready_event_not_set_on_fresh_instance(self):
        s = InterviewSession()
        assert not s._answer_ready.is_set()


# ---------------------------------------------------------------------------
# No shared state across instances (restart semantics)
# ---------------------------------------------------------------------------

class TestNoSharedStateBetweenInstances:
    """
    Two separate InterviewSession instances must not share state.
    This mirrors what happens when the backend process restarts:
    the old in-memory state is gone and a brand-new object is created.
    """

    def test_question_not_shared(self):
        s1 = InterviewSession()
        s2 = InterviewSession()
        run(s1.set_question("First session?", ["A", "B"]))
        assert s2.active_question is None

    def test_answer_not_shared(self):
        s1 = InterviewSession()
        s2 = InterviewSession()
        run(s1.submit_answer("yes"))
        assert s2.pending_answer is None

    def test_owner_token_not_shared(self):
        s1 = InterviewSession()
        s2 = InterviewSession()
        token = s1.claim_session()
        assert s2.owner_token is None
        assert token != s2.owner_token

    def test_subscribers_not_shared(self):
        s1 = InterviewSession()
        s2 = InterviewSession()
        q = s1.subscribe()
        assert q not in s2._subscribers

    def test_answer_ready_event_not_shared(self):
        s1 = InterviewSession()
        s2 = InterviewSession()
        s1._answer_ready.set()
        assert not s2._answer_ready.is_set()


# ---------------------------------------------------------------------------
# Module-level singleton behaviour
# ---------------------------------------------------------------------------

class TestModuleSingleton:
    """
    get_interview_session() must always return the same object within a
    process lifetime.  A restart (new process) gives a fresh object.
    """

    def test_get_interview_session_returns_same_object(self):
        a = get_interview_session()
        b = get_interview_session()
        assert a is b

    def test_singleton_is_interview_session_instance(self):
        assert isinstance(get_interview_session(), InterviewSession)


# ---------------------------------------------------------------------------
# No SQLAlchemy model for interview state
# ---------------------------------------------------------------------------

class TestNoDatabaseModel:
    """
    Confirms that no SQLAlchemy model (and therefore no DB table) is defined
    for interview state in api/database.py.
    """

    def test_no_interview_table_in_sqlalchemy_models(self):
        from api.database import Base
        table_names = set(Base.metadata.tables.keys())
        interview_tables = {t for t in table_names if 'interview' in t.lower()}
        assert interview_tables == set(), (
            f"Unexpected interview-related DB tables found: {interview_tables}. "
            "Interview state must remain ephemeral (in-memory only)."
        )

    def test_only_expected_tables_exist(self):
        from api.database import Base
        table_names = set(Base.metadata.tables.keys())
        assert table_names == {'features', 'comments'}, (
            f"Unexpected tables: {table_names - {'features', 'comments'}}. "
            "Add new tables here if they are intentionally persisted."
        )
