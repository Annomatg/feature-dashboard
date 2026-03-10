"""
Task-related HTTP endpoints router.

Provides endpoints for accessing task-specific data like agent graphs.
"""

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
)
from backend.schemas import TaskGraphResponse, TaskMetadataResponse, TaskSubagentsResponse, SubagentLogEntry, SessionLogResponse, SessionLogEntry

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("/{task_id}/graph", response_model=TaskGraphResponse)
async def get_task_graph(task_id: int):
    """Get the agent graph for a task session.

    Returns a graph JSON object with {nodes: [...], edges: [...]} representing
    the main agent and all its subagents for a given task session.

    Args:
        task_id: The feature/task ID to get the graph for

    Returns:
        TaskGraphResponse with nodes and edges

    Raises:
        404: If task not found or no session file available
    """
    session = get_session()
    try:
        feature = session.query(Feature).filter(Feature.id == task_id).first()

        if feature is None:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        # Check if the feature has a session ID
        if not feature.claude_session_id:
            raise HTTPException(
                status_code=404,
                detail=f"No session file available for task {task_id}"
            )

        # Validate session ID format to prevent path traversal
        session_id = feature.claude_session_id
        if '/' in session_id or '\\' in session_id or not session_id.endswith('.jsonl'):
            raise HTTPException(
                status_code=400,
                detail="Invalid session ID format"
            )

        # Get the Claude projects directory
        working_dir = str(_deps._current_db_path.parent)
        projects_dir = _get_claude_projects_dir(working_dir)

        if projects_dir is None:
            raise HTTPException(
                status_code=404,
                detail="Claude projects directory not found"
            )

        # Find the session file
        session_file = projects_dir / feature.claude_session_id
        if not session_file.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Session file not found: {feature.claude_session_id}"
            )

        # Parse the agent graph
        try:
            graph = _parse_agent_graph(session_file)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to parse session file: {str(e)}"
            )

        return TaskGraphResponse(
            nodes=graph["nodes"],
            edges=graph["edges"],
        )
    finally:
        session.close()


@router.get("/{task_id}/metadata", response_model=TaskMetadataResponse)
async def get_task_metadata(task_id: int):
    """Get metadata for a task session.

    Returns metadata about the main agent session including:
    - turn_count: number of turns (user + assistant messages)
    - token_estimate: rough token count estimated from character lengths
    - last_tool_used: name of the last tool_use block, or None
    - agent_type: extracted from filename or first system message

    Args:
        task_id: The feature/task ID to get metadata for

    Returns:
        TaskMetadataResponse with metadata fields

    Raises:
        404: If task not found or no session file available
    """
    session = get_session()
    try:
        feature = session.query(Feature).filter(Feature.id == task_id).first()

        if feature is None:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        # Check if the feature has a session ID
        if not feature.claude_session_id:
            raise HTTPException(
                status_code=404,
                detail=f"No session file available for task {task_id}"
            )

        # Validate session ID format to prevent path traversal
        session_id = feature.claude_session_id
        if '/' in session_id or '\\' in session_id or not session_id.endswith('.jsonl'):
            raise HTTPException(
                status_code=400,
                detail="Invalid session ID format"
            )

        # Get the Claude projects directory
        working_dir = str(_deps._current_db_path.parent)
        projects_dir = _get_claude_projects_dir(working_dir)

        if projects_dir is None:
            raise HTTPException(
                status_code=404,
                detail="Claude projects directory not found"
            )

        # Find the session file
        session_file = projects_dir / feature.claude_session_id
        if not session_file.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Session file not found: {feature.claude_session_id}"
            )

        # Parse the metadata
        try:
            metadata = _parse_main_agent_metadata(session_file)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to parse session file: {str(e)}"
            )

        return TaskMetadataResponse(
            turn_count=metadata["turn_count"],
            token_estimate=metadata["token_estimate"],
            last_tool_used=metadata["last_tool_used"],
            agent_type=metadata["agent_type"],
        )
    finally:
        session.close()


