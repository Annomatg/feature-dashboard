"""
Unit tests for backend/autopilot_engine.py
===========================================

Covers the autopilot state machine and helpers extracted from main.py:
- _AutoPilotState defaults
- _append_log
- _disable_autopilot_state
- handle_all_complete
- get_next_autopilot_feature
- _extract_output_snippet
- handle_budget_exhausted
- _get_child_procs / _any_proc_running
- _wait_for_process_and_children
- _reset_autopilot_in_config / _read_autopilot_from_config / _write_autopilot_to_config
- CLAUDE_RATE_LIMIT_PATTERNS / CLAUDE_SESSION_LIMIT_EXIT_CODES constants
"""

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(autouse=True)
def restore_event_loop():
    """Ensure a current event loop exists after each test.

    asyncio.run() closes the event loop it creates.  Other test modules that
    use the deprecated asyncio.get_event_loop().run_until_complete() pattern
    require a current event loop to exist, so we recreate one after every
    test in this file.
    """
    yield
    # After the test, create and register a fresh event loop so subsequent
    # tests can call asyncio.get_event_loop() safely.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

from backend.autopilot_engine import (
    _AutoPilotState,
    _append_log,
    _disable_autopilot_state,
    _extract_output_snippet,
    _get_child_procs,
    _any_proc_running,
    _wait_for_process_and_children,
    _wait_for_stopping_process,
    _reset_autopilot_in_config,
    _read_autopilot_from_config,
    _write_autopilot_to_config,
    CLAUDE_RATE_LIMIT_PATTERNS,
    CLAUDE_SESSION_LIMIT_EXIT_CODES,
    AUTOPILOT_PROCESS_TIMEOUT_SECS,
    handle_all_complete,
    handle_budget_exhausted,
    get_next_autopilot_feature,
)


# ---------------------------------------------------------------------------
# _AutoPilotState defaults
# ---------------------------------------------------------------------------

class TestAutoPilotStateDefaults:
    def test_enabled_is_false(self):
        state = _AutoPilotState()
        assert state.enabled is False

    def test_stopping_is_false(self):
        state = _AutoPilotState()
        assert state.stopping is False

    def test_current_feature_id_is_none(self):
        state = _AutoPilotState()
        assert state.current_feature_id is None

    def test_current_feature_name_is_none(self):
        state = _AutoPilotState()
        assert state.current_feature_name is None

    def test_last_error_is_none(self):
        state = _AutoPilotState()
        assert state.last_error is None

    def test_log_is_empty(self):
        state = _AutoPilotState()
        assert len(state.log) == 0

    def test_features_completed_is_zero(self):
        state = _AutoPilotState()
        assert state.features_completed == 0

    def test_budget_exhausted_is_false(self):
        state = _AutoPilotState()
        assert state.budget_exhausted is False

    def test_manual_active_is_false(self):
        state = _AutoPilotState()
        assert state.manual_active is False

    def test_log_maxlen_is_100(self):
        state = _AutoPilotState()
        # Append 120 entries; only last 100 should remain
        for i in range(120):
            _append_log(state, 'info', f"msg {i}")
        assert len(state.log) == 100
        assert state.log[-1].message == "msg 119"


# ---------------------------------------------------------------------------
# _append_log
# ---------------------------------------------------------------------------

class TestAppendLog:
    def test_appends_entry(self):
        state = _AutoPilotState()
        _append_log(state, 'info', 'hello')
        assert len(state.log) == 1

    def test_entry_has_correct_level(self):
        state = _AutoPilotState()
        _append_log(state, 'error', 'boom')
        assert state.log[-1].level == 'error'

    def test_entry_has_correct_message(self):
        state = _AutoPilotState()
        _append_log(state, 'success', 'done')
        assert state.log[-1].message == 'done'

    def test_entry_has_timestamp(self):
        state = _AutoPilotState()
        _append_log(state, 'info', 'ts')
        assert state.log[-1].timestamp is not None
        assert 'T' in state.log[-1].timestamp  # ISO format


