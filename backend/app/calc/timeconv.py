"""Time conversion module: local time to UTC and Julian Day (UT).

Converts birth date, local time, and location into UTC and Julian Day,
with strict validation of timezones, offsets, and coordinates.
"""

from __future__ import annotations

import datetime
import math
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from swisseph_ffi import SE_GREG_CAL  # type: ignore[import-untyped]

from app.calc.ayanamsha import SWE_LOCK, CalculationError, get_swe_engine


class TimeConversionError(ValueError):
    """Raised for expected local time, timezone, coordinate, or DST input errors.

    Inherits from ``ValueError`` for validation compatibility while carrying an
    explicit machine-readable ``code`` distinct from unexpected runtime errors.
    """

    def __init__(self, message: str, *, code: str = "invalid_time_input") -> None:
        super().__init__(message)
        self.code = code


def _validate_finite_float(value: float, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TimeConversionError(f"{name} must be a numeric value.", code="invalid_numeric")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise TimeConversionError(f"{name} must be a finite number.", code="non_finite_numeric")
    return 0.0 if numeric == 0.0 else numeric


class TimeInput(BaseModel):
    """Input parameters for birth time and place."""

    model_config = ConfigDict(extra="forbid")

    date: datetime.date
    time: datetime.time
    latitude: float = Field(ge=-90.0, le=90.0, description="Latitude in decimal degrees")
    longitude: float = Field(ge=-180.0, le=180.0, description="Longitude in decimal degrees")
    timezone: str | None = None
    utc_offset_hours: float | None = None

    @field_validator("latitude")
    @classmethod
    def check_latitude_finite(cls, v: float) -> float:
        """Ensure latitude is finite and normalize negative zero."""
        return _validate_finite_float(v, name="Latitude")

    @field_validator("longitude")
    @classmethod
    def check_longitude_finite(cls, v: float) -> float:
        """Ensure longitude is finite and normalize negative zero."""
        return _validate_finite_float(v, name="Longitude")

    @field_validator("utc_offset_hours")
    @classmethod
    def check_utc_offset_hours(cls, v: float | None) -> float | None:
        """Validate finite UTC offset strictly within Python's (-24, +24) hour limits."""
        if v is None:
            return None
        numeric = _validate_finite_float(v, name="UTC offset hours")
        if numeric <= -24.0 or numeric >= 24.0:
            raise TimeConversionError(
                f"utc_offset_hours must be strictly between -24 and 24, got {numeric}",
                code="invalid_utc_offset",
            )
        return numeric

    @field_validator("timezone")
    @classmethod
    def check_timezone_non_empty(cls, v: str | None) -> str | None:
        """Strip non-empty timezone strings."""
        if v is None:
            return None
        cleaned = v.strip()
        if not cleaned:
            raise TimeConversionError("Timezone must not be blank.", code="invalid_timezone")
        return cleaned

    @model_validator(mode="after")
    def check_timezone_or_offset_present(self) -> TimeInput:
        """Require exactly one of timezone or utc_offset_hours."""
        if self.timezone is None and self.utc_offset_hours is None:
            raise TimeConversionError(
                "Either timezone or utc_offset_hours must be provided.",
                code="missing_timezone_spec",
            )
        if self.timezone is not None and self.utc_offset_hours is not None:
            raise TimeConversionError(
                "Only one of timezone or utc_offset_hours must be provided, not both.",
                code="conflicting_timezone_spec",
            )
        return self


class TimeConversionResult(BaseModel):
    """Normalized astronomical time context."""

    model_config = ConfigDict(extra="forbid")

    date_local: datetime.date
    time_local: datetime.time
    datetime_utc: datetime.datetime
    julian_day: float
    utc_offset_hours: float
    timezone_name: str | None
    latitude: float
    longitude: float


def convert_local_to_utc_jd(inp: TimeInput) -> TimeConversionResult:
    """Convert local birth time and coordinates to UTC and Julian Day (UT).

    Raises TimeConversionError (a ValueError subclass) for invalid coordinates/offsets/
    timezones, nonexistent local times (DST gaps), or ambiguous local times (DST overlaps).
    Raises CalculationError if Swiss Ephemeris fails to produce a finite Julian Day.
    """
    lat = _validate_finite_float(inp.latitude, name="Latitude")
    lon = _validate_finite_float(inp.longitude, name="Longitude")
    if lat < -90.0 or lat > 90.0:
        raise TimeConversionError(
            f"Latitude must be between -90 and 90, got {lat}",
            code="invalid_coordinates",
        )
    if lon < -180.0 or lon > 180.0:
        raise TimeConversionError(
            f"Longitude must be between -180 and 180, got {lon}",
            code="invalid_coordinates",
        )

    if inp.timezone is None and inp.utc_offset_hours is None:
        raise TimeConversionError(
            "Either timezone or utc_offset_hours must be provided.",
            code="missing_timezone_spec",
        )
    if inp.timezone is not None and inp.utc_offset_hours is not None:
        raise TimeConversionError(
            "Only one of timezone or utc_offset_hours must be provided, not both.",
            code="conflicting_timezone_spec",
        )

    naive_dt = datetime.datetime.combine(inp.date, inp.time)

    if inp.timezone is not None:
        tz_clean = inp.timezone.strip()
        if not tz_clean:
            raise TimeConversionError("Invalid IANA timezone name.", code="invalid_timezone")
        try:
            tz = ZoneInfo(tz_clean)
        except Exception as exc:
            raise TimeConversionError(
                f"Invalid IANA timezone name: {inp.timezone}",
                code="invalid_timezone",
            ) from exc

        dt_fold0 = naive_dt.replace(tzinfo=tz, fold=0)
        dt_fold1 = naive_dt.replace(tzinfo=tz, fold=1)
        rt0 = dt_fold0.astimezone(datetime.UTC).astimezone(tz)
        rt1 = dt_fold1.astimezone(datetime.UTC).astimezone(tz)
        rt0_ok = rt0.replace(tzinfo=None) == naive_dt
        rt1_ok = rt1.replace(tzinfo=None) == naive_dt

        # Detect nonexistent times (DST gap, e.g. clocks jumped forward 2:00 -> 3:00)
        if not rt0_ok and not rt1_ok:
            raise TimeConversionError(
                f"Nonexistent local time in DST gap: {naive_dt} in {tz_clean}. "
                "This wall-clock time was skipped by daylight saving.",
                code="dst_gap",
            )

        # Detect ambiguous times (DST overlap, e.g. clocks turned back 2:00 -> 1:00)
        if dt_fold0.utcoffset() != dt_fold1.utcoffset():
            raise TimeConversionError(
                f"Ambiguous local time in DST overlap: {naive_dt} in {tz_clean}. "
                "Specify exact UTC offset or disambiguated time.",
                code="dst_overlap",
            )

        utc_dt = dt_fold0.astimezone(datetime.UTC)
        offset = dt_fold0.utcoffset()
        if offset is None:
            raise TimeConversionError(
                f"Unable to determine UTC offset for timezone: {tz_clean}",
                code="invalid_timezone",
            )
        offset_hours = offset.total_seconds() / 3600.0
        tz_name: str | None = tz_clean
    else:
        assert inp.utc_offset_hours is not None
        offset_hours = _validate_finite_float(inp.utc_offset_hours, name="UTC offset hours")
        if offset_hours <= -24.0 or offset_hours >= 24.0:
            raise TimeConversionError(
                f"utc_offset_hours must be strictly between -24 and 24, got {offset_hours}",
                code="invalid_utc_offset",
            )
        offset_delta = datetime.timedelta(hours=offset_hours)
        tz_fixed = datetime.timezone(offset_delta)
        aware_local = naive_dt.replace(tzinfo=tz_fixed)
        utc_dt = aware_local.astimezone(datetime.UTC)
        tz_name = None

    # Compute Julian Day (UT) using shared synchronized engine instance
    utc_hour_dec = (
        utc_dt.hour
        + utc_dt.minute / 60.0
        + utc_dt.second / 3600.0
        + utc_dt.microsecond / 3_600_000_000.0
    )
    with SWE_LOCK:
        swe = get_swe_engine()
        try:
            jd = float(
                swe.swe_julday(utc_dt.year, utc_dt.month, utc_dt.day, utc_hour_dec, SE_GREG_CAL)
            )
        except Exception as exc:
            raise CalculationError("Swiss Ephemeris Julian Day computation failed.") from exc

    if not math.isfinite(jd):
        raise CalculationError("Swiss Ephemeris returned a non-finite Julian Day.")

    return TimeConversionResult(
        date_local=inp.date,
        time_local=inp.time,
        datetime_utc=utc_dt,
        julian_day=jd,
        utc_offset_hours=offset_hours,
        timezone_name=tz_name,
        latitude=lat,
        longitude=lon,
    )
