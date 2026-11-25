"""Birth profile database model with encrypted sensitive fields."""

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, LargeBinary, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.user import User


class InputCalendar(StrEnum):
    """Calendar system in which the birth date was originally entered."""

    AD = "AD"
    BS = "BS"


class TimeCertainty(StrEnum):
    """Certainty level recorded for local birth time."""

    EXACT = "exact"
    APPROXIMATE = "approximate"
    UNKNOWN = "unknown"


class BirthProfile(Base):
    """Encrypted birth profile belonging to an authenticated user."""

    __tablename__ = "birth_profiles"
    __table_args__ = (
        CheckConstraint(
            "input_calendar IN ('AD', 'BS')",
            name="check_birth_profile_input_calendar",
        ),
        CheckConstraint(
            "time_certainty IN ('exact', 'approximate', 'unknown')",
            name="check_birth_profile_time_certainty",
        ),
        CheckConstraint(
            "(time_certainty = 'unknown' AND time_local_enc IS NULL) "
            "OR (time_certainty IN ('exact', 'approximate') AND time_local_enc IS NOT NULL)",
            name="check_birth_profile_time_local_certainty",
        ),
        CheckConstraint(
            "(input_calendar = 'BS' AND date_ad_enc IS NULL) "
            "OR (input_calendar = 'AD' AND date_ad_enc IS NOT NULL)",
            name="check_birth_profile_calendar_date_ad",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    # Encrypted birth identity & location payloads (Fernet ciphertext)
    label_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    input_calendar: Mapped[InputCalendar] = mapped_column(
        sa.Enum(
            InputCalendar,
            name="input_calendar",
            native_enum=False,
            create_constraint=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    entered_date_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    date_ad_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    time_certainty: Mapped[TimeCertainty] = mapped_column(
        sa.Enum(
            TimeCertainty,
            name="time_certainty",
            native_enum=False,
            create_constraint=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    time_local_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    place_name_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    latitude_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    longitude_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    timezone_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

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

    owner: Mapped["User"] = relationship(
        "User",
        back_populates="birth_profiles",
        foreign_keys=[owner_id],
    )
