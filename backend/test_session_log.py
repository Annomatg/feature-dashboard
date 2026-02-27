"""
Unit tests for the Claude JSONL session log reader.
====================================================

Tests cover:
- _get_claude_projects_slug(): path encoding
- _format_tool_call(): tool call formatting
- _parse_jsonl_log(): JSONL file parsing
- _find_session_jsonl(): finding session files by timestamp
- GET /api/autopilot/session-log endpoint
"""

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import backend.main as main_module
from backend.main import (
    _format_tool_call,
    _get_claude_projects_slug,
    _jsonl_contains_prompt,
    _parse_jsonl_log,
    _find_session_jsonl,
    _get_claude_projects_dir,
)


# ---------------------------------------------------------------------------
# _get_claude_projects_slug tests
# ---------------------------------------------------------------------------

class TestGetClaudeProjectsSlug:
    def test_windows_path(self):
        slug = _get_claude_projects_slug(r'F:\Work\Godot\feature-dashboard')
        assert slug == 'F--Work-Godot-feature-dashboard'

    def test_unix_path(self):
        slug = _get_claude_projects_slug('/home/user/project')
        assert slug == '-home-user-project'

    def test_path_with_hyphens(self):
        slug = _get_claude_projects_slug(r'C:\my-project\sub-dir')
        assert slug == 'C--my-project-sub-dir'

    def test_no_colon_no_separator(self):
        slug = _get_claude_projects_slug('simple')
        assert slug == 'simple'


# ---------------------------------------------------------------------------
# _format_tool_call tests
# ---------------------------------------------------------------------------

class TestFormatToolCall:
    def test_bash_with_description(self):
        result = _format_tool_call('Bash', {'command': 'ls -la', 'description': 'List files'})
        assert result == '$ List files'

    def test_bash_without_description(self):
        result = _format_tool_call('Bash', {'command': 'ls -la'})
        assert result == '$ ls -la'

    def test_read_tool(self):
        result = _format_tool_call('Read', {'file_path': '/path/to/main.py'})
        assert result == 'Read: main.py'

    def test_edit_tool(self):
        result = _format_tool_call('Edit', {'file_path': '/path/to/utils.py'})
        assert result == 'Edit: utils.py'

    def test_write_tool(self):
        result = _format_tool_call('Write', {'file_path': '/path/to/new_file.js'})
        assert result == 'Write: new_file.js'

    def test_glob_tool(self):
        result = _format_tool_call('Glob', {'pattern': '**/*.py'})
        assert result == 'Glob: **/*.py'

    def test_grep_tool(self):
        result = _format_tool_call('Grep', {'pattern': 'def main'})
        assert result == 'Grep: def main'

    def test_mcp_feature_tool_with_id(self):
        result = _format_tool_call('mcp__features__feature_mark_passing', {'feature_id': 42})
        assert result == 'Feature #42: feature_mark_passing'

    def test_mcp_feature_tool_without_id(self):
        result = _format_tool_call('mcp__features__feature_get_next', {})
        assert result == 'Feature: feature_get_next'

    def test_task_create(self):
        result = _format_tool_call('TaskCreate', {'subject': 'Fix bug'})
        assert result == 'Task Create: Fix bug'

    def test_task_update(self):
        result = _format_tool_call('TaskUpdate', {'taskId': '5', 'status': 'completed'})
        assert result == 'Task Update #5: completed'

    def test_unknown_tool(self):
        result = _format_tool_call('UnknownTool', {})
        assert result == 'UnknownTool'

    def test_read_empty_path(self):
        result = _format_tool_call('Read', {'file_path': ''})
        assert result == 'Read: ?'


# ---------------------------------------------------------------------------
# _parse_jsonl_log tests
# ---------------------------------------------------------------------------

def make_jsonl_line(obj: dict) -> str:
    return json.dumps(obj) + '\n'


def make_assistant_tool_use(tool_name: str, tool_input: dict, timestamp: str = '2026-01-01T00:00:00Z') -> str:
    return make_jsonl_line({
        'type': 'assistant',
        'timestamp': timestamp,
        'message': {
            'role': 'assistant',
            'content': [
                {'type': 'tool_use', 'name': tool_name, 'input': tool_input}
            ]
        }
    })


def make_assistant_text(text: str, timestamp: str = '2026-01-01T00:00:00Z') -> str:
    return make_jsonl_line({
        'type': 'assistant',
        'timestamp': timestamp,
        'message': {
            'role': 'assistant',
            'content': [
                {'type': 'text', 'text': text}
            ]
        }
    })


