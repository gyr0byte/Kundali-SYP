"""User management service for admin panel and account control."""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.permissions import UserRole
from app.db.models import User
from app.services.audit_service import log_action
from app.services.auth_service import revoke_all_tokens


def list_users(
    db: Session,
    role: UserRole | None = None,
    is_active: bool | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[Sequence[User], int]:
    """List users with optional role and status filters, returning items and total count."""
    query = select(User)
    count_query = select(func.count(User.id))

    if role is not None:
        query = query.where(User.role == role)
        count_query = count_query.where(User.role == role)

    if is_active is not None:
        query = query.where(User.is_active == is_active)
        count_query = count_query.where(User.is_active == is_active)

    total = db.scalar(count_query) or 0
    items = db.scalars(query.order_by(User.created_at.desc()).limit(limit).offset(offset)).all()
    return items, total


def deactivate_user(
    db: Session,
    target_user_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    clock: Clock,
) -> None:
    """Deactivate a user account, revoking all active sessions.

    Prevents self-deactivation and deactivating the last active administrator.
    """
    if target_user_id == actor_user_id:
        raise ValueError("Cannot deactivate your own account")

    target = db.get(User, target_user_id)
    if not target:
        raise ValueError("User not found")

    if not target.is_active:
        return

    # Check last active admin protection
    if target.role == UserRole.ADMIN:
        active_admins = db.scalar(
            select(func.count(User.id)).where(
                User.role == UserRole.ADMIN,
                User.is_active.is_(True),
            )
        )
        if (active_admins or 0) <= 1:
            raise ValueError("Cannot deactivate the last admin")

    target.is_active = False
    target.updated_at = clock.now()

    # Revoke all active sessions
    revoke_all_tokens(db, target.id, clock)

    log_action(
        db,
        action="user:deactivate",
        actor_id=actor_user_id,
        target_type="user",
        target_id=str(target.id),
    )
    db.commit()


def reactivate_user(
    db: Session,
    target_user_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> None:
    """Reactivate a previously deactivated user account."""
    target = db.get(User, target_user_id)
    if not target:
        raise ValueError("User not found")

    target.is_active = True
    target.failed_login_attempts = 0
    target.locked_until = None

    log_action(
        db,
        action="user:reactivate",
        actor_id=actor_user_id,
        target_type="user",
        target_id=str(target.id),
    )
    db.commit()
