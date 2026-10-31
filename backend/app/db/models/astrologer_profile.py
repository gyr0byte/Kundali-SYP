"""Astrologer profile database model."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.user import User


class AstrologerStatus(StrEnum):
    """Approval status of an astrologer profile."""

    PENDING = "pending"
    APPROVED = "approved"
    SUSPENDED = "suspended"


class AstrologerProfile(Base):
    """Profile and credentialing information for astrologers."""

    __tablename__ = "astrologer_profiles"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'suspended')",
            name="check_astrologer_status",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    credentials: Mapped[str] = mapped_column(Text, nullable=False)
    tradition: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[AstrologerStatus] = mapped_column(
        sa.Enum(
            AstrologerStatus,
            native_enum=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        default=AstrologerStatus.PENDING,
        nullable=False,
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="astrologer_profile",
        foreign_keys=[user_id],
    )
