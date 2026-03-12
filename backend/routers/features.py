"""
Feature CRUD endpoints router.
"""

import asyncio
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import text as sa_text

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from api.database import (
    CategoryToken,
    DescriptionBigram,
    DescriptionToken,
    Feature,
    NameBigram,
    NameToken,
)
from api.tokens import extract_bigrams, normalize_tokens
import backend.deps as _deps
from backend.deps import (
    get_session,
    get_commit_counts,
    feature_to_response,
    _feature_subscribers,
)
import backend.autopilot_engine as _autopilot_engine
from backend.routers.push import send_push_to_all as _send_push_to_all
from backend.claude_process import _get_claude_projects_dir, _parse_jsonl_log
from backend.schemas import (
    ClaudeLogLineResponse,
    ClaudeLogResponse,
    CreateFeatureRequest,
    FeatureResponse,
    MoveFeatureRequest,
    PaginatedFeaturesResponse,
    ReorderFeatureRequest,
    SessionLogEntry,
    SessionLogResponse,
    StatsResponse,
    UpdateFeaturePriorityRequest,
    UpdateFeatureRequest,
    UpdateFeatureStateRequest,
)

router = APIRouter(prefix="/api", tags=["features"])

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Set of valid model shorthand names accepted by feature create/update.
VALID_MODELS = {"opus", "sonnet", "haiku"}

# Gap between adjacent feature priorities. Clean multiples of 100 give plenty
# of room for future insertions without normalisation collisions.
_PRIORITY_STEP = 100

# Heartbeat interval for the feature SSE stream (seconds).
# Override in tests to avoid long waits.
_FEATURE_SSE_HEARTBEAT_SECONDS: float = 15.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_lane_priorities(features_in_order: list) -> None:
    """Assign clean sequential priorities (100, 200, 300, ...) to features in order.

    Normalising the whole lane on every move/reorder keeps priorities distinct
    and well-spaced so that subsequent swaps never produce conflicts.
    """
    for i, f in enumerate(features_in_order, start=1):
        f.priority = i * _PRIORITY_STEP


async def _broadcast_feature_event(event: dict) -> None:
    """Push an event dict to every connected /api/features/stream subscriber."""
    for q in list(_feature_subscribers):
        await q.put(event)


# ---------------------------------------------------------------------------
# Feature list and stats
# ---------------------------------------------------------------------------

@router.get("/features")
async def get_features(
    passes: Optional[bool] = None,
    in_progress: Optional[bool] = None,
    category: Optional[str] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None
):
    """
    Get all features with optional filters and pagination.

    Query parameters:
    - passes: Filter by passing status (true/false)
    - in_progress: Filter by in-progress status (true/false)
    - category: Filter by category name
    - limit: Maximum number of features to return (pagination)
    - offset: Number of features to skip (pagination)

    Returns:
    - If limit is provided: PaginatedFeaturesResponse with metadata
    - Otherwise: list[FeatureResponse] (backward compatible)
    """
    session = get_session()
    try:
        query = session.query(Feature)

        if passes is not None:
            query = query.filter(Feature.passes == passes)

        if in_progress is not None:
            query = query.filter(Feature.in_progress == in_progress)

        if category is not None:
            query = query.filter(Feature.category == category)

        # Order by completed_at DESC for done features (passes=true), otherwise by priority
        if passes is True:
            query = query.order_by(Feature.completed_at.desc().nulls_last())
        else:
            query = query.order_by(Feature.priority.asc())

        # If pagination parameters provided, return paginated response
        if limit is not None:
            # Get total count before pagination
            total = query.count()

            # Apply pagination with default limit of 20 for done features
            actual_limit = limit if limit > 0 else 20
            actual_offset = offset if offset is not None else 0

            features = query.limit(actual_limit).offset(actual_offset).all()
            fids = [f.id for f in features]
            commits = get_commit_counts(session, fids)

            return PaginatedFeaturesResponse(
                features=[feature_to_response(f, commits) for f in features],
                total=total,
                limit=actual_limit,
                offset=actual_offset
            )

        # Otherwise return simple list (backward compatible)
        features = query.all()
        fids = [f.id for f in features]
        commits = get_commit_counts(session, fids)
        return [feature_to_response(f, commits) for f in features]
    finally:
        session.close()