class TestParseJsonlLog:
    def test_parses_tool_use(self, tmp_path):
        f = tmp_path / 'session.jsonl'
        f.write_text(make_assistant_tool_use('Bash', {'command': 'ls', 'description': 'List'}))
        entries = _parse_jsonl_log(f)
        assert len(entries) == 1
        assert entries[0]['entry_type'] == 'tool_use'
        assert entries[0]['tool_name'] == 'Bash'
        assert '$ List' in entries[0]['text']

    def test_parses_text(self, tmp_path):
        f = tmp_path / 'session.jsonl'
        f.write_text(make_assistant_text('I will now fix the bug.'))
        entries = _parse_jsonl_log(f)
        assert len(entries) == 1
        assert entries[0]['entry_type'] == 'text'
        assert 'fix the bug' in entries[0]['text']

    def test_skips_non_assistant_lines(self, tmp_path):
        f = tmp_path / 'session.jsonl'
        content = (
            make_jsonl_line({'type': 'user', 'message': {'content': 'hello'}}) +
            make_assistant_tool_use('Read', {'file_path': 'main.py'})
        )
        f.write_text(content)
        entries = _parse_jsonl_log(f)
        assert len(entries) == 1
        assert entries[0]['tool_name'] == 'Read'

    def test_skips_thinking_entries(self, tmp_path):
        f = tmp_path / 'session.jsonl'
        content = make_jsonl_line({
            'type': 'assistant',
            'timestamp': '2026-01-01T00:00:00Z',
            'message': {
                'content': [{'type': 'thinking', 'thinking': 'internal thoughts'}]
            }
        })
        f.write_text(content)
        entries = _parse_jsonl_log(f)
        assert len(entries) == 0

    def test_respects_limit(self, tmp_path):
        f = tmp_path / 'session.jsonl'
        lines = ''.join(
            make_assistant_tool_use('Bash', {'command': f'cmd{i}'}, f'2026-01-01T00:00:0{i}Z')
            for i in range(5)
        )
        f.write_text(lines)
        entries = _parse_jsonl_log(f, limit=3)
        assert len(entries) == 3
        # Should return the LAST 3 entries
        assert 'cmd2' in entries[0]['text'] or 'cmd4' in entries[-1]['text']

    def test_empty_file(self, tmp_path):
        f = tmp_path / 'session.jsonl'
        f.write_text('')
        entries = _parse_jsonl_log(f)
        assert entries == []

    def test_invalid_json_lines_skipped(self, tmp_path):
        f = tmp_path / 'session.jsonl'
        content = 'not valid json\n' + make_assistant_text('valid entry')
        f.write_text(content)
        entries = _parse_jsonl_log(f)
        assert len(entries) == 1

    def test_text_truncated_to_200(self, tmp_path):
        f = tmp_path / 'session.jsonl'
        long_text = 'x' * 500
        f.write_text(make_assistant_text(long_text))
        entries = _parse_jsonl_log(f)
        assert len(entries[0]['text']) <= 200

    def test_text_newlines_replaced(self, tmp_path):
        f = tmp_path / 'session.jsonl'
        f.write_text(make_assistant_text('line1\nline2\nline3'))
        entries = _parse_jsonl_log(f)
        assert '\n' not in entries[0]['text']

    def test_nonexistent_file(self, tmp_path):
        f = tmp_path / 'nonexistent.jsonl'
        entries = _parse_jsonl_log(f)
        assert entries == []

    def test_multiple_content_items(self, tmp_path):
        f = tmp_path / 'session.jsonl'
        content = make_jsonl_line({
            'type': 'assistant',
            'timestamp': '2026-01-01T00:00:00Z',
            'message': {
                'content': [
                    {'type': 'tool_use', 'name': 'Bash', 'input': {'command': 'ls'}},
                    {'type': 'tool_use', 'name': 'Read', 'input': {'file_path': 'x.py'}},
                ]
            }
        })
        f.write_text(content)
        entries = _parse_jsonl_log(f)
        assert len(entries) == 2


# ---------------------------------------------------------------------------
# _find_session_jsonl tests
# ---------------------------------------------------------------------------

class TestFindSessionJsonl:
    def test_finds_file_after_since(self, tmp_path):
        since = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        f = tmp_path / 'session.jsonl'
        f.write_text('{}')
        # Set mtime to after 'since'
        new_ts = since.timestamp() + 60
        import os
        os.utime(str(f), (new_ts, new_ts))
        result = _find_session_jsonl(tmp_path, since)
        assert result == f

    def test_returns_none_if_all_older(self, tmp_path):
        since = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        f = tmp_path / 'old_session.jsonl'
        f.write_text('{}')
        # Set mtime to before 'since'
        old_ts = since.timestamp() - 3600
        import os
        os.utime(str(f), (old_ts, old_ts))
        result = _find_session_jsonl(tmp_path, since)
        assert result is None

    def test_returns_newest_when_multiple(self, tmp_path):
        since = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        import os
        f1 = tmp_path / 'session1.jsonl'
        f1.write_text('{}')
        ts1 = since.timestamp() + 60
        os.utime(str(f1), (ts1, ts1))

        f2 = tmp_path / 'session2.jsonl'
        f2.write_text('{}')
        ts2 = since.timestamp() + 120
        os.utime(str(f2), (ts2, ts2))

        result = _find_session_jsonl(tmp_path, since)
        assert result == f2

    def test_empty_directory(self, tmp_path):
        since = datetime(2026, 1, 1, tzinfo=timezone.utc)
        result = _find_session_jsonl(tmp_path, since)
        assert result is None


