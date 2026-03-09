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
    _parse_agent_graph,
    _parse_main_agent_metadata,
)
from backend.schemas import TaskGraphResponse, TaskMetadataResponse

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
