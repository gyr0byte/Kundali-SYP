"""Regression tests against public synthetic fixtures and private reference charts.

Adheres strictly to tolerances defined in Kundali_Project_Plan.md §15.1:
- Planet longitudes within ±0.01° of direct ephemeris call
- Lagna sign exact
- Moon nakshatra and pada exact
- Null expected values are skipped without guessing
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

import pytest

from app.calc.ayanamsha import AyanamshaMode
from app.calc.ephemeris import NodeType
from app.calc.facts import ChartSettings, compute_chart_facts
from app.calc.houses import rashi_name
from app.calc.timeconv import TimeInput

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
PUBLIC_FIXTURES_DIR = PROJECT_ROOT / "fixtures" / "charts"
PRIVATE_FIXTURES_DIR = PROJECT_ROOT / "fixtures" / "charts_private"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _build_inputs(data: dict[str, Any]) -> tuple[TimeInput, ChartSettings]:
    b = data["birth"]
    date_val = datetime.date.fromisoformat(b["date"])
    time_val = datetime.time.fromisoformat(b["time"])
    tz_val = b.get("timezone")
    offset_val = b.get("utc_offset_hours")

    time_inp = TimeInput(
        date=date_val,
        time=time_val,
        latitude=b["latitude"],
        longitude=b["longitude"],
        timezone=tz_val,
        utc_offset_hours=offset_val if tz_val is None else None,
    )

    s = data.get("settings", {})
    ayanamsha_str = s.get("ayanamsha", "lahiri")
    node_str = s.get("node_type", "mean")

    settings = ChartSettings(
        ayanamsha=AyanamshaMode(ayanamsha_str),
        house_system="whole_sign",
        node_type=NodeType(node_str),
    )
    return time_inp, settings


def test_private_fixture_001() -> None:
    """Validate Builder's Chart (fixture_001) in fixtures/charts_private.

    Skips cleanly if the file is absent.
    Any expected value left null is SKIPPED, never guessed.
    """
    fixture_path = PRIVATE_FIXTURES_DIR / "fixture_001.json"
    if not fixture_path.exists():
        pytest.skip("Private fixture #1 (fixtures/charts_private/fixture_001.json) is not present.")

    data = _load_json(fixture_path)
    time_inp, settings = _build_inputs(data)
    doc = compute_chart_facts(time_inp, settings, chart_id=data.get("id", "c_priv_001"))

    expected = data.get("expected", {})

    # 1. Moon validation
    moon_exp = expected.get("moon")
    if moon_exp is not None:
        moon_fact = next(f for f in doc.facts if f.id == "f_moon")

        # Check Moon sign
        if "sign" in moon_exp and moon_exp["sign"] is not None:
            assert moon_fact.sign == moon_exp["sign"]

        # Check Moon rashi (Vedic Sanskrit)
        if "sign_rashi" in moon_exp and moon_exp["sign_rashi"] is not None:
            assert rashi_name(moon_fact.sign_index) == moon_exp["sign_rashi"]

        # Check Nakshatra & Pada
        if "nakshatra" in moon_exp and moon_exp["nakshatra"] is not None:
            assert moon_fact.nakshatra == moon_exp["nakshatra"]
        if "pada" in moon_exp and moon_exp["pada"] is not None:
            assert moon_fact.pada == moon_exp["pada"]

    # 2. Lagna validation (skip if null)
    lagna_exp = expected.get("lagna")
    if lagna_exp is not None:
        lagna_fact = next(f for f in doc.facts if f.id == "f_lagna")
        if "sign" in lagna_exp and lagna_exp["sign"] is not None:
            assert lagna_fact.sign == lagna_exp["sign"]
        if "longitude" in lagna_exp and lagna_exp["longitude"] is not None:
            assert lagna_fact.longitude == pytest.approx(lagna_exp["longitude"], abs=0.01)

    # 3. Planet validations (skip if null)
    planets_exp = expected.get("planets", {})
    for p_name, p_data in planets_exp.items():
        if p_data is None:
            continue
        p_fact = next(f for f in doc.facts if f.id == f"f_{p_name}")
        if "sign" in p_data and p_data["sign"] is not None:
            assert p_fact.sign == p_data["sign"]
        if "longitude" in p_data and p_data["longitude"] is not None:
            assert p_fact.longitude == pytest.approx(p_data["longitude"], abs=0.01)


@pytest.mark.parametrize(
    "fixture_filename",
    [
        "fixture_north_london.json",
        "fixture_south_sydney.json",
        "fixture_near_midnight_tokyo.json",
    ],
)
def test_public_synthetic_fixtures(fixture_filename: str) -> None:
    """Validate calculation engine against public synthetic test fixtures."""
    path = PUBLIC_FIXTURES_DIR / fixture_filename
    assert path.exists(), f"Synthetic fixture missing: {path}"

    data = _load_json(path)
    time_inp, settings = _build_inputs(data)
    doc = compute_chart_facts(time_inp, settings, chart_id=data["id"])

    expected = data["expected"]
    tol = data.get("tolerances", {})
    lon_tol = tol.get("planet_longitude_degrees", 0.01)

    # Lagna
    lagna_fact = next(f for f in doc.facts if f.id == "f_lagna")
    assert lagna_fact.sign == expected["lagna"]["sign"]
    assert lagna_fact.longitude == pytest.approx(expected["lagna"]["longitude"], abs=lon_tol)
    assert lagna_fact.nakshatra == expected["lagna"]["nakshatra"]
    assert lagna_fact.pada == expected["lagna"]["pada"]

    # Moon
    moon_fact = next(f for f in doc.facts if f.id == "f_moon")
    assert moon_fact.sign == expected["moon"]["sign"]
    assert moon_fact.longitude == pytest.approx(expected["moon"]["longitude"], abs=lon_tol)
    assert moon_fact.nakshatra == expected["moon"]["nakshatra"]
    assert moon_fact.pada == expected["moon"]["pada"]

    # Other planets
    for p_name, p_exp in expected.get("planets", {}).items():
        if p_exp is None:
            continue
        p_fact = next(f for f in doc.facts if f.id == f"f_{p_name}")
        assert p_fact.sign == p_exp["sign"]
        assert p_fact.longitude == pytest.approx(p_exp["longitude"], abs=lon_tol)
        assert p_fact.house == p_exp["house"]
        assert p_fact.retrograde == p_exp["retrograde"]
