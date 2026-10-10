"""Ayanamsha configuration and computation.

Exposes supported Vedic ayanamsha systems mapped to Swiss Ephemeris sidereal modes.
Thread-safe execution under a module-level lock to prevent global state leakage.
"""

from __future__ import annotations

import threading
from ctypes import c_double
from enum import StrEnum
from pathlib import Path

from swisseph_ffi import (  # type: ignore[import-untyped]
    SE_SIDM_KRISHNAMURTI,
    SE_SIDM_LAHIRI,
    SE_SIDM_RAMAN,
    SwissEph,
)

# Global lock for Swiss Ephemeris calls that mutate or depend on global C library state
SWE_LOCK = threading.Lock()

EPHE_DIR = Path(__file__).resolve().parent.parent.parent / "ephe"

_SWE_INSTANCE: SwissEph | None = None


def get_swe_engine() -> SwissEph:
    """Return a cached SwissEph instance with ephemeris path set."""
    global _SWE_INSTANCE
    if _SWE_INSTANCE is None:
        swe = SwissEph()
        if EPHE_DIR.exists():
            swe.swe_set_ephe_path(str(EPHE_DIR).encode("utf-8"))
        _SWE_INSTANCE = swe
    return _SWE_INSTANCE


class AyanamshaMode(str, Enum):
    """Supported sidereal ayanamsha systems."""

    LAHIRI = "lahiri"
    RAMAN = "raman"
    KRISHNAMURTI = "krishnamurti"


_SIDM_MAP = {
    AyanamshaMode.LAHIRI: SE_SIDM_LAHIRI,
    AyanamshaMode.RAMAN: SE_SIDM_RAMAN,
    AyanamshaMode.KRISHNAMURTI: SE_SIDM_KRISHNAMURTI,
}


def get_ayanamsha_degrees(jd: float, mode: AyanamshaMode = AyanamshaMode.LAHIRI) -> float:
    """Return the ayanamsha value in decimal degrees for a Julian Day.

    Thread-safe: sets sid_mode and queries ayanamsha under SWE_LOCK.
    """
    sid_mode = _SIDM_MAP[mode]
    swe = get_swe_engine()
    with SWE_LOCK:
        swe.swe_set_sid_mode(sid_mode, 0, 0)
        ayanamsa: float = swe.swe_get_ayanamsa_ut(c_double(jd))
    return ayanamsa
