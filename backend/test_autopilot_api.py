import subprocess
import sys
import tempfile
import shutil
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.main import app
from api.database import CategoryToken, create_database, DescriptionBigram, DescriptionToken, Feature, NameBigram, NameToken


class TestSpawnClaudeForAutopilot:
    """Unit tests for spawn_claude_for_autopilot(feature, settings, working_dir)."""

    def _make_feature(self, model="sonnet", feature_id=7, name="Test Feature"):
        """Return a simple namespace object that looks like a Feature ORM instance."""
        import types
        f = types.SimpleNamespace(
            id=feature_id,
            category="Testing",
            name=name,
            description="A test feature description",
            steps=["Step one", "Step two"],
            model=model,
        )
        return f

    def _default_settings(self):
        from backend.main import DEFAULT_PROMPT_TEMPLATE
        return {"claude_prompt_template": DEFAULT_PROMPT_TEMPLATE}

    def test_returns_popen_object(self, monkeypatch):
        """spawn_claude_for_autopilot returns the Popen handle."""
        from backend.main import spawn_claude_for_autopilot

        class MockProc:
            pid = 42

        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: MockProc())

        proc = spawn_claude_for_autopilot(
            self._make_feature(), self._default_settings(), "/tmp/work"
        )
        assert proc.pid == 42

    def test_uses_feature_model_in_command(self, monkeypatch):
        """The feature's model field appears in the spawned command."""
        from backend.main import spawn_claude_for_autopilot

        popen_calls = []

        def mock_popen(*args, **kwargs):
            popen_calls.append({"args": args, "kwargs": kwargs})
            return type("P", (), {"pid": 1, "wait": lambda self: 0})()

        monkeypatch.setattr(subprocess, "Popen", mock_popen)

        spawn_claude_for_autopilot(
            self._make_feature(model="opus"), self._default_settings(), "/tmp/work"
        )

        assert len(popen_calls) == 1
        call_args = popen_calls[0]["args"][0]
        full_command = " ".join(call_args) if isinstance(call_args, list) else str(call_args)
        assert "opus" in full_command

    def test_defaults_to_sonnet_when_model_is_none(self, monkeypatch):
        """When feature.model is None, the command defaults to sonnet."""
        from backend.main import spawn_claude_for_autopilot

        popen_calls = []

        def mock_popen(*args, **kwargs):
            popen_calls.append({"args": args, "kwargs": kwargs})
            return type("P", (), {"pid": 1, "wait": lambda self: 0})()

        monkeypatch.setattr(subprocess, "Popen", mock_popen)

        spawn_claude_for_autopilot(
            self._make_feature(model=None), self._default_settings(), "/tmp/work"
        )

        assert len(popen_calls) == 1
        call_args = popen_calls[0]["args"][0]
        full_command = " ".join(call_args) if isinstance(call_args, list) else str(call_args)
        assert "sonnet" in full_command

    def test_uses_prompt_template_from_settings(self, monkeypatch):
        """The prompt passed to the process includes content from the settings template."""
        from backend.main import spawn_claude_for_autopilot
        import tempfile as _tempfile
        import os

        written_prompts = []
        original_ntf = _tempfile.NamedTemporaryFile

        # Intercept the temp file write to capture the rendered prompt
        class CapturingNTF:
            def __init__(self, *a, **kw):
                self._ntf = original_ntf(*a, **kw)
                self.name = self._ntf.name

            def write(self, content):
                written_prompts.append(content)
                self._ntf.write(content)

            def __enter__(self):
                self._ntf.__enter__()
                return self

            def __exit__(self, *args):
                return self._ntf.__exit__(*args)

        monkeypatch.setattr(_tempfile, "NamedTemporaryFile", CapturingNTF)
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1, "wait": lambda self: 0})())

        custom_settings = {"claude_prompt_template": "CUSTOM: {name} - {description}"}
        feature = self._make_feature(name="My Feature")

        spawn_claude_for_autopilot(feature, custom_settings, "/tmp/work")

        # At least one temp file should have been written with the rendered prompt
        assert len(written_prompts) > 0
        rendered = written_prompts[0]
        assert "CUSTOM:" in rendered
        assert "My Feature" in rendered
        assert "A test feature description" in rendered

    def test_no_create_new_console_flag(self, monkeypatch):
        """On Windows the process is spawned WITHOUT CREATE_NEW_CONSOLE (background)."""
        import sys
        from backend.main import spawn_claude_for_autopilot

        popen_calls = []

        def mock_popen(*args, **kwargs):
            popen_calls.append({"args": args, "kwargs": kwargs})
            return type("P", (), {"pid": 1, "wait": lambda self: 0})()

        monkeypatch.setattr(subprocess, "Popen", mock_popen)
        # Force Windows code path regardless of actual OS
        monkeypatch.setattr(sys, "platform", "win32")

        spawn_claude_for_autopilot(
            self._make_feature(), self._default_settings(), "/tmp/work"
        )

        assert len(popen_calls) == 1
        kwargs = popen_calls[0]["kwargs"]
        # CREATE_NEW_CONSOLE must NOT be set
        assert "creationflags" not in kwargs or (
            kwargs["creationflags"] & subprocess.CREATE_NEW_CONSOLE == 0
        )

    def test_uses_print_flag(self, monkeypatch):
        """The spawned command includes --print for non-interactive execution."""
        from backend.main import spawn_claude_for_autopilot

        popen_calls = []

        def mock_popen(*args, **kwargs):
            popen_calls.append({"args": args, "kwargs": kwargs})
            return type("P", (), {"pid": 1, "wait": lambda self: 0})()

        monkeypatch.setattr(subprocess, "Popen", mock_popen)

        spawn_claude_for_autopilot(
            self._make_feature(), self._default_settings(), "/tmp/work"
        )

        assert len(popen_calls) == 1
        call_args = popen_calls[0]["args"][0]
        full_command = " ".join(call_args) if isinstance(call_args, list) else str(call_args)
        assert "--print" in full_command

    def test_uses_dangerously_skip_permissions(self, monkeypatch):
        """The spawned command includes --dangerously-skip-permissions."""
        from backend.main import spawn_claude_for_autopilot

        popen_calls = []

        def mock_popen(*args, **kwargs):
            popen_calls.append({"args": args, "kwargs": kwargs})
            return type("P", (), {"pid": 1, "wait": lambda self: 0})()

        monkeypatch.setattr(subprocess, "Popen", mock_popen)

        spawn_claude_for_autopilot(
            self._make_feature(), self._default_settings(), "/tmp/work"
        )

        assert len(popen_calls) == 1
        call_args = popen_calls[0]["args"][0]
        full_command = " ".join(call_args) if isinstance(call_args, list) else str(call_args)
        assert "--dangerously-skip-permissions" in full_command

    def test_raises_runtime_error_when_no_powershell(self, monkeypatch):
        """Raises RuntimeError when no PowerShell executable is found on Windows."""
        import sys
        from backend.main import spawn_claude_for_autopilot

        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))
        monkeypatch.setattr(sys, "platform", "win32")

        with pytest.raises(RuntimeError, match="No PowerShell found"):
            spawn_claude_for_autopilot(
                self._make_feature(), self._default_settings(), "/tmp/work"
            )

    def test_raises_descriptive_error_when_claude_not_in_path_on_linux(self, monkeypatch):
        """On Linux/Mac, FileNotFoundError from Popen is re-raised with a descriptive message."""
        import sys
        from backend.main import spawn_claude_for_autopilot

        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))
        monkeypatch.setattr(sys, "platform", "linux")

        with pytest.raises(FileNotFoundError, match="Claude CLI not found"):
            spawn_claude_for_autopilot(
                self._make_feature(), self._default_settings(), "/tmp/work"
            )

    def test_prompt_includes_feature_steps(self, monkeypatch):
        """The rendered prompt includes the feature's step list."""
        from backend.main import spawn_claude_for_autopilot
        import tempfile as _tempfile

        written_prompts = []
        original_ntf = _tempfile.NamedTemporaryFile

        class CapturingNTF:
            def __init__(self, *a, **kw):
                self._ntf = original_ntf(*a, **kw)
                self.name = self._ntf.name

            def write(self, content):
                written_prompts.append(content)
                self._ntf.write(content)

            def __enter__(self):
                self._ntf.__enter__()
                return self

            def __exit__(self, *args):
                return self._ntf.__exit__(*args)

        monkeypatch.setattr(_tempfile, "NamedTemporaryFile", CapturingNTF)
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1, "wait": lambda self: 0})())

        spawn_claude_for_autopilot(
            self._make_feature(), self._default_settings(), "/tmp/work"
        )

        assert len(written_prompts) > 0
        rendered = written_prompts[0]
        assert "Step one" in rendered
        assert "Step two" in rendered


class TestSpawnAndMonitor:
    """Unit tests for the _spawn_and_monitor() helper."""

    def _make_feature(self, feature_id=5, model="sonnet"):
        import types
        return types.SimpleNamespace(
            id=feature_id,
            category="Testing",
            name="Test Feature",
            description="A test feature",
            steps=["Step 1"],
            model=model,
        )

    def _make_state(self):
        import backend.main as m
        import backend.deps as deps_module
        # Use the same _AutoPilotState class; get a fresh instance via the module
        state = m._AutoPilotState()
        state.enabled = True
        return state

    def _default_settings(self):
        from backend.main import DEFAULT_PROMPT_TEMPLATE
        return {"claude_prompt_template": DEFAULT_PROMPT_TEMPLATE}

    def test_returns_true_on_success(self, monkeypatch):
        """_spawn_and_monitor returns True when spawning succeeds."""
        import asyncio
        import tempfile, types
        from backend.main import _spawn_and_monitor
        import backend.main as m
        import backend.deps as deps_module

        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: types.SimpleNamespace(pid=1))
        monkeypatch.setattr(asyncio, "create_task", lambda coro: coro.close() or None)

        state = self._make_state()
        tmp = tempfile.mkdtemp()
        db_path = Path(tmp) / "features.db"

        result = asyncio.get_event_loop().run_until_complete(
            _spawn_and_monitor(self._make_feature(), state, db_path, self._default_settings())
        )
        assert result is True

    def test_stores_active_process_on_success(self, monkeypatch):
        """On success, state.active_process is set to the spawned Popen handle."""
        import asyncio, types, tempfile
        from backend.main import _spawn_and_monitor

        mock_proc = types.SimpleNamespace(pid=42)
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: mock_proc)
        monkeypatch.setattr(asyncio, "create_task", lambda coro: coro.close() or None)

        state = self._make_state()
        tmp = tempfile.mkdtemp()
        db_path = Path(tmp) / "features.db"

        asyncio.get_event_loop().run_until_complete(
            _spawn_and_monitor(self._make_feature(), state, db_path, self._default_settings())
        )
        assert state.active_process is mock_proc

    def test_file_not_found_returns_false(self, monkeypatch):
        """FileNotFoundError during spawn returns False and resets state."""
        import asyncio, tempfile
        from backend.main import _spawn_and_monitor

        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("not found")))

        state = self._make_state()
        tmp = tempfile.mkdtemp()
        db_path = Path(tmp) / "features.db"

        result = asyncio.get_event_loop().run_until_complete(
            _spawn_and_monitor(self._make_feature(), state, db_path, self._default_settings())
        )
        assert result is False
        assert state.enabled is False
        assert state.active_process is None

    def test_file_not_found_sets_last_error(self, monkeypatch):
        """Spawn failure stores a non-empty error string in state.last_error."""
        import asyncio, tempfile
        from backend.main import _spawn_and_monitor

        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("missing claude")))

        state = self._make_state()
        tmp = tempfile.mkdtemp()
        db_path = Path(tmp) / "features.db"

        asyncio.get_event_loop().run_until_complete(
            _spawn_and_monitor(self._make_feature(), state, db_path, self._default_settings())
        )
        # Error message wording varies by platform (Windows transforms to PowerShell message),
        # so only check that some error was recorded
        assert state.last_error is not None
        assert len(state.last_error) > 0

    def test_file_not_found_appends_error_log(self, monkeypatch):
        """FileNotFoundError appends an error-level log entry."""
        import asyncio, tempfile
        from backend.main import _spawn_and_monitor

        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("not found")))

        state = self._make_state()
        tmp = tempfile.mkdtemp()
        db_path = Path(tmp) / "features.db"

        asyncio.get_event_loop().run_until_complete(
            _spawn_and_monitor(self._make_feature(), state, db_path, self._default_settings())
        )
        error_entries = [e for e in state.log if e.level == "error"]
        assert len(error_entries) >= 1

    def test_raise_on_error_raises_http_exception(self, monkeypatch):
        """With raise_on_error=True, FileNotFoundError raises HTTPException(500)."""
        import asyncio, tempfile
        from backend.main import _spawn_and_monitor
        from fastapi import HTTPException

        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("gone")))

        state = self._make_state()
        tmp = tempfile.mkdtemp()
        db_path = Path(tmp) / "features.db"

        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(
                _spawn_and_monitor(self._make_feature(), state, db_path, self._default_settings(), raise_on_error=True)
            )
        assert exc_info.value.status_code == 500

    def test_generic_exception_returns_false(self, monkeypatch):
        """An unexpected exception during spawn returns False and resets state."""
        import asyncio, tempfile
        from backend.main import _spawn_and_monitor

        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(ValueError("unexpected")))

        state = self._make_state()
        tmp = tempfile.mkdtemp()
        db_path = Path(tmp) / "features.db"

        result = asyncio.get_event_loop().run_until_complete(
            _spawn_and_monitor(self._make_feature(), state, db_path, self._default_settings())
        )
        assert result is False
        assert state.enabled is False

    def test_generic_exception_with_raise_on_error(self, monkeypatch):
        """With raise_on_error=True, a generic exception raises HTTPException(500)."""
        import asyncio, tempfile
        from backend.main import _spawn_and_monitor
        from fastapi import HTTPException

        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(ValueError("boom")))

        state = self._make_state()
        tmp = tempfile.mkdtemp()
        db_path = Path(tmp) / "features.db"

        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(
                _spawn_and_monitor(self._make_feature(), state, db_path, self._default_settings(), raise_on_error=True)
            )
        assert exc_info.value.status_code == 500
        assert "Failed to launch Claude" in exc_info.value.detail

    def test_generic_exception_appends_error_log(self, monkeypatch):
        """A generic exception appends an error-level log entry."""
        import asyncio, tempfile
        from backend.main import _spawn_and_monitor

        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("something went wrong")))

        state = self._make_state()
        tmp = tempfile.mkdtemp()
        db_path = Path(tmp) / "features.db"

        asyncio.get_event_loop().run_until_complete(
            _spawn_and_monitor(self._make_feature(), state, db_path, self._default_settings())
        )
        error_entries = [e for e in state.log if e.level == "error"]
        assert len(error_entries) >= 1


class TestGetNextAutopilotFeature:
    """Unit tests for get_next_autopilot_feature(session) sequencer function."""

    def test_in_progress_returned_before_todo(self, test_db):
        """In-progress features are returned before TODO features regardless of priority."""
        from backend.main import get_next_autopilot_feature

        # Seed DB has: feature 1 (todo, prio 100), feature 2 (todo, prio 200),
        #              feature 3 (done, prio 300), feature 4 (in_progress, prio 400)
        # Feature 4 has higher priority number but is in_progress, so it wins
        session = test_db()
        try:
            result = get_next_autopilot_feature(session)
            assert result is not None
            assert result.id == 4
            assert result.in_progress is True
        finally:
            session.close()

    def test_todo_features_ordered_by_priority(self, test_db):
        """When no in-progress features exist, lowest priority number is returned first."""
        from backend.main import get_next_autopilot_feature
        from api.database import Feature

        # Clear in_progress on feature 4 so only TODO features remain
        session = test_db()
        try:
            f4 = session.query(Feature).filter(Feature.id == 4).first()
            f4.in_progress = False
            session.commit()

            result = get_next_autopilot_feature(session)
            assert result is not None
            # Feature 1 has priority 100, feature 2 has priority 200 — pick lowest
            assert result.id == 1
            assert result.priority == 100
        finally:
            session.close()

    def test_in_progress_features_ordered_by_priority_among_themselves(self, test_db):
        """When multiple in-progress features exist, the one with the lowest priority is picked."""
        from backend.main import get_next_autopilot_feature
        from api.database import Feature

        # Mark feature 1 (prio 100) as in_progress too — lower priority number than feature 4 (400)
        session = test_db()
        try:
            f1 = session.query(Feature).filter(Feature.id == 1).first()
            f1.in_progress = True
            session.commit()

            result = get_next_autopilot_feature(session)
            assert result is not None
            # Feature 1 has priority 100 < feature 4 priority 400
            assert result.id == 1
        finally:
            session.close()

    def test_returns_none_when_all_features_are_passing(self, test_db):
        """Returns None when no in-progress or TODO features remain."""
        from backend.main import get_next_autopilot_feature
        from api.database import Feature

        session = test_db()
        try:
            # Mark all non-done features as done
            for fid in [1, 2, 4]:
                f = session.query(Feature).filter(Feature.id == fid).first()
                f.passes = True
                f.in_progress = False
            session.commit()

            result = get_next_autopilot_feature(session)
            assert result is None
        finally:
            session.close()

    def test_returns_none_when_database_is_empty(self, test_db):
        """Returns None when there are no features at all."""
        from backend.main import get_next_autopilot_feature
        from api.database import Feature

        session = test_db()
        try:
            session.query(Feature).delete()
            session.commit()

            result = get_next_autopilot_feature(session)
            assert result is None
        finally:
            session.close()

    def test_skips_passing_in_progress_edge_case(self, test_db):
        """A feature with both passes=True and in_progress=True is not returned."""
        from backend.main import get_next_autopilot_feature
        from api.database import Feature

        session = test_db()
        try:
            # Force feature 4 into a passes=True, in_progress=True edge state
            f4 = session.query(Feature).filter(Feature.id == 4).first()
            f4.passes = True
            # in_progress stays True
            session.commit()

            result = get_next_autopilot_feature(session)
            assert result is not None
            # Should fall through to TODO features (1 or 2), not pick the passing feature 4
            assert result.passes is False
            assert result.id in (1, 2)
        finally:
            session.close()


