"""Astrologer review and application endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.schemas.user import AstrologerApplyRequest, AstrologerProfileResponse
from app.core.dependencies import get_current_user, get_db
from app.core.permissions import UserRole
from app.db.models import AstrologerProfile, AstrologerStatus, User
from app.services.astrologer_service import apply_for_astrologer

router = APIRouter(tags=["astrologer"])


@router.post(
    "/astrologer/apply",
    response_model=AstrologerProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
def apply(
    req: AstrologerApplyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    """Submit an application to become a credentialed astrologer."""
    try:
        profile = apply_for_astrologer(
            db=db,
            user_id=current_user.id,
            display_name=req.display_name,
            credentials=req.credentials,
            tradition=req.tradition,
        )
        return profile
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from None


@router.get("/review/queue", response_model=list[dict[str, Any]])
def get_review_queue(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Return the review queue.

    Accessible only to approved astrologers or administrators.
    Returns an empty list until the review feature is implemented.
    """
    if current_user.role == UserRole.ADMIN:
        return []

    if current_user.role == UserRole.ASTROLOGER:
        profile = db.get(AstrologerProfile, current_user.id)
        if profile and profile.status == AstrologerStatus.APPROVED:
            return []

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Approved astrologer or administrator access required",
    )