# ---------------------------------------------------------------------------
# GET /api/autopilot/session-log endpoint tests
# ---------------------------------------------------------------------------

from fastapi.testclient import TestClient

class TestSessionLogEndpoint:
    def setup_method(self):
        self.client = TestClient(main_module.app)

    def test_returns_empty_when_not_active(self):
        state = main_module.get_autopilot_state()
        state.enabled = False
        state.manual_active = False
        state.session_start_time = None
        resp = self.client.get('/api/autopilot/session-log')
        assert resp.status_code == 200
        data = resp.json()
        assert data['active'] is False
        assert data['entries'] == []

    def test_returns_empty_when_no_start_time(self):
        state = main_module.get_autopilot_state()
        state.enabled = True
        state.session_start_time = None
        resp = self.client.get('/api/autopilot/session-log')
        assert resp.status_code == 200
        data = resp.json()
        assert data['entries'] == []
        # Reset
        state.enabled = False

    def test_returns_entries_when_active(self, tmp_path):
        # Create a fake projects directory
        since = datetime.now(timezone.utc) - timedelta(seconds=30)
        session_file = tmp_path / 'abc123.jsonl'
        session_file.write_text(
            make_assistant_tool_use('Bash', {'command': 'ls', 'description': 'List files'}) +
            make_assistant_text('I will now proceed.')
        )

        state = main_module.get_autopilot_state()
        state.enabled = True
        state.session_start_time = since
        state.session_jsonl_path = None

        with patch('backend.main._get_claude_projects_dir', return_value=tmp_path):
            with patch('backend.main._find_session_jsonl', return_value=session_file):
                resp = self.client.get('/api/autopilot/session-log?limit=50')

        assert resp.status_code == 200
        data = resp.json()
        assert data['active'] is True
        assert len(data['entries']) == 2
        assert data['entries'][0]['entry_type'] == 'tool_use'
        assert data['entries'][1]['entry_type'] == 'text'
        assert state.session_jsonl_path == session_file
        # Reset
        state.enabled = False
        state.session_start_time = None
        state.session_jsonl_path = None

    def test_limit_clamped(self, tmp_path):
        since = datetime.now(timezone.utc) - timedelta(seconds=30)
        session_file = tmp_path / 'test.jsonl'
        # Write 10 tool_use entries
        lines = ''.join(
            make_assistant_tool_use('Bash', {'command': f'cmd{i}'}, f'2026-01-01T00:00:0{i}Z')
            for i in range(10)
        )
        session_file.write_text(lines)

        state = main_module.get_autopilot_state()
        state.enabled = True
        state.session_start_time = since

        with patch('backend.main._get_claude_projects_dir', return_value=tmp_path):
            with patch('backend.main._find_session_jsonl', return_value=session_file):
                resp = self.client.get('/api/autopilot/session-log?limit=3')

        assert resp.status_code == 200
        data = resp.json()
        assert len(data['entries']) == 3
        # Reset
        state.enabled = False
        state.session_start_time = None

    def test_returns_entries_when_stopping(self, tmp_path):
        """Session log stays readable while stopping=True (process still running)."""
        since = datetime.now(timezone.utc) - timedelta(seconds=30)
        session_file = tmp_path / 'stopping_session.jsonl'
        session_file.write_text(
            make_assistant_tool_use('Bash', {'command': 'ls', 'description': 'List files'}) +
            make_assistant_text('Finishing up.')
        )

        state = main_module.get_autopilot_state()
        state.enabled = False       # autopilot was disabled
        state.stopping = True       # but Claude process still running
        state.manual_active = False
        state.session_start_time = since
        state.session_jsonl_path = None

        with patch('backend.main._get_claude_projects_dir', return_value=tmp_path):
            with patch('backend.main._find_session_jsonl', return_value=session_file):
                resp = self.client.get('/api/autopilot/session-log')

        assert resp.status_code == 200
        data = resp.json()
        # active should reflect stopping state
        assert data['active'] is True
        assert len(data['entries']) == 2
        # Reset
        state.stopping = False
        state.session_start_time = None
        state.session_jsonl_path = None

    def test_returns_empty_after_stopping_completes(self):
        """Once stopping completes (stopping=False, enabled=False), log returns empty."""
        state = main_module.get_autopilot_state()
        state.enabled = False
        state.stopping = False
        state.manual_active = False
        state.session_start_time = None
        resp = self.client.get('/api/autopilot/session-log')
        assert resp.status_code == 200
        data = resp.json()
        assert data['active'] is False
        assert data['entries'] == []

    def test_caches_session_file_after_first_find(self, tmp_path):
        """session_jsonl_path is set on first successful find and reused."""
        since = datetime.now(timezone.utc) - timedelta(seconds=30)
        session_file = tmp_path / 'cached.jsonl'
        session_file.write_text(make_assistant_text('hello'))

        state = main_module.get_autopilot_state()
        state.enabled = True
        state.session_start_time = since
        state.session_jsonl_path = None
        state.session_prompt_snippet = None

        call_count = {'n': 0}

        def counting_find(*args, **kwargs):
            call_count['n'] += 1
            return session_file

        with patch('backend.main._get_claude_projects_dir', return_value=tmp_path):
            with patch('backend.main._find_session_jsonl', side_effect=counting_find):
                self.client.get('/api/autopilot/session-log')
                self.client.get('/api/autopilot/session-log')

        # _find_session_jsonl should only be called once; second poll uses cache
        assert call_count['n'] == 1
        assert state.session_jsonl_path == session_file

        # Reset
        state.enabled = False
        state.session_start_time = None
        state.session_jsonl_path = None


