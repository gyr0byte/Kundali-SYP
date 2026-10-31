"""Unit tests for AstrologerService: application, approval, suspension."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.clock import FrozenClock
from app.core.permissions import UserRole
from app.db.base import Base
from app.db.models import AstrologerProfile, AstrologerStatus, User
from app.services.astrologer_service import (
    apply_for_astrologer,
    approve_astrologer,
    list_astrologers,
    suspend_astrologer,
)


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


def test_astrologer_application_workflow(db_session: Session, clock: FrozenClock) -> None:
    """User applies -> profile created in pending status."""
    user = User(email="applicant@example.com", password_hash="h", role=UserRole.USER)
    admin = User(email="admin@example.com", password_hash="h", role=UserRole.ADMIN)
    db_session.add_all([user, admin])
    db_session.commit()

    profile = apply_for_astrologer(
        db=db_session,
        user_id=user.id,
        display_name="Jyotishi Shastri",
        credentials="Acharya in Jyotish from Varanasi, 10 yrs practice",
        tradition="Parashari",
    )
    assert profile.status == AstrologerStatus.PENDING

    # Duplicate application is prevented
    with pytest.raises(ValueError, match="already submitted"):
        apply_for_astrologer(
            db=db_session,
            user_id=user.id,
            display_name="Duplicate",
            credentials="xyz",
            tradition="xyz",
        )

    # Admin lists pending astrologers
    pending, count = list_astrologers(db_session, status=AstrologerStatus.PENDING)
    assert count == 1
    assert pending[0].user_id == user.id

    # Admin approves
    approve_astrologer(db=db_session, user_id=user.id, admin_id=admin.id, clock=clock)
    u_after = db_session.get(User, user.id)
    p_after = db_session.get(AstrologerProfile, user.id)
    assert u_after is not None and u_after.role == UserRole.ASTROLOGER
    assert p_after is not None and p_after.status == AstrologerStatus.APPROVED
    assert p_after.approved_by == admin.id
    assert p_after.approved_at is not None

    # Admin suspends astrologer
    suspend_astrologer(db=db_session, user_id=user.id, admin_id=admin.id, clock=clock)
    p_suspended = db_session.get(AstrologerProfile, user.id)
    assert p_suspended is not None and p_suspended.status == AstrologerStatus.SUSPENDED
