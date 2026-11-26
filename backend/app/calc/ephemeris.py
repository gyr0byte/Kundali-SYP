"""Swiss Ephemeris wrapper for planetary and nodal positions.

Calculates sidereal positions, daily speeds, and retrograde status for the 9 Vedic grahas.
Enforces thread safety under SWE_LOCK to prevent global sidereal mode leakage.
"""

from __future__ import annotations

import math
from ctypes import Array, c_char, c_double, create_string_buffer
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict
from swisseph_ffi import (  # type: ignore[import-untyped]
    SE_JUPITER,
    SE_MARS,
    SE_MEAN_NODE,
    SE_MERCURY,
    SE_MOON,
    SE_SATURN,
    SE_SUN,
    SE_TRUE_NODE,
    SE_VENUS,
    SEFLG_NONUT,
    SEFLG_SIDEREAL,
    SEFLG_SPEED,
    SEFLG_SWIEPH,
    SwissEph,
)

from app.calc.ayanamsha import (
    _SIDM_MAP,
    SWE_LOCK,
    AyanamshaMode,
    CalculationError,
    classify_ephemeris_flag,
    get_swe_engine,
)
from app.calc.houses import normalize_longitude

BodyEphemerisSource = Literal["swieph", "moshier"]
EphemerisSource = Literal["swieph", "moshier", "mixed"]
# Swiss Ephemeris sweph.h uses these TT bounds for planet and Moon fallback.
_MOSHIER_START_TT = 625000.5
_MOSHIER_END_TT = 2818000.5


class EphemerisDateRangeError(CalculationError):
    """The installed ephemeris and native fallback cannot cover the requested instant."""


# Auxiliary flags returned by Swiss Ephemeris for sidereal speed calculations.
PLANETARY_AUXILIARY_FLAGS: int = SEFLG_SPEED | SEFLG_SIDEREAL | SEFLG_NONUT


class NodeType(StrEnum):
    """Lunar node calculation method."""

    MEAN = "mean"
    TRUE = "true"


class PlanetPosition(BaseModel):
    """Astronomical position and motion of a celestial body."""

    model_config = ConfigDict(extra="forbid")

    name: str
    longitude: float
    speed: float
    retrograde: bool


class EphemerisResult(BaseModel):
    """Calculated planetary positions for an epoch."""

    model_config = ConfigDict(extra="forbid")

    positions: dict[str, PlanetPosition]
    ephemeris_source: EphemerisSource
    body_sources: dict[str, BodyEphemerisSource]


_PLANET_BODIES = [
    ("sun", SE_SUN),
    ("moon", SE_MOON),
    ("mars", SE_MARS),
    ("mercury", SE_MERCURY),
    ("jupiter", SE_JUPITER),
    ("venus", SE_VENUS),
    ("saturn", SE_SATURN),
]


def _resolve_overall_ephemeris_source(
    sources: set[BodyEphemerisSource],
) -> EphemerisSource:
    """Aggregate per-body provenance without hiding partial Moshier fallbacks."""
    if sources == {"swieph"}:
        return "swieph"
    if sources == {"moshier"}:
        return "moshier"
    if sources == {"swieph", "moshier"}:
        return "mixed"
    raise CalculationError("Unable to determine valid ephemeris provenance.")


def _is_date_range_failure(swe: SwissEph, jd: float, flags: int, message: bytes) -> bool:
    """Recognize coverage errors without retaining native diagnostics or file paths."""
    if message.startswith(b"jd ") and any(
        marker in message
        for marker in (
            b"outside Moshier planet range",
            b"outside Moshier's Moon range",
            b"outside mean node range",
        )
    ):
        return True

    missing_file = message.startswith(b"SwissEph file '") and b".se1' not found in PATH" in message
    file_limit = message.startswith((b"planets eph. file (", b"moon eph. file (")) and (
        b" < lower limit " in message or b" > upper limit " in message
    )
    # Without Swiss coverage, the library only tries Moshier inside its TT interval.
    if missing_file or file_limit:
        jd_tt = jd + float(swe.swe_deltat_ex(c_double(jd), flags, None))
        return jd_tt <= _MOSHIER_START_TT or jd_tt >= _MOSHIER_END_TT
    return False


