"""Pydantic v2 schemas and domain validation for birth profiles."""

from __future__ import annotations

import datetime
import math
import re
import uuid
from dataclasses import dataclass
from typing import Literal
from zoneinfo import ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from app.calc.bikram_sambat import (
    BikramSambatDate,
    CalendarDateError,
    bs_to_ad,
    normalize_date_text,
    parse_ad_date,
)
from app.calc.timeconv import TimeConversionError, TimeInput, convert_local_to_utc_jd
from app.calc.timezones import load_timezone
from app.db.models.profile import InputCalendar, TimeCertainty
from app.geo.nepal import resolve_birthplace

BsConversionStatus = Literal["resolved", "awaiting_bs_conversion"]

_TIME_PATTERN = re.compile(r"^\d{2}:\d{2}(?::\d{2})?$")

# Canonical continent/ocean region prefixes recognized by IANA tzdb (plus explicit "UTC").
_IANA_REGIONS: frozenset[str] = frozenset(
    {
        "Africa",
        "America",
        "Antarctica",
        "Arctic",
        "Asia",
        "Atlantic",
        "Australia",
        "Europe",
        "Indian",
        "Pacific",
    }
)


@dataclass(frozen=True)
class ValidatedProfileData:
    """Validated, normalized birth profile values ready for encrypted persistence."""

    label: str
    input_calendar: InputCalendar
    entered_date: str
    date_ad: str | None
    bs_conversion_status: BsConversionStatus
    time_certainty: TimeCertainty
    time_local: str | None
    place_name: str
    latitude: float
    longitude: float
    timezone: str


def _validate_non_empty_text(value: str, *, field_label: str, max_length: int) -> str:
    """Validate and strip non-empty text without echoing submitted values."""
    if not isinstance(value, str):
        raise ValueError(f"{field_label} must be text")
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_label} is required")
    if len(cleaned) > max_length:
        raise ValueError(f"{field_label} must be at most {max_length} characters")
    return cleaned