@router.get("/features/stats", response_model=StatsResponse)
async def get_stats():
    """Get feature statistics."""
    session = get_session()
    try:
        total = session.query(Feature).count()
        passing = session.query(Feature).filter(Feature.passes == True).count()
        in_progress = session.query(Feature).filter(Feature.in_progress == True).count()
        percentage = round((passing / total) * 100, 1) if total > 0 else 0.0

        return StatsResponse(
            passing=passing,
            in_progress=in_progress,
            total=total,
            percentage=percentage
        )
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Autocomplete endpoints
# ---------------------------------------------------------------------------

@router.get("/autocomplete/name")
def get_autocomplete_name(
    prefix: str = Query(default="", max_length=100),
    prev: str = Query(default="", max_length=100),
):
    """Return up to 5 name token suggestions matching the given prefix.

    When prev is provided (the last fully-typed word before the cursor), uses
    bigram context to suggest the next word — no minimum prefix length required.
    Each suggestion may itself be followed by a second predicted word (two-word
    suggestion) derived from the bigram table.

    When prev is not provided, falls back to token-prefix matching with a
    minimum prefix length of 3 characters.
    Results are ordered by usage_count descending.
    """
    session = get_session()
    try:
        if prev:
            # Context-aware: suggest next words after 'prev' using bigrams.
            # Also look up a second predicted word for each candidate.
            rows = session.execute(sa_text("""
                SELECT b.word2,
                       (SELECT b2.word2 FROM name_bigrams b2
                        WHERE b2.word1 = b.word2
                        ORDER BY b2.usage_count DESC LIMIT 1) as next_word
                FROM name_bigrams b
                WHERE b.word1 = :prev
                  AND (:prefix = '' OR b.word2 LIKE :prefix_like)
                ORDER BY b.usage_count DESC
                LIMIT 5
            """), {"prev": prev.lower(), "prefix": prefix.lower(),
                   "prefix_like": f"{prefix.lower()}%"}).fetchall()
            suggestions = [
                f"{row[0]} {row[1]}" if row[1] else row[0]
                for row in rows
            ]
            return {"suggestions": suggestions}

        if len(prefix) < 3:
            return {"suggestions": []}

        rows = session.execute(sa_text("""
            SELECT t.token,
                   (SELECT b.word2 FROM name_bigrams b
                    WHERE b.word1 = t.token
                    ORDER BY b.usage_count DESC LIMIT 1) as next_word
            FROM name_tokens t
            WHERE t.token LIKE :prefix
            ORDER BY t.usage_count DESC
            LIMIT 5
        """), {"prefix": f"{prefix}%"}).fetchall()
        suggestions = [
            f"{row[0]} {row[1]}" if row[1] else row[0]
            for row in rows
        ]
        return {"suggestions": suggestions}
    finally:
        session.close()


@router.get("/autocomplete/description")
def get_autocomplete_description(
    prefix: str = Query(default="", max_length=100),
    prev: str = Query(default="", max_length=100),
):
    """Return up to 5 description token suggestions matching the given prefix.

    When prev is provided (the last fully-typed word before the cursor), uses
    bigram context to suggest the next word — no minimum prefix length required.
    Each suggestion may itself be followed by a second predicted word (two-word
    suggestion) derived from the bigram table.

    When prev is not provided, falls back to token-prefix matching with a
    minimum prefix length of 3 characters.
    Results are ordered by usage_count descending.
    """
    session = get_session()
    try:
        if prev:
            rows = session.execute(sa_text("""
                SELECT b.word2,
                       (SELECT b2.word2 FROM description_bigrams b2
                        WHERE b2.word1 = b.word2
                        ORDER BY b2.usage_count DESC LIMIT 1) as next_word
                FROM description_bigrams b
                WHERE b.word1 = :prev
                  AND (:prefix = '' OR b.word2 LIKE :prefix_like)
                ORDER BY b.usage_count DESC
                LIMIT 5
            """), {"prev": prev.lower(), "prefix": prefix.lower(),
                   "prefix_like": f"{prefix.lower()}%"}).fetchall()
            suggestions = [
                f"{row[0]} {row[1]}" if row[1] else row[0]
                for row in rows
            ]
            return {"suggestions": suggestions}

        if len(prefix) < 3:
            return {"suggestions": []}

        rows = session.execute(sa_text("""
            SELECT t.token,
                   (SELECT b.word2 FROM description_bigrams b
                    WHERE b.word1 = t.token
                    ORDER BY b.usage_count DESC LIMIT 1) as next_word
            FROM description_tokens t
            WHERE t.token LIKE :prefix
            ORDER BY t.usage_count DESC
            LIMIT 5
        """), {"prefix": f"{prefix}%"}).fetchall()
        suggestions = [
            f"{row[0]} {row[1]}" if row[1] else row[0]
            for row in rows
        ]
        return {"suggestions": suggestions}
    finally:
        session.close()


