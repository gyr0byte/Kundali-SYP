"""Nakshatra and Pada divisions.

Divides the 360° zodiac into 27 lunar mansions (13° 20' each)
and 108 padas (quarters, 3° 20' each).
"""

from __future__ import annotations

NAKSHATRA_NAMES: list[str] = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni",
    "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha",
    "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta", "Shatabhisha",
    "Purva Bhadrapada", "Uttara Bhadrapada", "Revati",
]

NAKSHATRA_SPAN: float = 360.0 / 27.0  # 13° 20' = 13.333333333333334°
PADA_SPAN: float = NAKSHATRA_SPAN / 4.0  # 3° 20' = 3.3333333333333335°


def nakshatra_of(longitude: float) -> tuple[int, str, int]:
    """Calculate the nakshatra index (0..26), name, and pada (1..4).

    Handles boundary points at 0.0° and 359.999° with floating-point stability.
    """
    normalized_lon = longitude % 360.0
    if normalized_lon < 0.0:
        normalized_lon += 360.0

    idx = int(normalized_lon / NAKSHATRA_SPAN)
    if idx >= 27:
        idx = 26

    rem = normalized_lon - (idx * NAKSHATRA_SPAN)
    pada = int(rem / PADA_SPAN) + 1
    if pada > 4:
        pada = 4

    return idx, NAKSHATRA_NAMES[idx], pada
