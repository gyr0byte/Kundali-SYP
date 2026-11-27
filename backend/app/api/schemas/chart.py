"""Pydantic v2 request and response schemas for deterministic chart calculation."""

from __future__ import annotations

import datetime
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.calc.ayanamsha import AyanamshaMode
from app.calc.ephemeris import NodeType
from app.calc.facts import (
    CALCULATION_PRESETS,
    SUPPORTED_YEAR_DAYS,
    ChartFacts,
    ChartSettings,
)
from app.db.models.profile import InputCalendar, TimeCertainty

ChartPreset = Literal["hamro_patro_compat"]
ChartConflictErrorCode = Literal[
    "AWAITING_BS_CONVERSION",
    "UNKNOWN_TIME_UNSUPPORTED",
    "INCOMPLETE_BIRTH_DATA",
    "CHART_DATE_OUT_OF_RANGE",
    "PROFILE_CHANGED",
]


class ChartCalculationRequest(BaseModel):
    """Calculation settings supplied by the client for an owned birth profile.

    Birth date, time, coordinates, and timezone are NEVER accepted from the client;
    they are decrypted strictly from the server-side owned BirthProfile record.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    ayanamsha: AyanamshaMode = AyanamshaMode.LAHIRI
    house_system: Literal["whole_sign"] = "whole_sign"
    node_type: NodeType = NodeType.MEAN
    year_days: float = Field(
        default=365.25,
        description="Supported Dasha year length: 360.0, 365.2425, or 365.25",
        json_schema_extra={"enum": list(SUPPORTED_YEAR_DAYS)},
    )
    preset: ChartPreset | None = None

    @field_validator("year_days", mode="before")
    @classmethod
    def check_year_days_supported(cls, value: object) -> float:
        """Check the numeric allowlist before converting to float."""
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or value not in SUPPORTED_YEAR_DAYS
        ):
            raise ValueError("year_days must be one of 360.0, 365.2425, 365.25")
        return float(value)

    @field_validator("preset", mode="before")
    @classmethod
    def check_preset_known(cls, value: object) -> str | None:
        """Reject non-string or unknown preset identifiers before Literal validation."""
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("Unknown calculation preset")
        cleaned = value.strip()
        if cleaned not in CALCULATION_PRESETS:
            available = ", ".join(sorted(CALCULATION_PRESETS))
            raise ValueError(f"Unknown calculation preset; available: {available}")
        return cleaned

    @model_validator(mode="after")
    def validate_preset_consistency(self) -> ChartCalculationRequest:
        """Reject explicit settings that contradict the selected preset."""
        if self.preset is not None:
            preset_settings = ChartSettings.from_preset(self.preset)
            for field_name in ("ayanamsha", "house_system", "node_type"):
                if field_name in self.model_fields_set and getattr(self, field_name) != getattr(
                    preset_settings, field_name
                ):
                    raise ValueError(f"Setting {field_name} contradicts preset {self.preset!r}")

        return self

    def to_chart_settings(self) -> ChartSettings:
        """Resolve explicit options against the engine defaults or selected preset."""
        overrides = self.model_dump(exclude_unset=True, exclude={"preset"})
        if self.preset is not None:
            defaults = ChartSettings.from_preset(self.preset).model_dump()
            return ChartSettings(**(defaults | overrides))
        return ChartSettings(**overrides)


class ChartCalculationResponse(BaseModel):
    """Response envelope pairing computed ChartFacts with source profile certainty context."""

    model_config = ConfigDict(extra="forbid")

    profile_id: uuid.UUID
    profile_updated_at: datetime.datetime
    input_calendar: InputCalendar
    time_certainty: TimeCertainty
    chart: ChartFacts


class ChartConflictErrorResponse(BaseModel):
    """Structured HTTP 409 error response for blocked or incomplete profile states."""

    detail: str
    code: ChartConflictErrorCode


class ChartFactUnits(BaseModel):
    """Units of angular fields and planetary speed in the v1 fact values."""

    model_config = ConfigDict(extra="forbid")

    angle: Literal["degree"] = "degree"
    speed: Literal["degree/day"] = "degree/day"


class ChartSnapshotResponse(ChartCalculationResponse):
    """An immutable result and its status relative to the profile at read time."""

    snapshot_id: uuid.UUID
    schema_version: int
    profile_revision: int
    is_current_profile_revision: bool
    created_at: datetime.datetime
    fact_units: ChartFactUnits