def _validate_coordinate(value: float, *, name: str, minimum: float, maximum: float) -> float:
    """Validate finite numeric geographic coordinates without echoing values."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{name} must be a valid number")
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < minimum or numeric > maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}")
    return 0.0 if numeric == 0.0 else numeric


def validate_iana_timezone(value: str) -> str:
    """Validate region-based IANA timezone identifier (with explicit UTC exception).

    Rejects abbreviations (such as EST, NPT, IST, GMT) and non-region aliases while
    preserving exact canonical IANA identifier casing across platforms.
    """
    if not isinstance(value, str):
        raise ValueError("Timezone must be a valid region-based IANA identifier or UTC")
    cleaned = value.strip()
    if not cleaned or any(ch.isspace() for ch in cleaned):
        raise ValueError("Timezone must be a valid region-based IANA identifier or UTC")

    if cleaned == "UTC":
        load_timezone("UTC")
        return cleaned

    parts = cleaned.split("/")
    if len(parts) < 2 or parts[0] not in _IANA_REGIONS:
        raise ValueError("Timezone must be a valid region-based IANA identifier or UTC")
    if any(not segment or segment in {".", ".."} for segment in parts):
        raise ValueError("Timezone must be a valid region-based IANA identifier or UTC")

    try:
        load_timezone(cleaned)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        raise ValueError("Timezone must be a valid region-based IANA identifier or UTC") from None

    return cleaned


def validate_date_format(value: str) -> str:
    """Validate YYYY-MM-DD syntax without echoing the submitted date."""
    try:
        return normalize_date_text(value)
    except CalendarDateError as exc:
        raise PydanticCustomError(exc.code, str(exc)) from None


def validate_time_format(value: str) -> str:
    """Validate HH:MM or HH:MM:SS local wall time without echoing submitted values."""
    if not isinstance(value, str):
        raise ValueError("Local birth time must use HH:MM or HH:MM:SS format")
    cleaned = value.strip()
    if not _TIME_PATTERN.fullmatch(cleaned):
        raise ValueError("Local birth time must use HH:MM or HH:MM:SS format")
    try:
        datetime.time.fromisoformat(cleaned)
    except ValueError:
        raise ValueError("Local birth time is invalid") from None
    return cleaned


def validate_birth_profile_state(
    *,
    label: str,
    input_calendar: InputCalendar,
    entered_date: str,
    time_certainty: TimeCertainty,
    time_local: str | None,
    place_name: str,
    latitude: float,
    longitude: float,
    timezone: str,
) -> ValidatedProfileData:
    """Validate complete birth profile consistency with strictly PII-free errors."""
    clean_label = _validate_non_empty_text(label, field_label="Label", max_length=120)
    clean_place = _validate_non_empty_text(place_name, field_label="Place name", max_length=200)
    clean_lat = _validate_coordinate(latitude, name="Latitude", minimum=-90.0, maximum=90.0)
    clean_lon = _validate_coordinate(longitude, name="Longitude", minimum=-180.0, maximum=180.0)
    clean_tz = validate_iana_timezone(timezone)
    clean_date = normalize_date_text(entered_date)

    parsed_ad_date = (
        parse_ad_date(clean_date)
        if input_calendar == InputCalendar.AD
        else bs_to_ad(BikramSambatDate.parse(clean_date))
    )

    # Birth-time certainty validation: keep unknown strictly separate from clock times.
    clean_time: str | None
    parsed_time: datetime.time | None = None
    if time_certainty == TimeCertainty.UNKNOWN:
        if time_local is not None:
            raise ValueError("Local birth time must be omitted when time certainty is unknown")
        clean_time = None
    else:
        if time_local is None:
            raise ValueError("Local birth time is required unless time certainty is unknown")
        clean_time = validate_time_format(time_local)
        parsed_time = datetime.time.fromisoformat(clean_time)

    # Reject impossible DST gaps and ambiguous DST overlaps for resolved single-instant AD times.
    if parsed_time is not None:
        try:
            convert_local_to_utc_jd(
                TimeInput(
                    date=parsed_ad_date,
                    time=parsed_time,
                    latitude=clean_lat,
                    longitude=clean_lon,
                    timezone=clean_tz,
                )
            )
        except TimeConversionError as exc:
            if exc.code == "dst_gap":
                raise TimeConversionError(
                    "A clock change skipped this local birth time", code=exc.code
                ) from None
            if exc.code == "dst_overlap":
                raise TimeConversionError(
                    "A clock change repeated this local birth time", code=exc.code
                ) from None
            raise ValueError(
                "Invalid birth date, time, coordinate, or timezone combination"
            ) from None

    return ValidatedProfileData(
        label=clean_label,
        input_calendar=input_calendar,
        entered_date=clean_date,
        date_ad=parsed_ad_date.isoformat(),
        bs_conversion_status="resolved",
        time_certainty=time_certainty,
        time_local=clean_time,
        place_name=clean_place,
        latitude=clean_lat,
        longitude=clean_lon,
        timezone=clean_tz,
    )


class BirthProfileLocationFields(BaseModel):
    """Accept verified search selections or the existing manual location fields."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    location_id: int | None = Field(default=None, strict=True, gt=0)
    place_name: str | None = Field(default=None, min_length=1, max_length=200)
    latitude: float | None = None
    longitude: float | None = None
    timezone: str | None = None

    @model_validator(mode="before")
    @classmethod
    def resolve_selected_location(cls, value: object) -> object:
        if not isinstance(value, dict) or value.get("location_id") is None:
            return value
        location_id = value["location_id"]
        place = resolve_birthplace(location_id) if type(location_id) is int else None
        if place is None:
            raise PydanticCustomError("invalid_birthplace", "Select an available birthplace")
        # Location fields from the request are ignored whenever a selection is supplied.
        return {
            **value,
            "place_name": place.profile_name,
            "latitude": place.latitude,
            "longitude": place.longitude,
            "timezone": place.timezone,
        }

    @field_validator("latitude")
    @classmethod
    def check_latitude(cls, v: float | None) -> float | None:
        return (
            None
            if v is None
            else _validate_coordinate(v, name="Latitude", minimum=-90.0, maximum=90.0)
        )

    @field_validator("longitude")
    @classmethod
    def check_longitude(cls, v: float | None) -> float | None:
        return (
            None
            if v is None
            else _validate_coordinate(v, name="Longitude", minimum=-180.0, maximum=180.0)
        )

    @field_validator("timezone")
    @classmethod
    def check_timezone(cls, v: str | None) -> str | None:
        return None if v is None else validate_iana_timezone(v)


