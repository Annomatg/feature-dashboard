"""
Unit tests for backend/claude_process.py
==========================================

Covers the utility functions and classes extracted from main.py:
- _get_claude_projects_slug
- _get_claude_projects_dir (path existence logic)
- _jsonl_contains_prompt
- _format_tool_call
- _parse_jsonl_log
- ClaudeProcessLog / LogLine (re-verified from new import path)
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.claude_process import (
    ClaudeProcessLog,
    LogLine,
    _format_tool_call,
    _get_claude_projects_dir,
    _get_claude_projects_slug,
    _jsonl_contains_prompt,
    _parse_jsonl_log,
)


# ---------------------------------------------------------------------------
# _get_claude_projects_slug
# ---------------------------------------------------------------------------

class TestGetClaudeProjectsSlug:
    def test_windows_path(self):
        slug = _get_claude_projects_slug(r"F:\Work\Godot\feature-dashboard")
        assert slug == "F--Work-Godot-feature-dashboard"

    def test_unix_path(self):
        slug = _get_claude_projects_slug("/home/user/project")
        assert slug == "-home-user-project"

    def test_mixed_separators(self):
        slug = _get_claude_projects_slug("C:/Users/foo/bar")
        assert slug == "C--Users-foo-bar"

    def test_plain_name(self):
        slug = _get_claude_projects_slug("myproject")
        assert slug == "myproject"


# ---------------------------------------------------------------------------
# _get_claude_projects_dir
# ---------------------------------------------------------------------------

class TestGetClaudeProjectsDir:
    def test_returns_none_when_not_exists(self, tmp_path):
        # A directory that definitely does not exist as a claude project
        result = _get_claude_projects_dir(str(tmp_path / "nonexistent"))
        assert result is None

    def test_returns_path_when_exists(self, tmp_path, monkeypatch):
        # Monkey-patch Path.home() to point to tmp_path
        fake_slug = "test-project"
        fake_projects_dir = tmp_path / ".claude" / "projects" / fake_slug
        fake_projects_dir.mkdir(parents=True)

        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))

        result = _get_claude_projects_dir("test:project")
        assert result == fake_projects_dir


# ---------------------------------------------------------------------------
# _jsonl_contains_prompt
# ---------------------------------------------------------------------------

class TestJsonlContainsPrompt:
    def _write_jsonl(self, tmp_path, lines: list[dict]) -> Path:
        p = tmp_path / "session.jsonl"
        with open(p, "w", encoding="utf-8") as f:
            for obj in lines:
                f.write(json.dumps(obj) + "\n")
        return p

    def test_finds_snippet_in_string_content(self, tmp_path):
        p = self._write_jsonl(tmp_path, [
            {"type": "user", "message": {"content": "Please work on Feature #42 [Backend]: Add logging"}},
        ])
        assert _jsonl_contains_prompt(p, "Feature #42") is True

    def test_finds_snippet_in_list_content_text(self, tmp_path):
        p = self._write_jsonl(tmp_path, [
            {"type": "user", "message": {"content": [{"type": "text", "text": "Feature #99 task"}]}},
        ])
        assert _jsonl_contains_prompt(p, "Feature #99") is True

    def test_returns_false_when_snippet_absent(self, tmp_path):
        p = self._write_jsonl(tmp_path, [
            {"type": "user", "message": {"content": "unrelated message"}},
        ])
        assert _jsonl_contains_prompt(p, "Feature #999") is False

    def test_only_checks_user_messages(self, tmp_path):
        p = self._write_jsonl(tmp_path, [
            {"type": "assistant", "message": {"content": "Feature #1 is done"}},
        ])
        assert _jsonl_contains_prompt(p, "Feature #1") is False

    def test_returns_false_on_missing_file(self, tmp_path):
        assert _jsonl_contains_prompt(tmp_path / "ghost.jsonl", "anything") is False

    def test_handles_malformed_json_lines(self, tmp_path):
        p = tmp_path / "session.jsonl"
        p.write_text('not json\n{"type": "user", "message": {"content": "Feature #5"}}\n')
        assert _jsonl_contains_prompt(p, "Feature #5") is True


# ---------------------------------------------------------------------------
# _format_tool_call
# ---------------------------------------------------------------------------

class TestFormatToolCall:
    def test_bash_with_description(self):
        result = _format_tool_call("Bash", {"description": "run tests", "command": "pytest"})
        assert result == "$ run tests"

    def test_bash_without_description_uses_command(self):
        result = _format_tool_call("Bash", {"command": "echo hello"})
        assert result == "$ echo hello"

    def test_read_uses_filename(self):
        result = _format_tool_call("Read", {"file_path": "/some/path/main.py"})
        assert result == "Read: main.py"

    def test_edit_uses_filename(self):
        result = _format_tool_call("Edit", {"file_path": "/project/foo.txt"})
        assert result == "Edit: foo.txt"

    def test_write_uses_filename(self):
        result = _format_tool_call("Write", {"file_path": "C:/some/file.py"})
        assert result == "Write: file.py"

    def test_glob_uses_pattern(self):
        result = _format_tool_call("Glob", {"pattern": "**/*.py"})
        assert result == "Glob: **/*.py"

    def test_grep_uses_pattern(self):
        result = _format_tool_call("Grep", {"pattern": "def test_"})
        assert result == "Grep: def test_"

    def test_task_create(self):
        result = _format_tool_call("TaskCreate", {"subject": "my task"})
        assert result == "Task Create: my task"

    def test_task_update(self):
        result = _format_tool_call("TaskUpdate", {"taskId": "abc", "status": "completed"})
        assert result == "Task Update #abc: completed"

    def test_mcp_features_with_id(self):
        result = _format_tool_call("mcp__features__feature_mark_passing", {"feature_id": 42})
        assert result == "Feature #42: feature_mark_passing"

    def test_mcp_features_without_id(self):
        result = _format_tool_call("mcp__features__feature_get_stats", {})
        assert result == "Feature: feature_get_stats"

    def test_unknown_tool_returns_name(self):
        result = _format_tool_call("SomeFutureTool", {"x": 1})
        assert result == "SomeFutureTool"


# ---------------------------------------------------------------------------
# _parse_jsonl_log
# ---------------------------------------------------------------------------

class TestParseJsonlLog:
    def _write_jsonl(self, tmp_path, lines: list[dict]) -> Path:
        p = tmp_path / "session.jsonl"
        with open(p, "w", encoding="utf-8") as f:
            for obj in lines:
                f.write(json.dumps(obj) + "\n")
        return p

    def _assistant_msg(self, content_items: list, timestamp: str = "2026-01-01T00:00:00Z") -> dict:
        return {
            "type": "assistant",
            "timestamp": timestamp,
            "message": {"content": content_items},
        }

    def test_parses_tool_use(self, tmp_path):
        p = self._write_jsonl(tmp_path, [
            self._assistant_msg([{"type": "tool_use", "name": "Bash", "input": {"command": "pytest"}}]),
        ])
        entries = _parse_jsonl_log(p, limit=10)
        assert len(entries) == 1
        assert entries[0]["entry_type"] == "tool_use"
        assert entries[0]["tool_name"] == "Bash"
        assert "pytest" in entries[0]["text"]

    def test_parses_text_content(self, tmp_path):
        p = self._write_jsonl(tmp_path, [
            self._assistant_msg([{"type": "text", "text": "Hello world"}]),
        ])
        entries = _parse_jsonl_log(p, limit=10)
        assert len(entries) == 1
        assert entries[0]["entry_type"] == "text"
        assert entries[0]["text"] == "Hello world"

    def test_parses_thinking_content(self, tmp_path):
        p = self._write_jsonl(tmp_path, [
            self._assistant_msg([{"type": "thinking", "thinking": "I think..."}]),
        ])
        entries = _parse_jsonl_log(p, limit=10)
        assert len(entries) == 1
        assert entries[0]["entry_type"] == "thinking"

    def test_skips_non_assistant_messages(self, tmp_path):
        p = self._write_jsonl(tmp_path, [
            {"type": "user", "message": {"content": [{"type": "text", "text": "hello"}]}},
        ])
        entries = _parse_jsonl_log(p, limit=10)
        assert entries == []

    def test_respects_limit(self, tmp_path):
        items = [
            self._assistant_msg([{"type": "text", "text": f"msg {i}"}], f"2026-01-01T00:{i:02d}:00Z")
            for i in range(20)
        ]
        p = self._write_jsonl(tmp_path, items)
        entries = _parse_jsonl_log(p, limit=5)
        assert len(entries) == 5
        # Should return the last 5
        assert entries[-1]["text"] == "msg 19"

    def test_returns_empty_for_missing_file(self, tmp_path):
        result = _parse_jsonl_log(tmp_path / "ghost.jsonl", limit=10)
        assert result == []

    def test_truncates_long_text(self, tmp_path):
        long_text = "x" * 500
        p = self._write_jsonl(tmp_path, [
            self._assistant_msg([{"type": "text", "text": long_text}]),
        ])
        entries = _parse_jsonl_log(p, limit=10)
        assert len(entries[0]["text"]) <= 200
