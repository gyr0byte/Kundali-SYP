"""Conservative geocentric sidereal Moon classifications for an unknown birth time."""

from __future__ import annotations

import hashlib
import json
import math
from ctypes import c_double, create_string_buffer
from datetime import UTC, date, datetime, timedelta
from typing import Final, Generic, Literal, TypeVar
from zoneinfo import ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict
from swisseph_ffi import (  # type: ignore[import-untyped]
    SE_MOON,
    SEFLG_SIDEREAL,
    SEFLG_SPEED,
    SEFLG_SWIEPH,
)

from app.calc.ayanamsha import _SIDM_MAP, SWE_LOCK, AyanamshaMode, get_swe_engine
from app.calc.ephemeris import BodyEphemerisSource, _calc_single_body
from app.calc.facts import ENGINE_VERSION
from app.calc.nakshatra import NAKSHATRA_NAMES
from app.calc.timeconv import TimeConversionError
from app.calc.timezones import load_timezone

METHOD: Final = "moon-civil-window-v1"
MIN_DATE = date(1801, 1, 1)
MAX_DATE = date(2199, 12, 31)
_SPEED_LIMIT = 30.0  # Degrees per UTC day, conditional model bound.
_MARGIN = 0.01  # Degrees, reserved for numerical and ephemeris uncertainty.
_CELL_SECONDS = 600
_DAY = 86400
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
T = TypeVar("T")


class MoonDateRangeError(ValueError):
    """The date falls outside the validated scope of the lunar window method."""


class CivilInterval(BaseModel, frozen=True):
    start_utc: datetime
    end_utc_exclusive: datetime


class MoonValues(BaseModel, Generic[T], frozen=True):  # noqa: UP046 - Python 3.11
    status: Literal["stable", "uncertain", "unavailable"]
    possible: tuple[T, ...]


class LunarPada(BaseModel, frozen=True):
    nakshatra: str
    pada: int


class MoonWindow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    chart_id: str
    method: Literal["moon-civil-window-v1"] = METHOD
    ayanamsha: AyanamshaMode
    utc_intervals: tuple[CivilInterval, ...]
    duration_seconds: int
    ephemeris_source: BodyEphemerisSource | None
    signs: MoonValues[int]
    nakshatras: MoonValues[str]
    padas: MoonValues[LunarPada]


def civil_date_spans(day: date, timezone: str) -> tuple[tuple[int, int], ...]:
    """Find the complete UTC preimage of a local date on the TZif second grid."""
    if not MIN_DATE <= day <= MAX_DATE:
        raise MoonDateRangeError("Date outside the supported lunar window range")
    try:
        zone = load_timezone(timezone)
    except ZoneInfoNotFoundError:
        raise TimeConversionError("Invalid profile timezone", code="invalid_timezone") from None
    midnight = (day - date(1970, 1, 1)).days * _DAY
    spans = []
    start = None
    for second in range(midnight - _DAY, midnight + 2 * _DAY):
        if (_EPOCH + timedelta(seconds=second)).astimezone(zone).date() == day:
            if start is None:
                start = second
        elif start is not None:
            spans.append((start, second))
            start = None
    if not spans:
        raise TimeConversionError(
            "This local date did not occur in the profile timezone",
            code="nonexistent_local_date",
        )
    return tuple(spans)


def _bins(longitude: float, radius: float, count: int) -> set[int]:
    low = math.floor((longitude - radius) * count / 360)
    high = math.floor((longitude + radius) * count / 360)
    return {index % count for index in range(low, high + 1)}


def _values(possible: tuple[T, ...]) -> MoonValues[T]:  # noqa: UP047 - Python 3.11
    status: Literal["stable", "uncertain", "unavailable"]
    status = "stable" if len(possible) == 1 else "uncertain" if possible else "unavailable"
    return MoonValues(status=status, possible=possible)


def _enclose(
    spans: tuple[tuple[int, int], ...],
    ayanamsha: AyanamshaMode,
) -> tuple[BodyEphemerisSource | None, set[int], set[int]]:
    signs: set[int] = set()
    padas: set[int] = set()
    source = None
    flags = SEFLG_SWIEPH | SEFLG_SPEED | SEFLG_SIDEREAL
    xx, serr = (c_double * 6)(), create_string_buffer(256)
    with SWE_LOCK:
        swe = get_swe_engine()
        swe.swe_set_sid_mode(_SIDM_MAP[ayanamsha], 0, 0)
        for start, end in spans:
            previous = None
            cells = [
                ((lo + min(lo + _CELL_SECONDS, end)) / 2, min(_CELL_SECONDS, end - lo) / 2)
                for lo in range(start, end, _CELL_SECONDS)
            ]
            # Check coverage and source at the outer edges as well as the cell midpoints.
            for second, half_width in [(float(start), 0.0), *cells, (float(end), 0.0)]:
                lon, speed, current = _calc_single_body(
                    swe,
                    2440587.5 + second / _DAY,
                    SE_MOON,
                    flags,
                    "moon",
                    xx,
                    serr,
                )
                if abs(speed) > _SPEED_LIMIT or (source is not None and source != current):
                    return None, set(), set()
                if previous is not None:
                    old_second, old_lon = previous
                    motion = abs((lon - old_lon + 180) % 360 - 180)
                    if motion > _SPEED_LIMIT * (second - old_second) / _DAY + 2 * _MARGIN:
                        return None, set(), set()
                previous = (second, lon)
                source = current
                if half_width:
                    radius = _SPEED_LIMIT * half_width / _DAY + _MARGIN
                    signs.update(_bins(lon, radius, 12))
                    padas.update(_bins(lon, radius, 108))
    return source, signs, padas


def calculate_moon_window(day: date, timezone: str, ayanamsha: AyanamshaMode) -> MoonWindow:
    spans = civil_date_spans(day, timezone)
    source, signs, padas = _enclose(spans, ayanamsha)
    sign_values = _values(tuple(sorted(signs)))
    mansion_values = _values(
        tuple(NAKSHATRA_NAMES[index] for index in sorted({p // 4 for p in padas}))
    )
    pada_values = _values(
        tuple(
            LunarPada(nakshatra=NAKSHATRA_NAMES[index // 4], pada=index % 4 + 1)
            for index in sorted(padas)
        )
    )
    identity = json.dumps(
        [
            METHOD,
            ENGINE_VERSION,
            ayanamsha.value,
            spans,
            source,
            sorted(signs),
            sorted(padas),
        ],
        separators=(",", ":"),
    )
    return MoonWindow(
        chart_id="m_" + hashlib.sha256(identity.encode()).hexdigest()[:32],
        ayanamsha=ayanamsha,
        utc_intervals=tuple(
            CivilInterval(
                start_utc=_EPOCH + timedelta(seconds=start),
                end_utc_exclusive=_EPOCH + timedelta(seconds=end),
            )
            for start, end in spans
        ),
        duration_seconds=sum(end - start for start, end in spans),
        ephemeris_source=source,
        signs=sign_values,
        nakshatras=mansion_values,
        padas=pada_values,
    )