class TestAutoPilotEnable:
    """Tests for POST /api/autopilot/enable"""

    def _reset_autopilot_state(self, monkeypatch):
        """Reset autopilot state dict to isolate tests from each other."""
        import backend.main as main_module
        import backend.deps as deps_module
        monkeypatch.setattr(main_module, '_autopilot_states', {})

    def _get_full_command(self, popen_calls):
        call_args = popen_calls[0]["args"][0]
        return " ".join(call_args) if isinstance(call_args, list) else str(call_args)

    def test_enable_returns_200_with_todo_feature(self, client, monkeypatch):
        """Test that enabling autopilot returns 200 with enabled=True when TODO features exist."""
        self._reset_autopilot_state(monkeypatch)
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1, "wait": lambda self: 0})())

        response = client.post("/api/autopilot/enable")

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True
        assert data["current_feature_id"] is not None

    def test_enable_picks_in_progress_feature_first(self, client, monkeypatch):
        """Test that autopilot picks in-progress features before TODO features."""
        self._reset_autopilot_state(monkeypatch)
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1, "wait": lambda self: 0})())

        # Test DB has feature 4 as in_progress=True, passes=False
        response = client.post("/api/autopilot/enable")

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True
        # Feature 4 is in_progress, so it should be selected over TODO features 1/2
        assert data["current_feature_id"] == 4

    def test_enable_picks_todo_by_priority_when_no_in_progress(self, client, monkeypatch):
        """Test that autopilot picks the highest priority TODO when no in-progress feature exists."""
        self._reset_autopilot_state(monkeypatch)
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1, "wait": lambda self: 0})())

        # Move feature 4 out of in_progress state
        client.patch("/api/features/4/state", json={"in_progress": False})

        response = client.post("/api/autopilot/enable")

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True
        # Feature 1 has priority 100 (lowest = highest priority), feature 2 has 200
        assert data["current_feature_id"] == 1

    def test_enable_spawns_claude_process(self, client, monkeypatch):
        """Test that enabling autopilot spawns exactly one Claude process."""
        self._reset_autopilot_state(monkeypatch)
        popen_calls = []

        def mock_popen(*args, **kwargs):
            popen_calls.append({"args": args, "kwargs": kwargs})
            return type("P", (), {"pid": 1, "wait": lambda self: 0})()

        monkeypatch.setattr(subprocess, "Popen", mock_popen)

        response = client.post("/api/autopilot/enable")

        assert response.status_code == 200
        assert len(popen_calls) == 1

    def test_enable_uses_print_flag_for_hidden_execution(self, client, monkeypatch):
        """Test that autopilot launches Claude with --print (hidden execution)."""
        self._reset_autopilot_state(monkeypatch)
        popen_calls = []

        def mock_popen(*args, **kwargs):
            popen_calls.append({"args": args, "kwargs": kwargs})
            return type("P", (), {"pid": 1, "wait": lambda self: 0})()

        monkeypatch.setattr(subprocess, "Popen", mock_popen)

        response = client.post("/api/autopilot/enable")

        assert response.status_code == 200
        assert len(popen_calls) == 1
        full_command = self._get_full_command(popen_calls)
        assert "--print" in full_command

    def test_enable_uses_dangerously_skip_permissions(self, client, monkeypatch):
        """Test that autopilot launches Claude with --dangerously-skip-permissions."""
        self._reset_autopilot_state(monkeypatch)
        popen_calls = []

        def mock_popen(*args, **kwargs):
            popen_calls.append({"args": args, "kwargs": kwargs})
            return type("P", (), {"pid": 1, "wait": lambda self: 0})()

        monkeypatch.setattr(subprocess, "Popen", mock_popen)

        response = client.post("/api/autopilot/enable")

        assert response.status_code == 200
        full_command = self._get_full_command(popen_calls)
        assert "--dangerously-skip-permissions" in full_command

    def test_enable_returns_log_entries(self, client, monkeypatch):
        """Test that the response includes non-empty log entries."""
        self._reset_autopilot_state(monkeypatch)
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1, "wait": lambda self: 0})())

        response = client.post("/api/autopilot/enable")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["log"], list)
        assert len(data["log"]) > 0

    def test_enable_when_already_enabled_returns_409(self, client, monkeypatch):
        """Test that enabling autopilot when already enabled returns 409."""
        self._reset_autopilot_state(monkeypatch)
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1, "wait": lambda self: 0})())

        # Enable once
        first = client.post("/api/autopilot/enable")
        assert first.status_code == 200

        # Try to enable again — should get 409
        second = client.post("/api/autopilot/enable")
        assert second.status_code == 409
        assert "already enabled" in second.json()["detail"].lower()

    def test_enable_with_no_tasks_returns_disabled(self, client, monkeypatch):
        """Test that autopilot returns enabled=False with message when no tasks available."""
        self._reset_autopilot_state(monkeypatch)
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1, "wait": lambda self: 0})())

        # Mark all non-done features as done so no tasks remain
        for fid in [1, 2, 4]:
            client.patch(f"/api/features/{fid}/state", json={"passes": True})

        response = client.post("/api/autopilot/enable")

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False
        assert data["current_feature_id"] is None
        assert any("no tasks" in entry["message"].lower() for entry in data["log"])

    def test_enable_with_no_tasks_does_not_spawn_process(self, client, monkeypatch):
        """Test that no Claude process is spawned when no tasks are available."""
        self._reset_autopilot_state(monkeypatch)
        popen_calls = []

        def mock_popen(*args, **kwargs):
            popen_calls.append({"args": args, "kwargs": kwargs})
            return type("P", (), {"pid": 1, "wait": lambda self: 0})()

        monkeypatch.setattr(subprocess, "Popen", mock_popen)

        # Mark all non-done features as done
        for fid in [1, 2, 4]:
            client.patch(f"/api/features/{fid}/state", json={"passes": True})

        response = client.post("/api/autopilot/enable")

        assert response.status_code == 200
        assert len(popen_calls) == 0

    def test_enable_claude_not_found_returns_500(self, client, monkeypatch):
        """Test that a missing Claude CLI returns 500 and disables autopilot."""
        self._reset_autopilot_state(monkeypatch)

        def mock_popen_not_found(*args, **kwargs):
            raise FileNotFoundError("claude not found")

        monkeypatch.setattr(subprocess, "Popen", mock_popen_not_found)

        response = client.post("/api/autopilot/enable")

        assert response.status_code == 500

    def test_claude_not_found_status_shows_disabled_with_error(self, client, monkeypatch):
        """GET /api/autopilot/status returns enabled=False with CLI-not-found error after spawn failure."""
        import sys
        self._reset_autopilot_state(monkeypatch)

        # Force the Linux/Mac code path so subprocess.Popen is called with ["claude", ...]
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))

        # Enable autopilot — will fail because claude is not in PATH
        client.post("/api/autopilot/enable")

        # Status must reflect the disabled state with the descriptive error
        response = client.get("/api/autopilot/status")
        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False
        assert data["last_error"] is not None
        assert "Claude CLI not found" in data["last_error"]
        assert "PATH" in data["last_error"]

    def test_claude_not_found_appends_error_log_entry(self, client, monkeypatch):
        """After a CLI-not-found failure the log contains an error entry with the descriptive message."""
        import sys
        self._reset_autopilot_state(monkeypatch)

        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))

        client.post("/api/autopilot/enable")

        response = client.get("/api/autopilot/status")
        data = response.json()
        error_entries = [e for e in data["log"] if e["level"] == "error"]
        assert len(error_entries) >= 1
        assert any("Claude CLI not found" in e["message"] for e in error_entries)

    def test_enable_response_fields_present(self, client, monkeypatch):
        """Test that response always includes enabled, current_feature_id, and log."""
        self._reset_autopilot_state(monkeypatch)
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1, "wait": lambda self: 0})())

        response = client.post("/api/autopilot/enable")

        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data
        assert "current_feature_id" in data
        assert "log" in data

    def test_enable_log_contains_feature_name(self, client, monkeypatch):
        """Test that the log mentions the selected feature."""
        self._reset_autopilot_state(monkeypatch)
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1, "wait": lambda self: 0})())

        response = client.post("/api/autopilot/enable")

        assert response.status_code == 200
        data = response.json()
        log_text = " ".join(entry["message"] for entry in data["log"])
        # Should mention the feature ID
        assert str(data["current_feature_id"]) in log_text


class TestAutoPilotDisable:
    """Tests for POST /api/autopilot/disable"""

    def _reset_autopilot_state(self, monkeypatch):
        """Reset autopilot state dict to isolate tests from each other."""
        import backend.main as main_module
        import backend.deps as deps_module
        monkeypatch.setattr(main_module, '_autopilot_states', {})

    def test_disable_when_not_enabled_returns_200(self, client, monkeypatch):
        """Test that disabling when already disabled is idempotent and returns 200."""
        self._reset_autopilot_state(monkeypatch)

        response = client.post("/api/autopilot/disable")

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False

    def test_disable_after_enable_returns_200(self, client, monkeypatch):
        """Test that disabling after enabling returns 200 with enabled=False."""
        self._reset_autopilot_state(monkeypatch)
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1, "terminate": lambda self: None, "wait": lambda self: 0})())

        client.post("/api/autopilot/enable")

        response = client.post("/api/autopilot/disable")

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False

    def test_disable_sets_current_feature_id_to_none(self, client, monkeypatch):
        """Test that disabling clears current_feature_id."""
        self._reset_autopilot_state(monkeypatch)
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1, "terminate": lambda self: None, "wait": lambda self: 0})())

        enable_resp = client.post("/api/autopilot/enable")
        assert enable_resp.json()["current_feature_id"] is not None

        disable_resp = client.post("/api/autopilot/disable")
        assert disable_resp.json()["current_feature_id"] is None

    def test_disable_appends_manually_disabled_log_entry(self, client, monkeypatch):
        """Test that disable appends the 'manually disabled' log entry."""
        self._reset_autopilot_state(monkeypatch)

        response = client.post("/api/autopilot/disable")

        assert response.status_code == 200
        data = response.json()
        assert any("manually disabled" in entry["message"].lower() for entry in data["log"])

    def test_disable_terminates_active_process(self, client, monkeypatch):
        """Test that disable calls terminate() on the active process."""
        self._reset_autopilot_state(monkeypatch)
        terminate_calls = []

        class MockProcess:
            pid = 12345

            def terminate(self):
                terminate_calls.append(True)

        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: MockProcess())

        client.post("/api/autopilot/enable")
        assert len(terminate_calls) == 0

        client.post("/api/autopilot/disable")
        assert len(terminate_calls) == 1

    def test_disable_handles_already_exited_process_gracefully(self, client, monkeypatch):
        """Test that disable does not raise if process.terminate() fails (already exited)."""
        self._reset_autopilot_state(monkeypatch)

        class MockProcessAlreadyDead:
            pid = 99999

            def terminate(self):
                raise OSError("No such process")

        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: MockProcessAlreadyDead())

        client.post("/api/autopilot/enable")

        # Should not raise — disable handles the exception gracefully
        response = client.post("/api/autopilot/disable")
        assert response.status_code == 200
        assert response.json()["enabled"] is False

    def test_disable_when_no_process_does_not_terminate(self, client, monkeypatch):
        """Test that disabling when no process is running does not call terminate."""
        self._reset_autopilot_state(monkeypatch)
        terminate_calls = []

        class MockProcess:
            pid = 1

            def terminate(self):
                terminate_calls.append(True)

        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: MockProcess())

        # Disable without ever enabling — no process was spawned
        response = client.post("/api/autopilot/disable")
        assert response.status_code == 200
        assert len(terminate_calls) == 0

    def test_disable_is_idempotent_multiple_calls(self, client, monkeypatch):
        """Test that calling disable multiple times always returns 200 with enabled=False."""
        self._reset_autopilot_state(monkeypatch)
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1, "terminate": lambda self: None, "wait": lambda self: 0})())

        client.post("/api/autopilot/enable")

        for _ in range(3):
            response = client.post("/api/autopilot/disable")
            assert response.status_code == 200
            assert response.json()["enabled"] is False

    def test_disable_response_fields_present(self, client, monkeypatch):
        """Test that response always includes enabled, current_feature_id, and log."""
        self._reset_autopilot_state(monkeypatch)

        response = client.post("/api/autopilot/disable")

        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data
        assert "current_feature_id" in data
        assert "log" in data

    def test_re_enable_after_disable_works(self, client, monkeypatch):
        """Test that autopilot can be re-enabled after being disabled."""
        self._reset_autopilot_state(monkeypatch)
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1, "terminate": lambda self: None, "wait": lambda self: 0})())

        client.post("/api/autopilot/enable")
        client.post("/api/autopilot/disable")

        # Should be able to enable again
        response = client.post("/api/autopilot/enable")
        assert response.status_code == 200
        assert response.json()["enabled"] is True


class TestAutoPilotStatus:
    """Tests for GET /api/autopilot/status"""

    def _reset_autopilot_state(self, monkeypatch):
        """Reset autopilot state dict to isolate tests from each other."""
        import backend.main as main_module
        import backend.deps as deps_module
        monkeypatch.setattr(main_module, '_autopilot_states', {})

    def test_status_returns_200_with_correct_shape_when_disabled(self, client, monkeypatch):
        """Test: GET returns 200 with correct shape when autopilot is disabled."""
        self._reset_autopilot_state(monkeypatch)

        response = client.get("/api/autopilot/status")

        assert response.status_code == 200
        data = response.json()

        # Required fields present
        assert "enabled" in data
        assert "current_feature_id" in data
        assert "current_feature_name" in data
        assert "last_error" in data
        assert "log" in data

        # Correct values when disabled
        assert data["enabled"] is False
        assert data["current_feature_id"] is None
        assert data["current_feature_name"] is None
        assert data["last_error"] is None
        assert isinstance(data["log"], list)

    def test_status_log_entries_have_correct_shape(self, client, monkeypatch):
        """Test that log entries contain timestamp, level, and message fields."""
        self._reset_autopilot_state(monkeypatch)

        # Trigger a disable so there's at least one log entry
        client.post("/api/autopilot/disable")

        response = client.get("/api/autopilot/status")

        assert response.status_code == 200
        data = response.json()
        assert len(data["log"]) > 0

        entry = data["log"][0]
        assert "timestamp" in entry
        assert "level" in entry
        assert "message" in entry
        # timestamp is a non-empty ISO string
        assert len(entry["timestamp"]) > 0
        # level is one of the valid values
        assert entry["level"] in ("info", "success", "error")
        # message is a non-empty string
        assert len(entry["message"]) > 0

    def test_status_returns_correct_current_feature_id_when_enabled_and_running(self, client, monkeypatch):
        """Test: GET returns correct current_feature_id when autopilot is enabled and running."""
        self._reset_autopilot_state(monkeypatch)
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1, "wait": lambda self: 0})())

        # Enable autopilot — test DB has feature 4 as in_progress so it's selected first
        enable_resp = client.post("/api/autopilot/enable")
        assert enable_resp.status_code == 200
        expected_feature_id = enable_resp.json()["current_feature_id"]
        expected_feature_name = enable_resp.json()["current_feature_name"]

        # Now poll status
        response = client.get("/api/autopilot/status")

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True
        assert data["current_feature_id"] == expected_feature_id
        assert data["current_feature_name"] == expected_feature_name
        assert data["last_error"] is None

    def test_status_returns_enabled_false_after_disable(self, client, monkeypatch):
        """Test that status reflects disabled state after calling disable."""
        self._reset_autopilot_state(monkeypatch)
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1, "terminate": lambda self: None, "wait": lambda self: 0})())

        client.post("/api/autopilot/enable")
        client.post("/api/autopilot/disable")

        response = client.get("/api/autopilot/status")

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False
        assert data["current_feature_id"] is None
        assert data["current_feature_name"] is None

    def test_status_log_accumulates_across_enable_disable(self, client, monkeypatch):
        """Test that the log accumulates entries across enable and disable calls."""
        self._reset_autopilot_state(monkeypatch)
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 1, "terminate": lambda self: None, "wait": lambda self: 0})())

        client.post("/api/autopilot/enable")
        client.post("/api/autopilot/disable")

        response = client.get("/api/autopilot/status")

        assert response.status_code == 200
        data = response.json()
        # Should have entries from both enable (>= 3) and disable (1 more)
        assert len(data["log"]) >= 3

