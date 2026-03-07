"""
Comment endpoints router.
"""

import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from api.database import Comment, Feature
from backend.deps import get_session
from backend.schemas import CommentResponse, CreateCommentRequest

router = APIRouter(prefix="/api/features", tags=["comments"])


@router.get("/{feature_id}/comments", response_model=list[CommentResponse])
async def get_comments(feature_id: int):
    """Get all comments for a feature, ordered by created_at ascending."""
    session = get_session()
    try:
        feature = session.query(Feature).filter(Feature.id == feature_id).first()
        if feature is None:
            raise HTTPException(status_code=404, detail=f"Feature {feature_id} not found")

        comments = session.query(Comment).filter(Comment.feature_id == feature_id).order_by(Comment.created_at.asc()).all()
        return [CommentResponse(**c.to_dict()) for c in comments]
    finally:
        session.close()


@router.post("/{feature_id}/comments", response_model=CommentResponse, status_code=201)
async def add_comment(feature_id: int, request: CreateCommentRequest):
    """Add a comment to a feature."""
    if not request.content.strip():
        raise HTTPException(status_code=400, detail="Comment content cannot be empty")

    session = get_session()
    try:
        feature = session.query(Feature).filter(Feature.id == feature_id).first()
        if feature is None:
            raise HTTPException(status_code=404, detail=f"Feature {feature_id} not found")

        comment = Comment(feature_id=feature_id, content=request.content.strip())
        session.add(comment)
        session.commit()
        session.refresh(comment)

        return CommentResponse(**comment.to_dict())
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to add comment: {str(e)}")
    finally:
        session.close()


@router.delete("/{feature_id}/comments/{comment_id}", status_code=204)
async def delete_comment(feature_id: int, comment_id: int):
    """Delete a comment from a feature."""
    session = get_session()
    try:
        comment = session.query(Comment).filter(
            Comment.id == comment_id,
            Comment.feature_id == feature_id
        ).first()

        if comment is None:
            raise HTTPException(status_code=404, detail=f"Comment {comment_id} not found on feature {feature_id}")

        session.delete(comment)
        session.commit()
        return None
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete comment: {str(e)}")
    finally:
        session.close()
