"""Unit tests for ChartFacts generation, schema, determinism, concurrency, and fact IDs."""

from __future__ import annotations

import concurrent.futures
import datetime
import shutil
import threading
from pathlib import Path
from typing import Any

import pytest

import app.calc.ayanamsha as ayanamsha_mod
import app.calc.facts as facts_mod
from app.calc.ayanamsha import SWE_LOCK, AyanamshaMode
from app.calc.ephemeris import (
    BodyEphemerisSource,
    EphemerisResult,
    EphemerisSource,
    NodeType,
    PlanetPosition,
)
from app.calc.facts import (
    ENGINE_VERSION,
    ChartFactLagna,
    ChartFactPlacement,
    ChartFactSensitivity,
    ChartSettings,
    compute_chart_facts,
)
from app.calc.houses import compute_lagna
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


def test_engine_version_bumped() -> None:
    """ENGINE_VERSION reflects the hardened calculation engine contract."""
    assert ENGINE_VERSION == "0.2.0"


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
    assert len(set(fact_ids)) == len(fact_ids)


def test_lagna_sensitivity_fact_added_when_boundary_triggered(
    sample_settings: ChartSettings,
) -> None:
    """When Lagna is within 0.5 degrees of sign edge, f_lagna_sensitivity is emitted."""
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
        assert isinstance(sens, ChartFactSensitivity)
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


def test_schema_disallows_extra_fields_and_blank_chart_id(
    sample_birth_input: TimeInput, sample_settings: ChartSettings
) -> None:
    """Extra fields and empty chart_id are rejected cleanly."""
    with pytest.raises(Exception):
        ChartSettings(
            ayanamsha=AyanamshaMode.LAHIRI,
            extra_invented_setting="invalid",  # type: ignore[call-arg]
        )

    with pytest.raises(ValueError, match="chart_id"):
        compute_chart_facts(sample_birth_input, sample_settings, chart_id="   ")


