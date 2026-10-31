"""Unit tests for core configuration settings."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_requires_jwt_secret() -> None:
    """Settings must refuse to start without a valid JWT_SECRET."""
    with pytest.raises(ValidationError):
        Settings(JWT_SECRET="", DATABASE_URL="sqlite:///:memory:")  # type: ignore[call-arg]


def test_settings_requires_jwt_secret_min_length() -> None:
    """JWT_SECRET must be at least 32 characters long."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(JWT_SECRET="too-short-secret", DATABASE_URL="sqlite:///:memory:")
    assert "at least 32" in str(exc_info.value).lower()


def test_settings_environment_default_is_prod() -> None:
    """ENVIRONMENT must default to 'prod'."""
    settings = Settings(
        JWT_SECRET="a" * 32,
        DATABASE_URL="sqlite:///:memory:",
    )
    assert settings.ENVIRONMENT == "prod"


def test_settings_cors_allowed_origins_default_is_empty() -> None:
    """CORS_ALLOWED_ORIGINS must default to an empty list."""
    settings = Settings(
        JWT_SECRET="a" * 32,
        DATABASE_URL="sqlite:///:memory:",
    )
    assert settings.CORS_ALLOWED_ORIGINS == []


def test_settings_requires_database_url() -> None:
    """DATABASE_URL has no default outside test overrides."""
    with pytest.raises(ValidationError):
        Settings(JWT_SECRET="a" * 32)  # type: ignore[call-arg]


def test_settings_token_and_lockout_defaults() -> None:
    """Verify default token expiration and lockout thresholds."""
    settings = Settings(
        JWT_SECRET="a" * 32,
        DATABASE_URL="sqlite:///:memory:",
    )
    assert settings.ACCESS_TOKEN_EXPIRE_MINUTES == 15
    assert settings.REFRESH_TOKEN_EXPIRE_DAYS == 7
    assert settings.RESET_TOKEN_EXPIRE_MINUTES == 30
    assert settings.LOCKOUT_THRESHOLD == 5
    assert settings.LOCKOUT_MINUTES == 15