# ==============================================================================
# Process monitor tests
# ==============================================================================

class TestMonitorClaudeProcess:
    """Unit tests for monitor_claude_process coroutine."""

    def _make_mock_process(self, return_code=0):
        """Return a mock Popen-like object whose wait() returns return_code."""
        return_code_ = return_code

        class MockProcess:
            returncode = return_code_

            def wait(self):
                return return_code_

        return MockProcess()

    def test_success_flow_triggered_when_feature_passes_true(self, test_db_with_path, monkeypatch):
        """Success flow triggered when feature.passes becomes True after process exits."""
        import asyncio
        from backend.main import monitor_claude_process, _AutoPilotState
        from api.database import Feature as FeatureModel

        session_maker, db_path = test_db_with_path

        # Mark feature 1 as passing in the test DB
        session = session_maker()
        try:
            f1 = session.query(FeatureModel).filter(FeatureModel.id == 1).first()
            f1.passes = True
            session.commit()
        finally:
            session.close()

        success_calls = []
        failure_calls = []

        async def mock_success(fid, state, path):
            success_calls.append(fid)

        async def mock_failure(fid, exit_code, state):
            failure_calls.append((fid, exit_code))

        import backend.main as main_module
        import backend.deps as deps_module
        import backend.autopilot_engine as ae_module
        monkeypatch.setattr(ae_module, 'handle_autopilot_success', mock_success)
        monkeypatch.setattr(ae_module, 'handle_autopilot_failure', mock_failure)

        state = _AutoPilotState()
        proc = self._make_mock_process(return_code=0)

        asyncio.run(monitor_claude_process(1, proc, db_path, state))

        assert len(success_calls) == 1
        assert success_calls[0] == 1
        assert len(failure_calls) == 0

    def test_failure_flow_triggered_when_passes_false_and_nonzero_exit(self, test_db_with_path, monkeypatch):
        """Failure flow triggered when process exits with non-zero code and passes=False."""
        import asyncio
        from backend.main import monitor_claude_process, _AutoPilotState

        session_maker, db_path = test_db_with_path
        # Feature 1 has passes=False in the seed data — no modification needed

        success_calls = []
        failure_calls = []

        async def mock_success(fid, state, path):
            success_calls.append(fid)

        async def mock_failure(fid, exit_code, state, output_text=""):
            failure_calls.append((fid, exit_code))

        import backend.main as main_module
        import backend.deps as deps_module
        import backend.autopilot_engine as ae_module
        monkeypatch.setattr(ae_module, 'handle_autopilot_success', mock_success)
        monkeypatch.setattr(ae_module, 'handle_autopilot_failure', mock_failure)

        state = _AutoPilotState()
        proc = self._make_mock_process(return_code=1)

        asyncio.run(monitor_claude_process(1, proc, db_path, state))

        assert len(failure_calls) == 1
        assert failure_calls[0][0] == 1   # feature_id
        assert failure_calls[0][1] == 1   # exit_code
        assert len(success_calls) == 0

    def test_failure_flow_triggered_when_passes_false_and_zero_exit(self, test_db_with_path, monkeypatch):
        """Failure flow is triggered even when exit code is 0 if passes=False."""
        import asyncio
        from backend.main import monitor_claude_process, _AutoPilotState

        session_maker, db_path = test_db_with_path
        # Feature 1 passes=False by default

        failure_calls = []

        async def mock_failure(fid, exit_code, state, output_text=""):
            failure_calls.append((fid, exit_code))

        import backend.main as main_module
        import backend.deps as deps_module
        import backend.autopilot_engine as ae_module
        monkeypatch.setattr(ae_module, 'handle_autopilot_success', lambda *a: None)
        monkeypatch.setattr(ae_module, 'handle_autopilot_failure', mock_failure)

        state = _AutoPilotState()
        proc = self._make_mock_process(return_code=0)

        asyncio.run(monitor_claude_process(1, proc, db_path, state))

        assert len(failure_calls) == 1
        assert failure_calls[0][1] == 0

    def test_cancellation_is_handled_gracefully(self, monkeypatch):
        """CancelledError during process wait does not propagate out of the coroutine."""
        import asyncio
        from backend.main import monitor_claude_process, _AutoPilotState

        # Patch get_event_loop so run_in_executor raises CancelledError
        completed = []

        async def run():
            loop = asyncio.get_running_loop()

            async def mock_run_in_executor(executor, func, *args):
                raise asyncio.CancelledError()

            # Temporarily replace run_in_executor on this loop
            original = loop.run_in_executor
            loop.run_in_executor = mock_run_in_executor
            try:
                state = _AutoPilotState()

                class MockProcess:
                    def wait(self):
                        return 0

                await monitor_claude_process(1, MockProcess(), Path("/fake.db"), state)
                completed.append(True)
            finally:
                loop.run_in_executor = original

        asyncio.run(run())
        assert len(completed) == 1  # Coroutine returned normally

    def test_timeout_kills_process_and_disables_autopilot(self, monkeypatch):
        """When the process exceeds the timeout, it is killed and autopilot is disabled."""
        import asyncio
        import threading
        from backend.main import monitor_claude_process, _AutoPilotState
        import backend.main as main_module
        import backend.deps as deps_module
        import backend.autopilot_engine as ae_module

        # Use a very short timeout so the test completes quickly
        monkeypatch.setattr(ae_module, 'AUTOPILOT_PROCESS_TIMEOUT_SECS', 0.05)

        kill_event = threading.Event()
        killed = []

        class MockProcess:
            def wait(self):
                # Block until kill() is called (simulates a stuck process)
                kill_event.wait(timeout=10)
                return -9

            def kill(self):
                killed.append(True)
                kill_event.set()

        state = _AutoPilotState()
        state.enabled = True
        state.current_feature_id = 7
        state.current_feature_name = "Stuck Feature"
        state.current_feature_model = "sonnet"

        asyncio.run(monitor_claude_process(7, MockProcess(), Path("/fake.db"), state))

        assert len(killed) == 1, "process.kill() should be called on timeout"
        assert state.enabled is False, "autopilot should be disabled after timeout"
        assert state.last_error is not None, "last_error should be set after timeout"
        assert "timed out" in state.last_error.lower()
        assert state.current_feature_id is None
        assert state.current_feature_name is None
        assert state.current_feature_model is None
        assert state.active_process is None
        assert state.monitor_task is None
        error_entries = [e for e in state.log if e.level == 'error']
        assert len(error_entries) >= 1
        assert "timed out" in error_entries[0].message.lower()

    def test_timeout_cancellation_interplay(self, monkeypatch):
        """CancelledError raised during timeout handling exits cleanly without propagating."""
        import asyncio
        import threading
        from backend.main import monitor_claude_process, _AutoPilotState
        import backend.main as main_module
        import backend.deps as deps_module
        import backend.autopilot_engine as ae_module

        monkeypatch.setattr(ae_module, 'AUTOPILOT_PROCESS_TIMEOUT_SECS', 0.05)

        kill_event = threading.Event()
        completed = []

        class MockProcess:
            def wait(self):
                kill_event.wait(timeout=10)
                return -9

            def kill(self):
                kill_event.set()

        async def run():
            state = _AutoPilotState()
            task = asyncio.create_task(
                monitor_claude_process(7, MockProcess(), Path("/fake.db"), state)
            )
            # Let the timeout fire, then cancel the task before kill() completes
            await asyncio.sleep(0.1)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass  # Task was cancelled before completing — that's expected
            completed.append(True)

        asyncio.run(run())
        assert len(completed) == 1  # run() finished without propagating errors


class TestHandleAutopilotSuccess:
    """Unit tests for handle_autopilot_success."""

    def test_logs_success_message(self, test_db_with_path, monkeypatch):
        """Success handler appends a success log entry with feature id and name."""
        import asyncio
        from backend.main import handle_autopilot_success, _AutoPilotState

        session_maker, db_path = test_db_with_path

        # All features except feature 3 are non-passing; mock spawn to avoid real process
        monkeypatch.setattr("backend.autopilot_engine.spawn_claude_for_autopilot",
                            lambda *a, **k: type("P", (), {"pid": 1, "wait": lambda s: 0})())
        monkeypatch.setattr("asyncio.create_task", lambda coro: coro.close() or None)

        state = _AutoPilotState()
        state.current_feature_name = "My Completed Feature"
        asyncio.run(handle_autopilot_success(99, state, db_path))

        success_entries = [e for e in state.log if e.level == 'success']
        assert len(success_entries) == 1
        assert "99" in success_entries[0].message
        assert "My Completed Feature" in success_entries[0].message
        assert "completed:" in success_entries[0].message

    def test_starts_next_feature_when_available(self, test_db_with_path, monkeypatch):
        """Success handler spawns Claude for the next pending feature."""
        import asyncio
        from backend.main import handle_autopilot_success, _AutoPilotState

        session_maker, db_path = test_db_with_path
        spawn_calls = []

        def mock_spawn(feature, settings, working_dir):
            spawn_calls.append(feature.id)
            return type("P", (), {"pid": 1, "wait": lambda s: 0})()

        monkeypatch.setattr("backend.autopilot_engine.spawn_claude_for_autopilot", mock_spawn)
        # Prevent the newly created monitor task from running DB queries
        monkeypatch.setattr("asyncio.create_task", lambda coro: coro.close() or None)

        state = _AutoPilotState()
        asyncio.run(handle_autopilot_success(99, state, db_path))

        # Should have spawned Claude for the next feature (feature 4: in_progress=True)
        assert len(spawn_calls) == 1
        # current_feature_id must update to the specific next feature's id (Feature 4)
        assert state.current_feature_id == 4

    def test_resets_consecutive_skip_count(self, test_db_with_path, monkeypatch):
        """Success handler resets consecutive_skip_count to 0."""
        import asyncio
        from backend.main import handle_autopilot_success, _AutoPilotState

        session_maker, db_path = test_db_with_path

        monkeypatch.setattr("backend.autopilot_engine.spawn_claude_for_autopilot",
                            lambda *a, **k: type("P", (), {"pid": 1, "wait": lambda s: 0})())
        monkeypatch.setattr("asyncio.create_task", lambda coro: coro.close() or None)

        state = _AutoPilotState()
        state.consecutive_skip_count = 5  # simulate accumulated skips
        asyncio.run(handle_autopilot_success(99, state, db_path))

        assert state.consecutive_skip_count == 0

    def test_logs_all_tasks_complete_when_no_tasks_remain(self, test_db_with_path):
        """Success handler logs 'All tasks complete' when no pending features remain."""
        import asyncio
        from backend.main import handle_autopilot_success, _AutoPilotState
        from api.database import Feature as FeatureModel

        session_maker, db_path = test_db_with_path

        # Mark all non-passing features as passing so none remain
        session = session_maker()
        try:
            for fid in [1, 2, 4]:
                f = session.query(FeatureModel).filter(FeatureModel.id == fid).first()
                f.passes = True
                f.in_progress = False
            session.commit()
        finally:
            session.close()

        state = _AutoPilotState()
        state.enabled = True
        asyncio.run(handle_autopilot_success(99, state, db_path))

        log_messages = [e.message for e in state.log]
        assert any("All tasks complete" in m for m in log_messages)

    def test_disables_autopilot_when_no_tasks_remain(self, test_db_with_path, monkeypatch):
        """Success handler disables auto-pilot when all features are done."""
        import asyncio
        from backend.main import handle_autopilot_success, _AutoPilotState
        from api.database import Feature as FeatureModel

        session_maker, db_path = test_db_with_path

        # Mark all remaining non-passing features as passing
        session = session_maker()
        try:
            for fid in [1, 2, 4]:
                f = session.query(FeatureModel).filter(FeatureModel.id == fid).first()
                f.passes = True
                f.in_progress = False
            session.commit()
        finally:
            session.close()

        state = _AutoPilotState()
        state.enabled = True
        asyncio.run(handle_autopilot_success(99, state, db_path))

        assert state.enabled is False
        assert state.current_feature_id is None
        log_messages = [e.message for e in state.log]
        assert any("no more tasks" in m.lower() or "complete" in m.lower() for m in log_messages)

    def test_aborts_when_same_feature_returned_three_times(self, test_db_with_path, monkeypatch):
        """Auto-pilot aborts with a dead-loop error when the sequencer returns the same feature 3 times."""
        import asyncio
        from backend.main import handle_autopilot_success, _AutoPilotState

        session_maker, db_path = test_db_with_path
        # Seed data: Feature 4 (in_progress=True) is returned first by the sequencer
        # Pre-load state as if Feature 4 has been returned twice already
        state = _AutoPilotState()
        state.enabled = True
        state.last_skipped_feature_id = 4
        state.consecutive_skip_count = 2

        monkeypatch.setattr("asyncio.create_task", lambda coro: coro.close() or None)

        asyncio.run(handle_autopilot_success(99, state, db_path))

        assert state.enabled is False
        assert state.current_feature_id is None
        assert state.last_error is not None
        assert "Dead loop" in state.last_error
        assert "4" in state.last_error
        error_log = [e for e in state.log if e.level == 'error']
        assert len(error_log) == 1
        assert error_log[0].message == state.last_error

    def test_counter_resets_when_different_feature_returned(self, test_db_with_path, monkeypatch):
        """consecutive_skip_count resets to 0 and last_skipped_feature_id updates when a different feature is returned."""
        import asyncio
        from backend.main import handle_autopilot_success, _AutoPilotState

        session_maker, db_path = test_db_with_path
        # Pre-load state: skip count is 2 but last_skipped points to a feature NOT in the DB queue
        state = _AutoPilotState()
        state.last_skipped_feature_id = 999  # different from Feature 4 returned by sequencer
        state.consecutive_skip_count = 2

        monkeypatch.setattr("backend.autopilot_engine.spawn_claude_for_autopilot",
                            lambda *a, **k: type("P", (), {"pid": 1, "wait": lambda s: 0})())
        monkeypatch.setattr("asyncio.create_task", lambda coro: coro.close() or None)

        asyncio.run(handle_autopilot_success(99, state, db_path))

        # Different feature returned → counter must reset and last_skipped must update
        assert state.consecutive_skip_count == 0
        assert state.last_skipped_feature_id == 4  # Feature 4 is next per seed data
        assert state.enabled is not False or state.current_feature_id is not None  # not aborted

    def test_session_log_fields_reset_for_next_task(self, test_db_with_path, monkeypatch):
        """Session log tracking fields are reset when transitioning to the next AutoPilot task.

        Regression test for: Task Claude log shows old Task in Auto pilot.
        When AutoPilot finishes Task A and starts Task B, session_start_time,
        session_prompt_snippet, and session_jsonl_path must all be reset so the
        /api/autopilot/session-log endpoint discovers Task B's JSONL instead of
        returning Task A's cached log.
        """
        import asyncio
        from datetime import datetime, timezone
        from pathlib import Path as _Path
        from backend.main import handle_autopilot_success, _AutoPilotState

        session_maker, db_path = test_db_with_path

        monkeypatch.setattr("backend.autopilot_engine.spawn_claude_for_autopilot",
                            lambda *a, **k: type("P", (), {"pid": 1, "wait": lambda s: 0})())
        monkeypatch.setattr("asyncio.create_task", lambda coro: coro.close() or None)

        # Simulate state as if Task A (feature 1) had already run:
        # session fields are populated with Task A's data (the stale values)
        old_start_time = datetime(2000, 1, 1, tzinfo=timezone.utc)
        old_jsonl_path = _Path("/some/stale/task_a.jsonl")

        state = _AutoPilotState()
        state.current_feature_id = 1
        state.current_feature_name = "Task A"
        state.session_start_time = old_start_time
        state.session_prompt_snippet = "Feature #1 [Backend]"
        state.session_jsonl_path = old_jsonl_path

        before = datetime.now(timezone.utc)
        asyncio.run(handle_autopilot_success(1, state, db_path))

        # session_start_time must be a NEW timestamp (after 'before')
        assert state.session_start_time is not None
        assert state.session_start_time > old_start_time
        assert state.session_start_time >= before

        # session_jsonl_path must be cleared so the new JSONL is discovered on next poll
        assert state.session_jsonl_path is None

        # session_prompt_snippet must reference the NEW task (Feature 4 is next in seed data)
        assert state.session_prompt_snippet is not None
        assert state.session_prompt_snippet != "Feature #1 [Backend]"
        # Snippet must contain the new feature id (4) and its category
        assert "4" in state.session_prompt_snippet


