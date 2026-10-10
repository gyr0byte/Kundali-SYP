"""House system and Lagna (Ascendant) calculations.

Implements Whole Sign house division (standard Vedic convention),
sign index mappings, and birth-time boundary sensitivity detection.
"""

from __future__ import annotations

from ctypes import c_double

from swisseph_ffi import SEFLG_SIDEREAL  # type: ignore[import-untyped]

from app.calc.ayanamsha import SWE_LOCK, AyanamshaMode, _SIDM_MAP, get_swe_engine

SIGN_NAMES: list[str] = [
    "Aries", "Taurus", "Gemini", "Cancer",
    "Leo", "Virgo", "Libra", "Scorpio",
    "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

RASHI_NAMES: list[str] = [
    "Mesha", "Vrishabha", "Mithun", "Karkat",
    "Singh", "Kanya", "Tula", "Vrishchika",
    "Dhanu", "Makar", "Kumbha", "Meen",
]


def sign_of(longitude: float) -> int:
    """Return the 0-indexed zodiac sign (0 = Aries/Mesha ... 11 = Pisces/Meen)."""
    return int((longitude % 360.0) // 30.0)


def degree_in_sign(longitude: float) -> float:
    """Return the degree position within the current sign (0.0 <= deg < 30.0)."""
    return (longitude % 360.0) % 30.0


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
    deg = degree_in_sign(lagna_longitude)
    return deg < threshold_degrees or deg >= (30.0 - threshold_degrees)


def compute_lagna(
    jd: float,
    latitude: float,
    longitude: float,
    ayanamsha: AyanamshaMode = AyanamshaMode.LAHIRI,
) -> float:
    """Compute the sidereal Lagna (Ascendant) longitude in decimal degrees.

    Thread-safe: sets sid_mode and calculates houses under SWE_LOCK.
    """
    swe = get_swe_engine()
    sid_mode = _SIDM_MAP[ayanamsha]
    cusps = (c_double * 13)()
    ascmc = (c_double * 10)()

    with SWE_LOCK:
        swe.swe_set_sid_mode(sid_mode, 0, 0)
        swe.swe_houses_ex(
            c_double(jd),
            SEFLG_SIDEREAL,
            c_double(latitude),
            c_double(longitude),
            ord("W"),  # Whole sign
            cusps,
            ascmc,
        )

    return float(ascmc[0] % 360.0)
