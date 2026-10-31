"""Authentication and session management services."""

import uuid
from datetime import timedelta

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.clock import Clock, ensure_utc
from app.core.config import Settings
from app.core.mailer import Mailer
from app.core.permissions import UserRole
from app.core.security import (
    create_access_token,
    dummy_verify_password,
    generate_raw_token,
    hash_password,
    hash_token,
    password_needs_rehash,
    validate_password,
    verify_password,
)
from app.db.models import PasswordResetToken, RefreshToken, User
from app.services.audit_service import log_action


def normalize_email(email: str) -> str:
    """Validate email syntax and normalize to lowercase."""
    try:
        valid = validate_email(email.strip(), check_deliverability=False)
        return str(valid.normalized).lower()
    except EmailNotValidError as e:
        raise ValueError(f"Invalid email address: {e}") from e


def register_user(
    db: Session,
    email: str,
    password: str,
    clock: Clock,
    for_testing: bool = False,
) -> User:
    """Register a new user account."""
    clean_email = normalize_email(email)

    # Validate password complexity
    valid_pass, err = validate_password(password, clean_email)
    if not valid_pass:
        raise ValueError(err or "Invalid password")

    # Check if email is already registered
    existing = db.scalar(select(User).where(User.email == clean_email))
    if existing:
        raise ValueError("Email already registered")

    now = clock.now()
    hashed = hash_password(password, for_testing=for_testing)

    user = User(
        email=clean_email,
        password_hash=hashed,
        role=UserRole.USER,
        language="en",
        is_active=True,
        failed_login_attempts=0,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    log_action(
        db, action="auth:register", actor_id=user.id, target_type="user", target_id=str(user.id)
    )
    db.commit()

    return user


def authenticate_user(
    db: Session,
    email: str,
    password: str,
    clock: Clock,
    for_testing: bool = False,
) -> User:
    """Authenticate user with constant-time mitigation and account lockout defenses."""
    now = clock.now()
    try:
        clean_email = normalize_email(email)
    except ValueError:
        # Email format invalid: run dummy verify to prevent timing leak and fail uniformly
        dummy_verify_password()
        raise ValueError("Invalid email or password") from None

    user = db.scalar(select(User).where(User.email == clean_email))

    if not user:
        # Unknown email: run dummy verification to prevent user enumeration
        dummy_verify_password()
        raise ValueError("Invalid email or password")

    # Check lockout
    locked_until = ensure_utc(user.locked_until)
    if locked_until and locked_until > now:
        # Account is currently locked
        dummy_verify_password()
        raise ValueError("Invalid email or password")

    # Check if deactivated
    if not user.is_active:
        dummy_verify_password()
        raise ValueError("Invalid email or password")

    # Verify password
    if not verify_password(password, user.password_hash):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= 5:
            user.locked_until = now + timedelta(minutes=15)
            log_action(
                db,
                action="auth:lockout",
                actor_id=user.id,
                target_type="user",
                target_id=str(user.id),
                metadata={"reason": "too_many_failed_attempts"},
            )
        db.commit()
        raise ValueError("Invalid email or password")

    # Password matched: reset failed login attempts and unlock
    user.failed_login_attempts = 0
    user.locked_until = None

    # Check if password needs rehash
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password, for_testing=for_testing)

    db.commit()
    db.refresh(user)
    return user


def create_token_pair(
    db: Session,
    user: User,
    clock: Clock,
    settings: Settings,
) -> tuple[str, str]:
    """Create a new access token and refresh token pair."""
    now = clock.now()
    access_token = create_access_token(
        subject=str(user.id),
        role=user.role.value if hasattr(user.role, "value") else str(user.role),
        secret=settings.JWT_SECRET,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    raw_refresh = generate_raw_token()
    token_hash = hash_token(raw_refresh)
    family_id = uuid.uuid4()

    refresh_entity = RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        family_id=family_id,
        expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        created_at=now,
    )
    db.add(refresh_entity)
    db.commit()

    return access_token, raw_refresh


