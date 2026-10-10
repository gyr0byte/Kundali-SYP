"""Swiss Ephemeris wrapper for planetary and nodal positions.

Calculates sidereal positions, daily speeds, and retrograde status for the 9 Vedic grahas.
Enforces thread safety under SWE_LOCK to prevent global sidereal mode leakage.
"""

from __future__ import annotations

from ctypes import c_double, create_string_buffer
from enum import Enum

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
    SEFLG_MOSEPH,
    SEFLG_SIDEREAL,
    SEFLG_SPEED,
    SEFLG_SWIEPH,
)

from app.calc.ayanamsha import SWE_LOCK, AyanamshaMode, _SIDM_MAP, get_swe_engine


class NodeType(str, Enum):
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
    ephemeris_source: str  # "swieph" or "moshier"


_PLANET_BODIES = [
    ("sun", SE_SUN),
    ("moon", SE_MOON),
    ("mars", SE_MARS),
    ("mercury", SE_MERCURY),
    ("jupiter", SE_JUPITER),
    ("venus", SE_VENUS),
    ("saturn", SE_SATURN),
]


def calculate_positions(
    jd: float,
    ayanamsha: AyanamshaMode = AyanamshaMode.LAHIRI,
    node_type: NodeType = NodeType.MEAN,
) -> EphemerisResult:
    """Calculate sidereal positions of Sun through Saturn, Rahu, and Ketu.

    Thread-safe: sets sid_mode and queries positions under SWE_LOCK.
    """
    swe = get_swe_engine()
    sid_mode = _SIDM_MAP[ayanamsha]
    flags = SEFLG_SWIEPH | SEFLG_SPEED | SEFLG_SIDEREAL

    xx = (c_double * 6)()
    serr = create_string_buffer(256)

    positions: dict[str, PlanetPosition] = {}
    ephemeris_sources: set[str] = set()

    with SWE_LOCK:
        swe.swe_set_sid_mode(sid_mode, 0, 0)

        # 7 Classical planets
        for name, pid in _PLANET_BODIES:
            iflag = swe.swe_calc_ut(c_double(jd), pid, flags, xx, serr)
            lon = xx[0] % 360.0
            speed = xx[3]

            if iflag & SEFLG_SWIEPH:
                ephemeris_sources.add("swieph")
            elif iflag & SEFLG_MOSEPH:
                ephemeris_sources.add("moshier")

            # Sun and Moon are never retrograde
            retrograde = speed < 0 if name not in ("sun", "moon") else False

            positions[name] = PlanetPosition(
                name=name,
                longitude=lon,
                speed=speed,
                retrograde=retrograde,
            )

        # Rahu (Mean or True node)
        node_id = SE_MEAN_NODE if node_type == NodeType.MEAN else SE_TRUE_NODE
        iflag = swe.swe_calc_ut(c_double(jd), node_id, flags, xx, serr)
        rahu_lon = xx[0] % 360.0
        rahu_speed = xx[3]

        if iflag & SEFLG_SWIEPH:
            ephemeris_sources.add("swieph")
        elif iflag & SEFLG_MOSEPH:
            ephemeris_sources.add("moshier")

        # Rahu is always flagged retrograde in Vedic astrology
        positions["rahu"] = PlanetPosition(
            name="rahu",
            longitude=rahu_lon,
            speed=rahu_speed,
            retrograde=True,
        )

        # Ketu = Rahu + 180° (mod 360), always retrograde
        ketu_lon = (rahu_lon + 180.0) % 360.0
        positions["ketu"] = PlanetPosition(
            name="ketu",
            longitude=ketu_lon,
            speed=rahu_speed,
            retrograde=True,
        )

    # Determine overall ephemeris source
    if "swieph" in ephemeris_sources:
        source = "swieph"
    elif "moshier" in ephemeris_sources:
        source = "moshier"
    else:
        source = "unknown"

    return EphemerisResult(positions=positions, ephemeris_source=source)
