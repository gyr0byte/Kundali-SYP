"""Deterministic Vimshottari periods from a recorded instant and sidereal Moon."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from fractions import Fraction
from typing import Final, Literal

from app.calc.facts import SUPPORTED_YEAR_DAYS, ChartFactPlacement, ChartFacts
from app.calc.houses import quantize_longitude
from app.calc.nakshatra import NAKSHATRA_NAMES, nakshatra_of

DASHA_METHOD: Final = "vimshottari-v1"
CYCLE_YEARS: Final = 120
_MICROSECONDS_PER_DAY: Final = 86_400_000_000
_MICRODEGREES_PER_DEGREE: Final = 1_000_000

BirthTimeCertainty = Literal["exact", "approximate", "unknown"]
RecordedTimeCertainty = Literal["exact", "approximate"]
DashaLevel = Literal["MD", "AD", "PD"]
_LEVELS: tuple[DashaLevel, ...] = ("MD", "AD", "PD")


class DashaInputError(ValueError):
    """The supplied chart, instant, or convention cannot produce a timeline."""


class DashaLord(StrEnum):
    """Traditional Vimshottari period lords."""

    KETU = "Ketu"
    VENUS = "Venus"
    SUN = "Sun"
    MOON = "Moon"
    MARS = "Mars"
    RAHU = "Rahu"
    JUPITER = "Jupiter"
    SATURN = "Saturn"
    MERCURY = "Mercury"


_YEARS = {
    DashaLord.KETU: 7,
    DashaLord.VENUS: 20,
    DashaLord.SUN: 6,
    DashaLord.MOON: 10,
    DashaLord.MARS: 7,
    DashaLord.RAHU: 18,
    DashaLord.JUPITER: 16,
    DashaLord.SATURN: 19,
    DashaLord.MERCURY: 17,
}
# The order starts at Ashwini; Krittika is the third entry, ruled by the Sun.
_ORDER = tuple(_YEARS)


@dataclass(frozen=True, slots=True)
class InitialDashaBalance:
    lord: DashaLord
    nakshatra_index: int
    nakshatra: str
    elapsed_fraction: Fraction
    remaining_years: Fraction


@dataclass(frozen=True, slots=True)
class DashaPeriod:
    """A full traditional period. Its UTC end is exclusive."""

    period_id: str
    level: DashaLevel
    lord: DashaLord
    start_utc: datetime
    end_utc_exclusive: datetime
    children: tuple[DashaPeriod, ...] = ()

    def clip(self, start: datetime, end_exclusive: datetime) -> DashaPeriodView | None:
        """Intersect this period with a presentation range, preserving its full bounds."""
        start_utc = _as_utc(start)
        end_utc = _as_utc(end_exclusive)
        if start_utc >= end_utc:
            raise DashaInputError("The display interval must have an end after its start")
        visible_start = max(start_utc, self.start_utc)
        visible_end = min(end_utc, self.end_utc_exclusive)
        if visible_start >= visible_end:
            return None
        return DashaPeriodView(self, visible_start, visible_end)


@dataclass(frozen=True, slots=True)
class DashaPeriodView:
    period: DashaPeriod
    start_utc: datetime
    end_utc_exclusive: datetime


@dataclass(frozen=True, slots=True)
class ActiveDashas:
    mahadasha: DashaPeriod
    antardasha: DashaPeriod
    pratyantardasha: DashaPeriod


@dataclass(frozen=True, slots=True)
class VimshottariTimeline:
    """One 120-year cycle starting at the original opening Mahadasha boundary."""

    timeline_id: str
    birth_utc: datetime
    year_days: float
    time_certainty: RecordedTimeCertainty
    moon_longitude: float
    initial_balance: InitialDashaBalance
    mahadashas: tuple[DashaPeriod, ...]

    @property
    def is_conditional(self) -> bool:
        return self.time_certainty == "approximate"

    def active_at(self, instant: datetime) -> ActiveDashas | None:
        """Return the three active periods at an explicit aware instant inside the cycle."""
        at_utc = _as_utc(instant)
        md = next((p for p in self.mahadashas if p.start_utc <= at_utc < p.end_utc_exclusive), None)
        if md is None:
            return None
        ad = next(p for p in md.children if p.start_utc <= at_utc < p.end_utc_exclusive)
        pd = next(p for p in ad.children if p.start_utc <= at_utc < p.end_utc_exclusive)
        return ActiveDashas(md, ad, pd)


def dasha_lord_of_nakshatra(nakshatra_index: int) -> DashaLord:
    """Map a zero-based Ashwini-first index to its traditional Vimshottari lord."""
    if type(nakshatra_index) is not int or not 0 <= nakshatra_index < len(NAKSHATRA_NAMES):
        raise DashaInputError("Nakshatra index must be between 0 and 26")
    return _ORDER[nakshatra_index % len(_ORDER)]


def _as_utc(instant: datetime) -> datetime:
    if not isinstance(instant, datetime):
        raise DashaInputError("An aware datetime is required")
    try:
        if instant.utcoffset() is not None:
            return instant.astimezone(UTC)
    except (OverflowError, ValueError) as exc:
        raise DashaInputError("The instant is outside the supported UTC datetime range") from exc
    raise DashaInputError("An aware datetime is required")


def _recorded_time(certainty: BirthTimeCertainty) -> RecordedTimeCertainty:
    if certainty == "exact":
        return "exact"
    if certainty == "approximate":
        return "approximate"
    raise DashaInputError("Vimshottari Dasha requires an exact or approximate birth time")


def _canonical_moon(longitude: float) -> float:
    if (
        isinstance(longitude, bool)
        or not isinstance(longitude, (int, float))
        or not 0 <= longitude <= 360
    ):
        raise DashaInputError("Sidereal Moon longitude must be between 0 and 360 degrees")
    return quantize_longitude(longitude, decimals=6)


def _periods(
    birth_utc: datetime,
    start: Fraction,
    duration: Fraction,
    first_lord: DashaLord,
    parent_id: str,
    depth: int,
) -> tuple[DashaPeriod, ...]:
    periods = []
    first = _ORDER.index(first_lord)
    level = _LEVELS[depth]
    offset = start
    for position in range(len(_ORDER)):
        lord = _ORDER[(first + position) % len(_ORDER)]
        length = duration * _YEARS[lord] / CYCLE_YEARS
        end = offset + length
        period_id = f"{parent_id}.{position}"
        children = (
            _periods(birth_utc, offset, length, lord, period_id, depth + 1)
            if depth < len(_LEVELS) - 1
            else ()
        )
        # Convert each exact boundary from the same origin. Never add a rounded duration.
        periods.append(
            DashaPeriod(
                period_id=period_id,
                level=level,
                lord=lord,
                start_utc=birth_utc + timedelta(microseconds=round(offset)),
                end_utc_exclusive=birth_utc + timedelta(microseconds=round(end)),
                children=children,
            )
        )
        offset = end
    return tuple(periods)


def calculate_vimshottari(
    moon_longitude: float,
    birth_instant: datetime,
    *,
    year_days: float,
    time_certainty: BirthTimeCertainty,
) -> VimshottariTimeline:
    """Calculate from a trusted sidereal longitude and a recorded birth instant."""
    certainty = _recorded_time(time_certainty)
    birth = _as_utc(birth_instant)
    if (
        isinstance(year_days, bool)
        or not isinstance(year_days, (int, float))
        or year_days not in SUPPORTED_YEAR_DAYS
    ):
        raise DashaInputError("Unsupported Vimshottari year length")
    year_days = float(year_days)
    longitude = _canonical_moon(moon_longitude)
    index, name, _ = nakshatra_of(longitude)
    lunar_units = round(longitude * _MICRODEGREES_PER_DEGREE)
    # Use exact 360/27 geometry on the same quantized angle as the natal fact.
    elapsed = Fraction(lunar_units * len(NAKSHATRA_NAMES), 360 * _MICRODEGREES_PER_DEGREE) - index
    if not 0 <= elapsed < 1:
        raise DashaInputError("Moon longitude disagrees with the natal Nakshatra convention")
    lord = dasha_lord_of_nakshatra(index)
    initial = InitialDashaBalance(lord, index, name, elapsed, _YEARS[lord] * (1 - elapsed))
    year_microseconds = Fraction(str(year_days)) * _MICROSECONDS_PER_DAY
    original_start = -elapsed * _YEARS[lord] * year_microseconds
    identity = json.dumps(
        [DASHA_METHOD, birth.isoformat(timespec="microseconds"), lunar_units, year_days, certainty],
        separators=(",", ":"),
    )
    timeline_id = "vd_" + hashlib.sha256(identity.encode("ascii")).hexdigest()[:32]
    try:
        mahadashas = _periods(
            birth,
            original_start,
            year_microseconds * CYCLE_YEARS,
            lord,
            timeline_id,
            0,
        )
    except OverflowError as exc:
        raise DashaInputError(
            "The Dasha cycle falls outside the supported UTC datetime range"
        ) from exc
    return VimshottariTimeline(
        timeline_id, birth, year_days, certainty, longitude, initial, mahadashas
    )


def calculate_vimshottari_from_chart(
    chart: ChartFacts, *, time_certainty: BirthTimeCertainty
) -> VimshottariTimeline:
    """Reuse the recorded UTC birth instant, Moon fact, and year convention of a natal chart."""
    certainty = _recorded_time(time_certainty)
    if not isinstance(chart, ChartFacts):
        raise DashaInputError("Vimshottari Dasha requires natal chart facts")
    moon_facts = [fact for fact in chart.facts if fact.id == "f_moon"]
    moon = moon_facts[0] if len(moon_facts) == 1 else None
    if not isinstance(moon, ChartFactPlacement) or moon.planet != "Moon":
        raise DashaInputError("The natal chart must contain one Moon placement fact")
    longitude = _canonical_moon(moon.longitude)
    _, name, pada = nakshatra_of(longitude)
    if longitude != moon.longitude or (name, pada) != (moon.nakshatra, moon.pada):
        raise DashaInputError("The natal Moon fact is inconsistent with the stored longitude")
    try:
        birth = datetime.fromisoformat(chart.metadata.datetime_utc_iso)
    except (ValueError, TypeError) as exc:
        raise DashaInputError("The natal chart must include a valid recorded UTC instant") from exc
    return calculate_vimshottari(
        longitude,
        birth,
        year_days=chart.settings.year_days,
        time_certainty=certainty,
    )