def test_chart_settings_year_days_and_preset_validation() -> None:
    """Validates finite supported year_days, known presets, and preset-field consistency."""
    for ok_days in (360, 360.0, 365.2425, 365.25):
        cfg = ChartSettings(year_days=float(ok_days))
        assert cfg.year_days == float(ok_days)

    for bad_days in (0.0, -365.25, 365.0, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            ChartSettings(year_days=bad_days)

    with pytest.raises(ValueError):
        ChartSettings(year_days=True)

    # Unknown preset rejected directly
    with pytest.raises(ValueError):
        ChartSettings(preset="unknown_preset")

    # Preset auto-populates omitted fields while allowing compatible year_days selection
    compat = ChartSettings(preset="hamro_patro_compat")
    assert compat.ayanamsha == AyanamshaMode.LAHIRI_1940
    assert compat.node_type == NodeType.TRUE

    compat_savana = ChartSettings(preset="hamro_patro_compat", year_days=360)
    assert compat_savana.ayanamsha == AyanamshaMode.LAHIRI_1940
    assert compat_savana.node_type == NodeType.TRUE
    assert compat_savana.year_days == 360.0

    # Contradictory explicit overrides rejected
    with pytest.raises(ValueError, match="contradicts preset"):
        ChartSettings(preset="hamro_patro_compat", ayanamsha=AyanamshaMode.RAMAN)
    with pytest.raises(ValueError, match="contradicts preset"):
        ChartSettings(preset="hamro_patro_compat", node_type=NodeType.MEAN)


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


def test_quantized_cusp_rounding_keeps_sign_degree_house_sensitivity_consistent(
    sample_birth_input: TimeInput,
    sample_settings: ChartSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Near-cusp values (29.9999996° and 359.9999996°) never yield degree == 30.0 or mismatches."""
    raw_positions = {
        "sun": PlanetPosition(name="sun", longitude=359.9999996, speed=1.0, retrograde=False),
        "moon": PlanetPosition(name="moon", longitude=29.9999996, speed=13.0, retrograde=False),
        "mars": PlanetPosition(name="mars", longitude=59.9999994, speed=0.6, retrograde=False),
        "mercury": PlanetPosition(name="mercury", longitude=90.0, speed=1.2, retrograde=False),
        "jupiter": PlanetPosition(name="jupiter", longitude=120.0, speed=0.1, retrograde=False),
        "venus": PlanetPosition(name="venus", longitude=150.0, speed=1.1, retrograde=False),
        "saturn": PlanetPosition(name="saturn", longitude=180.0, speed=-0.05, retrograde=True),
        "rahu": PlanetPosition(name="rahu", longitude=210.0, speed=-0.05, retrograde=True),
        "ketu": PlanetPosition(name="ketu", longitude=30.0, speed=-0.05, retrograde=True),
    }

    monkeypatch.setattr(facts_mod, "compute_lagna", lambda *_args: 29.9999996)
    monkeypatch.setattr(
        facts_mod,
        "calculate_positions",
        lambda *_args, **_kwargs: EphemerisResult(
            positions=raw_positions,
            ephemeris_source="swieph",
            body_sources=dict.fromkeys(raw_positions, "swieph"),
        ),
    )

    doc = compute_chart_facts(sample_birth_input, sample_settings, chart_id="c_round_001")
    lagna = next(f for f in doc.facts if isinstance(f, ChartFactLagna))
    assert lagna.sign == "Taurus"
    assert lagna.sign_index == 1
    assert lagna.longitude == 30.0
    assert lagna.degree == 0.0

    moon = next(f for f in doc.facts if f.id == "f_moon")
    assert isinstance(moon, ChartFactPlacement)
    assert moon.sign == "Taurus"
    assert moon.longitude == 30.0
    assert moon.degree == 0.0
    assert moon.house == 1

    sun = next(f for f in doc.facts if f.id == "f_sun")
    assert isinstance(sun, ChartFactPlacement)
    assert sun.sign == "Aries"
    assert sun.longitude == 0.0
    assert sun.degree == 0.0
    assert sun.house == 12

    mars = next(f for f in doc.facts if f.id == "f_mars")
    assert isinstance(mars, ChartFactPlacement)
    assert mars.sign == "Taurus"
    assert mars.degree == pytest.approx(29.999999)
    assert mars.degree < 30.0
    assert mars.house == 1

    sens = next(f for f in doc.facts if isinstance(f, ChartFactSensitivity))
    assert sens.degree_in_sign == 0.0
    assert sens.boundary_distance_degrees == 0.0


def test_result_identity_canonicalizes_body_sources_and_covers_final_facts(
    sample_birth_input: TimeInput, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Frozen positions isolate identity semantics from installed ephemeris files."""
    positions = {
        name: PlanetPosition(name=name, longitude=longitude, speed=0.5, retrograde=False)
        for name, longitude in (
            ("sun", 105.0),
            ("moon", 189.0),
            ("mars", 140.0),
            ("mercury", 94.0),
            ("jupiter", 242.0),
            ("venus", 175.0),
            ("saturn", 121.0),
            ("rahu", 328.0),
            ("ketu", 148.0),
        )
    }
    monkeypatch.setattr(facts_mod, "compute_lagna", lambda *_args: 115.0)

    def calculate(
        source: EphemerisSource,
        body_sources: dict[str, BodyEphemerisSource],
        birth: TimeInput = sample_birth_input,
    ) -> str:
        result = EphemerisResult(
            positions=positions, ephemeris_source=source, body_sources=body_sources
        )
        monkeypatch.setattr(facts_mod, "calculate_positions", lambda *_args, **_kwargs: result)
        return compute_chart_facts(birth, ChartSettings()).chart_id

    swieph: dict[str, BodyEphemerisSource] = dict.fromkeys(positions, "swieph")
    moshier: dict[str, BodyEphemerisSource] = dict.fromkeys(positions, "moshier")
    mixed = swieph | {"sun": "moshier"}
    other_mixed = swieph | {"moon": "moshier"}
    baseline = calculate("swieph", swieph)

    assert calculate("swieph", dict(reversed(list(swieph.items())))) == baseline
    assert (
        len(
            {
                baseline,
                calculate("moshier", moshier),
                calculate("mixed", mixed),
                calculate("mixed", other_mixed),
            }
        )
        == 4
    )

    shifted_location = sample_birth_input.model_copy(update={"latitude": 26.4500001})
    assert calculate("swieph", swieph, shifted_location) != baseline

    positions["sun"] = positions["sun"].model_copy(update={"longitude": 105.002})
    assert calculate("swieph", swieph) != baseline


def test_compute_chart_facts_propagates_swieph_moshier_and_mixed_provenance(
    sample_birth_input: TimeInput,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ChartMetadata accurately reports 'swieph', 'moshier', and 'mixed' ephemeris_source."""
    real_ephe = ayanamsha_mod.EPHE_DIR
    true_settings = ChartSettings(
        ayanamsha=AyanamshaMode.LAHIRI,
        house_system="whole_sign",
        node_type=NodeType.TRUE,
    )

    swi_doc = compute_chart_facts(sample_birth_input, true_settings, chart_id="c_swi")
    assert swi_doc.metadata.ephemeris_source == "swieph"

    empty_dir = tmp_path / "empty_ephe"
    empty_dir.mkdir()
    monkeypatch.setattr(ayanamsha_mod, "EPHE_DIR", empty_dir)
    mos_doc = compute_chart_facts(sample_birth_input, true_settings, chart_id="c_mos")
    assert mos_doc.metadata.ephemeris_source == "moshier"

    mean_settings = ChartSettings(node_type=NodeType.MEAN)
    mean_empty_doc = compute_chart_facts(sample_birth_input, mean_settings, chart_id="c_mix_mean")
    assert mean_empty_doc.metadata.ephemeris_source == "mixed"

    partial_dir = tmp_path / "partial_ephe"
    partial_dir.mkdir()
    shutil.copy2(real_ephe / "sepl_18.se1", partial_dir / "sepl_18.se1")
    monkeypatch.setattr(ayanamsha_mod, "EPHE_DIR", partial_dir)
    mix_doc = compute_chart_facts(sample_birth_input, true_settings, chart_id="c_mix_part")
    assert mix_doc.metadata.ephemeris_source == "mixed"


def test_concurrent_chart_calculations_synchronized_and_atomic(
    sample_birth_input: TimeInput,
) -> None:
    """Concurrent compute_chart_facts calls with distinct ayanamshas do not interleave or leak."""
    configs = [
        ChartSettings(ayanamsha=AyanamshaMode.LAHIRI, node_type=NodeType.MEAN),
        ChartSettings(ayanamsha=AyanamshaMode.LAHIRI_1940, node_type=NodeType.TRUE),
        ChartSettings(ayanamsha=AyanamshaMode.RAMAN, node_type=NodeType.MEAN),
        ChartSettings(ayanamsha=AyanamshaMode.KRISHNAMURTI, node_type=NodeType.TRUE),
    ]
    baseline_jsons = [
        compute_chart_facts(sample_birth_input, cfg, chart_id=f"c_conc_{idx}").model_dump_json()
        for idx, cfg in enumerate(configs)
    ]

    worker_count = 8
    barrier = threading.Barrier(worker_count)

    def run_worker(worker_idx: int) -> tuple[int, str]:
        cfg_idx = worker_idx % len(configs)
        barrier.wait(timeout=5.0)
        doc = compute_chart_facts(
            sample_birth_input, configs[cfg_idx], chart_id=f"c_conc_{cfg_idx}"
        )
        return cfg_idx, doc.model_dump_json()

    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
        submitted = [executor.submit(run_worker, i) for i in range(worker_count)]
        results = [fut.result() for fut in submitted]

    for cfg_idx, actual_json in results:
        assert actual_json == baseline_jsons[cfg_idx]


def test_atomic_lock_prevents_mid_chart_interleaving(
    sample_birth_input: TimeInput,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """compute_chart_facts holds outer SWE_LOCK continuously between Lagna and planets."""
    orig_compute_lagna = compute_lagna
    lagna_finished = threading.Event()
    allow_continue = threading.Event()
    probe_finished = threading.Event()

    acquired_by_competitor: list[bool] = []
    worker_errors: list[BaseException] = []
    completed_charts: list[str] = []

    def paused_compute_lagna(*args: Any, **kwargs: Any) -> float:
        result = orig_compute_lagna(*args, **kwargs)
        lagna_finished.set()
        if not allow_continue.wait(timeout=5.0):
            raise TimeoutError("Timed out waiting for continuation event after Lagna.")
        return result

    monkeypatch.setattr(facts_mod, "compute_lagna", paused_compute_lagna)

    def _chart_worker() -> None:
        try:
            doc = compute_chart_facts(
                sample_birth_input,
                ChartSettings(ayanamsha=AyanamshaMode.LAHIRI),
                chart_id="c_lock_outer_001",
            )
            completed_charts.append(doc.chart_id)
        except BaseException as exc:  # noqa: BLE001 - propagate thread exception to main thread
            worker_errors.append(exc)
        finally:
            lagna_finished.set()

    def _probe_worker() -> None:
        try:
            acquired = SWE_LOCK.acquire(blocking=False)
            acquired_by_competitor.append(acquired)
            if acquired:
                SWE_LOCK.release()
        except BaseException as exc:  # noqa: BLE001 - propagate thread exception to main thread
            worker_errors.append(exc)
        finally:
            probe_finished.set()

    t1 = threading.Thread(target=_chart_worker, name="chart-calc-worker")
    t2 = threading.Thread(target=_probe_worker, name="lock-probe-worker")

    try:
        t1.start()
        assert lagna_finished.wait(timeout=5.0), "First thread never finished Lagna."

        # Inner SWE_LOCK in compute_lagna() has exited; only outer compute_chart_facts()
        # SWE_LOCK holds the lock at this synchronization point.
        t2.start()
        assert probe_finished.wait(timeout=5.0), "Competing thread lock probe timed out."
    finally:
        allow_continue.set()
        t1.join(timeout=5.0)
        t2.join(timeout=5.0)

    assert not t1.is_alive()
    assert not t2.is_alive()
    if worker_errors:
        raise worker_errors[0]

    assert acquired_by_competitor == [False]
    assert completed_charts == ["c_lock_outer_001"]


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
