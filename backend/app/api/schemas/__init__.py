"""Pydantic v2 schemas for API requests and responses."""

from app.api.schemas.audit import AuditLogListResponse, AuditLogResponse, ErrorResponse
from app.api.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
)
from app.api.schemas.user import (
    AstrologerApplyRequest,
    AstrologerListResponse,
    AstrologerProfileResponse,
    UserListResponse,
    UserResponse,
)

__all__ = [
    "AstrologerApplyRequest",
    "AstrologerListResponse",
    "AstrologerProfileResponse",
    "AuditLogListResponse",
    "AuditLogResponse",
    "ChangePasswordRequest",
    "ErrorResponse",
    "ForgotPasswordRequest",
    "LoginRequest",
    "LogoutRequest",
    "RefreshRequest",
    "RegisterRequest",
    "ResetPasswordRequest",
    "TokenResponse",
    "UserListResponse",
    "UserResponse",
]
