"""
Unit tests for _extract_delegation_edges (Feature #194).
==========================================================

Tests cover:
- Empty JSONL returns no edges
- Single Agent tool call creates one edge (synthetic ID fallback)
- Agent call with resume field uses the resume value as subagent ID
- Agent calls correlated with subagent_log_infos use real agent IDs
- Duplicate (source, target) pairs are deduplicated
- Nested delegations from subagent logs are included
- Missing/unreadable files are handled gracefully
- Non-Agent tool_use blocks are ignored
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.claude_process import _extract_delegation_edges


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_jsonl_line(tool_name: str, tool_input: dict) -> str:
    """Build a minimal JSONL assistant line containing one tool_use block."""
    obj = {
        "type": "assistant",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "name": tool_name,
                    "input": tool_input,
                }
            ]
        },
        "timestamp": "2026-01-01T00:00:00.000Z",
    }
    return json.dumps(obj)


def _make_multi_tool_line(tool_calls: list[tuple]) -> str:
    """Build a JSONL line with multiple tool_use blocks in one assistant message."""
    content = []
    for name, inp in tool_calls:
        content.append({"type": "tool_use", "name": name, "input": inp})
    obj = {
        "type": "assistant",
        "message": {"content": content},
        "timestamp": "2026-01-01T00:00:00.000Z",
    }
    return json.dumps(obj)


def _write_jsonl(tmp_path: Path, lines: list[str], filename: str = "session.jsonl") -> Path:
    """Write JSONL lines to a temp file and return the path."""
    f = tmp_path / filename
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return f


# ---------------------------------------------------------------------------
# Basic edge extraction
# ---------------------------------------------------------------------------

class TestExtractDelegationEdgesBasic:

    def test_empty_file_returns_no_edges(self, tmp_path):
        f = _write_jsonl(tmp_path, [])
        assert _extract_delegation_edges(f) == []

    def test_no_agent_tool_calls_returns_no_edges(self, tmp_path):
        lines = [
            _make_jsonl_line("Bash", {"command": "ls"}),
            _make_jsonl_line("Read", {"file_path": "main.py"}),
        ]
        f = _write_jsonl(tmp_path, lines)
        assert _extract_delegation_edges(f) == []

    def test_single_agent_call_synthetic_id(self, tmp_path):
        lines = [_make_jsonl_line("Agent", {"subagent_type": "code-review", "description": "review"})]
        f = _write_jsonl(tmp_path, lines)
        edges = _extract_delegation_edges(f)
        assert len(edges) == 1
        assert edges[0]["source"] == "main"
        assert edges[0]["target"] == "agent_1"

    def test_multiple_agent_calls_synthetic_ids(self, tmp_path):
        lines = [
            _make_jsonl_line("Agent", {"description": "first"}),
            _make_jsonl_line("Agent", {"description": "second"}),
            _make_jsonl_line("Agent", {"description": "third"}),
        ]
        f = _write_jsonl(tmp_path, lines)
        edges = _extract_delegation_edges(f)
        assert len(edges) == 3
        targets = {e["target"] for e in edges}
        assert targets == {"agent_1", "agent_2", "agent_3"}
        for e in edges:
            assert e["source"] == "main"

    def test_nonexistent_file_returns_empty(self, tmp_path):
        result = _extract_delegation_edges(tmp_path / "nonexistent.jsonl")
        assert result == []

    def test_non_agent_tools_not_counted(self, tmp_path):
        """Non-Agent tool_use blocks must not affect edge generation."""
        lines = [
            _make_jsonl_line("Bash", {"command": "ls"}),
            _make_jsonl_line("Agent", {"description": "first agent"}),
            _make_jsonl_line("Read", {"file_path": "foo.py"}),
            _make_jsonl_line("Agent", {"description": "second agent"}),
        ]
        f = _write_jsonl(tmp_path, lines)
        edges = _extract_delegation_edges(f)
        assert len(edges) == 2
        assert edges[0] == {"source": "main", "target": "agent_1"}
        assert edges[1] == {"source": "main", "target": "agent_2"}


# ---------------------------------------------------------------------------
# Resume field extracts real subagent ID
# ---------------------------------------------------------------------------

class TestExtractDelegationEdgesResume:

    def test_resume_field_used_as_subagent_id(self, tmp_path):
        lines = [_make_jsonl_line("Agent", {"resume": "abc-123", "description": "resumed agent"})]
        f = _write_jsonl(tmp_path, lines)
        edges = _extract_delegation_edges(f)
        assert edges == [{"source": "main", "target": "abc-123"}]

    def test_resume_takes_priority_over_log_infos(self, tmp_path):
        """resume field wins over subagent_log_infos correlation."""
        lines = [_make_jsonl_line("Agent", {"resume": "real-id-xyz"})]
        f = _write_jsonl(tmp_path, lines)
        log_infos = [{"agent_id": "would-be-used", "file_path": str(tmp_path / "nonexistent.jsonl")}]
        edges = _extract_delegation_edges(f, subagent_log_infos=log_infos)
        assert edges == [{"source": "main", "target": "real-id-xyz"}]

    def test_mixed_resume_and_no_resume(self, tmp_path):
        lines = [
            _make_jsonl_line("Agent", {"resume": "existing-agent"}),
            _make_jsonl_line("Agent", {"description": "new agent"}),
        ]
        f = _write_jsonl(tmp_path, lines)
        edges = _extract_delegation_edges(f)
        assert edges[0] == {"source": "main", "target": "existing-agent"}
        assert edges[1]["source"] == "main"
        # The second call falls through to the synthetic counter (first new-agent)
        assert edges[1]["target"] == "agent_1"


# ---------------------------------------------------------------------------
# Correlation with subagent_log_infos
# ---------------------------------------------------------------------------

class TestExtractDelegationEdgesLogInfos:

    def test_single_call_uses_log_info_agent_id(self, tmp_path):
        lines = [_make_jsonl_line("Agent", {"description": "do work"})]
        f = _write_jsonl(tmp_path, lines)
        log_infos = [{"agent_id": "uuid-abc", "file_path": str(tmp_path / "agent-uuid-abc.jsonl")}]
        edges = _extract_delegation_edges(f, subagent_log_infos=log_infos)
        assert edges[0] == {"source": "main", "target": "uuid-abc"}

    def test_multiple_calls_correlated_by_order(self, tmp_path):
        lines = [
            _make_jsonl_line("Agent", {"description": "first"}),
            _make_jsonl_line("Agent", {"description": "second"}),
        ]
        f = _write_jsonl(tmp_path, lines)
        log_infos = [
            {"agent_id": "id-one", "file_path": str(tmp_path / "agent-id-one.jsonl")},
            {"agent_id": "id-two", "file_path": str(tmp_path / "agent-id-two.jsonl")},
        ]
        edges = _extract_delegation_edges(f, subagent_log_infos=log_infos)
        assert edges[0] == {"source": "main", "target": "id-one"}
        assert edges[1] == {"source": "main", "target": "id-two"}

    def test_more_calls_than_log_infos_uses_synthetic_for_extras(self, tmp_path):
        """Extra Agent calls beyond discovered log files get synthetic IDs.

        The synthetic counter is independent of call position, so the first
        call that falls through to the synthetic fallback gets agent_1, the
        second gets agent_2, etc.
        """
        lines = [
            _make_jsonl_line("Agent", {"description": "first"}),
            _make_jsonl_line("Agent", {"description": "second"}),
            _make_jsonl_line("Agent", {"description": "third"}),
        ]
        f = _write_jsonl(tmp_path, lines)
        log_infos = [{"agent_id": "real-id", "file_path": str(tmp_path / "agent-real-id.jsonl")}]
        edges = _extract_delegation_edges(f, subagent_log_infos=log_infos)
        assert edges[0]["target"] == "real-id"
        # Synthetic counter starts at 1 for the first fallback call
        assert edges[1]["target"] == "agent_1"
        assert edges[2]["target"] == "agent_2"


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

class TestExtractDelegationEdgesDeduplication:

    def test_duplicate_resume_ids_deduplicated(self, tmp_path):
        """Same resume ID appearing twice produces only one edge."""
        lines = [
            _make_jsonl_line("Agent", {"resume": "same-id"}),
            _make_jsonl_line("Agent", {"resume": "same-id"}),
        ]
        f = _write_jsonl(tmp_path, lines)
        edges = _extract_delegation_edges(f)
        assert len(edges) == 1
        assert edges[0] == {"source": "main", "target": "same-id"}

    def test_different_targets_not_deduplicated(self, tmp_path):
        lines = [
            _make_jsonl_line("Agent", {"resume": "id-a"}),
            _make_jsonl_line("Agent", {"resume": "id-b"}),
        ]
        f = _write_jsonl(tmp_path, lines)
        edges = _extract_delegation_edges(f)
        assert len(edges) == 2

    def test_synthetic_counter_independent_of_position(self, tmp_path):
        """Synthetic ID suffix reflects unique-new-agent ordinal, not raw call position.

        resume calls use real IDs (no synthetic counter increment); the first
        fallback-to-synthetic call gets agent_1 even though it is not the first
        Agent call in the file.
        """
        lines = [
            _make_jsonl_line("Agent", {"resume": "real-id"}),   # position 0 — no synthetic
            _make_jsonl_line("Agent", {"description": "new"}),  # position 1 — first synthetic
        ]
        f = _write_jsonl(tmp_path, lines)
        edges = _extract_delegation_edges(f)
        assert edges[0] == {"source": "main", "target": "real-id"}
        assert edges[1] == {"source": "main", "target": "agent_1"}

    def test_nested_edges_deduplicated_against_main_edges(self, tmp_path):
        """If main and subagent produce same edge pair, only one is returned."""
        # Main agent calls sub-a
        main_lines = [_make_jsonl_line("Agent", {"resume": "sub-a"})]
        main_file = _write_jsonl(tmp_path, main_lines, "main.jsonl")

        # sub-a also calls "sub-a" itself (edge main->sub-a already exists)
        sub_lines = [_make_jsonl_line("Agent", {"resume": "sub-a"})]
        sub_file = _write_jsonl(tmp_path, sub_lines, "agent-sub-a.jsonl")

        log_infos = [{"agent_id": "sub-a", "file_path": str(sub_file)}]
        edges = _extract_delegation_edges(main_file, subagent_log_infos=log_infos)
        # main->sub-a appears twice (from main log + from sub-a log recursion)
        # but should be deduplicated
        main_sub_a_edges = [e for e in edges if e["source"] == "main" and e["target"] == "sub-a"]
        assert len(main_sub_a_edges) == 1


# ---------------------------------------------------------------------------
# Nested delegations from subagent logs
# ---------------------------------------------------------------------------

class TestExtractDelegationEdgesNested:

    def test_subagent_log_with_agent_call_creates_nested_edge(self, tmp_path):
        """When a subagent log itself contains an Agent call, add a nested edge."""
        # Main log: spawns sub-1
        main_lines = [_make_jsonl_line("Agent", {"resume": "sub-1"})]
        main_file = _write_jsonl(tmp_path, main_lines, "main.jsonl")

        # sub-1 log: spawns sub-2 (synthetic since no log_infos for sub-1)
        sub1_lines = [_make_jsonl_line("Agent", {"description": "deep work"})]
        sub1_file = _write_jsonl(tmp_path, sub1_lines, "agent-sub-1.jsonl")

        log_infos = [{"agent_id": "sub-1", "file_path": str(sub1_file)}]
        edges = _extract_delegation_edges(main_file, subagent_log_infos=log_infos)

        edge_tuples = {(e["source"], e["target"]) for e in edges}
        assert ("main", "sub-1") in edge_tuples
        assert ("sub-1", "agent_1") in edge_tuples

    def test_subagent_with_resume_in_nested_log(self, tmp_path):
        """Nested subagent log with resume field uses real ID."""
        main_lines = [_make_jsonl_line("Agent", {"resume": "sub-alpha"})]
        main_file = _write_jsonl(tmp_path, main_lines, "main.jsonl")

        sub_lines = [_make_jsonl_line("Agent", {"resume": "sub-beta"})]
        sub_file = _write_jsonl(tmp_path, sub_lines, "agent-sub-alpha.jsonl")

        log_infos = [{"agent_id": "sub-alpha", "file_path": str(sub_file)}]
        edges = _extract_delegation_edges(main_file, subagent_log_infos=log_infos)

        assert {"source": "main", "target": "sub-alpha"} in edges
        assert {"source": "sub-alpha", "target": "sub-beta"} in edges

    def test_missing_subagent_file_does_not_raise(self, tmp_path):
        """If a subagent log file doesn't exist, skip it gracefully."""
        main_lines = [_make_jsonl_line("Agent", {"resume": "sub-x"})]
        main_file = _write_jsonl(tmp_path, main_lines, "main.jsonl")

        log_infos = [{"agent_id": "sub-x", "file_path": str(tmp_path / "nonexistent.jsonl")}]
        edges = _extract_delegation_edges(main_file, subagent_log_infos=log_infos)
        # Only the main->sub-x edge from main log; recursive call skipped
        assert edges == [{"source": "main", "target": "sub-x"}]

    def test_no_subagent_logs_no_nested_edges(self, tmp_path):
        lines = [_make_jsonl_line("Agent", {"resume": "sub-1"})]
        f = _write_jsonl(tmp_path, lines)
        edges = _extract_delegation_edges(f, subagent_log_infos=[])
        assert edges == [{"source": "main", "target": "sub-1"}]