@router.get("/autocomplete/category")
def get_autocomplete_category(prefix: str = ""):
    """Return up to 5 category token suggestions matching the given prefix.

    Returns an empty suggestion list if the prefix is shorter than 3 characters.
    Results are ordered by usage_count descending.
    """
    if len(prefix) < 3:
        return {"suggestions": []}

    session = get_session()
    try:
        rows = (
            session.query(CategoryToken.token)
            .filter(CategoryToken.token.like(f"{prefix}%"))
            .order_by(CategoryToken.usage_count.desc())
            .limit(5)
            .all()
        )
        return {"suggestions": [row.token for row in rows]}
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Feature SSE stream
# ---------------------------------------------------------------------------

@router.get("/features/stream")
async def feature_stream():
    """
    SSE endpoint for real-time board refresh notifications.

    The browser subscribes here once on page load.  Events pushed:
      - feature_created: when a new feature is created (e.g. via the interview skill)
      - heartbeat:       every 15 s to keep the connection alive through proxies

    On disconnect the subscriber queue is automatically removed.
    """
    queue: asyncio.Queue = asyncio.Queue()
    _feature_subscribers.append(queue)

    async def event_generator():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=_FEATURE_SSE_HEARTBEAT_SECONDS)
                except asyncio.TimeoutError:
                    yield "event: heartbeat\ndata: {}\n\n"
                    continue

                if event["type"] == "feature_created":
                    yield (
                        f"event: feature_created\n"
                        f"data: {json.dumps({'id': event.get('id'), 'name': event.get('name')})}\n\n"
                    )
        finally:
            try:
                _feature_subscribers.remove(queue)
            except ValueError:
                pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/features/notify", status_code=200)
async def notify_feature_created(feature_id: int, name: str):
    """
    Broadcast a feature_created event to all /api/features/stream subscribers.

    Called by the interview skill after feature_create MCP tool succeeds,
    so the board refreshes immediately without waiting for the 5-second poll.
    """
    await _broadcast_feature_event({"type": "feature_created", "id": feature_id, "name": name})
    return {"status": "notified", "subscribers": len(_feature_subscribers)}


# ---------------------------------------------------------------------------
# Debug endpoint
# ---------------------------------------------------------------------------

@router.get("/debug/features/{feature_id}")
async def get_feature_raw(feature_id: int):
    """Get raw feature dict for debugging."""
    session = get_session()
    try:
        feature = session.query(Feature).filter(Feature.id == feature_id).first()

        if feature is None:
            raise HTTPException(status_code=404, detail=f"Feature {feature_id} not found")

        return feature.to_dict()
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Single feature read
# ---------------------------------------------------------------------------

@router.get("/features/{feature_id}", response_model=FeatureResponse, response_model_exclude_none=False)
async def get_feature(feature_id: int):
    """Get a single feature by ID."""
    session = get_session()
    try:
        feature = session.query(Feature).filter(Feature.id == feature_id).first()

        if feature is None:
            raise HTTPException(status_code=404, detail=f"Feature {feature_id} not found")

        commits = get_commit_counts(session, [feature_id])
        return feature_to_response(feature, commits)
    finally:
        session.close()


