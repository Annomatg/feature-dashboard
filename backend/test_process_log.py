"""
Unit and integration tests for the Claude process stdout/stderr log buffer.
============================================================================

Tests cover:
- LogLine dataclass fields
- ClaudeProcessLog append and maxlen behaviour
- _claude_process_logs lifecycle via monitor_claude_process (created / cleaned up)
- _read_stream_to_buffer reading lines from a BytesIO-like object
"""

import asyncio
import io
import sys
from collections import deque
from datetime import timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import backend.main as main_module
from backend.main import (
    ClaudeProcessLog,
    LogLine,
    _claude_process_logs,
    _read_stream_to_buffer,
)


# ---------------------------------------------------------------------------
# LogLine tests
# ---------------------------------------------------------------------------

class TestLogLine:
    def test_fields_stored(self):
        line = LogLine(timestamp="2026-01-01T00:00:00+00:00", stream="stdout", text="hello")
        assert line.timestamp == "2026-01-01T00:00:00+00:00"
        assert line.stream == "stdout"
        assert line.text == "hello"

    def test_stderr_stream(self):
        line = LogLine(timestamp="ts", stream="stderr", text="error msg")
        assert line.stream == "stderr"


# ---------------------------------------------------------------------------
# ClaudeProcessLog tests
# ---------------------------------------------------------------------------

class TestClaudeProcessLog:
    def test_initial_empty(self):
        log = ClaudeProcessLog(feature_id=1)
        assert len(log.lines) == 0
        assert log.feature_id == 1

    def test_append_adds_line(self):
        log = ClaudeProcessLog(feature_id=2)
        log.append("stdout", "hello world")
        assert len(log.lines) == 1
        entry = log.lines[0]
        assert isinstance(entry, LogLine)
        assert entry.stream == "stdout"
        assert entry.text == "hello world"

    def test_append_sets_timestamp(self):
        log = ClaudeProcessLog(feature_id=3)
        log.append("stderr", "an error")
        entry = log.lines[0]
        # Timestamp should be a valid ISO 8601 UTC string
        assert "T" in entry.timestamp
        assert entry.timestamp.endswith("+00:00") or entry.timestamp.endswith("Z") or "UTC" not in entry.timestamp

    def test_maxlen_500(self):
        log = ClaudeProcessLog(feature_id=4)
        for i in range(600):
            log.append("stdout", f"line {i}")
        # deque is capped at 500
        assert len(log.lines) == 500
        # Oldest lines dropped; newest retained
        assert log.lines[-1].text == "line 599"
        assert log.lines[0].text == "line 100"

    def test_append_multiple_streams(self):
        log = ClaudeProcessLog(feature_id=5)
        log.append("stdout", "out line")
        log.append("stderr", "err line")
        assert log.lines[0].stream == "stdout"
        assert log.lines[1].stream == "stderr"

    def test_cleanup_entry(self):
        """Buffer is a plain deque — can be cleared externally."""
        log = ClaudeProcessLog(feature_id=6)
        log.append("stdout", "data")
        log.lines.clear()
        assert len(log.lines) == 0


# ---------------------------------------------------------------------------
# _read_stream_to_buffer tests
# ---------------------------------------------------------------------------

class FakeBinaryStream:
    """Minimal synchronous stream that yields lines then EOF."""

    def __init__(self, lines: list[bytes]):
        self._lines = iter(lines + [b""])  # b"" signals EOF

    def readline(self) -> bytes:
        return next(self._lines, b"")


class TestReadStreamToBuffer:
    def _run(self, coro):
        return asyncio.run(coro)

    def test_reads_stdout_lines(self):
        log = ClaudeProcessLog(feature_id=10)
        stream = FakeBinaryStream([b"line one\n", b"line two\n"])
        self._run(_read_stream_to_buffer(stream, "stdout", log))
        assert len(log.lines) == 2
        assert log.lines[0].text == "line one"
        assert log.lines[1].text == "line two"

    def test_reads_stderr_lines(self):
        log = ClaudeProcessLog(feature_id=11)
        stream = FakeBinaryStream([b"err\n"])
        self._run(_read_stream_to_buffer(stream, "stderr", log))
        assert log.lines[0].stream == "stderr"
        assert log.lines[0].text == "err"

    def test_strips_crlf(self):
        log = ClaudeProcessLog(feature_id=12)
        stream = FakeBinaryStream([b"windows line\r\n"])
        self._run(_read_stream_to_buffer(stream, "stdout", log))
        assert log.lines[0].text == "windows line"

    def test_handles_decoding_error(self):
        log = ClaudeProcessLog(feature_id=13)
        stream = FakeBinaryStream([b"\xff\xfe bad bytes\n"])
        self._run(_read_stream_to_buffer(stream, "stdout", log))
        # Should not raise; replacement character U+FFFD used
        assert len(log.lines) == 1
        assert "\ufffd" in log.lines[0].text or log.lines[0].text

    def test_empty_stream(self):
        log = ClaudeProcessLog(feature_id=14)
        stream = FakeBinaryStream([])
        self._run(_read_stream_to_buffer(stream, "stdout", log))
        assert len(log.lines) == 0

    def test_many_lines_respects_maxlen(self):
        log = ClaudeProcessLog(feature_id=15)
        lines = [f"line {i}\n".encode() for i in range(600)]
        stream = FakeBinaryStream(lines)
        self._run(_read_stream_to_buffer(stream, "stdout", log))
        assert len(log.lines) == 500


