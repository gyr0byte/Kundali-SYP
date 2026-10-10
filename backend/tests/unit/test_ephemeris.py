"""Unit tests for planetary and nodal ephemeris calculations."""

from __future__ import annotations

import pytest

from app.calc.ayanamsha import AyanamshaMode
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

    # Sun & Moon never retrograde
    assert res.positions["sun"].retrograde is False
    assert res.positions["moon"].retrograde is False

    # Rahu & Ketu always retrograde
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
    # Typically difference between mean and true node is within 2 degrees
    assert abs(rahu_mean - rahu_true) < 2.5


def test_ephemeris_source_reported() -> None:
    """Metadata correctly reports whether swieph or moshier was used."""
    jd = 2453949.3506944
    res = calculate_positions(jd)
    assert res.ephemeris_source in ("swieph", "moshier")


def test_alternating_sidereal_modes_isolation() -> None:
    """Planetary positions under Lahiri vs Raman must remain isolated without leakage."""
    jd = 2453949.3506944

    lahiri_1 = calculate_positions(jd, ayanamsha=AyanamshaMode.LAHIRI)
    raman_1 = calculate_positions(jd, ayanamsha=AyanamshaMode.RAMAN)

    assert lahiri_1.positions["sun"].longitude != raman_1.positions["sun"].longitude

    # Alternate 20 times
    for _ in range(20):
        l_check = calculate_positions(jd, ayanamsha=AyanamshaMode.LAHIRI)
        r_check = calculate_positions(jd, ayanamsha=AyanamshaMode.RAMAN)
        assert l_check.positions["sun"].longitude == pytest.approx(lahiri_1.positions["sun"].longitude, abs=1e-8)
        assert r_check.positions["sun"].longitude == pytest.approx(raman_1.positions["sun"].longitude, abs=1e-8)
