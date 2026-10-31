"""Unit tests for UserService: user listing, self-deactivation protection, and last-admin protection."""

from datetime import UTC, datetime
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.clock import FrozenClock
from app.core.permissions import UserRole
from app.db.base import Base
from app.db.models import User
from app.services.user_service import deactivate_user, list_users, reactivate_user


@pytest.fixture
def db_session() -> Session:
    """Isolated SQLite database session."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC))


def test_list_users_pagination_and_filtering(db_session: Session) -> None:
    """List users supports filtering by role and status with pagination."""
    u1 = User(email="user1@example.com", password_hash="h1", role=UserRole.USER, is_active=True)
    u2 = User(email="user2@example.com", password_hash="h2", role=UserRole.USER, is_active=False)
    admin = User(email="admin@example.com", password_hash="h3", role=UserRole.ADMIN, is_active=True)
    db_session.add_all([u1, u2, admin])
    db_session.commit()

    users, total = list_users(db_session, role=UserRole.USER, limit=10, offset=0)
    assert total == 2
    assert len(users) == 2

    active_users, total_active = list_users(db_session, is_active=True, limit=10, offset=0)
    assert total_active == 2


def test_self_deactivation_is_prevented(db_session: Session, clock: FrozenClock) -> None:
    """An admin or user cannot deactivate their own account."""
    admin = User(email="admin@example.com", password_hash="h", role=UserRole.ADMIN)
    db_session.add(admin)
    db_session.commit()

    with pytest.raises(ValueError, match="Cannot deactivate your own account"):
        deactivate_user(
            db=db_session,
            target_user_id=admin.id,
            actor_user_id=admin.id,
            clock=clock,
        )


def test_last_admin_deactivation_is_prevented(
    db_session: Session, clock: FrozenClock
) -> None:
    """Cannot deactivate the sole remaining active administrator."""
    admin = User(email="sole_admin@example.com", password_hash="h", role=UserRole.ADMIN)
    other = User(email="other@example.com", password_hash="h", role=UserRole.USER)
    db_session.add_all([admin, other])
    db_session.commit()

    with pytest.raises(ValueError, match="Cannot deactivate the last admin"):
        deactivate_user(
            db=db_session,
            target_user_id=admin.id,
            actor_user_id=other.id,
            clock=clock,
        )


def test_deactivate_and_reactivate_user(
    db_session: Session, clock: FrozenClock
) -> None:
    """Deactivating a user disables login; reactivating restores it."""
    u = User(email="asha@example.com", password_hash="h", role=UserRole.USER)
    admin = User(email="admin@example.com", password_hash="h", role=UserRole.ADMIN)
    admin2 = User(email="admin2@example.com", password_hash="h", role=UserRole.ADMIN)
    db_session.add_all([u, admin, admin2])
    db_session.commit()

    # Admin deactivates Asha
    deactivate_user(
        db=db_session,
        target_user_id=u.id,
        actor_user_id=admin.id,
        clock=clock,
    )
    assert db_session.get(User, u.id).is_active is False  # type: ignore[union-attr]

    # Admin reactivates Asha
    reactivate_user(
        db=db_session,
        target_user_id=u.id,
        actor_user_id=admin.id,
    )
    assert db_session.get(User, u.id).is_active is True  # type: ignore[union-attr]
