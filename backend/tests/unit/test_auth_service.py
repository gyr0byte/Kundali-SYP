"""Unit tests for AuthService: registration, authentication, token rotation, and reset."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.clock import FrozenClock, ensure_utc
from app.core.config import Settings
from app.core.mailer import ConsoleMailer
from app.core.permissions import UserRole
from app.db.base import Base
from app.db.models import User
from app.services.auth_service import (
    authenticate_user,
    create_token_pair,
    refresh_tokens,
    register_user,
    request_password_reset,
    reset_password,
    revoke_all_tokens,
    revoke_token,
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
def settings() -> Settings:
    """Test configuration settings."""
    return Settings(
        JWT_SECRET="x" * 32,
        DATABASE_URL="sqlite:///:memory:",
        ENVIRONMENT="test",
    )


@pytest.fixture
def clock() -> FrozenClock:
    """Frozen clock for reproducible time checks."""
    return FrozenClock(datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC))


def test_register_user_success(db_session: Session, clock: FrozenClock) -> None:
    """Register user strips/lowercases email and creates active user."""
    user = register_user(
        db=db_session,
        email="  Asha.Sharma@Example.COM  ",
        password="ValidPassword2026!",
        clock=clock,
        for_testing=True,
    )
    assert user.email == "asha.sharma@example.com"
    assert user.is_active is True
    assert user.role == UserRole.USER


def test_register_user_duplicate_email_fails(db_session: Session, clock: FrozenClock) -> None:
    """Duplicate email registration raises ValueError."""
    register_user(
        db=db_session,
        email="asha@example.com",
        password="ValidPassword2026!",
        clock=clock,
        for_testing=True,
    )
    with pytest.raises(ValueError, match="already registered"):
        register_user(
            db=db_session,
            email="asha@example.com",
            password="ValidPassword2026!",
            clock=clock,
            for_testing=True,
        )


def test_authenticate_user_success_and_failure(db_session: Session, clock: FrozenClock) -> None:
    """Successful authentication resets failed attempts; wrong password increments them."""
    register_user(
        db=db_session,
        email="asha@example.com",
        password="ValidPassword2026!",
        clock=clock,
        for_testing=True,
    )

    # Success
    user = authenticate_user(
        db=db_session,
        email="asha@example.com",
        password="ValidPassword2026!",
        clock=clock,
    )
    assert user.email == "asha@example.com"
    assert user.failed_login_attempts == 0

    # Wrong password raises ValueError
    with pytest.raises(ValueError, match="Invalid email or password"):
        authenticate_user(
            db=db_session,
            email="asha@example.com",
            password="WrongPassword99!",
            clock=clock,
        )

    # Check failed attempts incremented
    u = db_session.get(User, user.id)
    assert u is not None
    assert u.failed_login_attempts == 1


def test_account_lockout_after_five_failed_attempts(
    db_session: Session, clock: FrozenClock
) -> None:
    """5 consecutive failures locks the account for 15 minutes."""
    register_user(
        db=db_session,
        email="asha@example.com",
        password="ValidPassword2026!",
        clock=clock,
        for_testing=True,
    )

    for _ in range(5):
        with pytest.raises(ValueError, match="Invalid email or password"):
            authenticate_user(
                db=db_session,
                email="asha@example.com",
                password="WrongPassword!",
                clock=clock,
            )

    u = db_session.query(User).filter_by(email="asha@example.com").one()
    assert u.failed_login_attempts == 5
    assert u.locked_until is not None
    assert ensure_utc(u.locked_until) > clock.now()

    # Even with correct password, login must fail while locked
    with pytest.raises(ValueError, match="Invalid email or password"):
        authenticate_user(
            db=db_session,
            email="asha@example.com",
            password="ValidPassword2026!",
            clock=clock,
        )

    # Fast forward clock past lockout window
    clock.advance(timedelta(minutes=16))
    unlocked = authenticate_user(
        db=db_session,
        email="asha@example.com",
        password="ValidPassword2026!",
        clock=clock,
    )
    assert unlocked.failed_login_attempts == 0
    assert unlocked.locked_until is None


def test_refresh_token_rotation_and_family_reuse_detection(
    db_session: Session, clock: FrozenClock, settings: Settings
) -> None:
    """Token rotation creates new token; presenting an already rotated token revokes family."""
    user = register_user(
        db=db_session,
        email="asha@example.com",
        password="ValidPassword2026!",
        clock=clock,
        for_testing=True,
    )

    access1, refresh1 = create_token_pair(db=db_session, user=user, clock=clock, settings=settings)
    assert access1 and refresh1

    # Normal rotation: refresh1 -> refresh2
    access2, refresh2 = refresh_tokens(
        db=db_session, raw_refresh_token=refresh1, clock=clock, settings=settings
    )
    assert access2 and refresh2
    assert refresh1 != refresh2

    # Attempting to use refresh1 AGAIN (replay / token theft attack):
    with pytest.raises(ValueError, match="Invalid or expired refresh token"):
        refresh_tokens(db=db_session, raw_refresh_token=refresh1, clock=clock, settings=settings)

    # Family revocation check: refresh2 must now ALSO be revoked!
    with pytest.raises(ValueError, match="Invalid or expired refresh token"):
        refresh_tokens(db=db_session, raw_refresh_token=refresh2, clock=clock, settings=settings)


def test_logout_and_logout_all(db_session: Session, clock: FrozenClock, settings: Settings) -> None:
    """Single token logout vs logout-all."""
    user = register_user(
        db=db_session,
        email="asha@example.com",
        password="ValidPassword2026!",
        clock=clock,
        for_testing=True,
    )

    _, refresh1 = create_token_pair(db=db_session, user=user, clock=clock, settings=settings)
    _, refresh2 = create_token_pair(db=db_session, user=user, clock=clock, settings=settings)

    # Revoke single token
    assert revoke_token(db=db_session, raw_refresh_token=refresh1, clock=clock) is True
    # Unknown token returns False
    assert revoke_token(db=db_session, raw_refresh_token="unknown-token", clock=clock) is False

    # refresh2 should still be valid
    _, refresh3 = refresh_tokens(
        db=db_session, raw_refresh_token=refresh2, clock=clock, settings=settings
    )
    assert refresh3

    # Logout all revokes remaining tokens
    revoked_count = revoke_all_tokens(db=db_session, user_id=user.id, clock=clock)
    assert revoked_count >= 1

    # Now refresh3 fails
    with pytest.raises(ValueError, match="Invalid or expired refresh token"):
        refresh_tokens(db=db_session, raw_refresh_token=refresh3, clock=clock, settings=settings)


def test_password_reset_flow(db_session: Session, clock: FrozenClock, settings: Settings) -> None:
    """Password reset request, execution, single-use enforcement, and token expiry."""
    register_user(
        db=db_session,
        email="asha@example.com",
        password="OldPassword2026!",
        clock=clock,
        for_testing=True,
    )

    mailer = ConsoleMailer(environment="test")
    # Request reset
    token = request_password_reset(
        db=db_session,
        email="asha@example.com",
        clock=clock,
        mailer=mailer,
        settings=settings,
    )
    assert token is not None

    # Reset with new password
    reset_password(
        db=db_session,
        raw_reset_token=token,
        new_password="NewSecurePassword2026!",
        clock=clock,
    )

    # Login with new password succeeds
    u = authenticate_user(
        db=db_session,
        email="asha@example.com",
        password="NewSecurePassword2026!",
        clock=clock,
    )
    assert u.email == "asha@example.com"

    # Reusing the same reset token fails
    with pytest.raises(ValueError, match="Invalid or expired reset token"):
        reset_password(
            db=db_session,
            raw_reset_token=token,
            new_password="AnotherPassword2026!",
            clock=clock,
        )