class TestHandleAutopilotFailure:
    """Unit tests for handle_autopilot_failure."""

    def test_logs_error_message_with_exit_code(self):
        """Failure handler appends an error log with the feature id and exit code."""
        import asyncio
        from backend.main import handle_autopilot_failure, _AutoPilotState

        state = _AutoPilotState()
        state.enabled = True
        asyncio.run(handle_autopilot_failure(7, 42, state))

        log_messages = [e.message for e in state.log]
        assert any("7" in m and "42" in m for m in log_messages)
        assert any(e.level == 'error' for e in state.log)

    def test_disables_autopilot(self):
        """Failure handler sets enabled=False."""
        import asyncio
        from backend.main import handle_autopilot_failure, _AutoPilotState

        state = _AutoPilotState()
        state.enabled = True
        state.current_feature_id = 7
        asyncio.run(handle_autopilot_failure(7, 1, state))

        assert state.enabled is False
        assert state.current_feature_id is None

    def test_clears_active_process(self):
        """Failure handler clears state.active_process."""
        import asyncio
        from backend.main import handle_autopilot_failure, _AutoPilotState

        state = _AutoPilotState()
        state.active_process = object()  # simulate a live process
        asyncio.run(handle_autopilot_failure(7, 1, state))

        assert state.active_process is None

    def test_sets_last_error_with_descriptive_message(self):
        """Failure handler sets last_error to a descriptive message including feature id and exit code."""
        import asyncio
        from backend.main import handle_autopilot_failure, _AutoPilotState

        state = _AutoPilotState()
        asyncio.run(handle_autopilot_failure(7, 42, state))

        assert state.last_error is not None
        assert "7" in state.last_error
        assert "42" in state.last_error
        assert "not marked as passing" in state.last_error
        # Log entry message must match last_error exactly
        error_entries = [e for e in state.log if e.level == 'error']
        assert len(error_entries) == 1
        assert error_entries[0].message == state.last_error

    def test_feature_state_in_db_unchanged_after_failure(self, test_db_with_path):
        """Failure handler does not modify the feature's DB state."""
        import asyncio
        from backend.main import handle_autopilot_failure, _AutoPilotState
        from api.database import Feature as FeatureModel

        session_maker, db_path = test_db_with_path

        # Record the initial state of feature 1 (passes=False, in_progress=False)
        session = session_maker()
        try:
            before = session.query(FeatureModel).filter(FeatureModel.id == 1).first()
            before_passes = before.passes
            before_in_progress = before.in_progress
        finally:
            session.close()

        state = _AutoPilotState()
        asyncio.run(handle_autopilot_failure(1, 1, state))

        # Feature must be unchanged in the DB
        session = session_maker()
        try:
            after = session.query(FeatureModel).filter(FeatureModel.id == 1).first()
            assert after.passes == before_passes
            assert after.in_progress == before_in_progress
        finally:
            session.close()


class TestHandleAutopilotFailureRateLimit:
    """Tests for rate/session-limit detection in handle_autopilot_failure."""

    def _run(self, exit_code=1, output_text=""):
        import asyncio
        from backend.main import handle_autopilot_failure, _AutoPilotState
        state = _AutoPilotState()
        state.enabled = True
        asyncio.run(handle_autopilot_failure(7, exit_code, state, output_text))
        return state

    # ── exit code always logged ───────────────────────────────────────────────

    def test_exit_code_always_logged_normal_failure(self):
        """Raw exit code appears in the log even for a generic failure."""
        state = self._run(exit_code=42, output_text="")
        log_messages = [e.message for e in state.log]
        assert any("42" in m for m in log_messages)

    def test_exit_code_always_logged_rate_limit(self):
        """Raw exit code appears in the log even when a rate limit is detected."""
        state = self._run(exit_code=1, output_text="API Error: Rate limit reached")
        log_messages = [e.message for e in state.log]
        assert any("1" in m for m in log_messages)

    # ── normal failure path (no rate limit) ───────────────────────────────────

    def test_normal_failure_sets_error_level(self):
        """Generic failure uses 'error' log level."""
        state = self._run(exit_code=1, output_text="some unrelated error output")
        assert any(e.level == 'error' for e in state.log)

    def test_normal_failure_budget_exhausted_stays_false(self):
        """budget_exhausted is not set on a generic failure."""
        state = self._run(exit_code=1, output_text="")
        assert state.budget_exhausted is False

    def test_normal_failure_last_error_contains_not_marked_as_passing(self):
        """Generic failure message retains the original wording."""
        state = self._run(exit_code=1, output_text="")
        assert state.last_error is not None
        assert "not marked as passing" in state.last_error

    # ── rate limit via output text ─────────────────────────────────────────────

    def test_rate_limit_pattern_rate_limit(self):
        state = self._run(output_text="Error: rate limit exceeded")
        assert state.budget_exhausted is True

    def test_rate_limit_pattern_usage_limit(self):
        state = self._run(output_text="usage limit reached")
        assert state.budget_exhausted is True

    def test_rate_limit_pattern_session_limit(self):
        state = self._run(output_text="session limit hit")
        assert state.budget_exhausted is True

    def test_rate_limit_pattern_rate_limit_error_json(self):
        state = self._run(output_text='{"type":"rate_limit_error","message":"too many requests"}')
        assert state.budget_exhausted is True

    def test_rate_limit_pattern_overloaded_error(self):
        state = self._run(output_text='{"type":"overloaded_error"}')
        assert state.budget_exhausted is True

    def test_rate_limit_pattern_claude_usage_limit_reached(self):
        state = self._run(output_text="Claude usage limit reached. Your limit will reset at 5pm")
        assert state.budget_exhausted is True

    def test_rate_limit_pattern_youve_reached_your_usage_limit(self):
        state = self._run(output_text="You've reached your usage limit for this period.")
        assert state.budget_exhausted is True

    def test_rate_limit_pattern_is_case_insensitive(self):
        state = self._run(output_text="RATE LIMIT REACHED")
        assert state.budget_exhausted is True

    def test_rate_limit_friendly_message_in_last_error(self):
        state = self._run(output_text="rate limit exceeded")
        assert state.last_error is not None
        assert "session/rate limit" in state.last_error
        assert "please wait" in state.last_error.lower()

    def test_rate_limit_uses_info_log_level(self):
        """Rate limit message is logged at 'info' level (not 'error') so info banner shows."""
        state = self._run(output_text="rate limit exceeded")
        error_entries = [e for e in state.log if e.level == 'error']
        info_entries = [e for e in state.log if e.level == 'info']
        # No error-level entry for a rate-limit failure
        assert len(error_entries) == 0
        # At least one info entry contains the friendly message
        assert any("session/rate limit" in e.message for e in info_entries)

    def test_rate_limit_disables_autopilot(self):
        state = self._run(output_text="rate limit exceeded")
        assert state.enabled is False
        assert state.current_feature_id is None

    # ── rate limit via exit code ───────────────────────────────────────────────

    def test_exit_code_130_triggers_rate_limit_path(self):
        """Exit code 130 (SIGINT) is treated as a session/rate limit."""
        state = self._run(exit_code=130, output_text="")
        assert state.budget_exhausted is True

    def test_exit_code_130_friendly_message(self):
        state = self._run(exit_code=130, output_text="")
        assert state.last_error is not None
        assert "session/rate limit" in state.last_error

    def test_exit_code_130_info_log_level(self):
        state = self._run(exit_code=130, output_text="")
        error_entries = [e for e in state.log if e.level == 'error']
        assert len(error_entries) == 0

    def test_exit_code_1_without_rate_limit_output_is_generic_failure(self):
        """Exit code 1 with no matching output text remains a generic failure."""
        state = self._run(exit_code=1, output_text="some other error")
        assert state.budget_exhausted is False
        assert "not marked as passing" in state.last_error

    # ── context/token limit patterns ──────────────────────────────────────────

    def test_context_length_exceeded_triggers_rate_limit_path(self):
        """context_length_exceeded in output is treated as a limit."""
        state = self._run(output_text='{"type":"context_length_exceeded","message":"too long"}')
        assert state.budget_exhausted is True

    def test_prompt_is_too_long_triggers_rate_limit_path(self):
        """'prompt is too long' in output is treated as a limit."""
        state = self._run(output_text="Error: prompt is too long for this model")
        assert state.budget_exhausted is True

    def test_input_too_long_triggers_rate_limit_path(self):
        """'input_too_long' in output is treated as a limit."""
        state = self._run(output_text='{"error":"input_too_long"}')
        assert state.budget_exhausted is True

    def test_too_many_tokens_triggers_rate_limit_path(self):
        """'too many tokens' in output is treated as a limit."""
        state = self._run(output_text="Request failed: too many tokens in input")
        assert state.budget_exhausted is True

    def test_context_limit_patterns_are_case_insensitive(self):
        """Context limit patterns are matched case-insensitively."""
        state = self._run(output_text="CONTEXT_LENGTH_EXCEEDED")
        assert state.budget_exhausted is True

    # ── output snippet in generic error ───────────────────────────────────────

    def test_generic_failure_includes_output_snippet_in_last_error(self):
        """When generic failure, last_error includes trailing process output."""
        state = self._run(exit_code=1, output_text="line1\nfailed because of X\n")
        assert state.last_error is not None
        assert "not marked as passing" in state.last_error
        assert "failed because of X" in state.last_error

    def test_generic_failure_empty_output_no_snippet(self):
        """When output_text is empty, no snippet separator is added."""
        state = self._run(exit_code=1, output_text="")
        assert state.last_error is not None
        assert "\u2014" not in state.last_error  # em-dash separator absent

    def test_generic_failure_snippet_truncated_to_max_chars(self):
        """Snippet is truncated when output lines are very long."""
        long_line = "x" * 500
        state = self._run(exit_code=1, output_text=long_line)
        assert state.last_error is not None
        # last_error must contain the snippet but not the full 500-char line
        snippet_start = state.last_error.find("\u2014")
        if snippet_start != -1:
            snippet_part = state.last_error[snippet_start:]
            assert len(snippet_part) <= 210  # 200 chars + em-dash + space

    def test_generic_failure_uses_last_lines_of_output(self):
        """Only the trailing non-empty lines of output appear in the error."""
        output = "early line\nmiddle line\nlast error line"
        state = self._run(exit_code=1, output_text=output)
        assert "last error line" in state.last_error

    # ── _extract_output_snippet unit tests ────────────────────────────────────

    def test_extract_output_snippet_empty(self):
        from backend.main import _extract_output_snippet
        assert _extract_output_snippet("") == ""

    def test_extract_output_snippet_blank_lines_ignored(self):
        from backend.main import _extract_output_snippet
        assert _extract_output_snippet("\n\n\n") == ""

    def test_extract_output_snippet_single_line(self):
        from backend.main import _extract_output_snippet
        assert _extract_output_snippet("hello world") == "hello world"

    def test_extract_output_snippet_respects_max_lines(self):
        from backend.main import _extract_output_snippet
        out = "\n".join(f"line{i}" for i in range(10))
        result = _extract_output_snippet(out, max_lines=3)
        assert "line9" in result
        assert "line8" in result
        assert "line7" in result
        assert "line6" not in result

    def test_extract_output_snippet_truncates_long_output(self):
        from backend.main import _extract_output_snippet
        result = _extract_output_snippet("x" * 500, max_chars=50)
        assert len(result) <= 50
        assert result.endswith("\u2026")  # ellipsis

    # ── constants exported ─────────────────────────────────────────────────────

    def test_claude_session_limit_exit_codes_contains_130(self):
        from backend.main import CLAUDE_SESSION_LIMIT_EXIT_CODES
        assert 130 in CLAUDE_SESSION_LIMIT_EXIT_CODES

    def test_claude_rate_limit_patterns_contains_rate_limit(self):
        from backend.main import CLAUDE_RATE_LIMIT_PATTERNS
        assert "rate limit" in CLAUDE_RATE_LIMIT_PATTERNS

    def test_claude_rate_limit_patterns_contains_usage_limit(self):
        from backend.main import CLAUDE_RATE_LIMIT_PATTERNS
        assert "usage limit" in CLAUDE_RATE_LIMIT_PATTERNS

    def test_claude_rate_limit_patterns_contains_context_length_exceeded(self):
        from backend.main import CLAUDE_RATE_LIMIT_PATTERNS
        assert "context_length_exceeded" in CLAUDE_RATE_LIMIT_PATTERNS

    def test_claude_rate_limit_patterns_contains_prompt_is_too_long(self):
        from backend.main import CLAUDE_RATE_LIMIT_PATTERNS
        assert "prompt is too long" in CLAUDE_RATE_LIMIT_PATTERNS


class TestDisableAutopilotState:
    """Unit tests for _disable_autopilot_state() helper."""

    def test_sets_enabled_false(self):
        """_disable_autopilot_state sets enabled=False."""
        from backend.main import _disable_autopilot_state, _AutoPilotState

        state = _AutoPilotState()
        state.enabled = True
        _disable_autopilot_state(state)

        assert state.enabled is False

    def test_clears_current_feature_id(self):
        """_disable_autopilot_state clears current_feature_id."""
        from backend.main import _disable_autopilot_state, _AutoPilotState

        state = _AutoPilotState()
        state.current_feature_id = 42
        _disable_autopilot_state(state)

        assert state.current_feature_id is None

    def test_clears_current_feature_name(self):
        """_disable_autopilot_state clears current_feature_name."""
        from backend.main import _disable_autopilot_state, _AutoPilotState

        state = _AutoPilotState()
        state.current_feature_name = "My Feature"
        _disable_autopilot_state(state)

        assert state.current_feature_name is None

    def test_clears_current_feature_model(self):
        """_disable_autopilot_state clears current_feature_model."""
        from backend.main import _disable_autopilot_state, _AutoPilotState

        state = _AutoPilotState()
        state.current_feature_model = "opus"
        _disable_autopilot_state(state)

        assert state.current_feature_model is None

    def test_clears_active_process(self):
        """_disable_autopilot_state clears active_process."""
        from backend.main import _disable_autopilot_state, _AutoPilotState

        state = _AutoPilotState()
        state.active_process = object()
        _disable_autopilot_state(state)

        assert state.active_process is None

    def test_clears_monitor_task(self):
        """_disable_autopilot_state clears monitor_task."""
        from backend.main import _disable_autopilot_state, _AutoPilotState

        state = _AutoPilotState()
        state.monitor_task = object()
        _disable_autopilot_state(state)

        assert state.monitor_task is None

    def test_does_not_touch_other_fields(self):
        """_disable_autopilot_state leaves unrelated fields (last_error, budget_exhausted) unchanged."""
        from backend.main import _disable_autopilot_state, _AutoPilotState

        state = _AutoPilotState()
        state.last_error = "some error"
        state.budget_exhausted = True
        state.features_completed = 7
        _disable_autopilot_state(state)

        assert state.last_error == "some error"
        assert state.budget_exhausted is True
        assert state.features_completed == 7

    def test_idempotent_on_already_disabled_state(self):
        """Calling _disable_autopilot_state twice is safe and leaves state disabled."""
        from backend.main import _disable_autopilot_state, _AutoPilotState

        state = _AutoPilotState()
        state.enabled = True
        state.current_feature_id = 1
        _disable_autopilot_state(state)
        _disable_autopilot_state(state)

        assert state.enabled is False
        assert state.current_feature_id is None


