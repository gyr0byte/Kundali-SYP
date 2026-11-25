"""Core security utilities: Argon2 password hashing, JWT, token, and encryption helpers."""

import base64
import binascii
import hashlib
import hmac
import math
import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

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


class DecryptionError(ValueError):
    """Raised when encrypted data cannot be authenticated or decrypted."""


# 32 raw bytes encoded as canonical URL-safe base64 always produces 43 base64 chars + '='.
_FERNET_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}=$")


def validate_fernet_key(encryption_key: str) -> str:
    """Validate that an encryption key is a canonical 32-byte URL-safe base64 Fernet key.

    Note:
        ``ENCRYPTION_KEY`` must remain stable and securely backed up across deployments.
        Losing or replacing the key without a controlled data migration makes existing
        encrypted profile records unrecoverable. Key rotation is intentionally out of scope.
    """
    if not isinstance(encryption_key, str):
        raise ValueError("ENCRYPTION_KEY must be a valid 32-byte URL-safe base64 Fernet key")
    cleaned = encryption_key.strip()
    if not cleaned or not _FERNET_KEY_PATTERN.fullmatch(cleaned):
        raise ValueError("ENCRYPTION_KEY must be a valid 32-byte URL-safe base64 Fernet key")
    try:
        raw = base64.urlsafe_b64decode(cleaned.encode("ascii"))
        if len(raw) != 32 or base64.urlsafe_b64encode(raw).decode("ascii") != cleaned:
            raise ValueError("ENCRYPTION_KEY must be a valid 32-byte URL-safe base64 Fernet key")
        Fernet(cleaned.encode("ascii"))
    except (ValueError, binascii.Error):
        raise ValueError(
            "ENCRYPTION_KEY must be a valid 32-byte URL-safe base64 Fernet key"
        ) from None
    return cleaned


def _get_fernet(encryption_key: str) -> Fernet:
    """Construct a Fernet instance after validating the encryption key."""
    validated_key = validate_fernet_key(encryption_key)
    return Fernet(validated_key.encode("ascii"))


def encrypt_text(value: str, encryption_key: str) -> bytes:
    """Encrypt UTF-8 text using symmetric authenticated Fernet encryption."""
    fernet = _get_fernet(encryption_key)
    if not isinstance(value, str):
        raise ValueError("Value to encrypt must be a string")
    return fernet.encrypt(value.encode("utf-8"))


def decrypt_text(ciphertext: bytes, encryption_key: str) -> str:
    """Decrypt and authenticate Fernet ciphertext back into UTF-8 text."""
    fernet = _get_fernet(encryption_key)
    if not isinstance(ciphertext, (bytes, bytearray)) or not ciphertext:
        raise DecryptionError("Failed to decrypt protected value")
    try:
        plaintext_bytes = fernet.decrypt(bytes(ciphertext))
        return plaintext_bytes.decode("utf-8")
    except (InvalidToken, UnicodeDecodeError):
        raise DecryptionError("Failed to decrypt protected value") from None


def encrypt_optional_text(value: str | None, encryption_key: str) -> bytes | None:
    """Encrypt optional UTF-8 text while always enforcing valid key configuration."""
    validate_fernet_key(encryption_key)
    if value is None:
        return None
    return encrypt_text(value, encryption_key)


def decrypt_optional_text(ciphertext: bytes | None, encryption_key: str) -> str | None:
    """Decrypt optional Fernet ciphertext while always enforcing valid key configuration."""
    validate_fernet_key(encryption_key)
    if ciphertext is None:
        return None
    return decrypt_text(ciphertext, encryption_key)


def encrypt_float(value: float, encryption_key: str) -> bytes:
    """Encrypt a finite floating-point coordinate using Fernet encryption."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Numeric value to encrypt must be finite")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError("Numeric value to encrypt must be finite")
    normalized = 0.0 if numeric == 0.0 else numeric
    return encrypt_text(repr(normalized), encryption_key)


def decrypt_float(ciphertext: bytes, encryption_key: str) -> float:
    """Decrypt and validate a finite floating-point coordinate."""
    text = decrypt_text(ciphertext, encryption_key)
    try:
        numeric = float(text)
    except ValueError:
        raise DecryptionError("Failed to decrypt protected numeric value") from None
    if not math.isfinite(numeric):
        raise DecryptionError("Failed to decrypt protected numeric value")
    return numeric


def encrypt_optional_float(value: float | None, encryption_key: str) -> bytes | None:
    """Encrypt an optional finite floating-point value while validating the key."""
    validate_fernet_key(encryption_key)
    if value is None:
        return None
    return encrypt_float(value, encryption_key)


def decrypt_optional_float(ciphertext: bytes | None, encryption_key: str) -> float | None:
    """Decrypt an optional finite floating-point value while validating the key."""
    validate_fernet_key(encryption_key)
    if ciphertext is None:
        return None
    return decrypt_float(ciphertext, encryption_key)