# ---------------------------------------------------------------------------
# _disable_autopilot_state
# ---------------------------------------------------------------------------

class TestDisableAutopilotState:
    def test_sets_enabled_false(self):
        state = _AutoPilotState()
        state.enabled = True
        _disable_autopilot_state(state)
        assert state.enabled is False

    def test_clears_current_feature_id(self):
        state = _AutoPilotState()
        state.current_feature_id = 42
        _disable_autopilot_state(state)
        assert state.current_feature_id is None

    def test_clears_current_feature_name(self):
        state = _AutoPilotState()
        state.current_feature_name = "My Feature"
        _disable_autopilot_state(state)
        assert state.current_feature_name is None

    def test_clears_current_feature_model(self):
        state = _AutoPilotState()
        state.current_feature_model = "opus"
        _disable_autopilot_state(state)
        assert state.current_feature_model is None

    def test_clears_active_process(self):
        state = _AutoPilotState()
        state.active_process = MagicMock()
        _disable_autopilot_state(state)
        assert state.active_process is None

    def test_clears_monitor_task(self):
        state = _AutoPilotState()
        state.monitor_task = MagicMock()
        _disable_autopilot_state(state)
        assert state.monitor_task is None

    def test_does_not_clear_last_error(self):
        state = _AutoPilotState()
        state.last_error = "some error"
        _disable_autopilot_state(state)
        assert state.last_error == "some error"

    def test_does_not_clear_log(self):
        state = _AutoPilotState()
        _append_log(state, 'info', 'keep me')
        _disable_autopilot_state(state)
        assert len(state.log) == 1


# ---------------------------------------------------------------------------
# handle_all_complete
# ---------------------------------------------------------------------------

class TestHandleAllComplete:
    def test_sets_enabled_false(self):
        state = _AutoPilotState()
        state.enabled = True
        handle_all_complete(state)
        assert state.enabled is False

    def test_clears_current_feature_id(self):
        state = _AutoPilotState()
        state.current_feature_id = 5
        handle_all_complete(state)
        assert state.current_feature_id is None

    def test_clears_last_error(self):
        state = _AutoPilotState()
        state.last_error = "oops"
        handle_all_complete(state)
        assert state.last_error is None

    def test_appends_log_entry(self):
        state = _AutoPilotState()
        handle_all_complete(state)
        messages = [e.message for e in state.log]
        assert any("All tasks complete" in m for m in messages)

    def test_log_entry_is_info_level(self):
        state = _AutoPilotState()
        handle_all_complete(state)
        assert state.log[-1].level == 'info'


# ---------------------------------------------------------------------------
# handle_budget_exhausted
# ---------------------------------------------------------------------------

class TestHandleBudgetExhausted:
    def test_sets_budget_exhausted(self):
        state = _AutoPilotState()
        state.features_completed = 3
        handle_budget_exhausted(state)
        assert state.budget_exhausted is True

    def test_disables_autopilot(self):
        state = _AutoPilotState()
        state.enabled = True
        handle_budget_exhausted(state)
        assert state.enabled is False

    def test_appends_log_with_count(self):
        state = _AutoPilotState()
        state.features_completed = 5
        handle_budget_exhausted(state)
        messages = [e.message for e in state.log]
        assert any("5" in m and "budget" in m.lower() for m in messages)

    def test_singular_feature_message(self):
        state = _AutoPilotState()
        state.features_completed = 1
        handle_budget_exhausted(state)
        msg = state.log[-1].message
        assert "feature" in msg.lower()
        assert "features" not in msg.lower()

    def test_plural_features_message(self):
        state = _AutoPilotState()
        state.features_completed = 2
        handle_budget_exhausted(state)
        assert "features" in state.log[-1].message.lower()


