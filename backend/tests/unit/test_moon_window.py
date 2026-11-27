"""Civil-date coverage and conservative lunar categories."""

from ctypes import c_double, create_string_buffer
from datetime import UTC, date, datetime
from typing import Any

import pytest
from swisseph_ffi import SE_MOON, SEFLG_SPEED, SEFLG_SWIEPH  # type: ignore[import-untyped]

import app.calc.moon_window as moon
from app.calc.ayanamsha import SWE_LOCK, AyanamshaMode, get_swe_engine
from app.calc.ephemeris import _calc_single_body
from app.calc.timeconv import TimeConversionError


@pytest.mark.parametrize(
    ("day", "timezone", "expected_seconds"),
    [
        ("1919-12-31", "Asia/Kathmandu", 86400 + 676),
        ("1986-01-01", "Asia/Kathmandu", 86400 - 900),
        ("2024-03-10", "America/New_York", 23 * 3600),
        ("2024-11-03", "America/New_York", 25 * 3600),
    ],
)
def test_complete_local_day(day: str, timezone: str, expected_seconds: int) -> None:
    spans = moon.civil_date_spans(date.fromisoformat(day), timezone)
    assert sum(end - start for start, end in spans) == expected_seconds


def test_rollback_across_midnight_can_split_a_date() -> None:
    spans = moon.civil_date_spans(date(1988, 10, 29), "America/St_Johns")
    assert len(spans) == 2 and spans[1][0] - spans[0][1] == 60


def test_skipped_and_unsupported_dates() -> None:
    with pytest.raises(TimeConversionError) as skipped:
        moon.civil_date_spans(date(2011, 12, 30), "Pacific/Apia")
    assert skipped.value.code == "nonexistent_local_date"
    with pytest.raises(moon.MoonDateRangeError):
        moon.civil_date_spans(date(1800, 12, 31), "UTC")


def test_native_interval_can_be_stable_for_sign_and_mansion_without_stable_pada() -> None:
    result = moon.calculate_moon_window(date(2000, 1, 5), "UTC", AyanamshaMode.LAHIRI)
    assert result.signs.status == result.nakshatras.status == "stable"
    assert result.signs.possible == (8,) and result.nakshatras.possible == ("Mula",)
    assert result.padas.status == "uncertain"


@pytest.mark.parametrize(
    ("jd", "reference"),
    [(2451544.5, 217.2933209), (2451545.5, 229.3171907), (2451546.5, 241.2218873)],
)
def test_native_moon_matches_independent_horizons_reference(jd: float, reference: float) -> None:
    # NASA/JPL Horizons DE441, Moon (301) from Earth (500@399), quantity 31.
    # 2000-01-01 to 2000-01-03, 00:00 UTC, apparent ecliptic longitude of date.
    with SWE_LOCK:
        lon, _, _ = _calc_single_body(
            get_swe_engine(),
            jd,
            SE_MOON,
            SEFLG_SWIEPH | SEFLG_SPEED,
            "moon",
            (c_double * 6)(),
            create_string_buffer(256),
        )
    assert lon == pytest.approx(reference, abs=0.01)


@pytest.mark.parametrize(
    ("starting_longitude", "speed", "signs", "mansions", "sign_status"),
    [
        (0.4, 12, (0,), ("Ashwini",), "stable"),
        (27, 12, (0, 1), ("Krittika",), "uncertain"),
        (355, 12, (0, 11), ("Ashwini", "Revati"), "uncertain"),
        (30, 0, (0, 1), ("Krittika",), "uncertain"),
        (0, 31, (), (), "unavailable"),
    ],
)
def test_enclosure_guards_categories(
    monkeypatch: pytest.MonkeyPatch,
    starting_longitude: float,
    speed: float,
    signs: tuple[int, ...],
    mansions: tuple[str, ...],
    sign_status: str,
) -> None:
    # Exact linear sample trajectory, with an epoch chosen independently of the Moon.
    def linear(_swe: Any, jd: float, *_args: Any) -> tuple[float, float, str]:
        return (starting_longitude + (jd - 2440587.5) * speed) % 360, speed, "swieph"

    monkeypatch.setattr(moon, "_calc_single_body", linear)
    result = moon.calculate_moon_window(date(1970, 1, 1), "UTC", AyanamshaMode.LAHIRI)
    assert result.signs.possible == signs
    assert result.signs.status == sign_status
    assert result.nakshatras.possible == mansions
    if starting_longitude == 0.4:
        assert result.nakshatras.status == "stable"
        assert result.padas.status == "uncertain"
        assert {pada.pada for pada in result.padas.possible} == {1, 2, 3, 4}
    assert result.utc_intervals[0].start_utc == datetime(1970, 1, 1, tzinfo=UTC)
    assert result.utc_intervals[-1].end_utc_exclusive == datetime(1970, 1, 2, tzinfo=UTC)
