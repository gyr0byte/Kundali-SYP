"""Ayanamsha configuration and computation.

Exposes supported Vedic ayanamsha systems mapped to Swiss Ephemeris sidereal modes.
Thread-safe execution under a reentrant lock to prevent global C state leakage.
"""

from __future__ import annotations

import math
import threading
from ctypes import byref, c_double, create_string_buffer
from enum import StrEnum
from pathlib import Path
from typing import Literal

from swisseph_ffi import (  # type: ignore[import-untyped]
    SE_SIDM_KRISHNAMURTI,
    SE_SIDM_LAHIRI,
    SE_SIDM_LAHIRI_1940,
    SE_SIDM_RAMAN,
    SEFLG_JPLEPH,
    SEFLG_MOSEPH,
    SEFLG_NONUT,
    SEFLG_SWIEPH,
    SwissEph,
)


class CalculationError(RuntimeError):
    """Raised when deterministic astronomical calculation fails or lacks valid provenance."""


# Reentrant lock protecting Swiss Ephemeris lazy init, path config, and global C state.
SWE_LOCK = threading.RLock()

EPHE_DIR = Path(__file__).resolve().parent.parent.parent / "ephe"

EPHE_SOURCE_MASK = SEFLG_JPLEPH | SEFLG_SWIEPH | SEFLG_MOSEPH

_SWE_INSTANCE: SwissEph | None = None
_CONFIGURED_EPHE_PATH: str | None = None
_EPHE_PATH_CONFIGURED: bool = False


def get_swe_engine() -> SwissEph:
    """Return the cached SwissEph instance with ephemeris path synchronized under SWE_LOCK."""
    global _SWE_INSTANCE, _CONFIGURED_EPHE_PATH, _EPHE_PATH_CONFIGURED
    with SWE_LOCK:
        try:
            if _SWE_INSTANCE is None:
                _SWE_INSTANCE = SwissEph()
            desired_path = str(EPHE_DIR) if EPHE_DIR.exists() else ""
            if not _EPHE_PATH_CONFIGURED or _CONFIGURED_EPHE_PATH != desired_path:
                _SWE_INSTANCE.swe_set_ephe_path(desired_path.encode("utf-8"))
                _CONFIGURED_EPHE_PATH = desired_path
                _EPHE_PATH_CONFIGURED = True
            return _SWE_INSTANCE
        except Exception as exc:
            raise CalculationError("Failed to initialize Swiss Ephemeris engine.") from exc


class AyanamshaMode(StrEnum):
    """Supported sidereal ayanamsha systems."""

    LAHIRI = "lahiri"
    LAHIRI_1940 = "lahiri_1940"
    RAMAN = "raman"
    KRISHNAMURTI = "krishnamurti"


_SIDM_MAP = {
    AyanamshaMode.LAHIRI: SE_SIDM_LAHIRI,
    AyanamshaMode.LAHIRI_1940: SE_SIDM_LAHIRI_1940,
    AyanamshaMode.RAMAN: SE_SIDM_RAMAN,
    AyanamshaMode.KRISHNAMURTI: SE_SIDM_KRISHNAMURTI,
}


def classify_ephemeris_flag(
    iflag: int,
    *,
    subject: str,
    allow_moshier: bool = True,
) -> Literal["swieph", "moshier"]:
    """Validate Swiss Ephemeris status/source flags independently from auxiliary flags.

    Checks ``iflag < 0`` BEFORE bitwise masking because C ``ERR (-1)`` has all bits set.
    Auxiliary flags such as ``SEFLG_SPEED``, ``SEFLG_SIDEREAL``, and ``SEFLG_NONUT`` are
    preserved by masking strictly against provenance bits.
    """
    if iflag < 0:
        raise CalculationError(
            f"Swiss Ephemeris calculation failed for {subject} (status={iflag})."
        )

    source_bits = iflag & EPHE_SOURCE_MASK
    if source_bits == SEFLG_SWIEPH:
        return "swieph"
    if source_bits == SEFLG_MOSEPH:
        if not allow_moshier:
            raise CalculationError(f"Moshier fallback is not permitted for {subject}.")
        return "moshier"
    if source_bits == SEFLG_JPLEPH:
        raise CalculationError(f"Unsupported JPL ephemeris provenance for {subject}.")
    if source_bits == 0:
        raise CalculationError(f"Missing ephemeris provenance flag for {subject}.")
    raise CalculationError(f"Contradictory ephemeris provenance flags for {subject}.")


def get_ayanamsha_degrees(jd: float, mode: AyanamshaMode = AyanamshaMode.LAHIRI) -> float:
    """Return the ayanamsha value in decimal degrees for a Julian Day.

    Preserves the mean-ecliptic nutation convention used by ``swe_get_ayanamsa_ut``
    (``SEFLG_SWIEPH | SEFLG_NONUT``) while verifying the return status via
    ``swe_get_ayanamsa_ex_ut``.
    """
    if isinstance(jd, bool) or not isinstance(jd, (int, float)) or not math.isfinite(float(jd)):
        raise CalculationError("Julian Day must be a finite numeric value.")

    sid_mode = _SIDM_MAP[mode]
    aya = c_double()
    serr = create_string_buffer(256)
    ephe_flag = SEFLG_SWIEPH | SEFLG_NONUT

    with SWE_LOCK:
        swe = get_swe_engine()
        try:
            swe.swe_set_sid_mode(sid_mode, 0, 0)
            rc = int(swe.swe_get_ayanamsa_ex_ut(c_double(float(jd)), ephe_flag, byref(aya), serr))
        except Exception as exc:
            raise CalculationError("Swiss Ephemeris ayanamsha computation failed.") from exc

    classify_ephemeris_flag(rc, subject="ayanamsha")

    val = float(aya.value)
    if not math.isfinite(val):
        raise CalculationError("Swiss Ephemeris returned a non-finite ayanamsha value.")
    return val