@router.get("/{task_id}/subagents", response_model=TaskSubagentsResponse)
async def get_task_subagents(task_id: int):
    """Discover subagent log files for a task session.

    Returns a list of subagent log files found under the session's
    subagents/ subdirectory.  Returns an empty list when the directory
    does not exist (task ran without subagents).

    Args:
        task_id: The feature/task ID to discover subagents for

    Returns:
        TaskSubagentsResponse with a list of {agent_id, file_path} records

    Raises:
        404: If task not found, no session file, or Claude projects dir missing
        400: If session ID format is invalid
    """
    session = get_session()
    try:
        feature = session.query(Feature).filter(Feature.id == task_id).first()

        if feature is None:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        if not feature.claude_session_id:
            raise HTTPException(
                status_code=404,
                detail=f"No session file available for task {task_id}"
            )

        # Validate session ID format to prevent path traversal
        session_id = feature.claude_session_id
        if '/' in session_id or '\\' in session_id or not session_id.endswith('.jsonl'):
            raise HTTPException(
                status_code=400,
                detail="Invalid session ID format"
            )

        working_dir = str(_deps._current_db_path.parent)
        projects_dir = _get_claude_projects_dir(working_dir)

        if projects_dir is None:
            raise HTTPException(
                status_code=404,
                detail="Claude projects directory not found"
            )

        subagents = _discover_subagent_logs(projects_dir, session_id)
        return TaskSubagentsResponse(
            subagents=[SubagentLogEntry(**s) for s in subagents]
        )
    finally:
        session.close()


@router.get("/{task_id}/node-log/{node_id}", response_model=SessionLogResponse)
async def get_task_node_log(task_id: int, node_id: str, limit: int = 50):
    """Get session log entries for a specific node (agent) in the task graph.

    For the main agent (node_id == "main"), reads the feature's own session file.
    For subagent nodes, looks up the corresponding subagent log file by agent_id.

    Args:
        task_id: The feature/task ID
        node_id: The node ID from the graph — "main" or a subagent ID
        limit: Max entries to return (1–200, default 50)

    Returns:
        SessionLogResponse with log entries for the selected node

    Raises:
        404: If task not found, no session file, or node_id not found
        400: If session ID format is invalid
    """
    db_session = get_session()
    try:
        feature = db_session.query(Feature).filter(Feature.id == task_id).first()

        if feature is None:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        if not feature.claude_session_id:
            raise HTTPException(
                status_code=404,
                detail=f"No session file available for task {task_id}"
            )

        session_id = feature.claude_session_id
        if '/' in session_id or '\\' in session_id or not session_id.endswith('.jsonl'):
            raise HTTPException(status_code=400, detail="Invalid session ID format")

        working_dir = str(_deps._current_db_path.parent)
        projects_dir = _get_claude_projects_dir(working_dir)

        if projects_dir is None:
            raise HTTPException(
                status_code=404,
                detail="Claude projects directory not found"
            )

        clamped_limit = max(1, min(limit, 200))

        if node_id == "main":
            session_file = projects_dir / session_id
            if not session_file.exists():
                raise HTTPException(
                    status_code=404,
                    detail=f"Session file not found: {session_id}"
                )
            entries = _parse_jsonl_log(session_file, limit=clamped_limit)
            return SessionLogResponse(
                active=False,
                feature_id=task_id,
                session_file=session_id,
                entries=[SessionLogEntry(**e) for e in entries],
                total_entries=len(entries),
            )

        # Subagent node — find the matching log file
        subagents = _discover_subagent_logs(projects_dir, session_id)
        match = next((s for s in subagents if s["agent_id"] == node_id), None)

        if match is None:
            raise HTTPException(
                status_code=404,
                detail=f"Node '{node_id}' not found for task {task_id}"
            )

        subagent_file = Path(match["file_path"])
        if not subagent_file.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Subagent log file not found for node '{node_id}'"
            )

        entries = _parse_jsonl_log(subagent_file, limit=clamped_limit)
        return SessionLogResponse(
            active=False,
            feature_id=task_id,
            session_file=subagent_file.name,
            entries=[SessionLogEntry(**e) for e in entries],
            total_entries=len(entries),
        )
    finally:
        db_session.close()