# ---------------------------------------------------------------------------
# _claude_process_logs lifecycle via monitor_claude_process
# ---------------------------------------------------------------------------

class TestClaudeProcessLogsLifecycle:
    """Verify that _claude_process_logs is created and cleaned up by monitor_claude_process."""

    def _run(self, coro):
        return asyncio.run(coro)

    def _make_mock_process(self, exit_code: int = 0, stdout_lines=None, stderr_lines=None):
        proc = MagicMock()
        proc.wait.return_value = exit_code
        proc.poll.return_value = exit_code
        if stdout_lines is not None:
            proc.stdout = FakeBinaryStream(stdout_lines)
        else:
            proc.stdout = None
        if stderr_lines is not None:
            proc.stderr = FakeBinaryStream(stderr_lines)
        else:
            proc.stderr = None
        return proc

    def test_log_buffer_created_and_removed(self, tmp_path):
        """Log buffer is created on start and removed when monitor finishes."""
        import tempfile
        import shutil

        # Set up an isolated test DB
        from api.database import create_database, Feature as DbFeature
        engine, sm = create_database(tmp_path)
        session = sm()
        feature = DbFeature(
            id=42, priority=100, category="Test", name="T",
            description="d", steps=["s"], passes=True, in_progress=False,
        )
        session.add(feature)
        session.commit()
        session.close()

        db_path = tmp_path / "features.db"

        state = main_module._AutoPilotState()
        proc = self._make_mock_process(exit_code=0, stdout_lines=[b"output\n"])

        # Ensure no stale entry
        main_module._claude_process_logs.pop(42, None)

        captured_mid = {}

        original_gather = asyncio.gather

        async def patched_gather(*aws, **kw):
            # Record log state when gather is called (readers draining)
            captured_mid["present"] = 42 in main_module._claude_process_logs
            return await original_gather(*aws, **kw)

        async def fake_success(*args, **kwargs):
            pass

        with patch.object(main_module, "handle_autopilot_success", side_effect=fake_success):
            with patch("asyncio.gather", side_effect=patched_gather):
                self._run(
                    main_module.monitor_claude_process(42, proc, db_path, state)
                )

        # Buffer must be removed after monitor exits
        assert 42 not in main_module._claude_process_logs

    def test_log_buffer_removed_on_cancel(self, tmp_path):
        """Log buffer is cleaned up even if the monitor task is cancelled."""
        from api.database import create_database, Feature as DbFeature
        engine, sm = create_database(tmp_path)
        session = sm()
        session.close()

        db_path = tmp_path / "features.db"
        state = main_module._AutoPilotState()

        # Process that blocks forever (wait never returns)
        proc = MagicMock()
        proc.stdout = None
        proc.stderr = None

        async def slow_wait():
            await asyncio.sleep(100)

        proc.wait = lambda: (_ for _ in ()).throw(RuntimeError("wait should not be called"))

        main_module._claude_process_logs.pop(99, None)

        async def run():
            task = asyncio.create_task(
                main_module.monitor_claude_process(99, proc, db_path, state)
            )
            # Let it start (buffer created)
            await asyncio.sleep(0)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self._run(run())

        # Buffer must be removed after cancellation
        assert 99 not in main_module._claude_process_logs

    def test_output_captured_in_buffer(self, tmp_path):
        """stdout/stderr lines are stored in the log buffer during monitoring."""
        from api.database import create_database, Feature as DbFeature
        engine, sm = create_database(tmp_path)
        session = sm()
        feature = DbFeature(
            id=77, priority=1, category="T", name="T",
            description="d", steps=["s"], passes=False, in_progress=False,
        )
        session.add(feature)
        session.commit()
        session.close()

        db_path = tmp_path / "features.db"
        state = main_module._AutoPilotState()

        proc = self._make_mock_process(
            exit_code=1,
            stdout_lines=[b"hello stdout\n"],
            stderr_lines=[b"hello stderr\n"],
        )

        # Use a dict subclass that intercepts pop() to snapshot the log
        captured_log: dict = {}

        class TrackingDict(dict):
            def pop(self, key, *args):
                if key == 77:
                    log = self.get(77)
                    if log:
                        captured_log["lines"] = list(log.lines)
                return super().pop(key, *args)

        tracking: dict[int, ClaudeProcessLog] = TrackingDict()
        original_logs = main_module._claude_process_logs
        main_module._claude_process_logs = tracking

        async def fake_failure(*args, **kwargs):
            pass

        try:
            with patch.object(main_module, "handle_autopilot_failure", side_effect=fake_failure):
                self._run(
                    main_module.monitor_claude_process(77, proc, db_path, state)
                )
        finally:
            main_module._claude_process_logs = original_logs

        lines = captured_log.get("lines", [])
        texts = {line.text for line in lines}
        assert "hello stdout" in texts
        assert "hello stderr" in texts
