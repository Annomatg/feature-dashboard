"""
Task-related HTTP endpoints router.

Provides endpoints for accessing task-specific data like agent graphs and logs.
"""

import re
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import backend.deps as _deps
from backend.deps import get_session
from api.database import Feature
from backend.claude_process import (
    _get_claude_projects_dir,
    _discover_subagent_logs,
    _parse_agent_graph,
    _parse_main_agent_metadata,
    _parse_jsonl_log,
    _parse_agent_turns,
)
from backend.schemas import (
    TaskGraphResponse,
    TaskMetadataResponse,
    TaskSubagentsResponse,
    SubagentLogEntry,
    SessionLogResponse,
    SessionLogEntry,
    AgentTurn,
    AgentTurnsResponse,
)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

# Strict allowlist: alphanumeric, hyphens, underscores, dots — no path components.
_SAFE_SESSION_RE = re.compile(r'^[a-zA-Z0-9_\-.]+\.jsonl$')
_SAFE_AGENT_RE = re.compile(r'^[a-zA-Z0-9_\-.]+$')


def _validate_session_id(session_id: str) -> None:
    """Raise HTTPException(400) if session_id is not safe to use as a filename.

    Enforces a strict allowlist AND checks that Path(session_id).name == session_id
    to catch any directory component that might survive URL decoding or encoding tricks.
    """
    if not _SAFE_SESSION_RE.match(session_id) or Path(session_id).name != session_id:
        raise HTTPException(status_code=400, detail="Invalid session ID format")


def _validate_agent_id(agent_id: str) -> None:
    """Raise HTTPException(400) if agent_id contains unsafe characters.

    'main' is always accepted. Other values must match the strict allowlist
    (alphanumeric, hyphens, underscores, dots — no path separators or null bytes).
    """
    if agent_id != "main" and not _SAFE_AGENT_RE.match(agent_id):
        raise HTTPException(status_code=400, detail="Invalid agent ID format")


# ---------------------------------------------------------------------------
# Resolution helpers
# ---------------------------------------------------------------------------

def _resolve_session_context(task_id: int, db_session) -> tuple[str, Path]:
    """Look up the task, validate its session ID, and resolve the projects dir.

    Returns:
        (session_id, projects_dir)

    Raises:
        HTTPException 404: task not found, no session ID, or projects dir missing
        HTTPException 400: session ID fails validation
    """
    feature = db_session.query(Feature).filter(Feature.id == task_id).first()

    if feature is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    if not feature.claude_session_id:
        raise HTTPException(
            status_code=404,
            detail=f"No session file available for task {task_id}",
        )

    session_id = feature.claude_session_id
    _validate_session_id(session_id)

    working_dir = str(_deps._current_db_path.parent)
    projects_dir = _get_claude_projects_dir(working_dir)

    if projects_dir is None:
        raise HTTPException(
            status_code=404,
            detail="Claude projects directory not found",
        )

    return session_id, projects_dir


def _resolve_main_file(session_id: str, projects_dir: Path) -> Path:
    """Return the main session file path or raise HTTPException(404)."""
    session_file = projects_dir / session_id
    if not session_file.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Session file not found: {session_id}",
        )
    return session_file


def _resolve_subagent_file(agent_id: str, session_id: str, projects_dir: Path) -> Path:
    """Look up a subagent log file by agent_id or raise HTTPException(404)."""
    subagents = _discover_subagent_logs(projects_dir, session_id)
    match = next((s for s in subagents if s["agent_id"] == agent_id), None)

    if match is None:
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{agent_id}' not found for this task",
        )

    subagent_file = Path(match["file_path"])
    if not subagent_file.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Subagent log file not found for agent '{agent_id}'",
        )

    return subagent_file


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/{task_id}/graph", response_model=TaskGraphResponse)
async def get_task_graph(task_id: int):
    """Get the agent graph for a task session.

    Returns a graph JSON object with {nodes: [...], edges: [...]} representing
    the main agent and all its subagents for a given task session.

    Raises:
        404: If task not found or no session file available
        400: If session ID format is invalid
        500: If the session file cannot be parsed
    """
    db_session = get_session()
    try:
        session_id, projects_dir = _resolve_session_context(task_id, db_session)
        session_file = _resolve_main_file(session_id, projects_dir)

        try:
            graph = _parse_agent_graph(session_file)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to parse session file: {str(e)}",
            )

        return TaskGraphResponse(nodes=graph["nodes"], edges=graph["edges"])
    finally:
        db_session.close()


