"""Pydantic v2 schemas for authentication requests and responses."""

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    """Payload for user registration."""

    model_config = ConfigDict(str_strip_whitespace=True)

    email: EmailStr
    password: str = Field(min_length=10, max_length=128)


class LoginRequest(BaseModel):
    """Payload for credentials-based login."""

    model_config = ConfigDict(str_strip_whitespace=True)

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Response containing access token and rotating refresh token."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """Payload for rotating refresh token."""

    refresh_token: str


class LogoutRequest(BaseModel):
    """Payload for single token logout."""

    refresh_token: str


class ChangePasswordRequest(BaseModel):
    """Payload for authenticated password change."""

    old_password: str
    new_password: str = Field(min_length=10, max_length=128)


class ForgotPasswordRequest(BaseModel):
    """Payload for requesting a password reset email."""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Payload for resetting password using a reset token."""

    token: str
    new_password: str = Field(min_length=10, max_length=128)