# ---------------------------------------------------------------------------
# _extract_output_snippet
# ---------------------------------------------------------------------------

class TestExtractOutputSnippet:
    def test_returns_empty_string_for_blank(self):
        assert _extract_output_snippet("") == ""

    def test_returns_last_lines(self):
        text = "line1\nline2\nline3\nline4"
        result = _extract_output_snippet(text, max_lines=2)
        assert "line3" in result
        assert "line4" in result
        assert "line1" not in result

    def test_skips_blank_lines(self):
        text = "hello\n\n\nworld\n\n"
        result = _extract_output_snippet(text, max_lines=2)
        assert "hello" in result
        assert "world" in result

    def test_truncates_to_max_chars(self):
        text = "x" * 500
        result = _extract_output_snippet(text, max_chars=50)
        assert len(result) <= 50

    def test_truncation_adds_ellipsis(self):
        text = "x" * 500
        result = _extract_output_snippet(text, max_chars=50)
        assert result.endswith("\u2026")

    def test_joins_with_pipe(self):
        text = "first\nsecond\nthird"
        result = _extract_output_snippet(text, max_lines=3)
        assert " | " in result


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_rate_limit_patterns_contains_rate_limit(self):
        assert "rate limit" in CLAUDE_RATE_LIMIT_PATTERNS

    def test_rate_limit_patterns_contains_usage_limit(self):
        assert "usage limit" in CLAUDE_RATE_LIMIT_PATTERNS

    def test_rate_limit_patterns_contains_context_length_exceeded(self):
        assert "context_length_exceeded" in CLAUDE_RATE_LIMIT_PATTERNS

    def test_session_limit_exit_codes_contains_130(self):
        assert 130 in CLAUDE_SESSION_LIMIT_EXIT_CODES

    def test_process_timeout_is_positive(self):
        assert AUTOPILOT_PROCESS_TIMEOUT_SECS > 0


# ---------------------------------------------------------------------------
# _get_child_procs / _any_proc_running
# ---------------------------------------------------------------------------

class TestProcessHelpers:
    def test_get_child_procs_returns_list_without_psutil(self, monkeypatch):
        """When psutil is unavailable, returns an empty list."""
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == 'psutil':
                raise ImportError("no psutil")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, '__import__', mock_import)
        proc = MagicMock()
        result = _get_child_procs(proc)
        assert result == []

    def test_any_proc_running_returns_false_for_empty(self):
        assert _any_proc_running([]) is False

    def test_any_proc_running_returns_false_when_all_dead(self):
        p = MagicMock()
        p.is_running.return_value = False
        assert _any_proc_running([p]) is False

    def test_any_proc_running_returns_true_when_one_alive(self):
        p = MagicMock()
        p.is_running.return_value = True
        p.status.return_value = "running"
        assert _any_proc_running([p]) is True

    def test_any_proc_running_ignores_zombie(self):
        p = MagicMock()
        p.is_running.return_value = True
        p.status.return_value = "zombie"
        assert _any_proc_running([p]) is False


# ---------------------------------------------------------------------------
# _wait_for_process_and_children
# ---------------------------------------------------------------------------

class TestWaitForProcessAndChildren:
    def test_waits_for_proc(self):
        waited = []
        proc = MagicMock()
        proc.wait.side_effect = lambda: waited.append('proc')
        _wait_for_process_and_children(proc, [])
        assert 'proc' in waited

    def test_waits_for_children(self):
        waited = []
        proc = MagicMock()
        child = MagicMock()
        child.wait.side_effect = lambda: waited.append('child')
        _wait_for_process_and_children(proc, [child])
        assert 'child' in waited

    def test_tolerates_proc_exception(self):
        proc = MagicMock()
        proc.wait.side_effect = OSError("dead")
        # Should not raise
        _wait_for_process_and_children(proc, [])

    def test_tolerates_child_exception(self):
        proc = MagicMock()
        child = MagicMock()
        child.wait.side_effect = Exception("gone")
        # Should not raise
        _wait_for_process_and_children(proc, [child])


