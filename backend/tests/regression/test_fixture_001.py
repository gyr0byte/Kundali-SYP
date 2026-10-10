"""Regression test for Fixture #1 (Builder's chart from Hamro Patro).

Validates that Swiss Ephemeris calculations match reference values within defined
tolerances per Kundali_Project_Plan.md §15.1.
"""

from __future__ import annotations

import json
from ctypes import c_double, create_string_buffer
from pathlib import Path
from typing import Any

import pytest
from swisseph_ffi import (  # type: ignore[import-untyped]
    SE_GREG_CAL,
    SE_JUPITER,
    SE_MARS,
    SE_MERCURY,
    SE_MOON,
    SE_SATURN,
    SE_SIDM_LAHIRI,
    SE_SUN,
    SE_TRUE_NODE,
    SE_VENUS,
    SEFLG_SIDEREAL,
    SEFLG_SPEED,
    SEFLG_SWIEPH,
    SwissEph,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
EPHE_DIR = PROJECT_ROOT / "backend" / "ephe"
FIXTURE_PATH = PROJECT_ROOT / "fixtures" / "charts" / "fixture_001_builder.json"

RASHIS = [
    "Mesha", "Vrishabha", "Mithun", "Karkat",
    "Singh", "Kanya", "Tula", "Vrishchika",
    "Dhanu", "Makar", "Kumbha", "Meen",
]

NAKSHATRAS = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni",
    "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha",
    "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta", "Shatabhisha",
    "Purva Bhadrapada", "Uttara Bhadrapada", "Revati",
]


@pytest.fixture(scope="module")
def fixture_data() -> dict[str, Any]:
    if not FIXTURE_PATH.exists():
        pytest.skip(f"Fixture file {FIXTURE_PATH} not present.")
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


@pytest.fixture(scope="module")
def swe_engine() -> SwissEph:
    swe = SwissEph()
    swe.swe_set_ephe_path(str(EPHE_DIR).encode("utf-8"))
    swe.swe_set_sid_mode(SE_SIDM_LAHIRI, 0, 0)
    return swe


def test_ephemeris_files_present() -> None:
    """Verify that Swiss Ephemeris data files are present on D:."""
    for filename in ["sepl_18.se1", "semo_18.se1", "seas_18.se1"]:
        file_path = EPHE_DIR / filename
        assert file_path.exists(), f"Ephemeris file {filename} is missing from {EPHE_DIR}"
        assert file_path.stat().st_size > 50_000, f"Ephemeris file {filename} is unexpectedly small"


def test_lagna_and_planetary_positions(
    swe_engine: SwissEph, fixture_data: dict[str, Any]
) -> None:
    """Validate computed positions against fixture reference."""
    # 2006-08-02 02:10:00 Nepal Time (+5:45) -> 2006-08-01 20:25:00 UTC
    jd = swe_engine.swe_julday(2006, 8, 1, 20.0 + 25.0 / 60.0, SE_GREG_CAL)

    xx = (c_double * 6)()
    serr = create_string_buffer(256)

    bodies = {
        "surya": SE_SUN,
        "chandra": SE_MOON,
        "mangal": SE_MARS,
        "budh": SE_MERCURY,
        "brihaspati": SE_JUPITER,
        "shukra": SE_VENUS,
        "shani": SE_SATURN,
        "rahu": SE_TRUE_NODE,
    }

    positions = fixture_data["positions"]

    # Test planets
    for key, pid in bodies.items():
        iflag = swe_engine.swe_calc_ut(
            c_double(jd), pid, SEFLG_SWIEPH | SEFLG_SPEED | SEFLG_SIDEREAL, xx, serr
        )
        assert iflag & SEFLG_SWIEPH, f"Failed to use SWIEPH for {key}: {serr.value.decode()}"

        lon = xx[0] % 360
        rashi = RASHIS[int(lon // 30)]
        ref = positions[key]

        # Sign must match exactly
        msg = f"{key} sign mismatch: computed {rashi}, expected {ref['sign']}"
        assert rashi == ref["sign"], msg

    # Ketu = Rahu + 180°
    swe_engine.swe_calc_ut(
        c_double(jd), SE_TRUE_NODE, SEFLG_SWIEPH | SEFLG_SPEED | SEFLG_SIDEREAL, xx, serr
    )
    ketu_lon = (xx[0] + 180) % 360
    ketu_rashi = RASHIS[int(ketu_lon // 30)]
    assert ketu_rashi == positions["ketu"]["sign"]

    # Lagna
    cusps = (c_double * 13)()
    ascmc = (c_double * 10)()
    swe_engine.swe_houses_ex(
        c_double(jd), SEFLG_SIDEREAL, c_double(26.45), c_double(87.283), ord("W"), cusps, ascmc
    )
    asc_lon = ascmc[0] % 360
    asc_rashi = RASHIS[int(asc_lon // 30)]
    assert asc_rashi == positions["lagna"]["sign"]


def test_moon_nakshatra_and_pada(
    swe_engine: SwissEph, fixture_data: dict[str, Any]
) -> None:
    """Validate Moon Nakshatra and Pada match ground truth."""
    jd = swe_engine.swe_julday(2006, 8, 1, 20.0 + 25.0 / 60.0, SE_GREG_CAL)
    xx = (c_double * 6)()
    serr = create_string_buffer(256)

    swe_engine.swe_calc_ut(
        c_double(jd), SE_MOON, SEFLG_SWIEPH | SEFLG_SPEED | SEFLG_SIDEREAL, xx, serr
    )
    moon_lon = xx[0] % 360

    nak_span = 360 / 27
    pada_span = nak_span / 4

    nak_idx = int(moon_lon // nak_span)
    pada = int((moon_lon % nak_span) // pada_span) + 1

    computed_nakshatra = NAKSHATRAS[nak_idx]
    ref_moon = fixture_data["positions"]["chandra"]

    assert computed_nakshatra == ref_moon["nakshatra"]
    assert pada == ref_moon["pada"]
