"""Unit tests for timeconv module (local time, timezone, and Julian Day)."""

from __future__ import annotations

import datetime
from typing import Any

import pytest

import app.calc.timeconv as timeconv_mod
from app.calc.ayanamsha import CalculationError
from app.calc.timeconv import TimeConversionError, TimeInput, convert_local_to_utc_jd
from app.calc.timezones import load_timezone


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


@pytest.mark.parametrize(
    ("local", "utc", "offset_seconds"),
    [
        ("1919-12-31T23:48:43", "1919-12-31T18:07:27+00:00", 20476),
        ("1920-01-01T00:00:00", "1919-12-31T18:30:00+00:00", 19800),
        ("1985-12-31T23:59:59", "1985-12-31T18:29:59+00:00", 19800),
        ("1986-01-01T00:15:00", "1985-12-31T18:30:00+00:00", 20700),
    ],
)
def test_nepal_historical_utc_offsets(local: str, utc: str, offset_seconds: int) -> None:
    wall_time = datetime.datetime.fromisoformat(local)
    result = convert_local_to_utc_jd(
        TimeInput(
            date=wall_time.date(),
            time=wall_time.time(),
            latitude=27.7,
            longitude=85.3,
            timezone="Asia/Kathmandu",
        )
    )
    assert result.datetime_utc == datetime.datetime.fromisoformat(utc)
    assert result.utc_offset_hours * 3600 == pytest.approx(offset_seconds)


@pytest.mark.parametrize(
    ("local", "code"),
    [
        ("1919-12-31T23:48:44", "dst_overlap"),
        ("1919-12-31T23:59:59", "dst_overlap"),
        ("1986-01-01T00:00:00", "dst_gap"),
        ("1986-01-01T00:14:59", "dst_gap"),
    ],
)
def test_nepal_historical_clock_changes_reject_ambiguous_and_skipped_times(
    local: str, code: str
) -> None:
    wall_time = datetime.datetime.fromisoformat(local)
    with pytest.raises(TimeConversionError) as error:
        convert_local_to_utc_jd(
            TimeInput(
                date=wall_time.date(),
                time=wall_time.time(),
                latitude=27.7,
                longitude=85.3,
                timezone="Asia/Kathmandu",
            )
        )
    assert error.value.code == code


def test_pinned_timezone_is_loaded_independently_of_system_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import zoneinfo

    monkeypatch.setattr(zoneinfo, "TZPATH", ())
    assert load_timezone("Asia/Kathmandu").key == "Asia/Kathmandu"
    with pytest.raises(zoneinfo.ZoneInfoNotFoundError):
        load_timezone("../UTC")


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


def test_latitude_longitude_bounds_and_finiteness() -> None:
    """Latitude (-90..90) and longitude (-180..180) must be finite and in bounds."""
    valid_date = datetime.date(2020, 1, 1)
    valid_time = datetime.time(12, 0, 0)

    for bad_lat in (91.0, -90.1, float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError, match="(?i)latitude"):
            convert_local_to_utc_jd(
                TimeInput(
                    date=valid_date,
                    time=valid_time,
                    latitude=bad_lat,
                    longitude=0.0,
                    utc_offset_hours=0.0,
                )
            )

    for bad_lon in (180.1, -180.1, float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError, match="(?i)longitude"):
            convert_local_to_utc_jd(
                TimeInput(
                    date=valid_date,
                    time=valid_time,
                    latitude=0.0,
                    longitude=bad_lon,
                    utc_offset_hours=0.0,
                )
            )


def test_utc_offset_bounds_and_finiteness() -> None:
    """UTC offset hours must be finite and strictly between -24 and +24."""
    valid_date = datetime.date(2020, 1, 1)
    valid_time = datetime.time(12, 0, 0)

    for ok_offset in (-23.75, -12.0, 0.0, 5.75, 14.0, 23.75):
        res = convert_local_to_utc_jd(
            TimeInput(
                date=valid_date,
                time=valid_time,
                latitude=0.0,
                longitude=0.0,
                utc_offset_hours=ok_offset,
            )
        )
        assert res.utc_offset_hours == pytest.approx(ok_offset)

    for bad_offset in (-24.0, 24.0, 48.0, float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError):
            convert_local_to_utc_jd(
                TimeInput(
                    date=valid_date,
                    time=valid_time,
                    latitude=0.0,
                    longitude=0.0,
                    utc_offset_hours=bad_offset,
                )
            )


