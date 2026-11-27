"""Application configuration settings via pydantic-settings."""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.security import validate_fernet_key


class Settings(BaseSettings):
    """Application settings with environment variable overrides."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    ENVIRONMENT: str = "prod"
    JWT_SECRET: str = Field(repr=False, exclude=True)
    DATABASE_URL: str = Field(repr=False, exclude=True)
    KUNDALI_DB_CA_FILE: str | None = None
    # Required 32-byte URL-safe base64 Fernet key for at-rest profile encryption.
    # IMPORTANT: Must remain stable and securely backed up; losing or changing it
    # without a controlled migration renders encrypted profile data unrecoverable.
    ENCRYPTION_KEY: str = Field(repr=False, exclude=True)

    CORS_ALLOWED_ORIGINS: list[str] = []

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    RESET_TOKEN_EXPIRE_MINUTES: int = 30
    LOCKOUT_THRESHOLD: int = 5
    LOCKOUT_MINUTES: int = 15

    @field_validator("JWT_SECRET")
    @classmethod
    def validate_jwt_secret(cls, v: str) -> str:
        """Validate that JWT_SECRET is provided and at least 32 characters long."""
        if not v or len(v.strip()) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters long")
        return v.strip()

    @field_validator("ENCRYPTION_KEY")
    @classmethod
    def validate_encryption_key(cls, v: str) -> str:
        """Validate that ENCRYPTION_KEY is a valid Fernet key in every environment."""
        return validate_fernet_key(v)


# Global settings instance placeholder (can be initialized with environment or overridden)
_settings: Settings | None = None


def get_settings() -> Settings:
    """Retrieve global settings instance or initialize from environment."""
    global _settings
    if _settings is None:
        _settings = Settings()  # type: ignore[call-arg]
    return _settings


def set_settings(settings: Settings) -> None:
    """Set the global settings instance (useful for testing)."""
    global _settings
    _settings = settings
