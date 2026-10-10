"""Unit tests for ChartFacts generation, schema, determinism, and fact IDs."""

from __future__ import annotations

import datetime

import pytest

from app.calc.ayanamsha import AyanamshaMode
from app.calc.ephemeris import NodeType
from app.calc.facts import (
    ENGINE_VERSION,
    ChartFactLagna,
    ChartFactPlacement,
    ChartSettings,
    compute_chart_facts,
)
from app.calc.timeconv import TimeInput


@pytest.fixture
def sample_birth_input() -> TimeInput:
    return TimeInput(
        date=datetime.date(2006, 8, 2),
        time=datetime.time(2, 10, 0),
        latitude=26.45,
        longitude=87.283,
        timezone="Asia/Kathmandu",
    )


@pytest.fixture
def sample_settings() -> ChartSettings:
    return ChartSettings(
        ayanamsha=AyanamshaMode.LAHIRI,
        house_system="whole_sign",
        node_type=NodeType.MEAN,
    )


def test_fact_ids_and_counts_standard(
    sample_birth_input: TimeInput, sample_settings: ChartSettings
) -> None:
    """Standard chart produces exactly 10 fact IDs (1 lagna + 9 planets)."""
    facts_doc = compute_chart_facts(sample_birth_input, sample_settings, chart_id="c_test_001")

    assert facts_doc.chart_id == "c_test_001"
    assert facts_doc.engine_version == ENGINE_VERSION
    assert facts_doc.settings.ayanamsha == AyanamshaMode.LAHIRI

    fact_ids = [f.id for f in facts_doc.facts]
    expected_ids = [
        "f_lagna",
        "f_sun",
        "f_moon",
        "f_mars",
        "f_mercury",
        "f_jupiter",
        "f_venus",
        "f_saturn",
        "f_rahu",
        "f_ketu",
    ]
    assert fact_ids == expected_ids
    assert len(set(fact_ids)) == len(fact_ids)  # Unique IDs


def test_lagna_sensitivity_fact_added_when_boundary_triggered(
    sample_settings: ChartSettings,
) -> None:
    """When Lagna is within 0.5 degrees of sign edge, f_lagna_sensitivity is emitted."""
    # Find an epoch where Lagna is within 0.5° of edge (e.g. degree < 0.5)
    # Using 2006-08-02 01:58:00 Asia/Kathmandu (Lagna near 0° Gemini)
    edge_input = TimeInput(
        date=datetime.date(2006, 8, 2),
        time=datetime.time(1, 58, 0),
        latitude=26.45,
        longitude=87.283,
        timezone="Asia/Kathmandu",
    )
    doc = compute_chart_facts(edge_input, sample_settings, chart_id="c_edge_001")
    lagna_fact = next(f for f in doc.facts if f.id == "f_lagna")
    assert isinstance(lagna_fact, ChartFactLagna)

    fact_ids = [f.id for f in doc.facts]
    if lagna_fact.degree < 0.5 or lagna_fact.degree >= 29.5:
        assert "f_lagna_sensitivity" in fact_ids
        sens = next(f for f in doc.facts if f.id == "f_lagna_sensitivity")
        assert sens.type == "sensitivity"
    else:
        assert "f_lagna_sensitivity" not in fact_ids


def test_determinism_identical_json(
    sample_birth_input: TimeInput, sample_settings: ChartSettings
) -> None:
    """Same input evaluated twice produces byte-identical JSON strings."""
    doc1 = compute_chart_facts(sample_birth_input, sample_settings, chart_id="c_det_001")
    doc2 = compute_chart_facts(sample_birth_input, sample_settings, chart_id="c_det_001")

    json1 = doc1.model_dump_json()
    json2 = doc2.model_dump_json()

    assert json1 == json2
    assert len(json1) > 0


def test_schema_disallows_extra_fields() -> None:
    """Extra fields are rejected by ChartSettings and ChartFacts models."""
    with pytest.raises(Exception):
        ChartSettings(
            ayanamsha=AyanamshaMode.LAHIRI,
            extra_invented_setting="invalid",  # type: ignore[call-arg]
        )


def test_planet_facts_structure(
    sample_birth_input: TimeInput, sample_settings: ChartSettings
) -> None:
    """Planet facts contain required fields and valid types."""
    doc = compute_chart_facts(sample_birth_input, sample_settings, chart_id="c_test_struct")
    moon_fact = next(f for f in doc.facts if f.id == "f_moon")
    assert isinstance(moon_fact, ChartFactPlacement)

    assert moon_fact.planet == "Moon"
    assert moon_fact.type == "placement"
    assert 1 <= moon_fact.house <= 12
    assert 0 <= moon_fact.sign_index <= 11
    assert 0.0 <= moon_fact.degree < 30.0
    assert 0.0 <= moon_fact.longitude < 360.0
    assert 1 <= moon_fact.pada <= 4
    assert isinstance(moon_fact.retrograde, bool)
    assert isinstance(moon_fact.speed, float)


def test_default_chart_settings() -> None:
    """Default ChartSettings uses Lahiri ayanamsha and Mean node."""
    settings = ChartSettings()
    assert settings.ayanamsha == AyanamshaMode.LAHIRI
    assert settings.node_type == NodeType.MEAN
    assert settings.house_system == "whole_sign"


def test_preset_hamro_patro_compat() -> None:
    """ChartSettings.from_preset('hamro_patro_compat') returns True node and LAHIRI_1940."""
    settings = ChartSettings.from_preset("hamro_patro_compat")
    assert settings.ayanamsha == AyanamshaMode.LAHIRI_1940
    assert settings.node_type == NodeType.TRUE
    assert settings.house_system == "whole_sign"
    assert settings.preset == "hamro_patro_compat"