def test_dst_gap_nonexistent_time_rejected() -> None:
    """Nonexistent local time in a DST gap raises TimeConversionError(code='dst_gap')."""
    with pytest.raises(TimeConversionError, match="Nonexistent|gap") as exc_info:
        convert_local_to_utc_jd(
            TimeInput(
                date=datetime.date(2024, 3, 10),
                time=datetime.time(2, 30, 0),
                latitude=40.7128,
                longitude=-74.0060,
                timezone="America/New_York",
            )
        )
    assert exc_info.value.code == "dst_gap"
    assert isinstance(exc_info.value, ValueError)
    assert not isinstance(exc_info.value, CalculationError)


def test_dst_overlap_ambiguous_time_rejected() -> None:
    """Ambiguous local time in a DST overlap raises TimeConversionError(code='dst_overlap')."""
    with pytest.raises(TimeConversionError, match="Ambiguous|overlap") as exc_info:
        convert_local_to_utc_jd(
            TimeInput(
                date=datetime.date(2024, 11, 3),
                time=datetime.time(1, 30, 0),
                latitude=40.7128,
                longitude=-74.0060,
                timezone="America/New_York",
            )
        )
    assert exc_info.value.code == "dst_overlap"
    assert isinstance(exc_info.value, ValueError)
    assert not isinstance(exc_info.value, CalculationError)


def test_invalid_timezone_raises_distinguishable_time_conversion_error() -> None:
    """Unknown timezone raises TimeConversionError distinguishable from plain ValueError."""
    with pytest.raises(TimeConversionError) as exc_info:
        convert_local_to_utc_jd(
            TimeInput(
                date=datetime.date(2020, 1, 1),
                time=datetime.time(12, 0, 0),
                latitude=0.0,
                longitude=0.0,
                timezone="Mars/Olympus_Mons",
            )
        )
    assert exc_info.value.code == "invalid_timezone"
    assert type(exc_info.value) is TimeConversionError


def test_missing_and_conflicting_timezone_spec() -> None:
    """Must provide either timezone or utc_offset_hours, not both or neither."""
    valid_date = datetime.date(2020, 1, 1)
    valid_time = datetime.time(12, 0, 0)

    with pytest.raises(ValueError, match="Either timezone or utc_offset_hours"):
        convert_local_to_utc_jd(
            TimeInput(date=valid_date, time=valid_time, latitude=0.0, longitude=0.0)
        )

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


def test_swe_julday_failure_raises_calculation_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Internal swe_julday failures raise CalculationError, not TimeConversionError."""

    class _FakeSweBadJd:
        def swe_julday(self, *_args: Any) -> float:
            return float("nan")

    monkeypatch.setattr(timeconv_mod, "get_swe_engine", lambda: _FakeSweBadJd())
    with pytest.raises(CalculationError):
        convert_local_to_utc_jd(
            TimeInput(
                date=datetime.date(2020, 1, 1),
                time=datetime.time(12, 0, 0),
                latitude=0.0,
                longitude=0.0,
                utc_offset_hours=0.0,
            )
        )

    class _FakeSweRaises:
        def swe_julday(self, *_args: Any) -> float:
            raise OSError("FFI failure")

    monkeypatch.setattr(timeconv_mod, "get_swe_engine", lambda: _FakeSweRaises())
    with pytest.raises(CalculationError):
        convert_local_to_utc_jd(
            TimeInput(
                date=datetime.date(2020, 1, 1),
                time=datetime.time(12, 0, 0),
                latitude=0.0,
                longitude=0.0,
                utc_offset_hours=0.0,
            )
        )