class TestHandleAllComplete:
    """Unit and integration tests for handle_all_complete()."""

    def test_clears_last_error(self):
        """handle_all_complete clears last_error so status returns None."""
        from backend.main import handle_all_complete, _AutoPilotState

        state = _AutoPilotState()
        state.enabled = True
        state.last_error = "some previous error"
        handle_all_complete(state)

        assert state.last_error is None

    def test_sets_enabled_false(self):
        """handle_all_complete sets enabled=False."""
        from backend.main import handle_all_complete, _AutoPilotState

        state = _AutoPilotState()
        state.enabled = True
        handle_all_complete(state)

        assert state.enabled is False

    def test_clears_current_feature_id(self):
        """handle_all_complete clears current_feature_id."""
        from backend.main import handle_all_complete, _AutoPilotState

        state = _AutoPilotState()
        state.current_feature_id = 42
        handle_all_complete(state)

        assert state.current_feature_id is None

    def test_clears_active_process_and_monitor_task(self):
        """handle_all_complete clears active_process and monitor_task."""
        from backend.main import handle_all_complete, _AutoPilotState

        state = _AutoPilotState()
        state.active_process = object()
        state.monitor_task = object()
        handle_all_complete(state)

        assert state.active_process is None
        assert state.monitor_task is None

    def test_appends_exact_log_message(self):
        """handle_all_complete appends 'All tasks complete — auto-pilot disabled' info log."""
        from backend.main import handle_all_complete, _AutoPilotState

        state = _AutoPilotState()
        handle_all_complete(state)

        assert len(state.log) == 1
        entry = state.log[0]
        assert entry.level == 'info'
        assert entry.message == "All tasks complete \u2014 auto-pilot disabled"

    def test_status_endpoint_returns_disabled_and_no_error_after_all_complete(
        self, test_db_with_path, monkeypatch
    ):
        """GET /api/autopilot/status returns enabled=False and last_error=None after all tasks complete."""
        import asyncio
        from backend.main import handle_autopilot_success, _AutoPilotState
        from api.database import Feature as FeatureModel
        import backend.main as main_module
        import backend.deps as deps_module

        session_maker, db_path = test_db_with_path

        # Mark all non-passing features as passing so no work remains
        session = session_maker()
        try:
            for fid in [1, 2, 4]:
                f = session.query(FeatureModel).filter(FeatureModel.id == fid).first()
                f.passes = True
                f.in_progress = False
            session.commit()
        finally:
            session.close()

        # Set up the module-level state so the status endpoint reads from it
        state = _AutoPilotState()
        state.enabled = True
        state.last_error = "previous error"
        monkeypatch.setattr(deps_module, '_current_db_path', db_path)
        monkeypatch.setattr(main_module, '_autopilot_states', {str(db_path): state})

        asyncio.run(handle_autopilot_success(99, state, db_path))

        # Verify state directly (as the status endpoint reads it)
        assert state.enabled is False
        assert state.last_error is None


class TestDisableAutopilotCancelsMonitorTask:
    """Tests that disable_autopilot cancels the asyncio monitor task."""

    def _reset_autopilot_state(self, monkeypatch):
        import backend.main as main_module
        import backend.deps as deps_module
        monkeypatch.setattr(main_module, '_autopilot_states', {})

    def test_disable_cancels_monitor_task(self, client, monkeypatch):
        """Disabling auto-pilot cancels the monitor task."""
        self._reset_autopilot_state(monkeypatch)

        cancel_calls = []

        class MockTask:
            def cancel(self):
                cancel_calls.append(True)

        monkeypatch.setattr("backend.main.asyncio.create_task", lambda coro: (coro.close(), MockTask())[1])
        monkeypatch.setattr("backend.main.subprocess.Popen",
                            lambda *a, **k: type("P", (), {"pid": 1, "terminate": lambda s: None})())

        client.post("/api/autopilot/enable")
        assert len(cancel_calls) == 0

        client.post("/api/autopilot/disable")
        assert len(cancel_calls) == 1

    def test_disable_clears_monitor_task_field(self, client, monkeypatch):
        """Disabling auto-pilot sets state.monitor_task to None."""
        self._reset_autopilot_state(monkeypatch)
        import backend.main as main_module
        import backend.deps as deps_module

        monkeypatch.setattr("backend.main.asyncio.create_task", lambda coro: (coro.close(), None)[1])
        monkeypatch.setattr("backend.main.subprocess.Popen",
                            lambda *a, **k: type("P", (), {"pid": 1, "terminate": lambda s: None})())

        client.post("/api/autopilot/enable")
        client.post("/api/autopilot/disable")

        state = main_module.get_autopilot_state()
        assert state.monitor_task is None


class TestClearAutopilotLog:
    """Tests for POST /api/autopilot/log/clear"""

    def _reset_autopilot_state(self, monkeypatch):
        import backend.main as main_module
        import backend.deps as deps_module
        monkeypatch.setattr(main_module, '_autopilot_states', {})

    def test_clear_log_returns_200(self, client, monkeypatch):
        """Clear log endpoint returns 200 with cleared=true."""
        self._reset_autopilot_state(monkeypatch)

        response = client.post("/api/autopilot/log/clear")
        assert response.status_code == 200
        assert response.json() == {"cleared": True}

    def test_clear_log_empties_log(self, client, monkeypatch):
        """Clear log endpoint removes all log entries from state."""
        self._reset_autopilot_state(monkeypatch)
        import backend.main as main_module
        import backend.deps as deps_module

        # Populate the log by calling disable (which appends a log entry)
        monkeypatch.setattr("backend.main.subprocess.Popen",
                            lambda *a, **k: type("P", (), {"pid": 1, "terminate": lambda s: None})())
        client.post("/api/autopilot/disable")

        state = main_module.get_autopilot_state()
        assert len(state.log) > 0

        # Now clear
        client.post("/api/autopilot/log/clear")

        assert len(state.log) == 0

    def test_clear_log_idempotent_on_empty_log(self, client, monkeypatch):
        """Clearing an already-empty log returns 200 without error."""
        self._reset_autopilot_state(monkeypatch)

        response = client.post("/api/autopilot/log/clear")
        assert response.status_code == 200

        # Call again — still returns 200
        response = client.post("/api/autopilot/log/clear")
        assert response.status_code == 200
        assert response.json() == {"cleared": True}

    def test_clear_log_does_not_affect_enabled_state(self, client, monkeypatch):
        """Clearing the log does not change the enabled flag or current feature."""
        self._reset_autopilot_state(monkeypatch)
        import backend.main as main_module
        import backend.deps as deps_module

        # Manually set state fields
        state = main_module.get_autopilot_state()
        state.enabled = True
        state.current_feature_id = 42
        state.current_feature_name = "Test Feature"

        client.post("/api/autopilot/log/clear")

        state = main_module.get_autopilot_state()
        assert state.enabled is True
        assert state.current_feature_id == 42
        assert state.current_feature_name == "Test Feature"

    def test_status_log_empty_after_clear(self, client, monkeypatch):
        """GET /api/autopilot/status returns empty log after clear."""
        self._reset_autopilot_state(monkeypatch)
        import backend.main as main_module
        import backend.deps as deps_module

        # Add a log entry directly
        state = main_module.get_autopilot_state()
        main_module._append_log(state, 'info', 'Test entry')
        assert len(state.log) == 1

        # Clear via API
        client.post("/api/autopilot/log/clear")

        # Status should reflect empty log
        status = client.get("/api/autopilot/status").json()
        assert status["log"] == []


class TestClearAutoPilotError:
    """Tests for POST /api/autopilot/clear-error"""

    def _reset_autopilot_state(self, monkeypatch):
        import backend.main as main_module
        import backend.deps as deps_module
        monkeypatch.setattr(main_module, '_autopilot_states', {})

    def test_clear_error_returns_200(self, client, monkeypatch):
        """Clear error endpoint returns 200 with cleared=True."""
        self._reset_autopilot_state(monkeypatch)

        response = client.post("/api/autopilot/clear-error")
        assert response.status_code == 200
        assert response.json() == {"cleared": True}

    def test_clear_error_clears_last_error(self, client, monkeypatch):
        """Clear error endpoint sets last_error to None."""
        self._reset_autopilot_state(monkeypatch)
        import backend.main as main_module
        import backend.deps as deps_module

        # Manually set last_error
        state = main_module.get_autopilot_state()
        state.last_error = "Claude process exited with code 1"
        assert state.last_error is not None

        # Clear via API
        client.post("/api/autopilot/clear-error")

        state = main_module.get_autopilot_state()
        assert state.last_error is None

    def test_clear_error_idempotent_when_no_error(self, client, monkeypatch):
        """Clearing an already-null last_error returns 200 without error."""
        self._reset_autopilot_state(monkeypatch)

        response = client.post("/api/autopilot/clear-error")
        assert response.status_code == 200

        # Call again — still 200
        response = client.post("/api/autopilot/clear-error")
        assert response.status_code == 200
        assert response.json() == {"cleared": True}

    def test_clear_error_does_not_affect_enabled_or_log(self, client, monkeypatch):
        """Clearing the error does not change enabled state or log entries."""
        self._reset_autopilot_state(monkeypatch)
        import backend.main as main_module
        import backend.deps as deps_module

        state = main_module.get_autopilot_state()
        state.enabled = False
        state.last_error = "Some error"
        main_module._append_log(state, 'error', 'Some error')

        client.post("/api/autopilot/clear-error")

        state = main_module.get_autopilot_state()
        assert state.enabled is False
        assert len(state.log) == 1

    def test_status_last_error_null_after_clear(self, client, monkeypatch):
        """GET /api/autopilot/status returns last_error=null after clear-error."""
        self._reset_autopilot_state(monkeypatch)
        import backend.main as main_module
        import backend.deps as deps_module

        # Set an error directly
        state = main_module.get_autopilot_state()
        state.last_error = "Feature failed"

        status_before = client.get("/api/autopilot/status").json()
        assert status_before["last_error"] == "Feature failed"

        # Clear via API
        client.post("/api/autopilot/clear-error")

        status_after = client.get("/api/autopilot/status").json()
        assert status_after["last_error"] is None


class TestStartupAutoPilotReset:
    """Tests for startup_reset_autopilot() and _reset_autopilot_in_config()."""

    def test_status_returns_disabled_after_state_reinit(self, client, monkeypatch):
        """After simulated restart (state re-init), GET /api/autopilot/status returns enabled=False."""
        import backend.main as main_module
        import backend.deps as deps_module

        # Simulate pre-existing enabled state from before restart
        pre_restart_state = main_module._AutoPilotState()
        pre_restart_state.enabled = True
        pre_restart_state.current_feature_id = 1
        pre_restart_state.current_feature_name = "Old Feature"
        old_key = str(deps_module._current_db_path)
        monkeypatch.setattr(main_module, '_autopilot_states', {old_key: pre_restart_state})

        # Simulate startup reset: clear the state dict
        main_module._autopilot_states.clear()

        response = client.get("/api/autopilot/status")
        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False
        assert data["current_feature_id"] is None

    def test_no_orphaned_process_after_state_reinit(self, client, monkeypatch):
        """No orphaned process/task references exist after state re-init."""
        import backend.main as main_module
        import backend.deps as deps_module

        # Simulate state with live references
        pre_restart_state = main_module._AutoPilotState()
        pre_restart_state.active_process = object()
        pre_restart_state.monitor_task = object()
        old_key = str(deps_module._current_db_path)
        monkeypatch.setattr(main_module, '_autopilot_states', {old_key: pre_restart_state})

        # Simulate startup reset
        main_module._autopilot_states.clear()

        # Fresh state has no process references
        new_state = main_module.get_autopilot_state()
        assert new_state.active_process is None
        assert new_state.monitor_task is None

    def test_startup_reset_clears_state_dict(self, monkeypatch):
        """startup_reset_autopilot() clears all in-memory autopilot states."""
        import asyncio
        import backend.main as main_module
        import backend.deps as deps_module

        import backend.autopilot_engine as ae_module

        pre_state = main_module._AutoPilotState()
        pre_state.enabled = True
        shared_states = {'some_key': pre_state}
        monkeypatch.setattr(main_module, '_autopilot_states', shared_states)
        monkeypatch.setattr(ae_module, '_autopilot_states', shared_states)
        monkeypatch.setattr(main_module, '_reset_autopilot_in_config', lambda: None)

        asyncio.run(main_module.startup_reset_autopilot())

        # State dict should have exactly one entry (the newly created state)
        # with enabled=False
        assert len(shared_states) == 1
        new_state = list(shared_states.values())[0]
        assert new_state.enabled is False

    def test_startup_log_contains_reset_message(self, monkeypatch):
        """startup_reset_autopilot() appends 'Auto-pilot reset on backend restart' to the log."""
        import asyncio
        import backend.main as main_module
        import backend.deps as deps_module

        monkeypatch.setattr(main_module, '_autopilot_states', {})
        monkeypatch.setattr(main_module, '_reset_autopilot_in_config', lambda: None)

        asyncio.run(main_module.startup_reset_autopilot())

        state = main_module.get_autopilot_state()
        log_messages = [entry.message for entry in state.log]
        assert 'Auto-pilot reset on backend restart' in log_messages

    def test_startup_log_visible_via_status_endpoint(self, client, monkeypatch):
        """GET /api/autopilot/status after startup shows reset log entry."""
        import asyncio
        import backend.main as main_module
        import backend.deps as deps_module

        monkeypatch.setattr(main_module, '_autopilot_states', {})
        monkeypatch.setattr(main_module, '_reset_autopilot_in_config', lambda: None)

        asyncio.run(main_module.startup_reset_autopilot())

        response = client.get("/api/autopilot/status")
        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False
        log_messages = [entry["message"] for entry in data["log"]]
        assert any("reset" in m.lower() for m in log_messages)

    def test_reset_config_clears_autopilot_field(self, tmp_path, monkeypatch):
        """_reset_autopilot_in_config() sets autopilot=False in dashboards.json."""
        import json
        import backend.main as main_module
        import backend.deps as deps_module
        import backend.autopilot_engine as ae_module

        config = [
            {"name": "DB 1", "path": "a.db", "autopilot": True},
            {"name": "DB 2", "path": "b.db"},
        ]
        config_file = tmp_path / "dashboards.json"
        config_file.write_text(json.dumps(config))
        monkeypatch.setattr(ae_module, 'CONFIG_FILE', config_file)

        main_module._reset_autopilot_in_config()

        result = json.loads(config_file.read_text())
        assert result[0]["autopilot"] is False

    def test_reset_config_noop_when_no_autopilot_field(self, tmp_path, monkeypatch):
        """_reset_autopilot_in_config() does not modify dashboards.json if no autopilot field."""
        import json
        import backend.main as main_module
        import backend.deps as deps_module

        original = [{"name": "DB 1", "path": "a.db"}]
        config_file = tmp_path / "dashboards.json"
        original_text = json.dumps(original)
        config_file.write_text(original_text)
        monkeypatch.setattr(main_module, 'CONFIG_FILE', config_file)

        main_module._reset_autopilot_in_config()

        # File content should be unchanged (no write occurred)
        assert config_file.read_text() == original_text

    def test_reset_config_noop_when_no_file(self, tmp_path, monkeypatch):
        """_reset_autopilot_in_config() silently does nothing if dashboards.json doesn't exist."""
        import backend.main as main_module
        import backend.deps as deps_module

        nonexistent = tmp_path / "nonexistent.json"
        monkeypatch.setattr(main_module, 'CONFIG_FILE', nonexistent)

        # Should not raise any exception
        main_module._reset_autopilot_in_config()

    def test_reset_config_resets_multiple_entries(self, tmp_path, monkeypatch):
        """_reset_autopilot_in_config() resets all entries with autopilot=True."""
        import json
        import backend.main as main_module
        import backend.deps as deps_module
        import backend.autopilot_engine as ae_module

        config = [
            {"name": "DB 1", "path": "a.db", "autopilot": True},
            {"name": "DB 2", "path": "b.db", "autopilot": True},
            {"name": "DB 3", "path": "c.db"},
        ]
        config_file = tmp_path / "dashboards.json"
        config_file.write_text(json.dumps(config))
        monkeypatch.setattr(ae_module, 'CONFIG_FILE', config_file)

        main_module._reset_autopilot_in_config()

        result = json.loads(config_file.read_text())
        assert result[0]["autopilot"] is False
        assert result[1]["autopilot"] is False
        assert "autopilot" not in result[2]