# ---------------------------------------------------------------------------
# Custom source_id
# ---------------------------------------------------------------------------

class TestExtractDelegationEdgesSourceId:

    def test_custom_source_id_used_in_edges(self, tmp_path):
        lines = [_make_jsonl_line("Agent", {"resume": "child-id"})]
        f = _write_jsonl(tmp_path, lines)
        edges = _extract_delegation_edges(f, source_id="parent-agent")
        assert edges == [{"source": "parent-agent", "target": "child-id"}]

    def test_default_source_id_is_main(self, tmp_path):
        lines = [_make_jsonl_line("Agent", {})]
        f = _write_jsonl(tmp_path, lines)
        edges = _extract_delegation_edges(f)
        assert edges[0]["source"] == "main"


# ---------------------------------------------------------------------------
# Malformed / edge-case JSONL
# ---------------------------------------------------------------------------

class TestExtractDelegationEdgesMalformed:

    def test_invalid_json_lines_skipped(self, tmp_path):
        content = "not valid json\n" + _make_jsonl_line("Agent", {"resume": "ok-id"}) + "\n"
        f = tmp_path / "session.jsonl"
        f.write_text(content, encoding="utf-8")
        edges = _extract_delegation_edges(f)
        assert edges == [{"source": "main", "target": "ok-id"}]

    def test_non_assistant_lines_ignored(self, tmp_path):
        """user/system type lines are not processed."""
        user_line = json.dumps({
            "type": "user",
            "message": {"content": [{"type": "tool_use", "name": "Agent", "input": {"resume": "fake"}}]},
        })
        agent_line = _make_jsonl_line("Agent", {"resume": "real"})
        f = _write_jsonl(tmp_path, [user_line, agent_line])
        edges = _extract_delegation_edges(f)
        assert edges == [{"source": "main", "target": "real"}]

    def test_empty_agent_input_uses_synthetic_id(self, tmp_path):
        """Agent call with empty/null input still works (no resume)."""
        obj = {
            "type": "assistant",
            "message": {
                "content": [{"type": "tool_use", "name": "Agent", "input": {}}]
            },
        }
        f = tmp_path / "session.jsonl"
        f.write_text(json.dumps(obj) + "\n", encoding="utf-8")
        edges = _extract_delegation_edges(f)
        assert len(edges) == 1
        assert edges[0]["source"] == "main"
        assert edges[0]["target"] == "agent_1"

    def test_null_input_uses_synthetic_id(self, tmp_path):
        """Agent call with null input is handled."""
        obj = {
            "type": "assistant",
            "message": {
                "content": [{"type": "tool_use", "name": "Agent", "input": None}]
            },
        }
        f = tmp_path / "session.jsonl"
        f.write_text(json.dumps(obj) + "\n", encoding="utf-8")
        edges = _extract_delegation_edges(f)
        assert len(edges) == 1

    def test_multiple_tool_uses_in_one_message(self, tmp_path):
        """Multiple Agent calls in one assistant message are all captured."""
        line = _make_multi_tool_line([
            ("Agent", {"resume": "sub-a"}),
            ("Bash", {"command": "ls"}),
            ("Agent", {"resume": "sub-b"}),
        ])
        f = _write_jsonl(tmp_path, [line])
        edges = _extract_delegation_edges(f)
        targets = {e["target"] for e in edges}
        assert targets == {"sub-a", "sub-b"}
        assert len(edges) == 2
