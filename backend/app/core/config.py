"""Application configuration settings via pydantic-settings."""

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable overrides."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ENVIRONMENT: str = "prod"
    JWT_SECRET: str
    DATABASE_URL: str

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
