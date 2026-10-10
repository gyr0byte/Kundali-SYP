"""Time conversion module: local time to UTC and Julian Day (UT).

Converts birth date, local time, and location into UTC and Julian Day,
with strict validation of timezones, offsets, and coordinates.
"""

from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field
from swisseph_ffi import SE_GREG_CAL, SwissEph  # type: ignore[import-untyped]

_SWE_INSTANCE: SwissEph | None = None


def _get_swe() -> SwissEph:
    global _SWE_INSTANCE
    if _SWE_INSTANCE is None:
        _SWE_INSTANCE = SwissEph()
    return _SWE_INSTANCE


class TimeInput(BaseModel):
    """Input parameters for birth time and place."""

    model_config = ConfigDict(extra="forbid")

    date: datetime.date
    time: datetime.time
    latitude: float = Field(ge=-90.0, le=90.0, description="Latitude in decimal degrees")
    longitude: float = Field(ge=-180.0, le=180.0, description="Longitude in decimal degrees")
    timezone: str | None = None
    utc_offset_hours: float | None = None


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

    Raises ValueError for invalid lat/long, nonexistent local times (DST gaps),
    or ambiguous local times (DST overlaps).
    """
    if inp.latitude < -90.0 or inp.latitude > 90.0:
        raise ValueError(f"Latitude must be between -90 and 90, got {inp.latitude}")
    if inp.longitude < -180.0 or inp.longitude > 180.0:
        raise ValueError(f"Longitude must be between -180 and 180, got {inp.longitude}")

    if inp.timezone is None and inp.utc_offset_hours is None:
        raise ValueError("Either timezone or utc_offset_hours must be provided.")
    if inp.timezone is not None and inp.utc_offset_hours is not None:
        raise ValueError("Only one of timezone or utc_offset_hours must be provided, not both.")

    naive_dt = datetime.datetime.combine(inp.date, inp.time)

    if inp.timezone is not None:
        try:
            tz = ZoneInfo(inp.timezone)
        except Exception as exc:
            raise ValueError(f"Invalid IANA timezone name: {inp.timezone}") from exc

        dt_fold0 = naive_dt.replace(tzinfo=tz, fold=0)
        dt_fold1 = naive_dt.replace(tzinfo=tz, fold=1)
        rt0 = dt_fold0.astimezone(datetime.UTC).astimezone(tz)
        rt1 = dt_fold1.astimezone(datetime.UTC).astimezone(tz)
        rt0_ok = rt0.replace(tzinfo=None) == naive_dt
        rt1_ok = rt1.replace(tzinfo=None) == naive_dt

        # Detect nonexistent times (DST gap, e.g. clocks jumped forward 2:00 -> 3:00)
        if not rt0_ok and not rt1_ok:
            raise ValueError(
                f"Nonexistent local time in DST gap: {naive_dt} in {inp.timezone}. "
                "This wall-clock time was skipped by daylight saving."
            )

        # Detect ambiguous times (DST overlap, e.g. clocks turned back 2:00 -> 1:00)
        if dt_fold0.utcoffset() != dt_fold1.utcoffset():
            raise ValueError(
                f"Ambiguous local time in DST overlap: {naive_dt} in {inp.timezone}. "
                "Specify exact UTC offset or disambiguated time."
            )

        utc_dt = dt_fold0.astimezone(datetime.UTC)
        offset = dt_fold0.utcoffset()
        assert offset is not None
        offset_hours = offset.total_seconds() / 3600.0
        tz_name = inp.timezone
    else:
        assert inp.utc_offset_hours is not None
        offset_delta = datetime.timedelta(hours=inp.utc_offset_hours)
        tz_fixed = datetime.timezone(offset_delta)
        aware_local = naive_dt.replace(tzinfo=tz_fixed)
        utc_dt = aware_local.astimezone(datetime.UTC)
        offset_hours = inp.utc_offset_hours
        tz_name = None

    # Compute Julian Day (UT)
    utc_hour_dec = (
        utc_dt.hour
        + utc_dt.minute / 60.0
        + utc_dt.second / 3600.0
        + utc_dt.microsecond / 3_600_000_000.0
    )
    swe = _get_swe()
    jd: float = swe.swe_julday(utc_dt.year, utc_dt.month, utc_dt.day, utc_hour_dec, SE_GREG_CAL)

    return TimeConversionResult(
        date_local=inp.date,
        time_local=inp.time,
        datetime_utc=utc_dt,
        julian_day=jd,
        utc_offset_hours=offset_hours,
        timezone_name=tz_name,
        latitude=inp.latitude,
        longitude=inp.longitude,
    )
