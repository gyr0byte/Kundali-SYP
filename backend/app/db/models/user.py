"""User database model."""

from datetime import UTC, datetime
import uuid

import sqlalchemy as sa
from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.permissions import UserRole
from app.db.base import Base


class User(Base):
    """User account entity."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'astrologer', 'admin')",
            name="check_user_role",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        sa.Enum(UserRole, native_enum=False),
        default=UserRole.USER,
        nullable=False,
    )
    language: Mapped[str] = mapped_column(String(10), default="en", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    astrologer_profile: Mapped["AstrologerProfile | None"] = relationship(  # type: ignore[name-defined]
        "AstrologerProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(  # type: ignore[name-defined]
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    reset_tokens: Mapped[list["PasswordResetToken"]] = relationship(  # type: ignore[name-defined]
        "PasswordResetToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )
