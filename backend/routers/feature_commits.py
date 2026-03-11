"""
Feature commit endpoints router.

Provides endpoints to attach git commit IDs to features so the frontend
can look up the commit message instead of duplicating it in the database.
"""

import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from api.database import Feature, FeatureCommit
from backend.deps import get_session
from backend.schemas import AddCommitRequest, FeatureCommitResponse

router = APIRouter(prefix="/api/features", tags=["feature-commits"])


@router.get("/{feature_id}/commits", response_model=list[FeatureCommitResponse])
async def get_feature_commits(feature_id: int):
    """Get all commit IDs attached to a feature, ordered by created_at ascending."""
    session = get_session()
    try:
        feature = session.query(Feature).filter(Feature.id == feature_id).first()
        if feature is None:
            raise HTTPException(status_code=404, detail=f"Feature {feature_id} not found")

        commits = (
            session.query(FeatureCommit)
            .filter(FeatureCommit.feature_id == feature_id)
            .order_by(FeatureCommit.created_at.asc())
            .all()
        )
        return [FeatureCommitResponse(**c.to_dict()) for c in commits]
    finally:
        session.close()


@router.post("/{feature_id}/commits", response_model=FeatureCommitResponse, status_code=201)
async def add_feature_commit(feature_id: int, request: AddCommitRequest):
    """Attach a git commit ID to a feature."""
    commit_hash = request.commit_hash.strip()
    if not commit_hash:
        raise HTTPException(status_code=400, detail="Commit hash cannot be empty")

    session = get_session()
    try:
        feature = session.query(Feature).filter(Feature.id == feature_id).first()
        if feature is None:
            raise HTTPException(status_code=404, detail=f"Feature {feature_id} not found")

        commit = FeatureCommit(feature_id=feature_id, commit_hash=commit_hash)
        session.add(commit)
        session.commit()
        session.refresh(commit)

        return FeatureCommitResponse(**commit.to_dict())
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to add commit: {str(e)}")
    finally:
        session.close()


@router.delete("/{feature_id}/commits/{commit_id}", status_code=204)
async def delete_feature_commit(feature_id: int, commit_id: int):
    """Remove a commit ID from a feature."""
    session = get_session()
    try:
        commit = session.query(FeatureCommit).filter(
            FeatureCommit.id == commit_id,
            FeatureCommit.feature_id == feature_id,
        ).first()

        if commit is None:
            raise HTTPException(status_code=404, detail=f"Commit {commit_id} not found on feature {feature_id}")

        session.delete(commit)
        session.commit()
        return None
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete commit: {str(e)}")
    finally:
        session.close()
