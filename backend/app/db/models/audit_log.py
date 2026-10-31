"""Audit log database model for tracking sensitive admin and security events."""

from datetime import UTC, datetime
from typing import Any
import uuid

from sqlalchemy import DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, PortableJSON


class AuditLog(Base):
    """Audit log recording security, administrative, and review decisions."""

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)

    # Note: 'metadata' is a reserved attribute on SQLAlchemy DeclarativeBase.
    # The Python attribute is 'event_metadata', mapped to the database column 'metadata'.
    event_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        PortableJSON,
        default=dict,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
