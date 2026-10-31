"""Astrologer profile application and credentialing management services."""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.permissions import UserRole
from app.db.models import AstrologerProfile, AstrologerStatus, User
from app.services.audit_service import log_action
from app.services.auth_service import revoke_all_tokens


def apply_for_astrologer(
    db: Session,
    user_id: uuid.UUID,
    display_name: str,
    credentials: str,
    tradition: str,
) -> AstrologerProfile:
    """Submit an astrologer application."""
    user = db.get(User, user_id)
    if not user:
        raise ValueError("User not found")

    existing = db.get(AstrologerProfile, user_id)
    if existing:
        raise ValueError("Application already submitted")

    profile = AstrologerProfile(
        user_id=user_id,
        display_name=display_name.strip(),
        credentials=credentials.strip(),
        tradition=tradition.strip(),
        status=AstrologerStatus.PENDING,
    )
    db.add(profile)
    log_action(
        db,
        action="astrologer:apply",
        actor_id=user_id,
        target_type="astrologer_profile",
        target_id=str(user_id),
    )
    db.commit()
    db.refresh(profile)
    return profile


def list_astrologers(
    db: Session,
    status: AstrologerStatus | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[Sequence[AstrologerProfile], int]:
    """List astrologer profiles filtered by status with total count."""
    query = select(AstrologerProfile)
    count_query = select(func.count(AstrologerProfile.user_id))

    if status is not None:
        query = query.where(AstrologerProfile.status == status)
        count_query = count_query.where(AstrologerProfile.status == status)

    total = db.scalar(count_query) or 0
    items = db.scalars(query.limit(limit).offset(offset)).all()
    return items, total


def approve_astrologer(
    db: Session,
    user_id: uuid.UUID,
    admin_id: uuid.UUID,
    clock: Clock,
) -> None:
    """Approve an astrologer profile and upgrade the user's role to astrologer."""
    profile = db.get(AstrologerProfile, user_id)
    if not profile:
        raise ValueError("Astrologer profile not found")

    user = db.get(User, user_id)
    if not user:
        raise ValueError("User not found")

    now = clock.now()
    profile.status = AstrologerStatus.APPROVED
    profile.approved_by = admin_id
    profile.approved_at = now

    user.role = UserRole.ASTROLOGER
    user.updated_at = now

    log_action(
        db,
        action="astrologer:approve",
        actor_id=admin_id,
        target_type="astrologer_profile",
        target_id=str(user_id),
    )
    db.commit()


def suspend_astrologer(
    db: Session,
    user_id: uuid.UUID,
    admin_id: uuid.UUID,
    clock: Clock,
) -> None:
    """Suspend an astrologer profile and revoke active sessions."""
    profile = db.get(AstrologerProfile, user_id)
    if not profile:
        raise ValueError("Astrologer profile not found")

    profile.status = AstrologerStatus.SUSPENDED

    # Invalidate active sessions
    revoke_all_tokens(db, user_id, clock)

    log_action(
        db,
        action="astrologer:suspend",
        actor_id=admin_id,
        target_type="astrologer_profile",
        target_id=str(user_id),
    )
    db.commit()