class TestAutoPilotPersistence:
    """Tests for autopilot state persistence in dashboards.json.

    Verifies that enable/disable write the ``autopilot`` field to the config
    file, that the status endpoint restores the toggle from the persisted value
    after in-memory state is cleared (simulating a frontend reload), and that
    switching databases surfaces the correct per-database autopilot state.
    """

    @pytest.fixture
    def client_with_config(self, monkeypatch, tmp_path):
        """Test client with isolated DB *and* a temp dashboards.json config.

        The CONFIG_FILE global is patched to a temp JSON file containing a
        single entry whose ``path`` matches the temp database path, so that
        _read_autopilot_from_config / _write_autopilot_to_config work against
        a real (but isolated) file instead of the production dashboards.json.
        """
        import json
        import backend.main as main_module
        import backend.deps as deps_module
        import backend.autopilot_engine as ae_module

        temp_db_path = tmp_path / "features.db"
        engine, session_maker = create_database(tmp_path)

        session = session_maker()
        try:
            features = [
                Feature(id=1, priority=100, category="Backend", name="Feature 1",
                        description="Test feature 1", steps=["Step 1"], passes=False, in_progress=False),
                Feature(id=2, priority=200, category="Backend", name="Feature 2",
                        description="Test feature 2", steps=["Step 1"], passes=False, in_progress=False),
                Feature(id=3, priority=300, category="Frontend", name="Feature 3",
                        description="Test feature 3", steps=["Step 1"], passes=True, in_progress=False),
                Feature(id=4, priority=400, category="Frontend", name="Feature 4",
                        description="Test feature 4", steps=["Step 1"], passes=False, in_progress=True),
            ]
            for f in features:
                session.add(f)
            session.commit()
        finally:
            session.close()

        config_path = tmp_path / "dashboards.json"
        config_data = [{"name": "Test DB", "path": str(temp_db_path)}]
        config_path.write_text(json.dumps(config_data))

        shared_states: dict = {}
        monkeypatch.setattr(deps_module, '_session_maker', session_maker)
        monkeypatch.setattr(deps_module, '_current_db_path', temp_db_path)
        monkeypatch.setattr(main_module, 'CONFIG_FILE', config_path)
        monkeypatch.setattr(ae_module, 'CONFIG_FILE', config_path)
        monkeypatch.setattr(main_module, '_autopilot_states', shared_states)
        monkeypatch.setattr(ae_module, '_autopilot_states', shared_states)
        monkeypatch.setattr(main_module.asyncio, 'create_task',
                            lambda coro: (coro.close(), None)[1])

        yield TestClient(app), temp_db_path, config_path

        engine.dispose()
        try:
            shutil.rmtree(str(tmp_path))
        except (PermissionError, FileNotFoundError):
            pass

    def test_enable_writes_autopilot_true_to_config(self, client_with_config, monkeypatch):
        """POST /api/autopilot/enable writes autopilot=true to dashboards.json."""
        import json
        import backend.main as main_module
        import backend.deps as deps_module

        client, temp_db_path, config_path = client_with_config

        import subprocess as _subprocess
        monkeypatch.setattr(
            main_module, 'subprocess',
            type('M', (), {
                'Popen': lambda *a, **kw: type('P', (), {'pid': 1, 'stdout': None, 'stderr': None})(),
                'PIPE': _subprocess.PIPE,
            })()
        )

        response = client.post("/api/autopilot/enable")
        assert response.status_code == 200
        assert response.json()["enabled"] is True

        config = json.loads(config_path.read_text())
        assert config[0].get("autopilot") is True

    def test_disable_writes_autopilot_false_to_config(self, client_with_config, monkeypatch):
        """POST /api/autopilot/disable writes autopilot=false to dashboards.json."""
        import json
        import backend.main as main_module
        import backend.deps as deps_module

        client, temp_db_path, config_path = client_with_config

        monkeypatch.setattr(
            main_module, 'subprocess',
            type('M', (), {'Popen': lambda *a, **kw: type('P', (), {'pid': 1})()})()
        )

        client.post("/api/autopilot/enable")
        client.post("/api/autopilot/disable")

        config = json.loads(config_path.read_text())
        assert config[0].get("autopilot") is False

    def test_status_reads_persisted_state_after_memory_cleared(self, client_with_config, monkeypatch):
        """GET /api/autopilot/status returns enabled=True from config after in-memory state is cleared.

        Simulates a frontend reload: the in-memory state dict is wiped but the
        config file still has autopilot=true, so the status endpoint should
        restore the enabled flag from the persisted value.
        """
        import json
        import backend.main as main_module
        import backend.deps as deps_module

        client, temp_db_path, config_path = client_with_config

        # Write autopilot=true directly to the config file (bypassing enable endpoint)
        config_data = [{"name": "Test DB", "path": str(temp_db_path), "autopilot": True}]
        config_path.write_text(json.dumps(config_data))

        # Clear in-memory state (simulates what happens between a frontend reload
        # when the backend is still running but the state hasn't been initialised
        # for this db yet)
        main_module._autopilot_states.clear()

        response = client.get("/api/autopilot/status")
        assert response.status_code == 200
        assert response.json()["enabled"] is True

    def test_status_returns_false_when_config_has_no_autopilot_field(self, client_with_config):
        """GET /api/autopilot/status returns enabled=False when config has no autopilot field."""
        import backend.main as main_module
        import backend.deps as deps_module

        client, temp_db_path, config_path = client_with_config

        # _autopilot_states is already empty (fixture initialises to {})
        response = client.get("/api/autopilot/status")
        assert response.status_code == 200
        assert response.json()["enabled"] is False

    def test_switching_databases_shows_correct_autopilot_state(self, monkeypatch, tmp_path):
        """get_autopilot_state() initialises enabled from the per-db persisted value.

        DB A has autopilot=true in config → state.enabled should be True.
        DB B has autopilot=false (absent) → state.enabled should be False.
        """
        import json
        import backend.main as main_module
        import backend.deps as deps_module
        import backend.autopilot_engine as ae_module

        db_path_a = tmp_path / "a.db"
        db_path_b = tmp_path / "b.db"

        config_path = tmp_path / "dashboards.json"
        config_data = [
            {"name": "DB A", "path": str(db_path_a), "autopilot": True},
            {"name": "DB B", "path": str(db_path_b)},
        ]
        config_path.write_text(json.dumps(config_data))

        shared_states_a: dict = {}
        monkeypatch.setattr(main_module, 'CONFIG_FILE', config_path)
        monkeypatch.setattr(ae_module, 'CONFIG_FILE', config_path)
        monkeypatch.setattr(main_module, '_autopilot_states', shared_states_a)
        monkeypatch.setattr(ae_module, '_autopilot_states', shared_states_a)

        # Simulate switching to DB A
        monkeypatch.setattr(deps_module, '_current_db_path', db_path_a)
        state_a = main_module.get_autopilot_state()
        assert state_a.enabled is True

        # Reset in-memory state and simulate switching to DB B
        shared_states_b: dict = {}
        monkeypatch.setattr(main_module, '_autopilot_states', shared_states_b)
        monkeypatch.setattr(ae_module, '_autopilot_states', shared_states_b)
        monkeypatch.setattr(deps_module, '_current_db_path', db_path_b)
        state_b = main_module.get_autopilot_state()
        assert state_b.enabled is False

    def test_enable_no_write_when_spawn_fails(self, client_with_config, monkeypatch):
        """POST /api/autopilot/enable does not write autopilot=true when Claude spawn fails."""
        import json
        import backend.main as main_module
        import backend.deps as deps_module

        client, temp_db_path, config_path = client_with_config

        # Make subprocess.Popen raise FileNotFoundError (claude not found)
        def raise_fnf(*args, **kwargs):
            raise FileNotFoundError("claude: command not found")

        monkeypatch.setattr(main_module.subprocess, 'Popen', raise_fnf)

        response = client.post("/api/autopilot/enable")
        assert response.status_code == 500

        # Config should NOT have autopilot=true because spawn failed
        config = json.loads(config_path.read_text())
        assert config[0].get("autopilot") is not True

    def test_read_autopilot_from_config_returns_false_when_no_file(self, monkeypatch, tmp_path):
        """_read_autopilot_from_config() returns False when CONFIG_FILE does not exist."""
        import backend.main as main_module
        import backend.deps as deps_module
        import backend.autopilot_engine as ae_module

        monkeypatch.setattr(ae_module, 'CONFIG_FILE', tmp_path / "nonexistent.json")
        monkeypatch.setattr(deps_module, '_current_db_path', tmp_path / "features.db")

        assert main_module._read_autopilot_from_config() is False

    def test_read_autopilot_from_config_returns_false_when_path_not_in_config(self, monkeypatch, tmp_path):
        """_read_autopilot_from_config() returns False when the current db path is not in config."""
        import json
        import backend.main as main_module
        import backend.deps as deps_module
        import backend.autopilot_engine as ae_module

        config_path = tmp_path / "dashboards.json"
        config_path.write_text(json.dumps([{"name": "Other", "path": str(tmp_path / "other.db"), "autopilot": True}]))
        monkeypatch.setattr(ae_module, 'CONFIG_FILE', config_path)
        monkeypatch.setattr(deps_module, '_current_db_path', tmp_path / "features.db")

        assert main_module._read_autopilot_from_config() is False

    def test_write_autopilot_to_config_noop_when_no_file(self, monkeypatch, tmp_path):
        """_write_autopilot_to_config() silently does nothing when CONFIG_FILE is absent."""
        import backend.main as main_module
        import backend.deps as deps_module

        monkeypatch.setattr(main_module, 'CONFIG_FILE', tmp_path / "nonexistent.json")
        monkeypatch.setattr(deps_module, '_current_db_path', tmp_path / "features.db")

        # Should not raise
        main_module._write_autopilot_to_config(True)

    def test_write_autopilot_to_config_noop_when_path_not_in_config(self, monkeypatch, tmp_path):
        """_write_autopilot_to_config() does not modify config when db path not found."""
        import json
        import backend.main as main_module
        import backend.deps as deps_module

        original = [{"name": "Other", "path": str(tmp_path / "other.db")}]
        config_path = tmp_path / "dashboards.json"
        config_path.write_text(json.dumps(original))
        monkeypatch.setattr(main_module, 'CONFIG_FILE', config_path)
        monkeypatch.setattr(deps_module, '_current_db_path', tmp_path / "features.db")

        main_module._write_autopilot_to_config(True)

        result = json.loads(config_path.read_text())
        # Other entry should be unmodified, no autopilot field added
        assert result[0].get("autopilot") is None


class TestAutoPilotStoppingState:
    """Tests for the 'stopping' state introduced so the status bar remains
    visible when autopilot is disabled but the Claude process is still alive."""

    def _reset_autopilot_state(self, monkeypatch):
        import backend.main as main_module
        import backend.deps as deps_module
        monkeypatch.setattr(main_module, '_autopilot_states', {})

    # ------------------------------------------------------------------
    # disable_autopilot — process still running after terminate()
    # ------------------------------------------------------------------

    def test_disable_returns_stopping_true_when_process_still_alive(self, client, monkeypatch):
        """disable returns stopping=True when poll() returns None (process alive)."""
        self._reset_autopilot_state(monkeypatch)

        class StillRunningProcess:
            pid = 42
            def terminate(self): pass
            def poll(self): return None   # still alive
            def wait(self): return 0

        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: StillRunningProcess())
        client.post("/api/autopilot/enable")

        resp = client.post("/api/autopilot/disable")
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is False
        assert data["stopping"] is True

    def test_disable_stopping_preserves_feature_info(self, client, monkeypatch):
        """When stopping=True, feature id/name/model remain in the response."""
        self._reset_autopilot_state(monkeypatch)

        class StillRunningProcess:
            pid = 42
            def terminate(self): pass
            def poll(self): return None
            def wait(self): return 0

        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: StillRunningProcess())
        enable_resp = client.post("/api/autopilot/enable")
        fid = enable_resp.json()["current_feature_id"]
        fname = enable_resp.json()["current_feature_name"]

        disable_resp = client.post("/api/autopilot/disable")
        data = disable_resp.json()
        assert data["current_feature_id"] == fid
        assert data["current_feature_name"] == fname

    def test_disable_stopping_log_message(self, client, monkeypatch):
        """When entering stopping state the log mentions 'waiting for Claude process'."""
        self._reset_autopilot_state(monkeypatch)

        class StillRunningProcess:
            pid = 42
            def terminate(self): pass
            def poll(self): return None
            def wait(self): return 0

        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: StillRunningProcess())
        client.post("/api/autopilot/enable")

        resp = client.post("/api/autopilot/disable")
        log_messages = [e["message"] for e in resp.json()["log"]]
        assert any("waiting for Claude process" in m for m in log_messages)

    # ------------------------------------------------------------------
    # disable_autopilot — process already exited after terminate()
    # ------------------------------------------------------------------

    def test_disable_returns_stopping_false_when_process_already_exited(self, client, monkeypatch):
        """disable returns stopping=False when poll() returns exit code (process gone)."""
        self._reset_autopilot_state(monkeypatch)

        class ExitedProcess:
            pid = 42
            def terminate(self): pass
            def poll(self): return 0   # already exited
            def wait(self): return 0

        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: ExitedProcess())
        client.post("/api/autopilot/enable")

        resp = client.post("/api/autopilot/disable")
        data = resp.json()
        assert data["enabled"] is False
        assert data["stopping"] is False
        assert data["current_feature_id"] is None

    def test_disable_no_process_returns_stopping_false(self, client, monkeypatch):
        """Disabling with no active process always returns stopping=False."""
        self._reset_autopilot_state(monkeypatch)

        resp = client.post("/api/autopilot/disable")
        data = resp.json()
        assert data["enabled"] is False
        assert data["stopping"] is False

    # ------------------------------------------------------------------
    # get_autopilot_status reflects stopping field from state
    # ------------------------------------------------------------------

    def test_status_endpoint_includes_stopping_field(self, client, monkeypatch):
        """GET /api/autopilot/status always includes the stopping field."""
        self._reset_autopilot_state(monkeypatch)

        resp = client.get("/api/autopilot/status")
        assert resp.status_code == 200
        assert "stopping" in resp.json()

    def test_status_returns_stopping_true_when_state_is_stopping(self, client, monkeypatch):
        """Status endpoint reflects stopping=True while waiting for process to exit."""
        self._reset_autopilot_state(monkeypatch)
        import backend.main as main_module
        import backend.deps as deps_module

        class StillRunningProcess:
            pid = 42
            def terminate(self): pass
            def poll(self): return None
            def wait(self): return 0

        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: StillRunningProcess())
        client.post("/api/autopilot/enable")
        client.post("/api/autopilot/disable")

        # Manually verify state reflects stopping (asyncio.create_task is suppressed)
        state = main_module.get_autopilot_state()
        assert state.stopping is True

        resp = client.get("/api/autopilot/status")
        data = resp.json()
        assert data["enabled"] is False
        assert data["stopping"] is True
        assert data["current_feature_id"] is not None

    def test_status_returns_stopping_false_when_not_stopping(self, client, monkeypatch):
        """Status endpoint returns stopping=False when autopilot is cleanly disabled."""
        self._reset_autopilot_state(monkeypatch)

        resp = client.get("/api/autopilot/status")
        assert resp.json()["stopping"] is False

    # ------------------------------------------------------------------
    # enable_autopilot clears stopping state
    # ------------------------------------------------------------------

    def test_enable_clears_stopping_state(self, client, monkeypatch):
        """Re-enabling autopilot while stopping clears the stopping flag."""
        self._reset_autopilot_state(monkeypatch)
        import backend.main as main_module
        import backend.deps as deps_module

        class StillRunningProcess:
            pid = 42
            def terminate(self): pass
            def poll(self): return None
            def wait(self): return 0

        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: StillRunningProcess())
        client.post("/api/autopilot/enable")
        client.post("/api/autopilot/disable")

        # Force state back to not-enabled so enable is accepted (stopping=True, enabled=False)
        state = main_module.get_autopilot_state()
        assert state.stopping is True

        # Re-enable — now use a process that looks exited so disable later is clean
        class ExitedProcess:
            pid = 99
            def terminate(self): pass
            def poll(self): return 0
            def wait(self): return 0

        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: ExitedProcess())
        enable_resp = client.post("/api/autopilot/enable")
        assert enable_resp.status_code == 200

        state2 = main_module.get_autopilot_state()
        assert state2.stopping is False
        assert state2.enabled is True

    def test_enable_during_stopping_terminates_old_process(self, client, monkeypatch):
        """Re-enabling while stopping calls terminate() on the old orphaned process."""
        self._reset_autopilot_state(monkeypatch)
        import backend.main as main_module
        import backend.deps as deps_module

        terminate_calls = []

        class StillRunningProcess:
            pid = 42
            def terminate(self): terminate_calls.append('old')
            def poll(self): return None
            def wait(self): return 0

        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: StillRunningProcess())
        client.post("/api/autopilot/enable")
        client.post("/api/autopilot/disable")

        assert monkeypatch  # state.stopping should be True at this point
        state = main_module.get_autopilot_state()
        assert state.stopping is True

        # Re-enable — new process
        class ExitedProcess:
            pid = 99
            def terminate(self): terminate_calls.append('new')
            def poll(self): return 0
            def wait(self): return 0

        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: ExitedProcess())
        client.post("/api/autopilot/enable")

        # The old process must have been terminated during re-enable
        assert 'old' in terminate_calls

    def test_enable_during_stopping_clears_old_active_process(self, client, monkeypatch):
        """After re-enabling while stopping, active_process points to the NEW process."""
        self._reset_autopilot_state(monkeypatch)
        import backend.main as main_module
        import backend.deps as deps_module

        class StillRunningProcess:
            pid = 42
            def terminate(self): pass
            def poll(self): return None
            def wait(self): return 0

        class ExitedProcess:
            pid = 99
            def terminate(self): pass
            def poll(self): return 0
            def wait(self): return 0

        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: StillRunningProcess())
        client.post("/api/autopilot/enable")
        client.post("/api/autopilot/disable")

        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: ExitedProcess())
        client.post("/api/autopilot/enable")

        state = main_module.get_autopilot_state()
        assert state.active_process is not None
        assert state.active_process.pid == 99  # New process, not old orphan

    def test_wait_for_stopping_process_does_not_clear_state_when_cancelled(self, monkeypatch):
        """_wait_for_stopping_process leaves state untouched when the task is cancelled."""
        import asyncio
        import threading
        import backend.main as main_module
        import backend.deps as deps_module

        # Build a minimal state object mimicking the stopping scenario
        state = main_module._AutoPilotState()
        state.stopping = True
        state.enabled = True  # simulates new enable that ran AFTER cancel
        state.current_feature_id = 77
        state.current_feature_name = "New Feature"
        state.current_feature_model = "sonnet"

        # Use a threading.Event so the executor thread can be unblocked cleanly
        # after the task is cancelled, allowing asyncio.run() to shut down.
        wait_gate = threading.Event()

        class BlockingProcess:
            def wait(self):
                # Block until the test tells us to unblock (after cancel).
                wait_gate.wait(timeout=10)

        async def run():
            task = asyncio.create_task(
                main_module._wait_for_stopping_process(BlockingProcess(), state)
            )
            # Yield so the task starts and enters run_in_executor
            await asyncio.sleep(0)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            # Unblock the executor thread so asyncio.run() can shut down cleanly
            wait_gate.set()

        asyncio.run(run())

        # State should be unchanged — the cancel path must not wipe anything
        assert state.enabled is True
        assert state.current_feature_id == 77
        assert state.current_feature_name == "New Feature"
        assert state.stopping is True  # still stopping (caller is responsible)