def refresh_tokens(
    db: Session,
    raw_refresh_token: str,
    clock: Clock,
    settings: Settings,
) -> tuple[str, str]:
    """Rotate refresh token.

    If reuse of an already revoked token is detected, revokes the entire family.
    """
    now = clock.now()
    token_hash = hash_token(raw_refresh_token)

    token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    if not token:
        raise ValueError("Invalid or expired refresh token")

    # Check reuse detection: was token already revoked?
    if token.revoked_at is not None:
        # Immediate family-wide revocation
        db.execute(
            update(RefreshToken)
            .where(
                RefreshToken.family_id == token.family_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        log_action(
            db,
            action="auth:token_reuse_detected",
            actor_id=token.user_id,
            target_type="token_family",
            target_id=str(token.family_id),
            metadata={"revoked_family": str(token.family_id)},
        )
        db.commit()
        raise ValueError("Invalid or expired refresh token")

    # Check expiration
    expires_at = ensure_utc(token.expires_at)
    if expires_at and expires_at <= now:
        token.revoked_at = now
        db.commit()
        raise ValueError("Invalid or expired refresh token")

    user = db.get(User, token.user_id)
    if not user or not user.is_active:
        token.revoked_at = now
        db.commit()
        raise ValueError("Invalid or expired refresh token")

    # Valid rotation: revoke current token
    token.revoked_at = now

    # Issue replacement in same family
    new_raw_refresh = generate_raw_token()
    new_hash = hash_token(new_raw_refresh)

    replacement = RefreshToken(
        user_id=user.id,
        token_hash=new_hash,
        family_id=token.family_id,
        replaced_by_id=token.id,
        expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        created_at=now,
    )
    db.add(replacement)

    new_access_token = create_access_token(
        subject=str(user.id),
        role=user.role.value if hasattr(user.role, "value") else str(user.role),
        secret=settings.JWT_SECRET,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    db.commit()
    return new_access_token, new_raw_refresh


def revoke_token(
    db: Session,
    raw_refresh_token: str,
    clock: Clock,
) -> bool:
    """Revoke a single refresh token (public logout endpoint).

    Returns True if token existed and was revoked; False if token was unknown or already revoked.
    """
    now = clock.now()
    token_hash = hash_token(raw_refresh_token)
    token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))

    if not token or token.revoked_at is not None:
        return False

    token.revoked_at = now
    db.commit()
    return True


def revoke_all_tokens(
    db: Session,
    user_id: uuid.UUID,
    clock: Clock,
) -> int:
    """Revoke all active refresh tokens for the given user."""
    now = clock.now()
    result = db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    db.commit()
    return int(result.rowcount)  # type: ignore[attr-defined]


def change_password(
    db: Session,
    user: User,
    old_password: str,
    new_password: str,
    clock: Clock,
    for_testing: bool = False,
) -> None:
    """Change user password, verifying old password and revoking all active sessions."""
    if not verify_password(old_password, user.password_hash):
        raise ValueError("Invalid current password")

    valid_pass, err = validate_password(new_password, user.email)
    if not valid_pass:
        raise ValueError(err or "Invalid new password")

    user.password_hash = hash_password(new_password, for_testing=for_testing)
    user.updated_at = clock.now()

    # Invalidate all user refresh tokens
    revoke_all_tokens(db, user.id, clock)
    log_action(
        db,
        action="auth:password_change",
        actor_id=user.id,
        target_type="user",
        target_id=str(user.id),
    )
    db.commit()


def request_password_reset(
    db: Session,
    email: str,
    clock: Clock,
    mailer: Mailer,
    settings: Settings,
) -> str | None:
    """Initiate password reset.

    Returns token string for dev/testing, but endpoint always responds 202.
    """
    now = clock.now()
    try:
        clean_email = normalize_email(email)
    except ValueError:
        return None

    user = db.scalar(select(User).where(User.email == clean_email))
    if not user or not user.is_active:
        return None

    raw_token = generate_raw_token()
    token_hash = hash_token(raw_token)

    reset_entity = PasswordResetToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=now + timedelta(minutes=settings.RESET_TOKEN_EXPIRE_MINUTES),
        created_at=now,
    )
    db.add(reset_entity)
    db.commit()

    reset_url = f"http://localhost:3000/auth/reset-password?token={raw_token}"
    mailer.send_password_reset_email(
        to_email=user.email, reset_token=raw_token, reset_url=reset_url
    )
    return raw_token


def reset_password(
    db: Session,
    raw_reset_token: str,
    new_password: str,
    clock: Clock,
    for_testing: bool = False,
) -> None:
    """Reset password using a valid, unused, unexpired reset token."""
    now = clock.now()
    token_hash = hash_token(raw_reset_token)

    token = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash))
    expires_at = ensure_utc(token.expires_at) if token else None
    if not token or token.used_at is not None or (expires_at and expires_at <= now):
        raise ValueError("Invalid or expired reset token")

    user = db.get(User, token.user_id)
    if not user or not user.is_active:
        raise ValueError("Invalid or expired reset token")

    valid_pass, err = validate_password(new_password, user.email)
    if not valid_pass:
        raise ValueError(err or "Invalid new password")

    user.password_hash = hash_password(new_password, for_testing=for_testing)
    user.updated_at = now
    token.used_at = now

    # Invalidate all active refresh tokens
    revoke_all_tokens(db, user.id, clock)
    log_action(
        db,
        action="auth:password_reset",
        actor_id=user.id,
        target_type="user",
        target_id=str(user.id),
    )
    db.commit()
