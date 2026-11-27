"""Owned, append-only chart snapshots and their encrypted calculation facts."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ChartSnapshot(Base):
    """One immutable calculation result for a particular birth profile revision."""

    __tablename__ = "chart_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "profile_id",
            "profile_revision",
            "schema_version",
            "fingerprint_key",
            name="uq_chart_snapshots_result",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("birth_profiles.id", ondelete="CASCADE"), nullable=False
    )
    profile_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    fingerprint_key: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, deferred=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