def _calc_single_body(
    swe: SwissEph,
    jd: float,
    pid: int,
    flags: int,
    body_name: str,
    xx: Array[c_double],
    serr: Array[c_char],
) -> tuple[float, float, BodyEphemerisSource]:
    """Query one body under active SWE_LOCK and fail closed on invalid output."""
    serr.value = b""
    try:
        iflag = int(swe.swe_calc_ut(c_double(jd), pid, flags, xx, serr))
        out_of_range = iflag == -1 and _is_date_range_failure(swe, jd, flags, serr.value)
    except Exception as exc:
        raise CalculationError(
            f"Swiss Ephemeris calculation raised an error for {body_name}."
        ) from exc

    if out_of_range:
        raise EphemerisDateRangeError("Date is outside the configured ephemeris coverage.")

    source = classify_ephemeris_flag(
        iflag,
        subject=body_name,
        allowed_auxiliary_flags=PLANETARY_AUXILIARY_FLAGS,
    )

    raw_lon = float(xx[0])
    speed = float(xx[3])
    if not math.isfinite(raw_lon) or not math.isfinite(speed):
        raise CalculationError(f"Swiss Ephemeris returned non-finite output for {body_name}.")

    return normalize_longitude(raw_lon), speed, source


def calculate_positions(
    jd: float,
    ayanamsha: AyanamshaMode = AyanamshaMode.LAHIRI,
    node_type: NodeType = NodeType.MEAN,
) -> EphemerisResult:
    """Calculate sidereal positions of Sun through Saturn, Rahu, and Ketu.

    Thread-safe: sets sid_mode and queries positions under SWE_LOCK.
    """
    if isinstance(jd, bool) or not isinstance(jd, (int, float)) or not math.isfinite(float(jd)):
        raise CalculationError("Julian Day must be a finite numeric value.")

    jd_float = float(jd)
    sid_mode = _SIDM_MAP[ayanamsha]
    flags = SEFLG_SWIEPH | SEFLG_SPEED | SEFLG_SIDEREAL

    xx = (c_double * 6)()
    serr = create_string_buffer(256)

    positions: dict[str, PlanetPosition] = {}
    body_sources: dict[str, BodyEphemerisSource] = {}

    with SWE_LOCK:
        swe = get_swe_engine()
        try:
            swe.swe_set_sid_mode(sid_mode, 0, 0)
        except Exception as exc:
            raise CalculationError("Failed to configure sidereal mode.") from exc

        # 7 Classical planets
        for name, pid in _PLANET_BODIES:
            lon, speed, source = _calc_single_body(swe, jd_float, pid, flags, name, xx, serr)
            body_sources[name] = source

            # Sun and Moon are never retrograde
            retrograde = speed < 0.0 if name not in ("sun", "moon") else False
            positions[name] = PlanetPosition(
                name=name,
                longitude=lon,
                speed=speed,
                retrograde=retrograde,
            )

        # Rahu (Mean or True node)
        node_id = SE_MEAN_NODE if node_type == NodeType.MEAN else SE_TRUE_NODE
        rahu_lon, rahu_speed, node_source = _calc_single_body(
            swe, jd_float, node_id, flags, "rahu", xx, serr
        )
        body_sources.update(rahu=node_source, ketu=node_source)

        # Rahu is always flagged retrograde in Vedic astrology
        positions["rahu"] = PlanetPosition(
            name="rahu",
            longitude=rahu_lon,
            speed=rahu_speed,
            retrograde=True,
        )

        # Ketu = Rahu + 180° (mod 360), always retrograde
        ketu_lon = normalize_longitude(rahu_lon + 180.0)
        positions["ketu"] = PlanetPosition(
            name="ketu",
            longitude=ketu_lon,
            speed=rahu_speed,
            retrograde=True,
        )

    return EphemerisResult(
        positions=positions,
        ephemeris_source=_resolve_overall_ephemeris_source(set(body_sources.values())),
        body_sources=body_sources,
    )