# ---------------------------------------------------------------------------
# _wait_for_stopping_process
# ---------------------------------------------------------------------------

class TestWaitForStoppingProcess:
    def test_clears_stopping_state_on_completion(self):
        proc = MagicMock()
        proc.wait.return_value = 0
        state = _AutoPilotState()
        state.stopping = True
        state.current_feature_id = 1
        state.current_feature_name = "Test"

        asyncio.run(_wait_for_stopping_process(proc, state))

        assert state.stopping is False
        assert state.current_feature_id is None
        assert state.current_feature_name is None

    def test_does_not_touch_state_on_cancellation(self):
        """CancelledError must not modify state (enable_autopilot owns it)."""
        import threading

        block_event = threading.Event()

        proc = MagicMock()
        proc.wait.side_effect = lambda: block_event.wait(timeout=10)

        state = _AutoPilotState()
        state.stopping = True
        state.current_feature_id = 99

        async def run():
            task = asyncio.create_task(_wait_for_stopping_process(proc, state))
            await asyncio.sleep(0)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            block_event.set()

        asyncio.run(run())
        # state.stopping should NOT have been cleared since task was cancelled
        assert state.stopping is True
        assert state.current_feature_id == 99


# ---------------------------------------------------------------------------
# Config persistence helpers
# ---------------------------------------------------------------------------

class TestResetAutopilotInConfig:
    def test_resets_autopilot_true_entries(self, tmp_path, monkeypatch):
        config = [{"name": "DB", "path": "a.db", "autopilot": True}]
        f = tmp_path / "dashboards.json"
        f.write_text(json.dumps(config))
        import backend.autopilot_engine as ae
        monkeypatch.setattr(ae, 'CONFIG_FILE', f)

        _reset_autopilot_in_config()

        result = json.loads(f.read_text())
        assert result[0]["autopilot"] is False

    def test_noop_when_no_autopilot_field(self, tmp_path, monkeypatch):
        config = [{"name": "DB", "path": "a.db"}]
        original_text = json.dumps(config)
        f = tmp_path / "dashboards.json"
        f.write_text(original_text)
        import backend.autopilot_engine as ae
        monkeypatch.setattr(ae, 'CONFIG_FILE', f)

        _reset_autopilot_in_config()

        assert f.read_text() == original_text

    def test_noop_when_file_missing(self, tmp_path, monkeypatch):
        import backend.autopilot_engine as ae
        monkeypatch.setattr(ae, 'CONFIG_FILE', tmp_path / "nonexistent.json")
        # Should not raise
        _reset_autopilot_in_config()


class TestReadAutopilotFromConfig:
    def test_returns_false_when_file_missing(self, tmp_path, monkeypatch):
        import backend.autopilot_engine as ae
        import backend.deps as deps
        monkeypatch.setattr(ae, 'CONFIG_FILE', tmp_path / "nonexistent.json")
        monkeypatch.setattr(deps, '_current_db_path', tmp_path / "features.db")

        assert _read_autopilot_from_config() is False

    def test_returns_true_when_path_matches_and_autopilot_true(self, tmp_path, monkeypatch):
        import backend.autopilot_engine as ae
        import backend.deps as deps
        db_path = tmp_path / "features.db"
        config = [{"name": "DB", "path": str(db_path), "autopilot": True}]
        f = tmp_path / "dashboards.json"
        f.write_text(json.dumps(config))
        monkeypatch.setattr(ae, 'CONFIG_FILE', f)
        monkeypatch.setattr(deps, '_current_db_path', db_path)

        assert _read_autopilot_from_config() is True

    def test_returns_false_when_path_not_in_config(self, tmp_path, monkeypatch):
        import backend.autopilot_engine as ae
        import backend.deps as deps
        config = [{"name": "Other", "path": str(tmp_path / "other.db"), "autopilot": True}]
        f = tmp_path / "dashboards.json"
        f.write_text(json.dumps(config))
        monkeypatch.setattr(ae, 'CONFIG_FILE', f)
        monkeypatch.setattr(deps, '_current_db_path', tmp_path / "features.db")

        assert _read_autopilot_from_config() is False


