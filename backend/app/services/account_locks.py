"""Acquire the administration lock first, then the affected user, then child rows."""

import uuid

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.permissions import UserRole
from app.db.models import User


class AdministrativeAuthorizationError(ValueError):
    """The administrator lost authorization before the write could begin."""


def lock_administration(db: Session) -> None:
    """Serialize role and activity changes before reading state or locking a user."""
    if db.get_bind().dialect.name == "postgresql":
        # Fixed application namespace and resource ID, released at commit or rollback.
        db.execute(text("SELECT pg_advisory_xact_lock(1263881796, 1)"))


def lock_user(db: Session, user_id: uuid.UUID) -> User | None:
    """Use PostgreSQL FOR NO KEY UPDATE to allow foreign-key checks of the account."""
    return db.get(User, user_id, populate_existing=True, with_for_update={"key_share": True})


def require_active_admin(db: Session, actor_id: uuid.UUID) -> None:
    """Recheck the actor after taking the administration lock."""
    if (
        db.scalar(
            select(User.id).where(User.id == actor_id, User.role == UserRole.ADMIN, User.is_active)
        )
        is None
    ):
        raise AdministrativeAuthorizationError("Active administrator required")