@router.get("/features/{feature_id}/claude-log", response_model=ClaudeLogResponse)
async def get_claude_log(feature_id: int, limit: int = 10, stream: str = "all"):
    """Get the last N lines of Claude process output for a feature.

    Returns 404 if no log buffer exists for the feature (process never started
    or has already exited and been cleaned up).  Returns 200 with an empty
    ``lines`` list if the process started but has not yet produced output.

    Query params:
    - limit: number of lines to return, clamped to 1–500 (default 10)
    - stream: 'stdout' | 'stderr' | 'all' (default 'all')
    """
    if feature_id not in _autopilot_engine._claude_process_logs:
        raise HTTPException(status_code=404, detail=f"No Claude log found for feature {feature_id}")

    log = _autopilot_engine._claude_process_logs[feature_id]
    all_lines = list(log.lines)

    if stream != "all":
        all_lines = [ln for ln in all_lines if ln.stream == stream]

    total = len(all_lines)
    clamped_limit = max(1, min(limit, 500))
    selected = all_lines[-clamped_limit:] if all_lines else []

    return ClaudeLogResponse(
        feature_id=feature_id,
        active=feature_id in _autopilot_engine._claude_process_logs,
        lines=[
            ClaudeLogLineResponse(timestamp=ln.timestamp, stream=ln.stream, text=ln.text)
            for ln in selected
        ],
        total_lines=total,
    )


# ---------------------------------------------------------------------------
# Feature create / update / delete
# ---------------------------------------------------------------------------

@router.post("/features", response_model=FeatureResponse, status_code=201)
async def create_feature(request: CreateFeatureRequest):
    """
    Create a new feature.

    Automatically assigns priority as max(existing_priorities) + 1.
    Sets passes=False and in_progress=False by default.
    """
    session = get_session()
    try:
        # Append after the current highest priority among active (non-passing) features
        max_priority = session.query(Feature.priority).filter(Feature.passes == False).order_by(Feature.priority.desc()).first()
        next_priority = (max_priority[0] + _PRIORITY_STEP) if max_priority else _PRIORITY_STEP

        # Validate model if provided
        if request.model is not None and request.model not in VALID_MODELS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid model '{request.model}'. Must be one of: {', '.join(sorted(VALID_MODELS))}"
            )

        # Create new feature
        new_feature = Feature(
            priority=next_priority,
            category=request.category,
            name=request.name,
            description=request.description,
            steps=request.steps,
            passes=False,
            in_progress=False,
            model=request.model or "sonnet",
        )

        session.add(new_feature)
        session.commit()
        session.refresh(new_feature)

        # Upsert name_tokens for each token in the new feature's name
        for token in set(normalize_tokens(new_feature.name)):
            existing = session.query(NameToken).filter(NameToken.token == token).first()
            if existing:
                existing.usage_count += 1
            else:
                session.add(NameToken(token=token, usage_count=1))

        # Upsert name_bigrams for consecutive word pairs in the new feature's name
        for (word1, word2), count in Counter(extract_bigrams(new_feature.name)).items():
            existing = session.query(NameBigram).filter(
                NameBigram.word1 == word1, NameBigram.word2 == word2
            ).first()
            if existing:
                existing.usage_count += count
            else:
                session.add(NameBigram(word1=word1, word2=word2, usage_count=count))

        # Upsert description_tokens for each token in the new feature's description
        for token in set(normalize_tokens(new_feature.description)):
            existing = session.query(DescriptionToken).filter(DescriptionToken.token == token).first()
            if existing:
                existing.usage_count += 1
            else:
                session.add(DescriptionToken(token=token, usage_count=1))

        # Upsert description_bigrams for consecutive word pairs in the new feature's description
        for (word1, word2), count in Counter(extract_bigrams(new_feature.description)).items():
            existing = session.query(DescriptionBigram).filter(
                DescriptionBigram.word1 == word1, DescriptionBigram.word2 == word2
            ).first()
            if existing:
                existing.usage_count += count
            else:
                session.add(DescriptionBigram(word1=word1, word2=word2, usage_count=count))

        # Upsert category_tokens for each token in the new feature's category
        for token in set(normalize_tokens(new_feature.category)):
            existing = session.query(CategoryToken).filter(CategoryToken.token == token).first()
            if existing:
                existing.usage_count += 1
            else:
                session.add(CategoryToken(token=token, usage_count=1))
        session.commit()

        return feature_to_response(new_feature)
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create feature: {str(e)}")
    finally:
        session.close()


