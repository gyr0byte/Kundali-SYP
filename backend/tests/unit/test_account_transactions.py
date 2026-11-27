"""SQLite regressions for service behavior and transaction boundaries, not locking."""

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.mailer import ConsoleMailer
from app.core.permissions import UserRole
from app.core.security import hash_token, verify_password
from app.db.models import AstrologerProfile, AstrologerStatus, AuditLog, RefreshToken
from app.services import astrologer_service, auth_service, user_service
from app.services.audit_service import log_action


def test_logout_with_rotated_token_revokes_only_that_family(
    db_session: Session, test_clock: FrozenClock, test_settings: Settings, user_factory: Any
) -> None:
    user = user_factory()
    _, initial = auth_service.create_token_pair(db_session, user, test_clock, test_settings)
    _, other = auth_service.create_token_pair(db_session, user, test_clock, test_settings)
    _, replacement = auth_service.refresh_tokens(db_session, initial, test_clock, test_settings)

    assert auth_service.revoke_token(db_session, initial, test_clock)
    assert not auth_service.revoke_token(db_session, initial, test_clock)
    with pytest.raises(ValueError, match="Invalid or expired refresh token"):
        auth_service.refresh_tokens(db_session, replacement, test_clock, test_settings)
    assert auth_service.refresh_tokens(db_session, other, test_clock, test_settings)


def test_applications_and_legacy_approval_cannot_demote_admin(
    db_session: Session, test_clock: FrozenClock, user_factory: Any
) -> None:
    admin = user_factory(role=UserRole.ADMIN)
    with pytest.raises(ValueError, match="Administrators cannot apply"):
        astrologer_service.apply_for_astrologer(
            db_session, admin.id, "Admin", "Credentials", "Vedic"
        )
    assert db_session.get(AstrologerProfile, admin.id) is None

    legacy = user_factory(
        email="legacy@example.com", role=UserRole.ADMIN, astrologer_status=AstrologerStatus.PENDING
    )
    with pytest.raises(ValueError, match="Cannot approve an administrator"):
        astrologer_service.approve_astrologer(db_session, legacy.id, admin.id, test_clock)
    profile = db_session.get(AstrologerProfile, legacy.id)
    assert profile is not None and profile.status == AstrologerStatus.PENDING
    assert legacy.role == UserRole.ADMIN
    assert db_session.scalars(select(AuditLog)).all() == []


@pytest.mark.parametrize("operation", ["deactivate", "suspend", "approve", "change", "reset"])
def test_failed_audit_rolls_back_entire_mutation(
    db_session: Session,
    test_clock: FrozenClock,
    test_settings: Settings,
    user_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    admin = user_factory(email="admin@example.com", role=UserRole.ADMIN)
    user = user_factory(astrologer_status=AstrologerStatus.PENDING)
    _, raw_refresh = auth_service.create_token_pair(db_session, user, test_clock, test_settings)
    raw_reset = auth_service.request_password_reset(
        db_session, user.email, test_clock, ConsoleMailer(environment="test"), test_settings
    )
    assert raw_reset is not None

    def fail_after_audit(*args: Any, **kwargs: Any) -> None:
        log_action(*args, **kwargs)
        raise RuntimeError("Audit failure")

    with monkeypatch.context() as patch, pytest.raises(RuntimeError, match="Audit failure"):
        patch.setattr(auth_service, "log_action", fail_after_audit)
        patch.setattr(user_service, "log_action", fail_after_audit)
        patch.setattr(astrologer_service, "log_action", fail_after_audit)
        match operation:
            case "deactivate":
                user_service.deactivate_user(db_session, user.id, admin.id, test_clock)
            case "suspend":
                astrologer_service.suspend_astrologer(db_session, user.id, admin.id, test_clock)
            case "approve":
                astrologer_service.approve_astrologer(db_session, user.id, admin.id, test_clock)
            case "change":
                auth_service.change_password(
                    db_session, user, "TestPassword2026!", "AnotherPassword2026!", test_clock, True
                )
            case "reset":
                auth_service.reset_password(
                    db_session, raw_reset, "AnotherPassword2026!", test_clock, True
                )

    db_session.rollback()
    assert user.is_active and user.role == UserRole.USER
    assert verify_password("TestPassword2026!", user.password_hash)
    token = db_session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_refresh))
    )
    assert token is not None and token.revoked_at is None
    profile = db_session.get(AstrologerProfile, user.id)
    assert profile is not None and profile.status == AstrologerStatus.PENDING
    assert db_session.scalars(select(AuditLog)).all() == []
    if operation == "reset":
        auth_service.reset_password(db_session, raw_reset, "AnotherPassword2026!", test_clock, True)