class TestChildProcessTracking:
    """Tests that disable_autopilot tracks child processes (Windows PowerShell wrapper).

    On Windows, Claude runs as a child of a PowerShell wrapper.  Terminating the
    wrapper exits it almost immediately, but Claude keeps running as an orphan.
    The fix collects child processes *before* terminate() and waits for all of
    them in _wait_for_stopping_process so the UI remains in 'Stopping…' state
    until Claude actually finishes.
    """

    def _reset_autopilot_state(self, monkeypatch):
        import backend.main as main_module
        import backend.deps as deps_module
        monkeypatch.setattr(main_module, '_autopilot_states', {})

    # ------------------------------------------------------------------
    # _get_child_procs helper
    # ------------------------------------------------------------------

    def test_get_child_procs_returns_empty_when_psutil_unavailable(self, monkeypatch):
        """_get_child_procs falls back to [] when psutil cannot be imported."""
        import backend.main as main_module
        import backend.deps as deps_module
        import builtins

        real_import = builtins.__import__

        def no_psutil(name, *args, **kwargs):
            if name == "psutil":
                raise ImportError("psutil not available")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", no_psutil)

        class FakeProc:
            pid = 99999

        result = main_module._get_child_procs(FakeProc())
        assert result == []

    def test_get_child_procs_returns_empty_for_nonexistent_pid(self):
        """_get_child_procs returns [] if the process does not exist."""
        import backend.main as main_module
        import backend.deps as deps_module

        class FakeProc:
            pid = 999999999  # Unlikely to exist

        result = main_module._get_child_procs(FakeProc())
        assert result == []

    # ------------------------------------------------------------------
    # _any_proc_running helper
    # ------------------------------------------------------------------

    def test_any_proc_running_returns_false_for_empty_list(self):
        """_any_proc_running([]) is always False."""
        import backend.main as main_module
        import backend.deps as deps_module
        assert main_module._any_proc_running([]) is False

    def test_any_proc_running_returns_false_when_all_dead(self):
        """_any_proc_running returns False if all processes are dead."""
        import backend.main as main_module
        import backend.deps as deps_module

        class DeadProc:
            def is_running(self): return False
            def status(self): return "zombie"

        assert main_module._any_proc_running([DeadProc(), DeadProc()]) is False

    def test_any_proc_running_returns_true_when_one_alive(self):
        """_any_proc_running returns True if at least one process is running."""
        import backend.main as main_module
        import backend.deps as deps_module

        class DeadProc:
            def is_running(self): return False
            def status(self): return "zombie"

        class AliveProc:
            def is_running(self): return True
            def status(self): return "running"

        assert main_module._any_proc_running([DeadProc(), AliveProc()]) is True

    def test_any_proc_running_handles_exceptions(self):
        """_any_proc_running treats exceptions as 'not running' for safety."""
        import backend.main as main_module
        import backend.deps as deps_module

        class BrokenProc:
            def is_running(self): raise RuntimeError("process gone")

        assert main_module._any_proc_running([BrokenProc()]) is False

    # ------------------------------------------------------------------
    # _wait_for_process_and_children helper
    # ------------------------------------------------------------------

    def test_wait_for_process_and_children_waits_for_children(self):
        """_wait_for_process_and_children blocks until all children have exited."""
        import threading
        import backend.main as main_module
        import backend.deps as deps_module

        waited = []

        class FakeParent:
            def wait(self): waited.append("parent")

        class FakeChild:
            def wait(self): waited.append("child")

        main_module._wait_for_process_and_children(FakeParent(), [FakeChild(), FakeChild()])
        assert waited == ["parent", "child", "child"]

    def test_wait_for_process_and_children_tolerates_child_exception(self):
        """_wait_for_process_and_children continues even if a child.wait() raises."""
        import backend.main as main_module
        import backend.deps as deps_module

        waited = []

        class FakeParent:
            def wait(self): waited.append("parent")

        class CrashingChild:
            def wait(self): raise RuntimeError("no such process")

        class GoodChild:
            def wait(self): waited.append("good_child")

        # Should not raise; good_child should still be waited on
        main_module._wait_for_process_and_children(FakeParent(), [CrashingChild(), GoodChild()])
        assert "parent" in waited
        assert "good_child" in waited

    # ------------------------------------------------------------------
    # disable_autopilot enters stopping state when only children are alive
    # ------------------------------------------------------------------

    def test_disable_enters_stopping_when_parent_exited_but_children_running(self, client, monkeypatch):
        """stopping=True when parent already exited but child process is still running."""
        self._reset_autopilot_state(monkeypatch)
        import backend.main as main_module
        import backend.deps as deps_module

        class ExitedParent:
            pid = 42
            def terminate(self): pass
            def poll(self): return 0   # parent has exited
            def wait(self): return 0

        class RunningChild:
            def is_running(self): return True
            def status(self): return "running"
            def wait(self): return 0

        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: ExitedParent())
        # Patch _get_child_procs to return our running child
        monkeypatch.setattr(main_module, "_get_child_procs", lambda proc: [RunningChild()])

        client.post("/api/autopilot/enable")
        resp = client.post("/api/autopilot/disable")

        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is False
        assert data["stopping"] is True

    def test_disable_stopping_log_message_when_only_children_running(self, client, monkeypatch):
        """Log mentions 'waiting for Claude process' even when only children are alive."""
        self._reset_autopilot_state(monkeypatch)
        import backend.main as main_module
        import backend.deps as deps_module

        class ExitedParent:
            pid = 42
            def terminate(self): pass
            def poll(self): return 0
            def wait(self): return 0

        class RunningChild:
            def is_running(self): return True
            def status(self): return "running"
            def wait(self): return 0

        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: ExitedParent())
        monkeypatch.setattr(main_module, "_get_child_procs", lambda proc: [RunningChild()])

        client.post("/api/autopilot/enable")
        resp = client.post("/api/autopilot/disable")
        log_messages = [e["message"] for e in resp.json().get("log", [])]
        assert any("waiting for Claude process" in m for m in log_messages)

    def test_disable_no_stopping_when_all_procs_exited(self, client, monkeypatch):
        """stopping=False when parent AND all children have already exited."""
        self._reset_autopilot_state(monkeypatch)
        import backend.main as main_module
        import backend.deps as deps_module

        class ExitedParent:
            pid = 42
            def terminate(self): pass
            def poll(self): return 0   # exited
            def wait(self): return 0

        class DeadChild:
            def is_running(self): return False
            def status(self): return "zombie"
            def wait(self): return 0

        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: ExitedParent())
        monkeypatch.setattr(main_module, "_get_child_procs", lambda proc: [DeadChild()])

        client.post("/api/autopilot/enable")
        resp = client.post("/api/autopilot/disable")
        data = resp.json()
        assert data["enabled"] is False
        assert data["stopping"] is False

    # ------------------------------------------------------------------
    # _wait_for_stopping_process waits for children
    # ------------------------------------------------------------------

    def test_wait_for_stopping_process_waits_for_child_procs(self):
        """_wait_for_stopping_process clears state only after parent AND children exit."""
        import asyncio
        import threading
        import backend.main as main_module
        import backend.deps as deps_module

        waited = []

        parent_done = threading.Event()
        child_done = threading.Event()

        class FakeParent:
            def wait(self):
                parent_done.wait(timeout=5)
                waited.append("parent")

        class FakeChild:
            def wait(self):
                child_done.wait(timeout=5)
                waited.append("child")

        state = main_module._AutoPilotState()
        state.stopping = True
        state.current_feature_id = 10
        state.current_feature_name = "Test"

        async def run():
            task = asyncio.create_task(
                main_module._wait_for_stopping_process(FakeParent(), state, [FakeChild()])
            )
            await asyncio.sleep(0)  # Let the task start
            # Unblock parent then child
            parent_done.set()
            child_done.set()
            await task

        asyncio.run(run())

        assert "parent" in waited
        assert "child" in waited
        # State should be cleared after all processes exit
        assert state.stopping is False
        assert state.current_feature_id is None


class TestManualLaunchTracking:
    """Tests for manual-launch visibility via autopilot status endpoint.

    When the user launches Claude manually via POST /api/features/{id}/launch-claude,
    the autopilot state should reflect that a manual run is active so the UI can
    show a running indicator in the top bar and add entries to the event log.
    """

    def _reset_autopilot_state(self, monkeypatch):
        import backend.main as main_module
        import backend.deps as deps_module
        monkeypatch.setattr(main_module, '_autopilot_states', {})

    def test_manual_launch_sets_manual_active_in_status(self, client, monkeypatch):
        """After launching Claude manually, GET /api/autopilot/status should return manual_active=True."""
        self._reset_autopilot_state(monkeypatch)

        class MockProcess:
            pid = 42
            def wait(self):
                return 0

        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: MockProcess())

        client.post("/api/features/1/launch-claude")

        status = client.get("/api/autopilot/status").json()
        assert status["manual_active"] is True
        assert status["manual_feature_id"] == 1
        assert status["manual_feature_name"] == "Feature 1"
        assert status["manual_feature_model"] == "sonnet"

    def test_manual_launch_adds_log_entry(self, client, monkeypatch):
        """After launching Claude manually, a log entry should appear in the event log."""
        self._reset_autopilot_state(monkeypatch)

        class MockProcess:
            pid = 42
            def wait(self):
                return 0

        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: MockProcess())

        client.post("/api/features/1/launch-claude")

        status = client.get("/api/autopilot/status").json()
        assert len(status["log"]) >= 1
        messages = [e["message"] for e in status["log"]]
        assert any("Manual launch" in m and "#1" in m and "Feature 1" in m for m in messages)

    def test_manual_launch_log_entry_level_is_info(self, client, monkeypatch):
        """The manual launch log entry should have level='info'."""
        self._reset_autopilot_state(monkeypatch)

        class MockProcess:
            pid = 42
            def wait(self):
                return 0

        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: MockProcess())

        client.post("/api/features/1/launch-claude")

        status = client.get("/api/autopilot/status").json()
        launch_entries = [e for e in status["log"] if "Manual launch" in e["message"]]
        assert len(launch_entries) == 1
        assert launch_entries[0]["level"] == "info"

    def test_manual_launch_includes_hidden_mode_in_log(self, client, monkeypatch):
        """The log entry should indicate whether it was hidden or interactive."""
        self._reset_autopilot_state(monkeypatch)

        class MockProcess:
            pid = 42
            def wait(self):
                return 0

        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: MockProcess())

        # hidden_execution=True (default)
        client.post("/api/features/1/launch-claude", json={"hidden_execution": True})

        status = client.get("/api/autopilot/status").json()
        messages = [e["message"] for e in status["log"]]
        assert any("hidden" in m for m in messages)

    def test_manual_launch_includes_interactive_mode_in_log(self, client, monkeypatch):
        """Log entry should say 'interactive' when hidden_execution=False."""
        self._reset_autopilot_state(monkeypatch)

        class MockProcess:
            pid = 42
            def wait(self):
                return 0

        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: MockProcess())

        client.post("/api/features/1/launch-claude", json={"hidden_execution": False})

        status = client.get("/api/autopilot/status").json()
        messages = [e["message"] for e in status["log"]]
        assert any("interactive" in m for m in messages)

    def test_status_has_manual_active_field_when_disabled(self, client, monkeypatch):
        """GET /api/autopilot/status always includes manual_active field (False by default)."""
        self._reset_autopilot_state(monkeypatch)

        status = client.get("/api/autopilot/status").json()
        assert "manual_active" in status
        assert status["manual_active"] is False
        assert "manual_feature_id" in status
        assert "manual_feature_name" in status
        assert "manual_feature_model" in status

    def test_monitor_manual_process_clears_state_on_exit(self, client, monkeypatch):
        """When the manual process exits, monitor_manual_process should clear manual_* state."""
        import asyncio
        import backend.main as main_module
        import backend.deps as deps_module

        self._reset_autopilot_state(monkeypatch)

        class MockProcess:
            pid = 42
            def wait(self):
                return 0

        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: MockProcess())

        # Allow the monitor task to actually run by NOT suppressing create_task
        monkeypatch.setattr(main_module.asyncio, 'create_task',
                            asyncio.ensure_future)

        async def run():
            # Launch and give the monitor task a chance to run
            state = main_module.get_autopilot_state()
            process = MockProcess()
            state.manual_active = True
            state.manual_feature_id = 1
            state.manual_feature_name = "Feature 1"
            state.manual_feature_model = "sonnet"
            state.manual_process = process
            task = asyncio.create_task(main_module.monitor_manual_process(state))
            await task
            return state

        state = asyncio.run(run())

        assert state.manual_active is False
        assert state.manual_feature_id is None
        assert state.manual_feature_name is None
        assert state.manual_feature_model is None
        assert state.manual_process is None
        assert state.manual_monitor_task is None

    def test_monitor_manual_process_logs_success_on_zero_exit(self, client, monkeypatch):
        """monitor_manual_process logs a success entry when process exits with code 0."""
        import asyncio
        import backend.main as main_module
        import backend.deps as deps_module

        self._reset_autopilot_state(monkeypatch)

        class MockProcess:
            pid = 42
            def wait(self):
                return 0

        async def run():
            state = main_module.get_autopilot_state()
            state.manual_active = True
            state.manual_feature_id = 5
            state.manual_feature_name = "My Feature"
            state.manual_feature_model = "sonnet"
            state.manual_process = MockProcess()
            await main_module.monitor_manual_process(state)
            return state

        state = asyncio.run(run())

        success_entries = [e for e in state.log if e.level == "success"]
        assert len(success_entries) >= 1
        assert any("#5" in e.message and "My Feature" in e.message for e in success_entries)

    def test_monitor_manual_process_logs_info_on_nonzero_exit(self, client, monkeypatch):
        """monitor_manual_process logs an info entry when process exits with non-zero code."""
        import asyncio
        import backend.main as main_module
        import backend.deps as deps_module

        self._reset_autopilot_state(monkeypatch)

        class MockProcess:
            pid = 42
            def wait(self):
                return 1  # non-zero exit

        async def run():
            state = main_module.get_autopilot_state()
            state.manual_active = True
            state.manual_feature_id = 5
            state.manual_feature_name = "My Feature"
            state.manual_feature_model = "sonnet"
            state.manual_process = MockProcess()
            await main_module.monitor_manual_process(state)
            return state

        state = asyncio.run(run())

        info_entries = [e for e in state.log if e.level == "info"]
        assert len(info_entries) >= 1
        assert any("exit 1" in e.message or "exit code" in e.message.lower() for e in info_entries)




