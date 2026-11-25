"""Unit tests for core security utilities."""

import base64
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.fernet import Fernet

from app.core.security import (
    DecryptionError,
    create_access_token,
    decode_access_token,
    decrypt_float,
    decrypt_optional_float,
    decrypt_optional_text,
    decrypt_text,
    dummy_verify_password,
    encrypt_float,
    encrypt_optional_float,
    encrypt_optional_text,
    encrypt_text,
    get_password_hasher,
    hash_password,
    hash_token,
    validate_fernet_key,
    validate_password,
    verify_password,
)
from tests.conftest import TEST_ENCRYPTION_KEY


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


def test_validate_fernet_key_accepts_valid_and_rejects_malformed() -> None:
    """Valid Fernet keys pass while invalid keys fail without leaking key material."""
    generated = Fernet.generate_key().decode("ascii")
    assert validate_fernet_key(f"  {generated}  ") == generated

    # Non-canonical base64 where unused trailing bits in byte 43 are non-zero.
    non_canonical_raw = base64.urlsafe_b64encode(b"k" * 32).decode("ascii")
    non_canonical = non_canonical_raw[:-2] + "B="

    invalid_keys = [
        "",
        "   ",
        "too-short",
        base64.urlsafe_b64encode(b"short-16-bytes!!").decode("ascii"),
        base64.b64encode(b"\xff" * 32).decode("ascii"),  # standard base64 with + /
        "काठ" + "a" * 40 + "=",  # non-ASCII
        non_canonical,
    ]
    for bad_key in invalid_keys:
        with pytest.raises(ValueError) as exc_info:
            validate_fernet_key(bad_key)
        if bad_key.strip():
            assert bad_key.strip() not in str(exc_info.value)


@pytest.mark.parametrize(
    "sample_text",
    [
        "Kathmandu, Nepal",
        "काठमाडौं, नेपाल — आशा शर्मा",
        "São Paulo • München • Reykjavík ☸",
        "",
    ],
)
def test_encrypt_decrypt_text_unicode_roundtrip(sample_text: str) -> None:
    """Text encryption handles ASCII, Unicode/Devanagari, and empty strings accurately."""
    ciphertext = encrypt_text(sample_text, TEST_ENCRYPTION_KEY)
    assert isinstance(ciphertext, bytes)
    if sample_text:
        assert sample_text.encode("utf-8") not in ciphertext
    assert TEST_ENCRYPTION_KEY.encode("ascii") not in ciphertext
    assert decrypt_text(ciphertext, TEST_ENCRYPTION_KEY) == sample_text


@pytest.mark.parametrize("coord", [27.7172, 85.3240, -33.8688, 179.999999, 0.0, -0.0])
def test_encrypt_decrypt_float_roundtrip(coord: float) -> None:
    """Coordinate floats round-trip accurately with normalized zero."""
    ciphertext = encrypt_float(coord, TEST_ENCRYPTION_KEY)
    assert isinstance(ciphertext, bytes)
    decrypted = decrypt_float(ciphertext, TEST_ENCRYPTION_KEY)
    expected = 0.0 if coord == 0.0 else coord
    assert decrypted == expected


@pytest.mark.parametrize("bad_coord", [float("nan"), float("inf"), float("-inf"), True, False])
def test_encrypt_float_rejects_non_finite_and_bool(bad_coord: object) -> None:
    """Non-finite floats and booleans are rejected before encryption."""
    with pytest.raises(ValueError):
        encrypt_float(bad_coord, TEST_ENCRYPTION_KEY)  # type: ignore[arg-type]


def test_decrypt_rejects_wrong_key_and_tampered_ciphertext() -> None:
    """Wrong key or modified ciphertext fails safely without exposing plaintext or keys."""
    other_key = Fernet.generate_key().decode("ascii")
    secret_place = "Pokhara Secret Valley"
    ciphertext = encrypt_text(secret_place, TEST_ENCRYPTION_KEY)

    with pytest.raises(DecryptionError) as wrong_key_exc:
        decrypt_text(ciphertext, other_key)
    assert secret_place not in str(wrong_key_exc.value)
    assert other_key not in str(wrong_key_exc.value)
    assert TEST_ENCRYPTION_KEY not in str(wrong_key_exc.value)

    tampered = bytearray(ciphertext)
    tampered[-5] ^= 0xFF
    with pytest.raises(DecryptionError) as tamper_exc:
        decrypt_text(bytes(tampered), TEST_ENCRYPTION_KEY)
    assert secret_place not in str(tamper_exc.value)

    with pytest.raises(DecryptionError):
        decrypt_text(ciphertext[:-4], TEST_ENCRYPTION_KEY)

    with pytest.raises(DecryptionError):
        decrypt_text(b"", TEST_ENCRYPTION_KEY)


def test_encrypt_decrypt_optional_values_and_key_validation() -> None:
    """Nullable helpers preserve None and non-None values while always validating the key."""
    assert encrypt_optional_text(None, TEST_ENCRYPTION_KEY) is None
    assert decrypt_optional_text(None, TEST_ENCRYPTION_KEY) is None
    assert encrypt_optional_float(None, TEST_ENCRYPTION_KEY) is None
    assert decrypt_optional_float(None, TEST_ENCRYPTION_KEY) is None

    enc_time = encrypt_optional_text("08:30", TEST_ENCRYPTION_KEY)
    assert enc_time is not None
    assert decrypt_optional_text(enc_time, TEST_ENCRYPTION_KEY) == "08:30"

    enc_lat = encrypt_optional_float(27.7172, TEST_ENCRYPTION_KEY)
    assert enc_lat is not None
    assert decrypt_optional_float(enc_lat, TEST_ENCRYPTION_KEY) == 27.7172

    with pytest.raises(ValueError):
        encrypt_optional_text(None, "invalid-key")
    with pytest.raises(ValueError):
        decrypt_optional_text(None, "invalid-key")
    with pytest.raises(ValueError):
        encrypt_optional_float(None, "invalid-key")
    with pytest.raises(ValueError):
        decrypt_optional_float(None, "invalid-key")
