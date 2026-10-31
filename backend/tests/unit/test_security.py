"""Unit tests for core security utilities."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.security import (
    create_access_token,
    decode_access_token,
    dummy_verify_password,
    get_password_hasher,
    hash_password,
    hash_token,
    validate_password,
    verify_password,
)


def test_password_hashing_and_verification() -> None:
    """Argon2 hashing must verify matching password and reject wrong password."""
    password = "CorrectHorseBattery99!"
    hashed = hash_password(password)
    assert hashed.startswith("$argon2")
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword123!", hashed) is False


def test_production_argon2_parameters_not_weakened() -> None:
    """Production Argon2 hasher must have robust parameters."""
    hasher = get_password_hasher(for_testing=False)
    # Default Argon2id parameters
    assert hasher.time_cost >= 3
    assert hasher.memory_cost >= 65536
    assert hasher.parallelism >= 4


def test_test_argon2_parameters_are_fast() -> None:
    """Test fixture Argon2 hasher should use fast parameters for speed."""
    hasher = get_password_hasher(for_testing=True)
    assert hasher.time_cost == 1
    assert hasher.memory_cost <= 8192
    assert hasher.parallelism == 1


def test_dummy_verify_password_prevents_timing_leak() -> None:
    """dummy_verify_password must run without exception."""
    dummy_verify_password()


@pytest.mark.parametrize(
    ("password", "email", "expected_valid", "error_substring"),
    [
        ("short9!", "user@example.com", False, "at least 10"),
        ("a" * 129, "user@example.com", False, "at most 128"),
        ("myuser@example.compass", "user@example.com", False, "email"),
        ("password123!", "user@example.com", False, "common"),
        ("SecurePassPhrase2026!", "user@example.com", True, None),
    ],
)
def test_validate_password(
    password: str, email: str, expected_valid: bool, error_substring: str | None
) -> None:
    """Validate password constraints: length, email containment, blocklist."""
    is_valid, err = validate_password(password, email)
    assert is_valid is expected_valid
    if error_substring:
        assert err is not None
        assert error_substring in err.lower()
    else:
        assert err is None


def test_create_and_decode_access_token() -> None:
    """Access token encode/decode flow."""
    secret = "x" * 32
    token = create_access_token(
        subject="test-user-id",
        role="user",
        secret=secret,
        expires_delta=timedelta(minutes=15),
    )
    payload = decode_access_token(token, secret=secret)
    assert payload["sub"] == "test-user-id"
    assert payload["role"] == "user"
    assert "exp" in payload


def test_decode_token_rejects_wrong_secret() -> None:
    """Decoding with wrong secret raises an error."""
    secret = "x" * 32
    token = create_access_token(
        subject="test-user-id",
        role="user",
        secret=secret,
        expires_delta=timedelta(minutes=15),
    )
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token, secret="y" * 32)


def test_decode_token_rejects_alg_none() -> None:
    """Tokens with alg='none' must be strictly rejected."""
    payload = {
        "sub": "attacker",
        "role": "admin",
        "exp": int((datetime.now(UTC) + timedelta(minutes=15)).timestamp()),
    }
    # Forge token with alg=none
    unsecured_token = jwt.encode(payload, key="", algorithm="none")
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(unsecured_token, secret="x" * 32)


def test_hash_token_sha256() -> None:
    """hash_token must produce a deterministic SHA-256 hex string."""
    raw = "sample_raw_token_xyz"
    h1 = hash_token(raw)
    h2 = hash_token(raw)
    assert h1 == h2
    assert len(h1) == 64
