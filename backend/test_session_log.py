"""
Unit tests for the Claude JSONL session log reader.
====================================================

Tests cover:
- _get_claude_projects_slug(): path encoding
- _format_tool_call(): tool call formatting
- _parse_jsonl_log(): JSONL file parsing
- _find_session_jsonl(): finding session files by timestamp
- GET /api/autopilot/session-log endpoint
- GET /api/features/{id}/session-log endpoint
- Session ID persistence from autopilot endpoint to DB
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
from backend.claude_process import (
    _format_tool_call,
    _get_claude_projects_slug,
    _jsonl_contains_prompt,
    _parse_jsonl_log,
    _find_session_jsonl,
    _get_claude_projects_dir,
    _parse_main_agent_metadata,
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

    def test_parses_thinking_content(self, tmp_path):
        """Parse 'thinking' content type from extended thinking models (e.g., zai-org/glm-5)."""
        f = tmp_path / 'session.jsonl'
        content = make_jsonl_line({
            'type': 'assistant',
            'timestamp': '2026-01-01T00:00:00Z',
            'message': {
                'content': [{'type': 'thinking', 'thinking': 'I need to analyze this code'}]
            }
        })
        f.write_text(content)
        entries = _parse_jsonl_log(f)
        assert len(entries) == 1
        assert entries[0]['entry_type'] == 'thinking'
        assert 'analyze this code' in entries[0]['text']

    def test_thinking_text_truncated_to_200(self, tmp_path):
        """Thinking text is truncated to 200 chars like regular text."""
        f = tmp_path / 'session.jsonl'
        long_thinking = 'x' * 500
        content = make_jsonl_line({
            'type': 'assistant',
            'timestamp': '2026-01-01T00:00:00Z',
            'message': {
                'content': [{'type': 'thinking', 'thinking': long_thinking}]
            }
        })
        f.write_text(content)
        entries = _parse_jsonl_log(f)
        assert len(entries[0]['text']) <= 200

    def test_thinking_newlines_replaced(self, tmp_path):
        """Thinking text has newlines replaced with spaces."""
        f = tmp_path / 'session.jsonl'
        content = make_jsonl_line({
            'type': 'assistant',
            'timestamp': '2026-01-01T00:00:00Z',
            'message': {
                'content': [{'type': 'thinking', 'thinking': 'line1\nline2\nline3'}]
            }
        })
        f.write_text(content)
        entries = _parse_jsonl_log(f)
        assert '\n' not in entries[0]['text']

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

    def test_mixed_content_types(self, tmp_path):
        """Parse tool_use, text, and thinking content in the same message."""
        f = tmp_path / 'session.jsonl'
        content = make_jsonl_line({
            'type': 'assistant',
            'timestamp': '2026-01-01T00:00:00Z',
            'message': {
                'content': [
                    {'type': 'thinking', 'thinking': 'Let me analyze this'},
                    {'type': 'text', 'text': 'I will now fix the bug.'},
                    {'type': 'tool_use', 'name': 'Read', 'input': {'file_path': 'main.py'}},
                ]
            }
        })
        f.write_text(content)
        entries = _parse_jsonl_log(f)
        assert len(entries) == 3
        assert entries[0]['entry_type'] == 'thinking'
        assert entries[1]['entry_type'] == 'text'
        assert entries[2]['entry_type'] == 'tool_use'


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

class TestSessionLogEndpoint:
    """Tests for GET /api/autopilot/session-log.

    Uses the isolated ``client`` fixture from conftest.py so that calls to
    ``_persist_feature_session_id`` (triggered when a JSONL session file is
    found) write to the test database instead of the production ``features.db``.
    """

    def test_returns_empty_when_not_active(self, client):
        state = main_module.get_autopilot_state()
        state.enabled = False
        state.manual_active = False
        state.session_start_time = None
        resp = client.get('/api/autopilot/session-log')
        assert resp.status_code == 200
        data = resp.json()
        assert data['active'] is False
        assert data['entries'] == []

    def test_returns_empty_when_no_start_time(self, client):
        state = main_module.get_autopilot_state()
        state.enabled = True
        state.session_start_time = None
        resp = client.get('/api/autopilot/session-log')
        assert resp.status_code == 200
        data = resp.json()
        assert data['entries'] == []
        # Reset
        state.enabled = False

    def test_returns_entries_when_active(self, client, tmp_path):
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

        with patch('backend.routers.autopilot._get_claude_projects_dir', return_value=tmp_path):
            with patch('backend.routers.autopilot._find_session_jsonl', return_value=session_file):
                resp = client.get('/api/autopilot/session-log?limit=50')

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

    def test_limit_clamped(self, client, tmp_path):
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

        with patch('backend.routers.autopilot._get_claude_projects_dir', return_value=tmp_path):
            with patch('backend.routers.autopilot._find_session_jsonl', return_value=session_file):
                resp = client.get('/api/autopilot/session-log?limit=3')

        assert resp.status_code == 200
        data = resp.json()
        assert len(data['entries']) == 3
        # Reset
        state.enabled = False
        state.session_start_time = None

    def test_returns_entries_when_stopping(self, client, tmp_path):
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

        with patch('backend.routers.autopilot._get_claude_projects_dir', return_value=tmp_path):
            with patch('backend.routers.autopilot._find_session_jsonl', return_value=session_file):
                resp = client.get('/api/autopilot/session-log')

        assert resp.status_code == 200
        data = resp.json()
        # active should reflect stopping state
        assert data['active'] is True
        assert len(data['entries']) == 2
        # Reset
        state.stopping = False
        state.session_start_time = None
        state.session_jsonl_path = None

    def test_returns_empty_after_stopping_completes(self, client):
        """Once stopping completes (stopping=False, enabled=False), log returns empty."""
        state = main_module.get_autopilot_state()
        state.enabled = False
        state.stopping = False
        state.manual_active = False
        state.session_start_time = None
        resp = client.get('/api/autopilot/session-log')
        assert resp.status_code == 200
        data = resp.json()
        assert data['active'] is False
        assert data['entries'] == []

    def test_caches_session_file_after_first_find(self, client, tmp_path):
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

        with patch('backend.routers.autopilot._get_claude_projects_dir', return_value=tmp_path):
            with patch('backend.routers.autopilot._find_session_jsonl', side_effect=counting_find):
                client.get('/api/autopilot/session-log')
                client.get('/api/autopilot/session-log')

        # _find_session_jsonl should only be called once; second poll uses cache
        assert call_count['n'] == 1
        assert state.session_jsonl_path == session_file

        # Reset
        state.enabled = False
        state.session_start_time = None
        state.session_jsonl_path = None

    def test_feature_id_none_when_not_active(self, client):
        """feature_id is None when no session is active."""
        state = main_module.get_autopilot_state()
        state.enabled = False
        state.manual_active = False
        state.stopping = False
        state.session_start_time = None
        resp = client.get('/api/autopilot/session-log')
        assert resp.status_code == 200
        data = resp.json()
        assert data['feature_id'] is None

    def test_feature_id_from_autopilot(self, client, tmp_path):
        """feature_id is current_feature_id when autopilot is enabled."""
        since = datetime.now(timezone.utc) - timedelta(seconds=30)
        session_file = tmp_path / 'autopilot.jsonl'
        session_file.write_text(make_assistant_text('Working on feature'))

        state = main_module.get_autopilot_state()
        state.enabled = True
        state.manual_active = False
        state.stopping = False
        state.current_feature_id = 1  # Use test DB feature ID
        state.session_start_time = since
        state.session_jsonl_path = None

        with patch('backend.routers.autopilot._get_claude_projects_dir', return_value=tmp_path):
            with patch('backend.routers.autopilot._find_session_jsonl', return_value=session_file):
                resp = client.get('/api/autopilot/session-log')

        assert resp.status_code == 200
        data = resp.json()
        assert data['feature_id'] == 1

        # Reset
        state.enabled = False
        state.current_feature_id = None
        state.session_start_time = None
        state.session_jsonl_path = None

    def test_feature_id_from_manual_launch(self, client, tmp_path):
        """feature_id is manual_feature_id when manual launch is active."""
        since = datetime.now(timezone.utc) - timedelta(seconds=30)
        session_file = tmp_path / 'manual.jsonl'
        session_file.write_text(make_assistant_text('Manual run'))

        state = main_module.get_autopilot_state()
        state.enabled = False
        state.manual_active = True
        state.stopping = False
        state.manual_feature_id = 2  # Use test DB feature IDs
        state.current_feature_id = 1  # Should NOT be used
        state.session_start_time = since
        state.session_jsonl_path = None

        with patch('backend.routers.autopilot._get_claude_projects_dir', return_value=tmp_path):
            with patch('backend.routers.autopilot._find_session_jsonl', return_value=session_file):
                resp = client.get('/api/autopilot/session-log')

        assert resp.status_code == 200
        data = resp.json()
        # Manual feature_id takes priority over current_feature_id
        assert data['feature_id'] == 2

        # Reset
        state.manual_active = False
        state.manual_feature_id = None
        state.current_feature_id = None
        state.session_start_time = None
        state.session_jsonl_path = None

    def test_feature_id_from_stopping_state(self, client, tmp_path):
        """feature_id is current_feature_id when in stopping state."""
        since = datetime.now(timezone.utc) - timedelta(seconds=30)
        session_file = tmp_path / 'stopping.jsonl'
        session_file.write_text(make_assistant_text('Finishing up'))

        state = main_module.get_autopilot_state()
        state.enabled = False
        state.manual_active = False
        state.stopping = True
        state.current_feature_id = 4  # Use test DB feature ID
        state.session_start_time = since
        state.session_jsonl_path = None

        with patch('backend.routers.autopilot._get_claude_projects_dir', return_value=tmp_path):
            with patch('backend.routers.autopilot._find_session_jsonl', return_value=session_file):
                resp = client.get('/api/autopilot/session-log')

        assert resp.status_code == 200
        data = resp.json()
        assert data['feature_id'] == 4

        # Reset
        state.stopping = False
        state.current_feature_id = None
        state.session_start_time = None
        state.session_jsonl_path = None

    def test_feature_id_none_when_no_feature_set(self, client, tmp_path):
        """feature_id is None when active but no feature id is set."""
        since = datetime.now(timezone.utc) - timedelta(seconds=30)
        session_file = tmp_path / 'no_feature.jsonl'
        session_file.write_text(make_assistant_text('No feature'))

        state = main_module.get_autopilot_state()
        state.enabled = True
        state.manual_active = False
        state.stopping = False
        state.current_feature_id = None
        state.session_start_time = since
        state.session_jsonl_path = None

        with patch('backend.routers.autopilot._get_claude_projects_dir', return_value=tmp_path):
            with patch('backend.routers.autopilot._find_session_jsonl', return_value=session_file):
                resp = client.get('/api/autopilot/session-log')

        assert resp.status_code == 200
        data = resp.json()
        assert data['feature_id'] is None

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


# ---------------------------------------------------------------------------
# GET /api/features/{id}/session-log endpoint tests
# ---------------------------------------------------------------------------

class TestFeatureSessionLogEndpoint:
    """Tests for GET /api/features/{id}/session-log."""

    def test_not_found(self, client):
        """Returns 404 for unknown feature."""
        resp = client.get('/api/features/9999/session-log')
        assert resp.status_code == 404
        assert 'not found' in resp.json()['detail'].lower()

    def test_no_session_id(self, client):
        """Returns empty response when feature has no claude_session_id."""
        # Feature 1 has no session ID in the test fixture
        resp = client.get('/api/features/1/session-log')
        assert resp.status_code == 200
        data = resp.json()
        assert data['active'] is False
        assert data['session_file'] is None
        assert data['entries'] == []
        assert data['total_entries'] == 0
        assert data['feature_id'] == 1

    def test_session_file_not_found(self, client, tmp_path):
        """Returns empty response when the JSONL file no longer exists on disk."""

        # Set a session ID on feature 1
        client.patch('/api/features/1/state', json={'claude_session_id': 'missing.jsonl'})

        with patch('backend.routers.features._get_claude_projects_dir', return_value=tmp_path):
            resp = client.get('/api/features/1/session-log')

        assert resp.status_code == 200
        data = resp.json()
        assert data['session_file'] is None
        assert data['entries'] == []

    def test_returns_entries_from_jsonl(self, client, tmp_path):
        """Returns log entries from the stored JSONL session file."""
        # Set session ID on feature 1
        client.patch('/api/features/1/state', json={'claude_session_id': 'abc123.jsonl'})

        # Create a JSONL file in tmp_path
        session_file = tmp_path / 'abc123.jsonl'
        session_file.write_text(
            make_assistant_tool_use('Bash', {'command': 'ls', 'description': 'List files'}) +
            make_assistant_text('I will now fix the issue.')
        )

        with patch('backend.routers.features._get_claude_projects_dir', return_value=tmp_path):
            resp = client.get('/api/features/1/session-log')

        assert resp.status_code == 200
        data = resp.json()
        assert data['active'] is False
        assert data['feature_id'] == 1
        assert data['session_file'] == 'abc123.jsonl'
        assert len(data['entries']) == 2
        assert data['entries'][0]['entry_type'] == 'tool_use'
        assert data['entries'][1]['entry_type'] == 'text'
        assert data['total_entries'] == 2

    def test_limit_parameter(self, client, tmp_path):
        """Respects the limit query parameter."""
        client.patch('/api/features/1/state', json={'claude_session_id': 'limit_test.jsonl'})

        session_file = tmp_path / 'limit_test.jsonl'
        lines = ''.join(
            make_assistant_tool_use('Bash', {'command': f'cmd{i}'}, f'2026-01-01T00:00:0{i}Z')
            for i in range(8)
        )
        session_file.write_text(lines)

        with patch('backend.routers.features._get_claude_projects_dir', return_value=tmp_path):
            resp = client.get('/api/features/1/session-log?limit=3')

        assert resp.status_code == 200
        assert len(resp.json()['entries']) == 3

    def test_no_projects_dir(self, client):
        """Returns empty response when projects directory does not exist."""
        client.patch('/api/features/2/state', json={'claude_session_id': 'somefile.jsonl'})

        with patch('backend.routers.features._get_claude_projects_dir', return_value=None):
            resp = client.get('/api/features/2/session-log')

        assert resp.status_code == 200
        data = resp.json()
        assert data['session_file'] is None
        assert data['entries'] == []

    def test_done_feature_returns_entries(self, client, tmp_path):
        """DONE features (passes=True) can still return their historical log."""
        # Feature 3 is DONE (passes=True)
        client.patch('/api/features/3/state', json={'claude_session_id': 'done_session.jsonl'})

        session_file = tmp_path / 'done_session.jsonl'
        session_file.write_text(make_assistant_text('Feature completed successfully.'))

        with patch('backend.routers.features._get_claude_projects_dir', return_value=tmp_path):
            resp = client.get('/api/features/3/session-log')

        assert resp.status_code == 200
        data = resp.json()
        assert data['feature_id'] == 3
        assert len(data['entries']) == 1
        assert 'completed successfully' in data['entries'][0]['text']


# ---------------------------------------------------------------------------
# Session ID persistence tests (autopilot endpoint -> DB)
# ---------------------------------------------------------------------------

class TestSessionIdPersistence:
    """Tests that _persist_feature_session_id saves the session file name to the DB."""

    def test_persist_saves_session_filename(self, client):
        """claude_session_id is updated when _persist_feature_session_id is called."""
        from backend.routers.autopilot import _persist_feature_session_id

        # Feature 1 starts with no session ID (conftest fixture)
        resp = client.get('/api/features/1')
        assert resp.json()['claude_session_id'] is None

        # Call the helper directly - it uses get_session() which the client fixture patches
        _persist_feature_session_id(1, 'abc-session.jsonl')

        # Verify the DB was updated
        resp = client.get('/api/features/1')
        assert resp.json()['claude_session_id'] == 'abc-session.jsonl'

    def test_persist_no_op_when_same_filename(self, client):
        """Does not update DB when the filename is already stored."""
        from backend.routers.autopilot import _persist_feature_session_id

        # Set a session ID first
        client.patch('/api/features/1/state', json={'claude_session_id': 'same.jsonl'})

        # Call again with the same name - should be a no-op
        _persist_feature_session_id(1, 'same.jsonl')

        resp = client.get('/api/features/1')
        assert resp.json()['claude_session_id'] == 'same.jsonl'

    def test_persist_silently_ignores_missing_feature(self, client):
        """Does not raise for unknown feature IDs."""
        from backend.routers.autopilot import _persist_feature_session_id

        # Feature 9999 does not exist - should not raise
        _persist_feature_session_id(9999, 'ghost.jsonl')  # no exception expected


# ---------------------------------------------------------------------------
# _parse_main_agent_metadata tests
# ---------------------------------------------------------------------------

class TestParseMainAgentMetadata:
    """Tests for _parse_main_agent_metadata function."""

    def test_empty_file(self, tmp_path):
        """Returns zeros and None for empty file."""
        f = tmp_path / 'session.jsonl'
        f.write_text('')
        result = _parse_main_agent_metadata(f)
        assert result['turn_count'] == 0
        assert result['token_estimate'] == 0
        assert result['last_tool_used'] is None
        assert result['agent_type'] is None

    def test_nonexistent_file(self, tmp_path):
        """Returns zeros and None for nonexistent file."""
        f = tmp_path / 'nonexistent.jsonl'
        result = _parse_main_agent_metadata(f)
        assert result['turn_count'] == 0
        assert result['token_estimate'] == 0
        assert result['last_tool_used'] is None
        assert result['agent_type'] is None

    def test_counts_turns(self, tmp_path):
        """Counts user and assistant messages as turns."""
        f = tmp_path / 'session.jsonl'
        content = (
            make_jsonl_line({'type': 'user', 'message': {'content': 'hello'}}) +
            make_jsonl_line({'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': 'hi'}]}}) +
            make_jsonl_line({'type': 'user', 'message': {'content': 'task'}}) +
            make_jsonl_line({'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': 'done'}]}})
        )
        f.write_text(content)
        result = _parse_main_agent_metadata(f)
        assert result['turn_count'] == 4

    def test_estimates_tokens(self, tmp_path):
        """Estimates tokens from character count (~4 chars per token)."""
        f = tmp_path / 'session.jsonl'
        # 400 characters should be ~100 tokens
        text = 'x' * 400
        content = make_jsonl_line({
            'type': 'assistant',
            'message': {'content': [{'type': 'text', 'text': text}]}
        })
        f.write_text(content)
        result = _parse_main_agent_metadata(f)
        assert result['token_estimate'] == 100

    def test_extracts_last_tool_used(self, tmp_path):
        """Extracts the name of the last tool_use block."""
        f = tmp_path / 'session.jsonl'
        content = (
            make_assistant_tool_use('Read', {'file_path': 'main.py'}) +
            make_assistant_tool_use('Edit', {'file_path': 'utils.py'}) +
            make_assistant_tool_use('Bash', {'command': 'pytest', 'description': 'Run tests'})
        )
        f.write_text(content)
        result = _parse_main_agent_metadata(f)
        assert result['last_tool_used'] == 'Bash'

    def test_last_tool_used_none_when_no_tools(self, tmp_path):
        """Returns None when no tool_use blocks exist."""
        f = tmp_path / 'session.jsonl'
        f.write_text(make_assistant_text('Hello world'))
        result = _parse_main_agent_metadata(f)
        assert result['last_tool_used'] is None

    def test_extracts_agent_type_from_filename(self, tmp_path):
        """Extracts agent type from filename pattern (e.g., session--sonnet.jsonl)."""
        f = tmp_path / 'session-abc123--sonnet.jsonl'
        f.write_text('{}')
        result = _parse_main_agent_metadata(f)
        assert result['agent_type'] == 'sonnet'

    def test_extracts_agent_type_opus_from_filename(self, tmp_path):
        """Extracts opus agent type from filename."""
        f = tmp_path / 'test--opus.jsonl'
        f.write_text('{}')
        result = _parse_main_agent_metadata(f)
        assert result['agent_type'] == 'opus'

    def test_extracts_agent_type_haiku_from_filename(self, tmp_path):
        """Extracts haiku agent type from filename."""
        f = tmp_path / 'session--haiku.jsonl'
        f.write_text('{}')
        result = _parse_main_agent_metadata(f)
        assert result['agent_type'] == 'haiku'

    def test_agent_type_from_system_message(self, tmp_path):
        """Extracts agent type from system message if not in filename."""
        f = tmp_path / 'session.jsonl'
        content = make_jsonl_line({
            'type': 'system',
            'message': {'model': 'claude-sonnet-4-6'}
        })
        f.write_text(content)
        result = _parse_main_agent_metadata(f)
        assert result['agent_type'] == 'sonnet'

    def test_agent_type_opus_from_system_message(self, tmp_path):
        """Extracts opus from system message model field."""
        f = tmp_path / 'session.jsonl'
        content = make_jsonl_line({
            'type': 'system',
            'message': {'model': 'claude-opus-4-6'}
        })
        f.write_text(content)
        result = _parse_main_agent_metadata(f)
        assert result['agent_type'] == 'opus'

    def test_agent_type_unknown_model_name(self, tmp_path):
        """Uses full model name when not a known type."""
        f = tmp_path / 'session.jsonl'
        content = make_jsonl_line({
            'type': 'system',
            'message': {'model': 'gpt-4'}
        })
        f.write_text(content)
        result = _parse_main_agent_metadata(f)
        assert result['agent_type'] == 'gpt-4'

    def test_filename_takes_precedence_over_system(self, tmp_path):
        """Filename agent type takes precedence over system message."""
        f = tmp_path / 'session--sonnet.jsonl'
        content = make_jsonl_line({
            'type': 'system',
            'message': {'model': 'claude-opus-4-6'}
        })
        f.write_text(content)
        result = _parse_main_agent_metadata(f)
        assert result['agent_type'] == 'sonnet'

    def test_counts_text_in_thinking_blocks(self, tmp_path):
        """Counts characters from thinking blocks for token estimation."""
        f = tmp_path / 'session.jsonl'
        thinking_text = 'x' * 200
        content = make_jsonl_line({
            'type': 'assistant',
            'message': {'content': [{'type': 'thinking', 'thinking': thinking_text}]}
        })
        f.write_text(content)
        result = _parse_main_agent_metadata(f)
        assert result['token_estimate'] == 50  # 200 chars / 4

    def test_counts_tool_input_json(self, tmp_path):
        """Counts characters from tool inputs for token estimation."""
        f = tmp_path / 'session.jsonl'
        # Tool input with substantial content
        large_input = {'file_path': 'x' * 200}
        content = make_assistant_tool_use('Read', large_input)
        f.write_text(content)
        result = _parse_main_agent_metadata(f)
        # Should have counted the tool input JSON
        assert result['token_estimate'] > 0

    def test_multiple_tools_last_one_wins(self, tmp_path):
        """The last tool_use in the last assistant message is returned."""
        f = tmp_path / 'session.jsonl'
        content = (
            make_assistant_tool_use('Read', {'file_path': 'a.py'}) +
            make_assistant_text('Some analysis') +
            make_assistant_tool_use('Bash', {'command': 'ls'}) +
            make_assistant_tool_use('Edit', {'file_path': 'b.py'})  # Last tool
        )
        f.write_text(content)
        result = _parse_main_agent_metadata(f)
        assert result['last_tool_used'] == 'Edit'

    def test_full_metadata_extraction(self, tmp_path):
        """Complete test with all metadata fields."""
        f = tmp_path / 'session--sonnet.jsonl'
        content = (
            make_jsonl_line({'type': 'user', 'message': {'content': 'Fix bug'}}) +
            make_assistant_tool_use('Read', {'file_path': 'main.py'}) +
            make_assistant_tool_use('Edit', {'file_path': 'main.py'}) +
            make_jsonl_line({'type': 'user', 'message': {'content': 'Run tests'}}) +
            make_assistant_tool_use('Bash', {'command': 'pytest', 'description': 'Run tests'})
        )
        f.write_text(content)
        result = _parse_main_agent_metadata(f)
        assert result['turn_count'] == 5  # 2 user + 3 assistant messages
        assert result['token_estimate'] > 0
        assert result['last_tool_used'] == 'Bash'
        assert result['agent_type'] == 'sonnet'

    def test_invalid_json_lines_skipped(self, tmp_path):
        """Invalid JSON lines are skipped without error."""
        f = tmp_path / 'session.jsonl'
        content = 'not valid json\n' + make_assistant_text('valid entry')
        f.write_text(content)
        result = _parse_main_agent_metadata(f)
        assert result['turn_count'] == 1  # Only the valid assistant message