@router.put("/features/{feature_id}", response_model=FeatureResponse)
async def update_feature(feature_id: int, request: UpdateFeatureRequest):
    """
    Update feature fields.

    Only updates fields that are provided in the request.
    Automatically updates modified_at timestamp.
    """
    session = get_session()
    try:
        feature = session.query(Feature).filter(Feature.id == feature_id).first()

        if feature is None:
            raise HTTPException(status_code=404, detail=f"Feature {feature_id} not found")

        # Update only provided fields
        if request.category is not None:
            feature.category = request.category
        if request.name is not None:
            feature.name = request.name
        if request.description is not None:
            feature.description = request.description
        if request.steps is not None:
            feature.steps = request.steps
        if request.model is not None:
            if request.model not in VALID_MODELS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid model '{request.model}'. Must be one of: {', '.join(sorted(VALID_MODELS))}"
                )
            feature.model = request.model

        session.commit()
        session.refresh(feature)

        # Upsert name_tokens if name was updated (append-only, no decrement)
        if request.name is not None:
            for token in set(normalize_tokens(feature.name)):
                existing = session.query(NameToken).filter(NameToken.token == token).first()
                if existing:
                    existing.usage_count += 1
                else:
                    session.add(NameToken(token=token, usage_count=1))
            for (word1, word2), count in Counter(extract_bigrams(feature.name)).items():
                existing = session.query(NameBigram).filter(
                    NameBigram.word1 == word1, NameBigram.word2 == word2
                ).first()
                if existing:
                    existing.usage_count += count
                else:
                    session.add(NameBigram(word1=word1, word2=word2, usage_count=count))
            session.commit()

        # Upsert description_tokens if description was updated (append-only, no decrement)
        if request.description is not None:
            for token in set(normalize_tokens(feature.description)):
                existing = session.query(DescriptionToken).filter(DescriptionToken.token == token).first()
                if existing:
                    existing.usage_count += 1
                else:
                    session.add(DescriptionToken(token=token, usage_count=1))
            for (word1, word2), count in Counter(extract_bigrams(feature.description)).items():
                existing = session.query(DescriptionBigram).filter(
                    DescriptionBigram.word1 == word1, DescriptionBigram.word2 == word2
                ).first()
                if existing:
                    existing.usage_count += count
                else:
                    session.add(DescriptionBigram(word1=word1, word2=word2, usage_count=count))
            session.commit()

        # Upsert category_tokens if category was updated (append-only, no decrement)
        if request.category is not None:
            for token in set(normalize_tokens(feature.category)):
                existing = session.query(CategoryToken).filter(CategoryToken.token == token).first()
                if existing:
                    existing.usage_count += 1
                else:
                    session.add(CategoryToken(token=token, usage_count=1))
            session.commit()

        return feature_to_response(feature, get_commit_counts(session, [feature.id]))
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update feature: {str(e)}")
    finally:
        session.close()


@router.delete("/features/{feature_id}", status_code=204)
async def delete_feature(feature_id: int):
    """
    Delete a feature permanently.

    Returns 204 No Content on success.
    """
    session = get_session()
    try:
        feature = session.query(Feature).filter(Feature.id == feature_id).first()

        if feature is None:
            raise HTTPException(status_code=404, detail=f"Feature {feature_id} not found")

        session.delete(feature)
        session.commit()

        return None
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete feature: {str(e)}")
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Feature state and priority mutations
# ---------------------------------------------------------------------------

