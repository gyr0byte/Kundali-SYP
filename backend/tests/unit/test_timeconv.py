"""Unit tests for timeconv module (local time, timezone, and Julian Day)."""

from __future__ import annotations

import datetime

import pytest

from app.calc.timeconv import TimeInput, convert_local_to_utc_jd


def test_julian_day_j2000_epoch() -> None:
    """2000-01-01 12:00 UT must equal exactly 2451545.0."""
    result = convert_local_to_utc_jd(
        TimeInput(
            date=datetime.date(2000, 1, 1),
            time=datetime.time(12, 0, 0),
            latitude=0.0,
            longitude=0.0,
            utc_offset_hours=0.0,
        )
    )
    assert result.julian_day == pytest.approx(2451545.0, abs=1e-7)
    assert result.datetime_utc == datetime.datetime(2000, 1, 1, 12, 0, 0, tzinfo=datetime.UTC)


def test_nepal_timezone_45_min_offset() -> None:
    """Asia/Kathmandu (+5:45) is correctly converted to UTC and Julian Day."""
    # 2006-08-02 02:10:00 NPT -> 2006-08-01 20:25:00 UTC
    result = convert_local_to_utc_jd(
        TimeInput(
            date=datetime.date(2006, 8, 2),
            time=datetime.time(2, 10, 0),
            latitude=26.45,
            longitude=87.283,
            timezone="Asia/Kathmandu",
        )
    )
    expected_utc = datetime.datetime(2006, 8, 1, 20, 25, 0, tzinfo=datetime.UTC)
    assert result.datetime_utc == expected_utc
    assert result.utc_offset_hours == pytest.approx(5.75, abs=1e-5)
    # 20 + 25/60 = 20.4166667 UT hour on 2006-08-01
    assert result.julian_day == pytest.approx(2453949.3506944, abs=1e-5)


def test_nepal_explicit_utc_offset() -> None:
    """Explicit UTC offset 5.75 produces the same result as Asia/Kathmandu."""
    res_tz = convert_local_to_utc_jd(
        TimeInput(
            date=datetime.date(2006, 8, 2),
            time=datetime.time(2, 10, 0),
            latitude=26.45,
            longitude=87.283,
            timezone="Asia/Kathmandu",
        )
    )
    res_offset = convert_local_to_utc_jd(
        TimeInput(
            date=datetime.date(2006, 8, 2),
            time=datetime.time(2, 10, 0),
            latitude=26.45,
            longitude=87.283,
            utc_offset_hours=5.75,
        )
    )
    assert res_tz.datetime_utc == res_offset.datetime_utc
    assert res_tz.julian_day == res_offset.julian_day


def test_latitude_longitude_bounds() -> None:
    """Latitude must be -90..90 and longitude -180..180."""
    valid_date = datetime.date(2020, 1, 1)
    valid_time = datetime.time(12, 0, 0)

    # Invalid latitude
    with pytest.raises(ValueError, match="(?i)latitude"):
        convert_local_to_utc_jd(
            TimeInput(date=valid_date, time=valid_time, latitude=91.0, longitude=0.0, utc_offset_hours=0.0)
        )
    with pytest.raises(ValueError, match="(?i)latitude"):
        convert_local_to_utc_jd(
            TimeInput(date=valid_date, time=valid_time, latitude=-90.1, longitude=0.0, utc_offset_hours=0.0)
        )

    # Invalid longitude
    with pytest.raises(ValueError, match="(?i)longitude"):
        convert_local_to_utc_jd(
            TimeInput(date=valid_date, time=valid_time, latitude=0.0, longitude=180.1, utc_offset_hours=0.0)
        )
    with pytest.raises(ValueError, match="(?i)longitude"):
        convert_local_to_utc_jd(
            TimeInput(date=valid_date, time=valid_time, latitude=0.0, longitude=-180.1, utc_offset_hours=0.0)
        )


def test_dst_gap_nonexistent_time_rejected() -> None:
    """Nonexistent local time in a DST gap (America/New_York) must raise ValueError."""
    # 2024-03-10 02:30:00 does not exist in America/New_York (clocks jump 02:00 -> 03:00)
    with pytest.raises(ValueError, match="Nonexistent|gap"):
        convert_local_to_utc_jd(
            TimeInput(
                date=datetime.date(2024, 3, 10),
                time=datetime.time(2, 30, 0),
                latitude=40.7128,
                longitude=-74.0060,
                timezone="America/New_York",
            )
        )


def test_dst_overlap_ambiguous_time_rejected() -> None:
    """Ambiguous local time in a DST overlap (America/New_York) must raise ValueError."""
    # 2024-11-03 01:30:00 occurs twice in America/New_York (clocks jump 02:00 -> 01:00)
    with pytest.raises(ValueError, match="Ambiguous|overlap"):
        convert_local_to_utc_jd(
            TimeInput(
                date=datetime.date(2024, 11, 3),
                time=datetime.time(1, 30, 0),
                latitude=40.7128,
                longitude=-74.0060,
                timezone="America/New_York",
            )
        )


def test_missing_and_conflicting_timezone_spec() -> None:
    """Must provide either timezone or utc_offset_hours, not both or neither."""
    valid_date = datetime.date(2020, 1, 1)
    valid_time = datetime.time(12, 0, 0)

    # Neither provided
    with pytest.raises(ValueError, match="Either timezone or utc_offset_hours"):
        convert_local_to_utc_jd(
            TimeInput(date=valid_date, time=valid_time, latitude=0.0, longitude=0.0)
        )

    # Both provided
    with pytest.raises(ValueError, match="Only one of timezone or utc_offset_hours"):
        convert_local_to_utc_jd(
            TimeInput(
                date=valid_date,
                time=valid_time,
                latitude=0.0,
                longitude=0.0,
                timezone="Asia/Kathmandu",
                utc_offset_hours=5.75,
            )
        )
