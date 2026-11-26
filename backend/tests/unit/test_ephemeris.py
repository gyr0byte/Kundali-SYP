"""Unit tests for planetary and nodal ephemeris calculations and provenance."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest
from swisseph_ffi import (  # type: ignore[import-untyped]
    SE_MOON,
    SEFLG_JPLEPH,
    SEFLG_MOSEPH,
    SEFLG_NONUT,
    SEFLG_RADIANS,
    SEFLG_SIDEREAL,
    SEFLG_SPEED,
    SEFLG_SWIEPH,
    SEFLG_TRUEPOS,
)

import app.calc.ayanamsha as ayanamsha_mod
import app.calc.ephemeris as ephemeris_mod
from app.calc.ayanamsha import AyanamshaMode, CalculationError
from app.calc.ephemeris import NodeType, calculate_positions


def test_ketu_opposite_rahu() -> None:
    """Ketu longitude must be exactly Rahu + 180 degrees (mod 360)."""
    jd = 2453949.3506944
    res = calculate_positions(jd, ayanamsha=AyanamshaMode.LAHIRI, node_type=NodeType.MEAN)
    rahu = res.positions["rahu"]
    ketu = res.positions["ketu"]

    expected_ketu = (rahu.longitude + 180.0) % 360.0
    assert ketu.longitude == pytest.approx(expected_ketu, abs=1e-7)


def test_retrograde_rules() -> None:
    """Sun and Moon are never retrograde. Rahu and Ketu are always retrograde."""
    jd = 2453949.3506944
    res = calculate_positions(jd, ayanamsha=AyanamshaMode.LAHIRI)

    assert res.positions["sun"].retrograde is False
    assert res.positions["moon"].retrograde is False
    assert res.positions["rahu"].retrograde is True
    assert res.positions["ketu"].retrograde is True


def test_node_type_mean_vs_true() -> None:
    """Mean and True nodes yield different coordinates for the same epoch."""
    jd = 2453949.3506944
    mean_res = calculate_positions(jd, ayanamsha=AyanamshaMode.LAHIRI, node_type=NodeType.MEAN)
    true_res = calculate_positions(jd, ayanamsha=AyanamshaMode.LAHIRI, node_type=NodeType.TRUE)

    rahu_mean = mean_res.positions["rahu"].longitude
    rahu_true = true_res.positions["rahu"].longitude

    assert rahu_mean != rahu_true
    assert abs(rahu_mean - rahu_true) < 2.5


def test_ephemeris_provenance_swieph_moshier_and_mixed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reports 'swieph', 'moshier', or 'mixed' accurately without masking partial fallback."""
    jd = 2453949.3506944
    real_ephe = ayanamsha_mod.EPHE_DIR

    # 1. Full backend/ephe assets -> swieph (both Mean and True node)
    assert calculate_positions(jd, node_type=NodeType.MEAN).ephemeris_source == "swieph"
    assert calculate_positions(jd, node_type=NodeType.TRUE).ephemeris_source == "swieph"

    # 2. Empty ephemeris folder on D:
    # - With TRUE node (requires semo_18.se1), all 8 bodies use Moshier -> moshier
    # - With MEAN node (analytic SE_MEAN_NODE needs no .se1), planets fall back -> mixed
    empty_dir = tmp_path / "empty_ephe"
    empty_dir.mkdir()
    monkeypatch.setattr(ayanamsha_mod, "EPHE_DIR", empty_dir)
    assert calculate_positions(jd, node_type=NodeType.TRUE).ephemeris_source == "moshier"
    assert calculate_positions(jd, node_type=NodeType.MEAN).ephemeris_source == "mixed"

    # 3. Partial assets (only sepl_18.se1 without semo_18.se1) -> mixed (Moon uses Moshier)
    partial_dir = tmp_path / "partial_ephe"
    partial_dir.mkdir()
    shutil.copy2(real_ephe / "sepl_18.se1", partial_dir / "sepl_18.se1")
    monkeypatch.setattr(ayanamsha_mod, "EPHE_DIR", partial_dir)
    assert calculate_positions(jd, node_type=NodeType.TRUE).ephemeris_source == "mixed"


def test_ephemeris_mixed_provenance_and_auxiliary_flags_via_mock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Accepts SEFLG_NONUT/SPEED/SIDEREAL alongside source bits and detects mixed fallback."""

    class _FakeSweMixed:
        def swe_set_sid_mode(self, _sid: int, _t0: float, _ayan_t0: float) -> None:
            pass

        def swe_calc_ut(self, _jd: Any, pid: int, _flags: int, xx: Any, _serr: Any) -> int:
            xx[0] = 45.0
            xx[3] = 0.5
            if pid == SE_MOON:
                return int(SEFLG_MOSEPH | SEFLG_SPEED | SEFLG_SIDEREAL | SEFLG_NONUT)
            return int(SEFLG_SWIEPH | SEFLG_SPEED | SEFLG_SIDEREAL | SEFLG_NONUT)

    monkeypatch.setattr(ephemeris_mod, "get_swe_engine", lambda: _FakeSweMixed())
    res = calculate_positions(2451545.0)
    assert res.ephemeris_source == "mixed"


def test_ephemeris_swieph_and_moshier_auxiliary_flags_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Accepts full permitted auxiliary flags (SPEED, SIDEREAL, NONUT) for both sources."""

    def _run_with_source_bit(source_flag: int) -> str:
        class _FakeSwe:
            def swe_set_sid_mode(self, _sid: int, _t0: float, _ayan_t0: float) -> None:
                pass

            def swe_calc_ut(self, _jd: Any, _pid: int, _flags: int, xx: Any, _serr: Any) -> int:
                xx[0] = 45.0
                xx[3] = 0.5
                return int(source_flag | SEFLG_SPEED | SEFLG_SIDEREAL | SEFLG_NONUT)

        monkeypatch.setattr(ephemeris_mod, "get_swe_engine", lambda: _FakeSwe())
        return calculate_positions(2451545.0).ephemeris_source

    assert _run_with_source_bit(SEFLG_SWIEPH) == "swieph"
    assert _run_with_source_bit(SEFLG_MOSEPH) == "moshier"