class BirthProfileCreate(BirthProfileLocationFields):
    """Payload to create an encrypted birth profile."""

    label: str = Field(min_length=1, max_length=120)
    input_calendar: InputCalendar
    entered_date: str
    time_certainty: TimeCertainty
    time_local: str | None = None

    @field_validator("entered_date")
    @classmethod
    def check_entered_date(cls, v: str) -> str:
        """Validate birth date syntax without echoing submitted date."""
        return validate_date_format(v)

    @field_validator("time_local")
    @classmethod
    def check_time_local(cls, v: str | None) -> str | None:
        """Validate local birth time syntax when provided."""
        if v is None:
            return None
        return validate_time_format(v)

    def validated(self) -> ValidatedProfileData:
        if (
            self.place_name is None
            or self.latitude is None
            or self.longitude is None
            or self.timezone is None
        ):
            raise PydanticCustomError(
                "missing_birthplace",
                "Enter complete manual location details or select a birthplace",
            )
        return validate_birth_profile_state(
            label=self.label,
            input_calendar=self.input_calendar,
            entered_date=self.entered_date,
            time_certainty=self.time_certainty,
            time_local=self.time_local,
            place_name=self.place_name,
            latitude=self.latitude,
            longitude=self.longitude,
            timezone=self.timezone,
        )

    @model_validator(mode="after")
    def validate_cross_field_consistency(self) -> BirthProfileCreate:
        try:
            validated = self.validated()
        except (CalendarDateError, TimeConversionError) as exc:
            raise PydanticCustomError(exc.code, str(exc)) from None
        self.label = validated.label
        self.entered_date = validated.entered_date
        self.time_local = validated.time_local
        self.place_name = validated.place_name
        self.latitude = validated.latitude
        self.longitude = validated.longitude
        self.timezone = validated.timezone
        return self


class BirthProfileUpdate(BirthProfileLocationFields):
    """Partial update payload validated against the merged existing birth profile."""

    label: str | None = Field(default=None, min_length=1, max_length=120)
    input_calendar: InputCalendar | None = None
    entered_date: str | None = None
    time_certainty: TimeCertainty | None = None
    time_local: str | None = None

    @field_validator("entered_date")
    @classmethod
    def check_entered_date(cls, v: str | None) -> str | None:
        """Validate optional birth date syntax without echoing submitted date."""
        if v is None:
            return None
        return validate_date_format(v)

    @field_validator("time_local")
    @classmethod
    def check_time_local(cls, v: str | None) -> str | None:
        """Validate optional local birth time syntax without echoing submitted value."""
        if v is None:
            return None
        return validate_time_format(v)

    @model_validator(mode="after")
    def reject_null_on_required_fields(self) -> BirthProfileUpdate:
        """Prevent explicitly passing null to non-nullable birth profile fields."""
        non_nullable = (
            "label",
            "input_calendar",
            "entered_date",
            "time_certainty",
            "place_name",
            "latitude",
            "longitude",
            "timezone",
        )
        for field_name in non_nullable:
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name.replace('_', ' ').capitalize()} cannot be null")
        return self


class BirthProfileResponse(BaseModel):
    """Decrypted birth profile returned exclusively to its authenticated owner."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    owner_id: uuid.UUID
    label: str
    input_calendar: InputCalendar
    entered_date: str
    date_ad: str | None
    bs_conversion_status: BsConversionStatus
    time_certainty: TimeCertainty
    time_local: str | None
    place_name: str
    latitude: float
    longitude: float
    timezone: str
    created_at: datetime.datetime
    updated_at: datetime.datetime


class BirthProfileListResponse(BaseModel):
    """Paginated list of decrypted birth profiles owned by the caller."""

    items: list[BirthProfileResponse]
    total: int
    limit: int
    offset: int