@router.patch("/features/{feature_id}/state", response_model=FeatureResponse)
async def update_feature_state(feature_id: int, request: UpdateFeatureStateRequest, background_tasks: BackgroundTasks):
    """
    Update feature state (passes/in_progress).

    This is used to move features between lanes (TODO, In Progress, Done).
    When setting passes=True, sets completed_at timestamp and sends a push notification.
    When setting passes=False, clears completed_at timestamp.
    """
    session = get_session()
    try:
        feature = session.query(Feature).filter(Feature.id == feature_id).first()

        if feature is None:
            raise HTTPException(status_code=404, detail=f"Feature {feature_id} not found")

        newly_passing = request.passes is True and not feature.passes

        # Update state fields
        if request.passes is not None:
            feature.passes = request.passes
            # Set/clear completed_at based on passes status
            if request.passes:
                feature.completed_at = datetime.now()
            else:
                feature.completed_at = None

        if request.in_progress is not None:
            feature.in_progress = request.in_progress

        if request.claude_session_id is not None:
            feature.claude_session_id = request.claude_session_id

        session.commit()
        session.refresh(feature)

        if newly_passing:
            push_payload = {
                "title": "Feature Done",
                "body": f"#{feature.id}: {feature.name}",
                "tag": "feature-done",
                "url": "/",
            }
            background_tasks.add_task(_send_push_to_all, push_payload)

        return feature_to_response(feature, get_commit_counts(session, [feature.id]))
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update feature state: {str(e)}")
    finally:
        session.close()