@pytest.mark.parametrize(
    ("bad_iflag", "lon_val", "speed_val"),
    [
        (-1, 10.0, 0.5),
        (-42, 10.0, 0.5),
        (SEFLG_SPEED | SEFLG_SIDEREAL | SEFLG_NONUT, 10.0, 0.5),
        (SEFLG_JPLEPH | SEFLG_SPEED | SEFLG_SIDEREAL | SEFLG_NONUT, 10.0, 0.5),
        (SEFLG_SWIEPH | SEFLG_MOSEPH | SEFLG_SPEED | SEFLG_SIDEREAL | SEFLG_NONUT, 10.0, 0.5),
        (SEFLG_SWIEPH | SEFLG_SPEED | SEFLG_SIDEREAL | SEFLG_NONUT | (1 << 24), 10.0, 0.5),
        (SEFLG_MOSEPH | SEFLG_SPEED | SEFLG_SIDEREAL | SEFLG_NONUT | (1 << 25), 10.0, 0.5),
        (SEFLG_SWIEPH | SEFLG_SPEED | SEFLG_SIDEREAL | SEFLG_NONUT | SEFLG_RADIANS, 10.0, 0.5),
        (SEFLG_SWIEPH | SEFLG_SPEED | SEFLG_SIDEREAL | SEFLG_NONUT | SEFLG_TRUEPOS, 10.0, 0.5),
        (SEFLG_SWIEPH | SEFLG_SPEED | SEFLG_SIDEREAL | SEFLG_NONUT, float("nan"), 0.5),
        (SEFLG_SWIEPH | SEFLG_SPEED | SEFLG_SIDEREAL | SEFLG_NONUT, 10.0, float("inf")),
    ],
)
def test_ephemeris_fails_closed_on_bad_flags_and_nonfinite_outputs(
    monkeypatch: pytest.MonkeyPatch,
    bad_iflag: int,
    lon_val: float,
    speed_val: float,
) -> None:
    """Negative status, missing/JPL/contradictory bits, unknown high bits, and NaN fail closed."""

    class _FakeSweBad:
        def swe_set_sid_mode(self, _sid: int, _t0: float, _ayan_t0: float) -> None:
            pass

        def swe_calc_ut(self, _jd: Any, _pid: int, _flags: int, xx: Any, _serr: Any) -> int:
            xx[0] = lon_val
            xx[3] = speed_val
            return bad_iflag

    monkeypatch.setattr(ephemeris_mod, "get_swe_engine", lambda: _FakeSweBad())
    with pytest.raises(CalculationError):
        calculate_positions(2451545.0)


def test_ephemeris_fails_closed_on_invalid_jd_or_wrapper_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-finite JD or FFI exceptions fail closed cleanly as CalculationError."""
    with pytest.raises(CalculationError):
        calculate_positions(float("nan"))

    class _FakeSweRaises:
        def swe_set_sid_mode(self, _sid: int, _t0: float, _ayan_t0: float) -> None:
            pass

        def swe_calc_ut(self, *_args: Any) -> int:
            raise RuntimeError("C library error")

    monkeypatch.setattr(ephemeris_mod, "get_swe_engine", lambda: _FakeSweRaises())
    with pytest.raises(CalculationError):
        calculate_positions(2451545.0)


def test_alternating_sidereal_modes_isolation() -> None:
    """Planetary positions under Lahiri vs Raman must remain isolated without leakage."""
    jd = 2453949.3506944

    lahiri_1 = calculate_positions(jd, ayanamsha=AyanamshaMode.LAHIRI)
    raman_1 = calculate_positions(jd, ayanamsha=AyanamshaMode.RAMAN)

    assert lahiri_1.positions["sun"].longitude != raman_1.positions["sun"].longitude

    for _ in range(20):
        l_check = calculate_positions(jd, ayanamsha=AyanamshaMode.LAHIRI)
        r_check = calculate_positions(jd, ayanamsha=AyanamshaMode.RAMAN)
        exp_l = lahiri_1.positions["sun"].longitude
        exp_r = raman_1.positions["sun"].longitude
        assert l_check.positions["sun"].longitude == pytest.approx(exp_l, abs=1e-8)
        assert r_check.positions["sun"].longitude == pytest.approx(exp_r, abs=1e-8)