class TestWriteAutopilotToConfig:
    def test_writes_true_to_matching_entry(self, tmp_path, monkeypatch):
        import backend.autopilot_engine as ae
        import backend.deps as deps
        db_path = tmp_path / "features.db"
        config = [{"name": "DB", "path": str(db_path)}]
        f = tmp_path / "dashboards.json"
        f.write_text(json.dumps(config))
        monkeypatch.setattr(ae, 'CONFIG_FILE', f)
        monkeypatch.setattr(deps, '_current_db_path', db_path)

        _write_autopilot_to_config(True)

        result = json.loads(f.read_text())
        assert result[0]["autopilot"] is True

    def test_writes_false_to_matching_entry(self, tmp_path, monkeypatch):
        import backend.autopilot_engine as ae
        import backend.deps as deps
        db_path = tmp_path / "features.db"
        config = [{"name": "DB", "path": str(db_path), "autopilot": True}]
        f = tmp_path / "dashboards.json"
        f.write_text(json.dumps(config))
        monkeypatch.setattr(ae, 'CONFIG_FILE', f)
        monkeypatch.setattr(deps, '_current_db_path', db_path)

        _write_autopilot_to_config(False)

        result = json.loads(f.read_text())
        assert result[0]["autopilot"] is False

    def test_noop_when_file_missing(self, tmp_path, monkeypatch):
        import backend.autopilot_engine as ae
        import backend.deps as deps
        monkeypatch.setattr(ae, 'CONFIG_FILE', tmp_path / "nonexistent.json")
        monkeypatch.setattr(deps, '_current_db_path', tmp_path / "features.db")
        # Should not raise
        _write_autopilot_to_config(True)


# ---------------------------------------------------------------------------
# get_next_autopilot_feature
# ---------------------------------------------------------------------------

class TestGetNextAutopilotFeature:
    """Integration tests using a real in-memory SQLite DB."""

    @pytest.fixture
    def db_session(self, tmp_path):
        """Provide an isolated DB session with seeded features."""
        from api.database import Feature, create_database
        engine, session_maker = create_database(tmp_path)
        session = session_maker()
        features = [
            Feature(id=1, priority=100, category="X", name="F1",
                    description="d", steps=[], passes=False, in_progress=False),
            Feature(id=2, priority=200, category="X", name="F2",
                    description="d", steps=[], passes=False, in_progress=True),
            Feature(id=3, priority=300, category="X", name="F3",
                    description="d", steps=[], passes=True, in_progress=False),
        ]
        for f in features:
            session.add(f)
        session.commit()
        yield session
        session.close()
        engine.dispose()

    def test_returns_in_progress_feature_first(self, db_session):
        feature = get_next_autopilot_feature(db_session)
        assert feature is not None
        assert feature.id == 2  # in_progress=True

    def test_returns_todo_when_no_in_progress(self, db_session):
        from api.database import Feature as FeatureModel
        f = db_session.query(FeatureModel).filter(FeatureModel.id == 2).first()
        f.in_progress = False
        db_session.commit()

        feature = get_next_autopilot_feature(db_session)
        assert feature is not None
        assert feature.id == 1  # lowest priority TODO

    def test_returns_none_when_all_passing(self, db_session):
        from api.database import Feature as FeatureModel
        for fid in [1, 2]:
            f = db_session.query(FeatureModel).filter(FeatureModel.id == fid).first()
            f.passes = True
            f.in_progress = False
        db_session.commit()

        feature = get_next_autopilot_feature(db_session)
        assert feature is None