@router.get("/features/{feature_id}/session-log", response_model=SessionLogResponse)
async def get_feature_session_log(feature_id: int, limit: int = 50):
    """Get log entries from the stored Claude JSONL session file for a specific feature.

    Reads the JSONL file identified by the feature's claude_session_id field.
    Returns log entries even when the feature is no longer in-progress, allowing
    users to review Claude's work history for completed and TODO tasks.

    Query params:
    - limit: number of entries to return (1–200, default 50)
    """
    session = get_session()
    try:
        feature = session.query(Feature).filter(Feature.id == feature_id).first()

        if feature is None:
            raise HTTPException(status_code=404, detail=f"Feature {feature_id} not found")

        session_filename = feature.claude_session_id
        if not session_filename:
            return SessionLogResponse(
                active=False, feature_id=feature_id, session_file=None,
                entries=[], total_entries=0,
            )

        working_dir = str(_deps._current_db_path.parent)
        projects_dir = _get_claude_projects_dir(working_dir)
        if projects_dir is None:
            return SessionLogResponse(
                active=False, feature_id=feature_id, session_file=None,
                entries=[], total_entries=0,
            )

        session_file = projects_dir / session_filename
        if not session_file.exists():
            return SessionLogResponse(
                active=False, feature_id=feature_id, session_file=None,
                entries=[], total_entries=0,
            )

        clamped_limit = max(1, min(limit, 200))
        entries = _parse_jsonl_log(session_file, limit=clamped_limit)

        return SessionLogResponse(
            active=False,
            feature_id=feature_id,
            session_file=session_filename,
            entries=[SessionLogEntry(**e) for e in entries],
            total_entries=len(entries),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read session log: {str(e)}")
    finally:
        session.close()


@router.patch("/features/{feature_id}/priority", response_model=FeatureResponse)
async def update_feature_priority(feature_id: int, request: UpdateFeaturePriorityRequest):
    """
    Update feature priority to a specific value.

    This is used for direct reordering by dragging features to specific positions.
    """
    session = get_session()
    try:
        feature = session.query(Feature).filter(Feature.id == feature_id).first()

        if feature is None:
            raise HTTPException(status_code=404, detail=f"Feature {feature_id} not found")

        if request.priority < 1:
            raise HTTPException(status_code=400, detail="Priority must be >= 1")

        feature.priority = request.priority

        session.commit()
        session.refresh(feature)

        return feature_to_response(feature, get_commit_counts(session, [feature.id]))
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update feature priority: {str(e)}")
    finally:
        session.close()


@router.patch("/features/{feature_id}/move", response_model=FeatureResponse)
async def move_feature(feature_id: int, request: MoveFeatureRequest):
    """
    Move a feature up or down within its current lane.

    Finds the adjacent feature by sorted position (not priority comparison) so
    that duplicate priority values are handled correctly. Deduplicates lane
    priorities after swapping to guarantee all values remain distinct.
    Direction must be "up" or "down".
    """
    if request.direction not in ["up", "down"]:
        raise HTTPException(status_code=400, detail="Direction must be 'up' or 'down'")

    session = get_session()
    try:
        feature = session.query(Feature).filter(Feature.id == feature_id).first()

        if feature is None:
            raise HTTPException(status_code=404, detail=f"Feature {feature_id} not found")

        # Get all features in the same lane sorted by (priority, id) for stable ordering.
        # Using id as a tiebreaker ensures deterministic results when priorities are equal.
        lane_features = session.query(Feature).filter(
            Feature.passes == feature.passes,
            Feature.in_progress == feature.in_progress,
        ).order_by(Feature.priority.asc(), Feature.id.asc()).all()

        # Find this feature's position in the sorted lane.
        feature_idx = next((i for i, f in enumerate(lane_features) if f.id == feature_id), None)

        if request.direction == "up":
            if feature_idx == 0:
                raise HTTPException(status_code=400, detail=f"Cannot move feature {request.direction}: already at the edge")
            adj_idx = feature_idx - 1
        else:
            if feature_idx == len(lane_features) - 1:
                raise HTTPException(status_code=400, detail=f"Cannot move feature {request.direction}: already at the edge")
            adj_idx = feature_idx + 1

        # Swap positions in the ordered list, then normalize the whole lane to clean
        # 100-step priorities. This resolves any pre-existing duplicates and ensures
        # future swaps never produce conflicts.
        lane_features[feature_idx], lane_features[adj_idx] = lane_features[adj_idx], lane_features[feature_idx]
        _normalize_lane_priorities(lane_features)

        session.commit()
        session.refresh(feature)

        return feature_to_response(feature, get_commit_counts(session, [feature.id]))
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to move feature: {str(e)}")
    finally:
        session.close()


@router.patch("/features/{feature_id}/reorder", response_model=FeatureResponse)
async def reorder_feature(feature_id: int, request: ReorderFeatureRequest):
    """
    Reorder a feature by placing it immediately before or after a target feature.

    Both features must be in the same lane. Redistributes priority values so
    the dragged card ends up at the exact drop position regardless of distance.
    """
    session = get_session()
    try:
        feature = session.query(Feature).filter(Feature.id == feature_id).first()
        if feature is None:
            raise HTTPException(status_code=404, detail=f"Feature {feature_id} not found")

        target = session.query(Feature).filter(Feature.id == request.target_id).first()
        if target is None:
            raise HTTPException(status_code=404, detail=f"Target feature {request.target_id} not found")

        if feature.passes != target.passes or feature.in_progress != target.in_progress:
            raise HTTPException(status_code=400, detail="Features must be in the same lane")

        # Get all features in the lane sorted by (priority, id) for stable ordering.
        lane_features = session.query(Feature).filter(
            Feature.passes == feature.passes,
            Feature.in_progress == feature.in_progress,
        ).order_by(Feature.priority.asc(), Feature.id.asc()).all()

        # Build new order: remove dragged feature, insert at target position
        ordered = [f for f in lane_features if f.id != feature_id]
        target_idx = next((i for i, f in enumerate(ordered) if f.id == request.target_id), None)

        if target_idx is None:
            raise HTTPException(status_code=400, detail="Target feature not found in the same lane")

        insert_idx = target_idx if request.insert_before else target_idx + 1
        ordered.insert(insert_idx, feature)

        # Normalize the whole lane to clean 100-step priorities. This eliminates
        # any pre-existing duplicates and gives room between slots so future moves
        # never produce conflicts.
        _normalize_lane_priorities(ordered)

        session.commit()
        session.refresh(feature)

        return feature_to_response(feature, get_commit_counts(session, [feature.id]))
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to reorder feature: {str(e)}")
    finally:
        session.close()
