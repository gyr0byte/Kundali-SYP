"""Offline conversion for the civil Bikram Sambat calendar used in Nepal."""

import csv
import re
from bisect import bisect_right
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

CALENDAR_DATA_SOURCE = "sambat 0.1.0 (32014630fb0fd63937736f4fe3b9d81d519b0d17)"
CALENDAR_DATA_VERSION = "kundali-bs-v1"
_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
# Months affected by competing historical tables. Nepal Rastra Bank's Jestha
# 2062 interest-rate report independently dates Jestha 1 to May 15, 2005.
_DISPUTED_MONTHS = {
    1989: (7, 8),
    1991: (8, 9),
    1993: (3, 4),
    2004: (9, 10),
}
CalendarDateCode = Literal[
    "birth_date_format",
    "invalid_ad_date",
    "invalid_bs_date",
    "bs_date_out_of_range",
    "bs_date_unconfirmed",
]
CALENDAR_DATE_ERROR_CODES = frozenset(
    {
        "birth_date_format",
        "invalid_ad_date",
        "invalid_bs_date",
        "bs_date_out_of_range",
        "bs_date_unconfirmed",
    }
)


class CalendarDateError(ValueError):
    """A calendar validation failure whose message never includes the submitted date."""

    def __init__(self, code: CalendarDateCode, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class _Year:
    number: int
    start: date
    months: tuple[int, ...]


def _load_years() -> tuple[_Year, ...]:
    data = Path(__file__).with_name("calendar_data") / "calendar.csv"
    with data.open(encoding="utf-8", newline="") as file:
        years = tuple(
            _Year(
                int(row["bs_year"]),
                date.fromisoformat(row["baisakh1_ad"]),
                tuple(int(row[f"m{month:02}"]) for month in range(1, 13)),
            )
            for row in csv.DictReader(file)
        )
    if (
        tuple(year.number for year in years) != tuple(range(1975, 2084))
        or any(
            not all(29 <= length <= 32 for length in year.months)
            or sum(year.months) not in (365, 366)
            for year in years
        )
        or any(
            (second.start - first.start).days != sum(first.months)
            for first, second in zip(years, years[1:], strict=False)
        )
    ):
        raise RuntimeError("Invalid pinned Bikram Sambat calendar table")
    return years


_YEARS = _load_years()
_YEAR_STARTS = tuple(year.start for year in _YEARS)
MIN_BS_YEAR = _YEARS[0].number
MAX_BS_YEAR = _YEARS[-1].number
MIN_AD_DATE = _YEAR_STARTS[0]
MAX_AD_DATE = _YEAR_STARTS[-1] + timedelta(days=sum(_YEARS[-1].months) - 1)


def normalize_date_text(value: str) -> str:
    """Normalize Devanagari digits while preserving the entered calendar and date."""
    if not isinstance(value, str):
        raise CalendarDateError("birth_date_format", "Birth date must use YYYY-MM-DD format")
    normalized = value.strip().translate(_DIGITS)
    if not _DATE_PATTERN.fullmatch(normalized):
        raise CalendarDateError("birth_date_format", "Birth date must use YYYY-MM-DD format")
    return normalized


def parse_ad_date(value: str) -> date:
    """Validate a Gregorian civil date, independently of the BS conversion range."""
    normalized = normalize_date_text(value)
    try:
        return date.fromisoformat(normalized)
    except ValueError:
        raise CalendarDateError("invalid_ad_date", "Invalid Gregorian AD birth date") from None


@dataclass(frozen=True)
class BikramSambatDate:
    """A validated BS date within the supported evidence-backed calendar."""

    year: int
    month: int
    day: int

    def __post_init__(self) -> None:
        if not MIN_BS_YEAR <= self.year <= MAX_BS_YEAR:
            raise CalendarDateError(
                "bs_date_out_of_range",
                f"Supported Bikram Sambat years are {MIN_BS_YEAR}–{MAX_BS_YEAR}",
            )
        months = _YEARS[self.year - MIN_BS_YEAR].months
        if not 1 <= self.month <= 12 or not 1 <= self.day <= months[self.month - 1]:
            raise CalendarDateError("invalid_bs_date", "Invalid Bikram Sambat month or day")
        if self.month in _DISPUTED_MONTHS.get(self.year, ()):
            raise CalendarDateError(
                "bs_date_unconfirmed", "Historical sources disagree for this Bikram Sambat month"
            )

    @classmethod
    def parse(cls, value: str) -> "BikramSambatDate":
        year, month, day = normalize_date_text(value).split("-")
        return cls(int(year), int(month), int(day))

    def isoformat(self) -> str:
        return f"{self.year:04d}-{self.month:02d}-{self.day:02d}"


def bs_to_ad(value: BikramSambatDate) -> date:
    year = _YEARS[value.year - MIN_BS_YEAR]
    return year.start + timedelta(days=sum(year.months[: value.month - 1]) + value.day - 1)


def ad_to_bs(value: date) -> BikramSambatDate:
    if not MIN_AD_DATE <= value <= MAX_AD_DATE:
        raise CalendarDateError(
            "bs_date_out_of_range", f"BS conversion covers AD {MIN_AD_DATE} through {MAX_AD_DATE}"
        )
    year = _YEARS[bisect_right(_YEAR_STARTS, value) - 1]
    remaining = (value - year.start).days
    for month, length in enumerate(year.months, start=1):
        if remaining < length:
            return BikramSambatDate(year.number, month, remaining + 1)
        remaining -= length
    raise RuntimeError("Inconsistent Bikram Sambat calendar table")