# ---------------------------------------------------------------------------
# _jsonl_contains_prompt tests
# ---------------------------------------------------------------------------

class TestJsonlContainsPrompt:
    def test_finds_snippet_in_string_content(self, tmp_path):
        f = tmp_path / 's.jsonl'
        f.write_text(make_jsonl_line({
            'type': 'user',
            'message': {'content': 'Please work on Feature #42 [Backend]: Fix bug'}
        }))
        assert _jsonl_contains_prompt(f, 'Feature #42 [Backend]') is True

    def test_finds_snippet_in_list_content(self, tmp_path):
        f = tmp_path / 's.jsonl'
        f.write_text(make_jsonl_line({
            'type': 'user',
            'message': {'content': [{'type': 'text', 'text': 'Feature #7 [Frontend]: Add button'}]}
        }))
        assert _jsonl_contains_prompt(f, 'Feature #7 [Frontend]') is True

    def test_returns_false_when_snippet_absent(self, tmp_path):
        f = tmp_path / 's.jsonl'
        f.write_text(make_jsonl_line({
            'type': 'user',
            'message': {'content': 'Hello world'}
        }))
        assert _jsonl_contains_prompt(f, 'Feature #99') is False

    def test_skips_assistant_lines(self, tmp_path):
        f = tmp_path / 's.jsonl'
        f.write_text(make_jsonl_line({
            'type': 'assistant',
            'message': {'content': [{'type': 'text', 'text': 'Feature #1 [X]: yes'}]}
        }))
        assert _jsonl_contains_prompt(f, 'Feature #1 [X]') is False

    def test_nonexistent_file_returns_false(self, tmp_path):
        assert _jsonl_contains_prompt(tmp_path / 'nope.jsonl', 'anything') is False


# ---------------------------------------------------------------------------
# Additional _find_session_jsonl tests (content-matching)
# ---------------------------------------------------------------------------

class TestFindSessionJsonlContentMatch:
    def test_prefers_content_match_over_newest(self, tmp_path):
        """When prompt_snippet is given, prefer the file that contains it."""
        since = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        import os

        # Older file — contains the target prompt
        f_match = tmp_path / 'match.jsonl'
        f_match.write_text(make_jsonl_line({
            'type': 'user',
            'message': {'content': 'Feature #5 [Backend]: task'}
        }))
        ts_older = since.timestamp() + 60
        os.utime(str(f_match), (ts_older, ts_older))

        # Newer file — unrelated (interactive session)
        f_other = tmp_path / 'other.jsonl'
        f_other.write_text(make_jsonl_line({
            'type': 'user',
            'message': {'content': 'Please help me debug this'}
        }))
        ts_newer = since.timestamp() + 120
        os.utime(str(f_other), (ts_newer, ts_newer))

        result = _find_session_jsonl(tmp_path, since, prompt_snippet='Feature #5 [Backend]')
        assert result == f_match

    def test_falls_back_to_newest_when_no_match(self, tmp_path):
        """Without a content match, returns the newest file."""
        since = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        import os

        f1 = tmp_path / 'a.jsonl'
        f1.write_text('{}')
        ts1 = since.timestamp() + 60
        os.utime(str(f1), (ts1, ts1))

        f2 = tmp_path / 'b.jsonl'
        f2.write_text('{}')
        ts2 = since.timestamp() + 120
        os.utime(str(f2), (ts2, ts2))

        result = _find_session_jsonl(tmp_path, since, prompt_snippet='Feature #99')
        assert result == f2
