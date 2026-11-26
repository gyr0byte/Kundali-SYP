"""House system and Lagna (Ascendant) calculations.

Implements Whole Sign house division (standard Vedic convention),
sign index mappings, longitude quantization, and boundary sensitivity detection.
"""

from __future__ import annotations

import math
from ctypes import c_double

from swisseph_ffi import SEFLG_SIDEREAL  # type: ignore[import-untyped]

from app.calc.ayanamsha import _SIDM_MAP, SWE_LOCK, AyanamshaMode, CalculationError, get_swe_engine

SIGN_NAMES: list[str] = [
    "Aries",
    "Taurus",
    "Gemini",
    "Cancer",
    "Leo",
    "Virgo",
    "Libra",
    "Scorpio",
    "Sagittarius",
    "Capricorn",
    "Aquarius",
    "Pisces",
]

RASHI_NAMES: list[str] = [
    "Mesha",
    "Vrishabha",
    "Mithun",
    "Karkat",
    "Singh",
    "Kanya",
    "Tula",
    "Vrishchika",
    "Dhanu",
    "Makar",
    "Kumbha",
    "Meen",
]


def normalize_longitude(longitude: float) -> float:
    """Normalize a finite ecliptic longitude strictly into [0.0, 360.0)."""
    if (
        isinstance(longitude, bool)
        or not isinstance(longitude, (int, float))
        or not math.isfinite(float(longitude))
    ):
        raise CalculationError("Ecliptic longitude must be finite.")
    normalized = float(longitude) % 360.0
    if normalized >= 360.0 or normalized == 0.0:
        return 0.0
    return normalized


def quantize_longitude(longitude: float, decimals: int = 6) -> float:
    """Round a normalized ecliptic longitude cleanly within [0.0, 360.0).

    Quantizing before sign, degree, house, nakshatra, and sensitivity derivation
    prevents values like 29.9999996° from serializing as sign_deg=30.0.
    """
    normalized = normalize_longitude(longitude)
    rounded = round(normalized, decimals)
    if rounded >= 360.0 or rounded == 0.0:
        return 0.0
    return rounded


def sign_of(longitude: float) -> int:
    """Return the 0-indexed zodiac sign (0 = Aries/Mesha ... 11 = Pisces/Meen)."""
    normalized = normalize_longitude(longitude)
    idx = int(normalized // 30.0)
    return 0 if idx >= 12 else idx


def degree_in_sign(longitude: float) -> float:
    """Return the degree position within the current sign (0.0 <= deg < 30.0)."""
    normalized = normalize_longitude(longitude)
    deg = normalized % 30.0
    if deg >= 30.0 or deg == 0.0:
        return 0.0
    return deg


def sign_name(sign_index: int) -> str:
    """Return the standard English zodiac sign name."""
    return SIGN_NAMES[sign_index % 12]


def rashi_name(sign_index: int) -> str:
    """Return the traditional Sanskrit Vedic rashi name."""
    return RASHI_NAMES[sign_index % 12]


def house_of(planet_longitude: float, lagna_longitude: float) -> int:
    """Return the whole-sign house number (1..12) of a planet relative to Lagna."""
    return (sign_of(planet_longitude) - sign_of(lagna_longitude)) % 12 + 1


def is_lagna_boundary_sensitive(lagna_longitude: float, threshold_degrees: float = 0.5) -> bool:
    """Check if the Lagna is within threshold degrees of a sign boundary.

    If true, a few minutes' shift in birth time could change the rising sign.
    """
    if (
        isinstance(threshold_degrees, bool)
        or not isinstance(threshold_degrees, (int, float))
        or not math.isfinite(float(threshold_degrees))
        or float(threshold_degrees) < 0.0
    ):
        raise CalculationError("Lagna boundary threshold must be finite and non-negative.")
    deg = degree_in_sign(lagna_longitude)
    threshold = float(threshold_degrees)
    return deg < threshold or deg >= (30.0 - threshold)


def compute_lagna(
    jd: float,
    latitude: float,
    longitude: float,
    ayanamsha: AyanamshaMode = AyanamshaMode.LAHIRI,
) -> float:
    """Compute the sidereal Lagna (Ascendant) longitude in decimal degrees.

    Thread-safe: validates inputs, sets sid_mode, and checks swe_houses_ex status
    under SWE_LOCK.
    """
    if isinstance(jd, bool) or not isinstance(jd, (int, float)) or not math.isfinite(float(jd)):
        raise CalculationError("Julian Day must be finite.")
    if (
        isinstance(latitude, bool)
        or not isinstance(latitude, (int, float))
        or not math.isfinite(float(latitude))
        or float(latitude) < -90.0
        or float(latitude) > 90.0
    ):
        raise CalculationError("Latitude must be finite and between -90 and 90 degrees.")
    if (
        isinstance(longitude, bool)
        or not isinstance(longitude, (int, float))
        or not math.isfinite(float(longitude))
        or float(longitude) < -180.0
        or float(longitude) > 180.0
    ):
        raise CalculationError("Longitude must be finite and between -180 and 180 degrees.")

    sid_mode = _SIDM_MAP[ayanamsha]
    cusps = (c_double * 13)()
    ascmc = (c_double * 10)()

    with SWE_LOCK:
        swe = get_swe_engine()
        try:
            swe.swe_set_sid_mode(sid_mode, 0, 0)
            rc = int(
                swe.swe_houses_ex(
                    c_double(float(jd)),
                    SEFLG_SIDEREAL,
                    c_double(float(latitude)),
                    c_double(float(longitude)),
                    ord("W"),  # Whole sign
                    cusps,
                    ascmc,
                )
            )
        except Exception as exc:
            raise CalculationError("Swiss Ephemeris house calculation failed.") from exc

    if rc < 0:
        raise CalculationError(f"Swiss Ephemeris house calculation returned error status ({rc}).")

    raw_asc = float(ascmc[0])
    if not math.isfinite(raw_asc):
        raise CalculationError("Swiss Ephemeris returned a non-finite Ascendant longitude.")

    return normalize_longitude(raw_asc)