@router.get("/{task_id}/metadata", response_model=TaskMetadataResponse)
async def get_task_metadata(task_id: int):
    """Get metadata for a task session.

    Returns turn_count, token_estimate, last_tool_used, and agent_type.

    Raises:
        404: If task not found or no session file available
        400: If session ID format is invalid
        500: If the session file cannot be parsed
    """
    db_session = get_session()
    try:
        session_id, projects_dir = _resolve_session_context(task_id, db_session)
        session_file = _resolve_main_file(session_id, projects_dir)

        try:
            metadata = _parse_main_agent_metadata(session_file)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to parse session file: {str(e)}",
            )

        return TaskMetadataResponse(
            turn_count=metadata["turn_count"],
            token_estimate=metadata["token_estimate"],
            last_tool_used=metadata["last_tool_used"],
            agent_type=metadata["agent_type"],
        )
    finally:
        db_session.close()


@router.get("/{task_id}/subagents", response_model=TaskSubagentsResponse)
async def get_task_subagents(task_id: int):
    """Discover subagent log files for a task session.

    Returns a list of subagent log files found under the session's
    subagents/ subdirectory. Returns an empty list when the directory
    does not exist (task ran without subagents).

    Raises:
        404: If task not found, no session file, or Claude projects dir missing
        400: If session ID format is invalid
    """
    db_session = get_session()
    try:
        session_id, projects_dir = _resolve_session_context(task_id, db_session)
        subagents = _discover_subagent_logs(projects_dir, session_id)
        return TaskSubagentsResponse(subagents=[SubagentLogEntry(**s) for s in subagents])
    finally:
        db_session.close()


@router.get("/{task_id}/node-log/{node_id}", response_model=SessionLogResponse)
async def get_task_node_log(task_id: int, node_id: str, limit: int = 50):
    """Get session log entries for a specific node (agent) in the task graph.

    For the main agent (node_id == "main"), reads the feature's own session file.
    For subagent nodes, looks up the corresponding subagent log file by agent_id.

    Args:
        task_id: The feature/task ID
        node_id: The node ID from the graph — "main" or a subagent ID
        limit: Max entries to return (1–200, default 50)

    Raises:
        404: If task not found, no session file, or node_id not found
        400: If session ID or node_id format is invalid
    """
    _validate_agent_id(node_id)
    db_session = get_session()
    try:
        session_id, projects_dir = _resolve_session_context(task_id, db_session)
        clamped_limit = max(1, min(limit, 200))

        if node_id == "main":
            log_file = _resolve_main_file(session_id, projects_dir)
            file_name = session_id
        else:
            log_file = _resolve_subagent_file(node_id, session_id, projects_dir)
            file_name = log_file.name

        entries = _parse_jsonl_log(log_file, limit=clamped_limit)
        return SessionLogResponse(
            active=False,
            feature_id=task_id,
            session_file=file_name,
            entries=[SessionLogEntry(**e) for e in entries],
            total_entries=len(entries),
        )
    finally:
        db_session.close()


@router.get("/{task_id}/agent/{agent_id}/log", response_model=AgentTurnsResponse)
async def get_agent_log(task_id: int, agent_id: str, limit: int = 50):
    """Get structured turn cards (role + content) for a specific agent in the task graph.

    Returns each conversation turn (user/assistant/system) as a card with role
    and human-readable content text extracted from the JSONL message.

    For the main agent (agent_id == "main"), reads the feature's own session file.
    For subagent nodes, looks up the corresponding subagent log file by agent_id.

    Args:
        task_id: The feature/task ID
        agent_id: The agent ID — "main" or a subagent UUID/ID
        limit: Max turns to return (1–200, default 50)

    Raises:
        404: If task not found, no session file, or agent_id not found
        400: If session ID or agent_id format is invalid
    """
    _validate_agent_id(agent_id)
    db_session = get_session()
    try:
        session_id, projects_dir = _resolve_session_context(task_id, db_session)
        clamped_limit = max(1, min(limit, 200))

        if agent_id == "main":
            log_file = _resolve_main_file(session_id, projects_dir)
        else:
            log_file = _resolve_subagent_file(agent_id, session_id, projects_dir)

        turns = _parse_agent_turns(log_file, limit=clamped_limit)
        return AgentTurnsResponse(
            turns=[AgentTurn(**t) for t in turns],
            total_turns=len(turns),
        )
    finally:
        db_session.close()
