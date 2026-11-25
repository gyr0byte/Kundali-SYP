"""Unit tests for core configuration settings."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from tests.conftest import TEST_ENCRYPTION_KEY


def test_settings_requires_jwt_secret() -> None:
    """Settings must refuse to start without a valid JWT_SECRET."""
    with pytest.raises(ValidationError):
        Settings(
            JWT_SECRET="",
            DATABASE_URL="sqlite:///:memory:",
            ENCRYPTION_KEY=TEST_ENCRYPTION_KEY,
        )  # type: ignore[call-arg]


def test_settings_requires_jwt_secret_min_length() -> None:
    """JWT_SECRET must be at least 32 characters long."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            JWT_SECRET="too-short-secret",
            DATABASE_URL="sqlite:///:memory:",
            ENCRYPTION_KEY=TEST_ENCRYPTION_KEY,
        )
    assert "at least 32" in str(exc_info.value).lower()


def test_settings_environment_default_is_prod() -> None:
    """ENVIRONMENT must default to 'prod'."""
    settings = Settings(
        JWT_SECRET="a" * 32,
        DATABASE_URL="sqlite:///:memory:",
        ENCRYPTION_KEY=TEST_ENCRYPTION_KEY,
    )
    assert settings.ENVIRONMENT == "prod"


def test_settings_cors_allowed_origins_default_is_empty() -> None:
    """CORS_ALLOWED_ORIGINS must default to an empty list."""
    settings = Settings(
        JWT_SECRET="a" * 32,
        DATABASE_URL="sqlite:///:memory:",
        ENCRYPTION_KEY=TEST_ENCRYPTION_KEY,
    )
    assert settings.CORS_ALLOWED_ORIGINS == []


def test_settings_requires_database_url() -> None:
    """DATABASE_URL has no default outside test overrides."""
    with pytest.raises(ValidationError):
        Settings(JWT_SECRET="a" * 32, ENCRYPTION_KEY=TEST_ENCRYPTION_KEY)  # type: ignore[call-arg]


def test_settings_token_and_lockout_defaults() -> None:
    """Verify default token expiration and lockout thresholds."""
    settings = Settings(
        JWT_SECRET="a" * 32,
        DATABASE_URL="sqlite:///:memory:",
        ENCRYPTION_KEY=TEST_ENCRYPTION_KEY,
    )
    assert settings.ACCESS_TOKEN_EXPIRE_MINUTES == 15
    assert settings.REFRESH_TOKEN_EXPIRE_DAYS == 7
    assert settings.RESET_TOKEN_EXPIRE_MINUTES == 30
    assert settings.LOCKOUT_THRESHOLD == 5
    assert settings.LOCKOUT_MINUTES == 15


@pytest.mark.parametrize("env_name", ["prod", "dev", "test"])
def test_settings_requires_encryption_key_in_all_environments(
    env_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ENCRYPTION_KEY has no fallback in any environment."""
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings(
            ENVIRONMENT=env_name,
            JWT_SECRET="a" * 32,
            DATABASE_URL="sqlite:///:memory:",
            _env_file=None,
        )  # type: ignore[call-arg]


@pytest.mark.parametrize(
    "bad_key",
    [
        "",
        "   ",
        "not-a-valid-fernet-key",
        "c2hvcnQ=",
        "a+" + "b" * 41 + "=",
    ],
)
def test_settings_rejects_invalid_encryption_key(bad_key: str) -> None:
    """Invalid ENCRYPTION_KEY fails validation without echoing key material."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ENVIRONMENT="test",
            JWT_SECRET="a" * 32,
            DATABASE_URL="sqlite:///:memory:",
            ENCRYPTION_KEY=bad_key,
        )
    if bad_key.strip():
        assert bad_key.strip() not in str(exc_info.value)


def test_settings_accepts_and_strips_valid_encryption_key() -> None:
    """Valid Fernet ENCRYPTION_KEY with surrounding whitespace is normalized."""
    settings = Settings(
        ENVIRONMENT="prod",
        JWT_SECRET="a" * 32,
        DATABASE_URL="sqlite:///:memory:",
        ENCRYPTION_KEY=f"  {TEST_ENCRYPTION_KEY}  ",
    )
    assert settings.ENCRYPTION_KEY == TEST_ENCRYPTION_KEY
