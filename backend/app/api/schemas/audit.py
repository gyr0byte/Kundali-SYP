"""Pydantic v2 schemas for audit logs and error responses."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AuditLogResponse(BaseModel):
    """Single audit log entry."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_id: uuid.UUID | None
    action: str
    target_type: str | None
    target_id: str | None
    ip: str | None
    event_metadata: dict[str, Any] = Field(default_factory=dict, alias="metadata")
    created_at: datetime


class AuditLogListResponse(BaseModel):
    """Paginated list of audit logs."""

    items: list[AuditLogResponse]
    total: int
    limit: int
    offset: int


class ErrorResponse(BaseModel):
    """Standardized API error response."""

    detail: str
