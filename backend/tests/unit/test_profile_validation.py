"""Unit tests for birth profile schemas, validation rules, and privacy guarantees."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.schemas.profile import (
    BirthProfileCreate,
    BirthProfileUpdate,
    validate_birth_profile_state,
    validate_iana_timezone,
)
from app.db.models.profile import InputCalendar, TimeCertainty


def _valid_create_kwargs(**overrides: object) -> dict[str, object]:
    """Return valid AD exact birth profile input kwargs."""
    base: dict[str, object] = {
        "label": "Asha Birth",
        "input_calendar": "AD",
        "entered_date": "1998-07-31",
        "time_certainty": "exact",
        "time_local": "08:30",
        "place_name": "Kathmandu, Nepal",
        "latitude": 27.7172,
        "longitude": 85.3240,
        "timezone": "Asia/Kathmandu",
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize("tz_name", ["Asia/Kathmandu", "Europe/London", "UTC", "America/New_York"])
def test_validate_iana_timezone_accepts_region_and_utc(tz_name: str) -> None:
    """Region-based IANA identifiers and UTC are accepted."""
    assert validate_iana_timezone(tz_name) == tz_name


@pytest.mark.parametrize(
    "bad_tz",
    [
        "",
        "   ",
        "EST",
        "NPT",
        "IST",
        "GMT",
        "HST",
        "Invalid/Zone",
        "Etc/UTC",
        "Etc/GMT+5",
        "US/Eastern",
        "SystemV/EST5",
        "asia/kathmandu",
        "Asia / Kathmandu",
    ],
)
def test_validate_iana_timezone_rejects_abbreviations_and_invalid_ids(bad_tz: str) -> None:
    """Abbreviations and non-region timezone strings are rejected without echoing input."""
    with pytest.raises(ValueError) as exc_info:
        validate_iana_timezone(bad_tz)
    if bad_tz.strip():
        assert bad_tz.strip() not in str(exc_info.value)


def test_bs_calendar_broad_bounds_and_awaiting_conversion_state() -> None:
    """BS dates receive format and broad numeric checks and preserve date_ad=None."""
    # Day 32 is valid in some BS months; broad bounds accept 1..32 without claiming exact calendar.
    validated = validate_birth_profile_state(
        label="BS Profile",
        input_calendar=InputCalendar.BS,
        entered_date="2055-04-32",
        time_certainty=TimeCertainty.EXACT,
        time_local="06:15:30",
        place_name="Patan, Nepal",
        latitude=27.6644,
        longitude=85.3188,
        timezone="Asia/Kathmandu",
    )
    assert validated.date_ad is None
    assert validated.bs_conversion_status == "awaiting_bs_conversion"
    assert validated.time_local == "06:15:30"

    # Out-of-bounds BS year, month, and day fail cleanly without echoing submitted date
    bad_bs_dates = (
        "1899-04-15",
        "2201-04-15",
        "2055-00-15",
        "2055-13-15",
        "2055-04-00",
        "2055-04-33",
    )
    for bad_bs in bad_bs_dates:
        with pytest.raises(ValueError) as exc_info:
            validate_birth_profile_state(
                label="Bad BS",
                input_calendar=InputCalendar.BS,
                entered_date=bad_bs,
                time_certainty=TimeCertainty.UNKNOWN,
                time_local=None,
                place_name="Kathmandu",
                latitude=27.7172,
                longitude=85.3240,
                timezone="Asia/Kathmandu",
            )
        assert bad_bs not in str(exc_info.value)


def test_ad_calendar_rejects_invalid_gregorian_date() -> None:
    """AD calendar rejects impossible Gregorian dates such as February 30 without leaking date."""
    with pytest.raises(ValidationError) as exc_info:
        BirthProfileCreate(**_valid_create_kwargs(entered_date="1999-02-30"))
    errors_no_input = exc_info.value.errors(include_input=False)
    assert "1999-02-30" not in str(errors_no_input)


def test_unknown_vs_exact_approximate_time_certainty() -> None:
    """Unknown time requires time_local=None; exact and approximate require clock times."""
    ok_unknown = BirthProfileCreate(
        **_valid_create_kwargs(time_certainty="unknown", time_local=None)
    )
    assert ok_unknown.time_local is None

    with pytest.raises(ValidationError) as exc_unknown:
        BirthProfileCreate(**_valid_create_kwargs(time_certainty="unknown", time_local="08:30"))
    assert "08:30" not in str(exc_unknown.value.errors(include_input=False))

    for cert in ("exact", "approximate"):
        with pytest.raises(ValidationError):
            BirthProfileCreate(**_valid_create_kwargs(time_certainty=cert, time_local=None))

    for bad_time in ("25:00", "12:60", "8:30", "08:30+05:45", "not-a-time"):
        with pytest.raises(ValidationError) as exc_time:
            BirthProfileCreate(**_valid_create_kwargs(time_local=bad_time))
        assert bad_time not in str(exc_time.value.errors(include_input=False))


def test_dst_gap_and_overlap_rejected_only_for_resolved_ad_times() -> None:
    """AD exact/approximate reject DST gaps and overlaps; unknown and BS stay decoupled."""
    # Spring forward gap in America/New_York: 2024-03-10 02:30 does not exist
    with pytest.raises(ValidationError) as exc_gap:
        BirthProfileCreate(
            **_valid_create_kwargs(
                entered_date="2024-03-10",
                time_certainty="exact",
                time_local="02:30",
                timezone="America/New_York",
                latitude=40.7128,
                longitude=-74.0060,
                place_name="New York, USA",
            )
        )
    gap_msg = str(exc_gap.value.errors(include_input=False))
    assert "daylight saving time gap" in gap_msg.lower()
    assert "2024-03-10" not in gap_msg
    assert "02:30" not in gap_msg
    assert "America/New_York" not in gap_msg

    # Fall back overlap in America/New_York: 2024-11-03 01:30 occurs twice
    with pytest.raises(ValidationError) as exc_overlap:
        BirthProfileCreate(
            **_valid_create_kwargs(
                entered_date="2024-11-03",
                time_certainty="approximate",
                time_local="01:30",
                timezone="America/New_York",
                latitude=40.7128,
                longitude=-74.0060,
                place_name="New York, USA",
            )
        )
    overlap_msg = str(exc_overlap.value.errors(include_input=False))
    assert "daylight saving time overlap" in overlap_msg.lower()
    assert "2024-11-03" not in overlap_msg
    assert "01:30" not in overlap_msg

    # Unknown birth time on the exact same DST transition day succeeds (never calls TimeInput)
    unknown_on_dst = BirthProfileCreate(
        **_valid_create_kwargs(
            entered_date="2024-03-10",
            time_certainty="unknown",
            time_local=None,
            timezone="America/New_York",
            latitude=40.7128,
            longitude=-74.0060,
            place_name="New York, USA",
        )
    )
    assert unknown_on_dst.time_local is None

    # BS profile does not apply AD Gregorian DST checks prior to BS->AD conversion
    bs_profile = BirthProfileCreate(
        **_valid_create_kwargs(
            input_calendar="BS",
            entered_date="2080-03-10",
            time_certainty="exact",
            time_local="02:30",
            timezone="America/New_York",
        )
    )
    assert bs_profile.input_calendar == InputCalendar.BS


@pytest.mark.parametrize(
    ("bad_lat", "bad_lon"),
    [
        (-90.0001, 0.0),
        (90.0001, 0.0),
        (0.0, -180.0001),
        (0.0, 180.0001),
        (float("nan"), 85.3240),
        (27.7172, float("inf")),
    ],
)
def test_coordinate_bounds_and_finiteness_enforced(bad_lat: float, bad_lon: float) -> None:
    """Out-of-range or non-finite coordinates fail validation cleanly."""
    with pytest.raises(ValidationError):
        BirthProfileCreate(**_valid_create_kwargs(latitude=bad_lat, longitude=bad_lon))


def test_patch_update_rejects_null_for_non_nullable_fields() -> None:
    """PATCH rejects explicit nulls for required non-nullable attributes."""
    for field_name in (
        "label",
        "input_calendar",
        "entered_date",
        "time_certainty",
        "place_name",
        "latitude",
        "longitude",
        "timezone",
    ):
        with pytest.raises(ValidationError):
            BirthProfileUpdate(**{field_name: None})

    # Null time_local is syntactically allowed on PATCH (validated against merged certainty)
    patch = BirthProfileUpdate(time_certainty=TimeCertainty.UNKNOWN, time_local=None)
    assert patch.time_local is None
