"""Calendar conversions pinned to external civil date references."""

from datetime import date, timedelta

import pytest

from app.calc.bikram_sambat import (
    MAX_AD_DATE,
    MIN_AD_DATE,
    BikramSambatDate,
    CalendarDateError,
    ad_to_bs,
    bs_to_ad,
    parse_ad_date,
)


@pytest.mark.parametrize(
    ("bs", "ad"),
    [
        # UNCTAD and ICC's published Nepal holiday schedule for 2002.
        ("2059-01-01", "2002-04-14"),
        # Nepal Rastra Bank's Jestha 2062 interest-rate report, interest on deposits.
        ("2062-01-01", "2005-04-14"),
        ("2062-02-01", "2005-05-15"),
        ("2062-02-05", "2005-05-19"),
        # The day immediately before the reported start of Jestha.
        ("2062-01-31", "2005-05-14"),
        # Nepal Ministry of Foreign Affairs earthquake relief report.
        ("2072-01-12", "2015-04-25"),
        # Embassy of Nepal, Tokyo, 2082 public holiday schedule.
        ("2082-01-01", "2025-04-14"),
        ("2082-01-29", "2025-05-12"),
        ("2082-02-15", "2025-05-29"),
        ("2082-06-03", "2025-09-19"),
        ("2082-07-06", "2025-10-23"),
        ("2082-09-17", "2026-01-01"),
        # Nepal's Cairo Embassy and Kolkata Consulate 2083 holiday schedules.
        ("2083-01-01", "2026-04-14"),
        ("2083-12-30", "2027-04-13"),
    ],
)
def test_independent_references(bs: str, ad: str) -> None:
    converted = BikramSambatDate.parse(bs)
    gregorian = date.fromisoformat(ad)
    assert bs_to_ad(converted) == gregorian
    assert ad_to_bs(gregorian) == converted


def test_endpoints_month_boundaries_and_leap_day() -> None:
    assert MIN_AD_DATE == date(1918, 4, 13)
    assert MAX_AD_DATE == date(2027, 4, 13)
    assert bs_to_ad(BikramSambatDate(1975, 1, 1)) == MIN_AD_DATE
    assert bs_to_ad(BikramSambatDate.parse("२०८३-१२-३०")) == MAX_AD_DATE
    assert bs_to_ad(BikramSambatDate(2082, 3, 32)) + timedelta(days=1) == bs_to_ad(
        BikramSambatDate(2082, 4, 1)
    )
    assert bs_to_ad(BikramSambatDate(2082, 12, 30)) + timedelta(days=1) == bs_to_ad(
        BikramSambatDate(2083, 1, 1)
    )
    assert bs_to_ad(ad_to_bs(parse_ad_date("2000-02-29"))) == date(2000, 2, 29)


@pytest.mark.parametrize("value", ["1900-02-29", "2001-02-29", "0000-01-01", "2024-04-31"])
def test_invalid_gregorian_dates(value: str) -> None:
    with pytest.raises(CalendarDateError) as error:
        parse_ad_date(value)
    assert error.value.code == "invalid_ad_date"


@pytest.mark.parametrize(
    ("value", "code"),
    [
        ("1974-12-30", "bs_date_out_of_range"),
        ("2084-01-01", "bs_date_out_of_range"),
        ("2083-13-01", "invalid_bs_date"),
        ("2083-12-31", "invalid_bs_date"),
        ("2083-01-00", "invalid_bs_date"),
        ("2083/01/01", "birth_date_format"),
        ("1989-07-01", "bs_date_unconfirmed"),
        ("1991-08-01", "bs_date_unconfirmed"),
        ("1993-03-01", "bs_date_unconfirmed"),
        ("2004-09-01", "bs_date_unconfirmed"),
    ],
)
def test_invalid_or_unconfirmed_bs(value: str, code: str) -> None:
    with pytest.raises(CalendarDateError) as error:
        BikramSambatDate.parse(value)
    assert error.value.code == code
    assert value not in str(error.value)


def test_every_supported_day_round_trips_without_extrapolation() -> None:
    day = timedelta(days=1)
    for outside in (MIN_AD_DATE - day, MAX_AD_DATE + day):
        with pytest.raises(CalendarDateError) as error:
            ad_to_bs(outside)
        assert error.value.code == "bs_date_out_of_range"
    unconfirmed = 0
    for offset in range((MAX_AD_DATE - MIN_AD_DATE).days + 1):
        gregorian = MIN_AD_DATE + offset * day
        try:
            converted = ad_to_bs(gregorian)
        except CalendarDateError as error:
            assert error.code == "bs_date_unconfirmed"
            unconfirmed += 1
        else:
            assert bs_to_ad(converted) == gregorian
    assert unconfirmed == 240