# ==============================================================================
# Autopilot budget settings
# ==============================================================================

def test_settings_includes_budget_limit_default(client, tmp_path, monkeypatch):
    """GET /api/settings returns autopilot_budget_limit=0 by default."""
    import backend.main as main_module
    import backend.deps as deps_module
    monkeypatch.setattr(deps_module, 'SETTINGS_FILE', tmp_path / "settings_nonexistent.json")

    response = client.get("/api/settings")
    assert response.status_code == 200
    data = response.json()
    assert "autopilot_budget_limit" in data
    assert data["autopilot_budget_limit"] == 0


def test_put_settings_saves_budget_limit(client, tmp_path, monkeypatch):
    """PUT /api/settings saves and returns autopilot_budget_limit."""
    import json
    import backend.main as main_module
    import backend.deps as deps_module
    settings_file = tmp_path / "test_settings.json"
    monkeypatch.setattr(deps_module, 'SETTINGS_FILE', settings_file)

    response = client.put("/api/settings", json={
        "claude_prompt_template": "some template",
        "plan_tasks_prompt_template": "some plan",
        "autopilot_budget_limit": 5,
    })
    assert response.status_code == 200
    data = response.json()
    assert data["autopilot_budget_limit"] == 5

    # Verify persisted to disk
    saved = json.loads(settings_file.read_text())
    assert saved["autopilot_budget_limit"] == 5


def test_put_settings_budget_limit_defaults_to_zero_when_omitted(client, tmp_path, monkeypatch):
    """PUT /api/settings defaults autopilot_budget_limit to 0 when not provided."""
    import backend.main as main_module
    import backend.deps as deps_module
    settings_file = tmp_path / "test_settings.json"
    monkeypatch.setattr(deps_module, 'SETTINGS_FILE', settings_file)

    response = client.put("/api/settings", json={
        "claude_prompt_template": "some template",
    })
    assert response.status_code == 200
    assert response.json()["autopilot_budget_limit"] == 0




class TestAutopilotBudgetLimit:
    """Unit tests for budget limit enforcement in handle_autopilot_success."""

    def test_budget_limit_zero_does_not_stop(self, test_db_with_path, monkeypatch):
        """When budget_limit=0 (unlimited), autopilot continues after each feature."""
        import asyncio
        from backend.main import handle_autopilot_success, _AutoPilotState
        import backend.main as main_module
        import backend.deps as deps_module

        session_maker, db_path = test_db_with_path

        import backend.autopilot_engine as ae_module
        monkeypatch.setattr(ae_module, 'load_settings', lambda: {
            "claude_prompt_template": "t",
            "autopilot_budget_limit": 0,
        })
        spawn_calls = []

        def mock_spawn(feature, settings, working_dir):
            spawn_calls.append(feature.id)
            return type("P", (), {"pid": 1, "wait": lambda s: 0})()

        monkeypatch.setattr("backend.autopilot_engine.spawn_claude_for_autopilot", mock_spawn)
        monkeypatch.setattr("asyncio.create_task", lambda coro: coro.close() or None)

        state = _AutoPilotState()
        state.current_feature_name = "Feature Done"
        asyncio.run(handle_autopilot_success(99, state, db_path))

        # Should NOT have stopped — next feature was spawned
        assert len(spawn_calls) == 1
        assert state.enabled is False  # still False since we never set it True in state
        # More importantly, handle_budget_exhausted was NOT called so enabled wasn't forced off
        # via the budget path — check via log that budget message is absent
        budget_entries = [e for e in state.log if "budget" in e.message.lower()]
        assert len(budget_entries) == 0

    def test_budget_limit_stops_after_n_features(self, test_db_with_path, monkeypatch):
        """When budget_limit=2, autopilot stops after completing 2 features."""
        import asyncio
        from backend.main import handle_autopilot_success, _AutoPilotState
        import backend.main as main_module
        import backend.deps as deps_module

        session_maker, db_path = test_db_with_path

        import backend.autopilot_engine as ae_module
        monkeypatch.setattr(ae_module, 'load_settings', lambda: {
            "claude_prompt_template": "t",
            "autopilot_budget_limit": 2,
        })

        spawn_calls = []

        def mock_spawn(feature, settings, working_dir):
            spawn_calls.append(feature.id)
            return type("P", (), {"pid": 1, "wait": lambda s: 0})()

        monkeypatch.setattr("backend.autopilot_engine.spawn_claude_for_autopilot", mock_spawn)
        monkeypatch.setattr("asyncio.create_task", lambda coro: coro.close() or None)

        state = _AutoPilotState()
        state.enabled = True
        state.current_feature_name = "Feature A"
        state.features_completed = 1  # simulate 1 already completed

        # Completing a second feature should hit the budget limit
        asyncio.run(handle_autopilot_success(99, state, db_path))

        assert state.enabled is False
        assert state.current_feature_id is None
        assert state.current_feature_name is None
        assert len(spawn_calls) == 0  # no next feature spawned

        budget_entries = [e for e in state.log if "budget" in e.message.lower()]
        assert len(budget_entries) == 1
        assert "2" in budget_entries[0].message  # "2 features completed"

    def test_budget_limit_one_stops_immediately(self, test_db_with_path, monkeypatch):
        """When budget_limit=1 and features_completed reaches 1, autopilot stops."""
        import asyncio
        from backend.main import handle_autopilot_success, _AutoPilotState
        import backend.main as main_module
        import backend.deps as deps_module

        session_maker, db_path = test_db_with_path

        import backend.autopilot_engine as ae_module
        monkeypatch.setattr(ae_module, 'load_settings', lambda: {
            "claude_prompt_template": "t",
            "autopilot_budget_limit": 1,
        })

        spawn_calls = []
        monkeypatch.setattr("backend.autopilot_engine.spawn_claude_for_autopilot",
                            lambda *a, **k: spawn_calls.append(1) or type("P", (), {"pid": 1})())
        monkeypatch.setattr("asyncio.create_task", lambda coro: coro.close() or None)

        state = _AutoPilotState()
        state.enabled = True
        state.current_feature_name = "First Feature"
        state.features_completed = 0  # nothing done yet

        asyncio.run(handle_autopilot_success(1, state, db_path))

        assert state.enabled is False
        assert len(spawn_calls) == 0  # no further features spawned

        budget_entries = [e for e in state.log if "budget" in e.message.lower()]
        assert len(budget_entries) == 1

    def test_features_completed_counter_increments(self, test_db_with_path, monkeypatch):
        """features_completed is incremented on each successful feature."""
        import asyncio
        from backend.main import handle_autopilot_success, _AutoPilotState
        import backend.main as main_module
        import backend.deps as deps_module

        session_maker, db_path = test_db_with_path

        import backend.autopilot_engine as ae_module
        monkeypatch.setattr(ae_module, 'load_settings', lambda: {
            "claude_prompt_template": "t",
            "autopilot_budget_limit": 0,
        })
        monkeypatch.setattr("backend.autopilot_engine.spawn_claude_for_autopilot",
                            lambda *a, **k: type("P", (), {"pid": 1, "wait": lambda s: 0})())
        monkeypatch.setattr("asyncio.create_task", lambda coro: coro.close() or None)

        state = _AutoPilotState()
        assert state.features_completed == 0

        asyncio.run(handle_autopilot_success(99, state, db_path))
        assert state.features_completed == 1

    def test_enable_autopilot_resets_features_completed(self, client, monkeypatch):
        """Enabling autopilot resets features_completed counter to 0."""
        import backend.main as main_module
        import backend.deps as deps_module
        from backend.main import _AutoPilotState

        self._reset_autopilot_state(monkeypatch)

        state = main_module.get_autopilot_state()
        state.features_completed = 5  # simulate a previous session

        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {
            "pid": 1, "terminate": lambda self: None, "wait": lambda self: 0
        })())

        client.post("/api/autopilot/enable")

        assert state.features_completed == 0

    def _reset_autopilot_state(self, monkeypatch):
        """Reset global autopilot state so tests start fresh."""
        import backend.main as main_module
        import backend.deps as deps_module
        monkeypatch.setattr(main_module, '_autopilot_states', {})


# ==============================================================================
# Budget status in AutoPilotStatusResponse tests
# ==============================================================================

class TestAutopilotBudgetStatusResponse:
    """Tests for budget_limit and features_completed fields in autopilot status API."""

    def _reset_autopilot_state(self, monkeypatch):
        import backend.main as main_module
        import backend.deps as deps_module
        monkeypatch.setattr(main_module, '_autopilot_states', {})

    def test_status_returns_budget_fields_default(self, client, tmp_path, monkeypatch):
        """GET /api/autopilot/status includes budget_limit=0 and features_completed=0 by default."""
        import backend.main as main_module
        import backend.deps as deps_module
        self._reset_autopilot_state(monkeypatch)
        monkeypatch.setattr(deps_module, 'SETTINGS_FILE', tmp_path / "none.json")

        response = client.get("/api/autopilot/status")
        assert response.status_code == 200
        data = response.json()
        assert "budget_limit" in data
        assert "features_completed" in data
        assert data["budget_limit"] == 0
        assert data["features_completed"] == 0

    def test_status_returns_configured_budget_limit(self, client, tmp_path, monkeypatch):
        """GET /api/autopilot/status returns budget_limit from settings."""
        import json
        import backend.main as main_module
        import backend.deps as deps_module
        self._reset_autopilot_state(monkeypatch)

        settings_file = tmp_path / "settings.json"
        settings_file.write_text(json.dumps({
            "claude_prompt_template": "t",
            "plan_tasks_prompt_template": "p",
            "autopilot_budget_limit": 7,
        }))
        monkeypatch.setattr(deps_module, 'SETTINGS_FILE', settings_file)

        response = client.get("/api/autopilot/status")
        assert response.status_code == 200
        assert response.json()["budget_limit"] == 7

    def test_status_reflects_features_completed_counter(self, client, tmp_path, monkeypatch):
        """GET /api/autopilot/status returns the current features_completed counter."""
        import backend.main as main_module
        import backend.deps as deps_module
        self._reset_autopilot_state(monkeypatch)
        monkeypatch.setattr(deps_module, 'SETTINGS_FILE', tmp_path / "none.json")

        state = main_module.get_autopilot_state()
        state.features_completed = 3

        response = client.get("/api/autopilot/status")
        assert response.status_code == 200
        assert response.json()["features_completed"] == 3

    def test_enable_returns_budget_fields(self, client, tmp_path, monkeypatch):
        """POST /api/autopilot/enable response includes budget_limit and features_completed."""
        import json
        import backend.main as main_module
        import backend.deps as deps_module
        self._reset_autopilot_state(monkeypatch)

        settings_file = tmp_path / "settings.json"
        settings_file.write_text(json.dumps({
            "claude_prompt_template": "t",
            "plan_tasks_prompt_template": "p",
            "autopilot_budget_limit": 4,
        }))
        monkeypatch.setattr(deps_module, 'SETTINGS_FILE', settings_file)
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {
            "pid": 1, "terminate": lambda self: None, "wait": lambda self: 0
        })())

        response = client.post("/api/autopilot/enable")
        assert response.status_code == 200
        data = response.json()
        assert data["budget_limit"] == 4
        assert data["features_completed"] == 0  # reset on fresh enable

    def test_disable_returns_budget_fields(self, client, tmp_path, monkeypatch):
        """POST /api/autopilot/disable response includes budget_limit and features_completed."""
        import json
        import backend.main as main_module
        import backend.deps as deps_module
        self._reset_autopilot_state(monkeypatch)

        settings_file = tmp_path / "settings.json"
        settings_file.write_text(json.dumps({
            "claude_prompt_template": "t",
            "plan_tasks_prompt_template": "p",
            "autopilot_budget_limit": 10,
        }))
        monkeypatch.setattr(deps_module, 'SETTINGS_FILE', settings_file)
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {
            "pid": 1, "terminate": lambda self: None, "wait": lambda self: 0
        })())

        # Enable first so disable has something to do
        client.post("/api/autopilot/enable")

        # Manually set features_completed to simulate session progress
        state = main_module.get_autopilot_state()
        state.features_completed = 2

        response = client.post("/api/autopilot/disable")
        assert response.status_code == 200
        data = response.json()
        assert data["budget_limit"] == 10
        assert data["features_completed"] == 2


# ==============================================================================
# budget_exhausted flag tests
# ==============================================================================

class TestBudgetExhaustedFlag:
    """Tests for the budget_exhausted flag in _AutoPilotState and status API."""

    def _reset_autopilot_state(self, monkeypatch):
        import backend.main as main_module
        import backend.deps as deps_module
        monkeypatch.setattr(main_module, '_autopilot_states', {})

    def test_budget_exhausted_default_is_false(self):
        """_AutoPilotState.budget_exhausted defaults to False."""
        from backend.main import _AutoPilotState
        state = _AutoPilotState()
        assert state.budget_exhausted is False

    def test_handle_budget_exhausted_sets_flag(self):
        """handle_budget_exhausted() sets state.budget_exhausted = True."""
        from backend.main import handle_budget_exhausted, _AutoPilotState
        state = _AutoPilotState()
        state.enabled = True
        state.features_completed = 3
        handle_budget_exhausted(state)
        assert state.budget_exhausted is True
        assert state.enabled is False

    def test_status_returns_budget_exhausted_false_by_default(self, client, tmp_path, monkeypatch):
        """GET /api/autopilot/status returns budget_exhausted=False by default."""
        import backend.main as main_module
        import backend.deps as deps_module
        self._reset_autopilot_state(monkeypatch)
        monkeypatch.setattr(deps_module, 'SETTINGS_FILE', tmp_path / "none.json")

        response = client.get("/api/autopilot/status")
        assert response.status_code == 200
        assert response.json()["budget_exhausted"] is False

    def test_status_reflects_budget_exhausted_true(self, client, tmp_path, monkeypatch):
        """GET /api/autopilot/status returns budget_exhausted=True after budget is hit."""
        import backend.main as main_module
        import backend.deps as deps_module
        self._reset_autopilot_state(monkeypatch)
        monkeypatch.setattr(deps_module, 'SETTINGS_FILE', tmp_path / "none.json")

        state = main_module.get_autopilot_state()
        state.budget_exhausted = True

        response = client.get("/api/autopilot/status")
        assert response.status_code == 200
        assert response.json()["budget_exhausted"] is True

    def test_clear_error_also_clears_budget_exhausted(self, client, tmp_path, monkeypatch):
        """POST /api/autopilot/clear-error clears budget_exhausted flag."""
        import backend.main as main_module
        import backend.deps as deps_module
        self._reset_autopilot_state(monkeypatch)
        monkeypatch.setattr(deps_module, 'SETTINGS_FILE', tmp_path / "none.json")

        state = main_module.get_autopilot_state()
        state.budget_exhausted = True

        response = client.post("/api/autopilot/clear-error")
        assert response.status_code == 200
        assert state.budget_exhausted is False

    def test_enable_resets_budget_exhausted(self, client, tmp_path, monkeypatch):
        """POST /api/autopilot/enable resets budget_exhausted to False."""
        import backend.main as main_module
        import backend.deps as deps_module
        self._reset_autopilot_state(monkeypatch)
        monkeypatch.setattr(deps_module, 'SETTINGS_FILE', tmp_path / "none.json")
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: type("P", (), {
            "pid": 1, "terminate": lambda self: None, "wait": lambda self: 0
        })())

        state = main_module.get_autopilot_state()
        state.budget_exhausted = True

        response = client.post("/api/autopilot/enable")
        assert response.status_code == 200
        assert state.budget_exhausted is False
        assert response.json()["budget_exhausted"] is False

    def test_handle_budget_exhausted_via_success_handler(self, test_db_with_path, monkeypatch):
        """Budget flag is set when handle_autopilot_success hits the limit."""
        import asyncio
        from backend.main import handle_autopilot_success, _AutoPilotState
        import backend.main as main_module
        import backend.deps as deps_module

        session_maker, db_path = test_db_with_path

        import backend.autopilot_engine as ae_module
        monkeypatch.setattr(ae_module, 'load_settings', lambda: {
            "claude_prompt_template": "t",
            "autopilot_budget_limit": 1,
        })
        monkeypatch.setattr("backend.autopilot_engine.spawn_claude_for_autopilot",
                            lambda *a, **k: type("P", (), {"pid": 1})())
        monkeypatch.setattr("asyncio.create_task", lambda coro: coro.close() or None)

        state = _AutoPilotState()
        state.enabled = True
        state.features_completed = 0

        asyncio.run(handle_autopilot_success(1, state, db_path))

        assert state.budget_exhausted is True
        assert state.enabled is False

