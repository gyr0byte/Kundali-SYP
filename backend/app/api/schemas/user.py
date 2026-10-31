"""Pydantic v2 schemas for user management and astrologer profiles."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserResponse(BaseModel):
    """Public user profile response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: str
    language: str
    is_active: bool
    created_at: datetime


class UserListResponse(BaseModel):
    """Paginated list of users."""

    items: list[UserResponse]
    total: int
    limit: int
    offset: int


class AstrologerApplyRequest(BaseModel):
    """Payload for submitting an astrologer application."""

    model_config = ConfigDict(str_strip_whitespace=True)

    display_name: str = Field(min_length=2, max_length=100)
    credentials: str = Field(min_length=10)
    tradition: str = Field(min_length=2, max_length=100)


class AstrologerProfileResponse(BaseModel):
    """Public profile for an astrologer."""

    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    display_name: str
    credentials: str
    tradition: str
    status: str
    approved_by: uuid.UUID | None = None
    approved_at: datetime | None = None


class AstrologerListResponse(BaseModel):
    """Paginated list of astrologer profiles."""

    items: list[AstrologerProfileResponse]
    total: int
    limit: int
    offset: int
