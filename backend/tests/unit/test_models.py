"""Unit tests for database models and schema constraints using in-memory SQLite."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.permissions import UserRole
from app.db.base import Base
from app.db.models import (
    AstrologerProfile,
    AstrologerStatus,
    AuditLog,
    PasswordResetToken,
    RefreshToken,
    User,
)


@pytest.fixture
def db_session() -> Session:
    """Fixture providing an isolated in-memory SQLite session with StaticPool."""
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


def test_user_creation_and_defaults(db_session: Session) -> None:
    """Verify user model creation, defaults, and portable UUID."""
    user = User(
        email="asha@example.com",
        password_hash="argon2_hashed_placeholder",
        role=UserRole.USER,
    )
    db_session.add(user)
    db_session.commit()

    retrieved = db_session.scalar(select(User).where(User.email == "asha@example.com"))
    assert retrieved is not None
    assert isinstance(retrieved.id, uuid.UUID)
    assert retrieved.language == "en"
    assert retrieved.is_active is True
    assert retrieved.failed_login_attempts == 0
    assert retrieved.locked_until is None
    assert retrieved.deleted_at is None
    assert retrieved.created_at is not None


def test_user_email_unique_constraint(db_session: Session) -> None:
    """User email must be unique."""
    u1 = User(email="duplicate@example.com", password_hash="hash1")
    u2 = User(email="duplicate@example.com", password_hash="hash2")
    db_session.add(u1)
    db_session.commit()

    db_session.add(u2)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_astrologer_profile_relationship(db_session: Session) -> None:
    """Astrologer profile connects to User via foreign key."""
    user = User(email="guru@example.com", password_hash="hash", role=UserRole.ASTROLOGER)
    db_session.add(user)
    db_session.commit()

    profile = AstrologerProfile(
        user_id=user.id,
        display_name="Pt. Sharma",
        credentials="MA in Jyotish, 15 years experience",
        tradition="Parashari",
        status=AstrologerStatus.PENDING,
    )
    db_session.add(profile)
    db_session.commit()

    retrieved = db_session.get(AstrologerProfile, user.id)
    assert retrieved is not None
    assert retrieved.display_name == "Pt. Sharma"
    assert retrieved.status == AstrologerStatus.PENDING
    assert retrieved.approved_at is None


def test_refresh_token_model_and_family(db_session: Session) -> None:
    """Refresh token supports family_id and replaced_by_id for rotation tracking."""
    user = User(email="tokenuser@example.com", password_hash="hash")
    db_session.add(user)
    db_session.commit()

    fam_id = uuid.uuid4()
    t1 = RefreshToken(
        user_id=user.id,
        token_hash="sha256_hash_1",
        family_id=fam_id,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    db_session.add(t1)
    db_session.commit()

    # Rotate to t2
    t2 = RefreshToken(
        user_id=user.id,
        token_hash="sha256_hash_2",
        family_id=fam_id,
        replaced_by_id=t1.id,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    t1.revoked_at = datetime.now(UTC)
    db_session.add(t2)
    db_session.commit()

    retrieved_t1 = db_session.get(RefreshToken, t1.id)
    assert retrieved_t1 is not None
    assert retrieved_t1.revoked_at is not None

    retrieved_t2 = db_session.get(RefreshToken, t2.id)
    assert retrieved_t2 is not None
    assert retrieved_t2.replaced_by_id == t1.id
    assert retrieved_t2.family_id == fam_id


def test_password_reset_token_model(db_session: Session) -> None:
    """Password reset token model creation and usage tracking."""
    user = User(email="resetuser@example.com", password_hash="hash")
    db_session.add(user)
    db_session.commit()

    token = PasswordResetToken(
        user_id=user.id,
        token_hash="reset_sha256_hash",
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    db_session.add(token)
    db_session.commit()

    retrieved = db_session.get(PasswordResetToken, token.id)
    assert retrieved is not None
    assert retrieved.used_at is None

    # Mark as used
    retrieved.used_at = datetime.now(UTC)
    db_session.commit()
    assert db_session.get(PasswordResetToken, token.id).used_at is not None  # type: ignore[union-attr]


def test_audit_log_event_metadata_mapping(db_session: Session) -> None:
    """AuditLog maps event_metadata attribute to the 'metadata' DB column."""
    user = User(email="admin@example.com", password_hash="hash", role=UserRole.ADMIN)
    db_session.add(user)
    db_session.commit()

    meta_payload = {"reason": "routine review", "score": 95}
    log = AuditLog(
        actor_id=user.id,
        action="user:deactivate",
        target_type="user",
        target_id=str(user.id),
        ip="127.0.0.1",
        event_metadata=meta_payload,
    )
    db_session.add(log)
    db_session.commit()

    retrieved = db_session.get(AuditLog, log.id)
    assert retrieved is not None
    assert retrieved.action == "user:deactivate"
    assert retrieved.ip == "127.0.0.1"
    assert retrieved.event_metadata == meta_payload
    # Verify the underlying column is named 'metadata'
    assert AuditLog.__table__.c.metadata.name == "metadata"
