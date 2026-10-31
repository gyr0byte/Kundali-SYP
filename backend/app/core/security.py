"""Core security utilities: Argon2 password hashing, JWT, and token helpers."""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError

# Blocklist of common passwords
COMMON_PASSWORD_BLOCKLIST: set[str] = {
    "password",
    "password123",
    "1234567890",
    "123456789",
    "12345678",
    "qwerty1234",
    "admin12345",
    "letmein1234",
    "welcome1234",
    "iloveyou123",
}

# Production Argon2id parameters (NOT weakened)
PROD_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
)

# Fast hasher for testing purposes
TEST_HASHER = PasswordHasher(
    time_cost=1,
    memory_cost=8192,
    parallelism=1,
    hash_len=32,
    salt_len=16,
)

# Precomputed dummy hash for timing-attack mitigation
DUMMY_PASSWORD_HASH = PROD_HASHER.hash("KundaliDummyMitigationPassword2026!")


def get_password_hasher(for_testing: bool = False) -> PasswordHasher:
    """Return appropriate PasswordHasher instance."""
    return TEST_HASHER if for_testing else PROD_HASHER


def hash_password(password: str, for_testing: bool = False) -> str:
    """Hash password using Argon2id."""
    hasher = get_password_hasher(for_testing)
    return hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against an Argon2id hash."""
    try:
        # PROD_HASHER can verify hashes produced by any valid Argon2 parameters
        return PROD_HASHER.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError):
        return False


def dummy_verify_password() -> None:
    """Perform a constant-time dummy verification to mitigate timing attacks on unknown emails."""
    try:
        PROD_HASHER.verify(DUMMY_PASSWORD_HASH, "incorrect-dummy-attempt")
    except (VerifyMismatchError, VerificationError):
        pass


def password_needs_rehash(password_hash: str) -> bool:
    """Check if hash parameters require updating."""
    return PROD_HASHER.check_needs_rehash(password_hash)


def validate_password(password: str, email: str) -> tuple[bool, str | None]:
    """Validate password constraints: length, email substring, common passwords."""
    if len(password) < 10:
        return False, "Password must be at least 10 characters long"
    if len(password) > 128:
        return False, "Password must be at most 128 characters long"

    # Check email localpart containment
    local_part = email.split("@")[0].lower() if "@" in email else email.lower()
    if len(local_part) >= 3 and local_part in password.lower():
        return False, "Password cannot contain parts of your email address"

    lower_pass = password.lower()
    if lower_pass in COMMON_PASSWORD_BLOCKLIST:
        return False, "Password is too common or easily guessable"

    base_word = lower_pass.strip("0123456789!@#$%^&*_-+=?.,")
    if base_word in COMMON_PASSWORD_BLOCKLIST:
        return False, "Password is too common or easily guessable"

    return True, None


def create_access_token(
    subject: str,
    role: str,
    secret: str,
    expires_delta: timedelta,
    additional_claims: dict[str, Any] | None = None,
) -> str:
    """Create a signed HS256 JWT access token."""
    now = datetime.now(UTC)
    expire = now + expires_delta
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    if additional_claims:
        payload.update(additional_claims)

    return jwt.encode(payload, secret, algorithm="HS256")


def decode_access_token(token: str, secret: str) -> dict[str, Any]:
    """Decode and validate an HS256 JWT access token. Strictly rejects alg='none'."""
    # PyJWT defaults require algorithm in algorithms and reject alg=none unless explicitly allowed
    payload: dict[str, Any] = jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        options={"require": ["sub", "role", "exp"]},
    )
    return payload


def generate_raw_token() -> str:
    """Generate a high-entropy URL-safe raw token (for refresh or password reset)."""
    return secrets.token_urlsafe(32)


def hash_token(raw_token: str) -> str:
    """Compute SHA-256 hex digest of a token."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def constant_time_compare(val1: str, val2: str) -> bool:
    """Constant-time string comparison."""
    return hmac.compare_digest(val1.encode("utf-8"), val2.encode("utf-8"))
