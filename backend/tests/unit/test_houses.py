"""Unit tests for houses, quantization, and Lagna calculations."""

from __future__ import annotations

from typing import Any

import pytest

import app.calc.houses as houses_mod
from app.calc.ayanamsha import CalculationError
from app.calc.houses import (
    compute_lagna,
    degree_in_sign,
    house_of,
    is_lagna_boundary_sensitive,
    normalize_longitude,
    quantize_longitude,
    sign_of,
)


def test_sign_of_and_degree_in_sign() -> None:
    """Correct sign index 0..11 and degree within sign 0..30."""
    assert sign_of(0.0) == 0
    assert degree_in_sign(0.0) == pytest.approx(0.0)
    assert sign_of(15.5) == 0
    assert degree_in_sign(15.5) == pytest.approx(15.5)

    assert sign_of(30.0) == 1
    assert degree_in_sign(30.0) == pytest.approx(0.0)
    assert sign_of(45.0) == 1
    assert degree_in_sign(45.0) == pytest.approx(15.0)

    assert sign_of(330.0) == 11
    assert degree_in_sign(330.0) == pytest.approx(0.0)
    assert sign_of(359.9) == 11
    assert degree_in_sign(359.9) == pytest.approx(29.9)


def test_longitude_normalization_and_quantization_boundaries() -> None:
    """Wrap/quantize edge values cleanly without ever emitting degree == 30.0 or lon == 360.0."""
    assert normalize_longitude(-1e-17) == 0.0
    assert sign_of(-1e-17) == 0
    assert degree_in_sign(-1e-17) == 0.0

    # Rounding across cusp promotes cleanly to next sign degree 0.0
    assert quantize_longitude(29.9999996) == 30.0
    assert sign_of(30.0) == 1
    assert degree_in_sign(30.0) == 0.0

    assert quantize_longitude(359.9999996) == 0.0
    assert sign_of(0.0) == 0
    assert degree_in_sign(0.0) == 0.0

    assert quantize_longitude(59.9999994) == 59.999999
    assert sign_of(59.999999) == 1
    assert degree_in_sign(59.999999) == pytest.approx(29.999999)

    for bad_lon in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(CalculationError):
            quantize_longitude(bad_lon)


def test_whole_sign_houses_all_combinations() -> None:
    """house_of wraps 1..12 correctly for all sign combinations."""
    for planet_sign in range(12):
        planet_lon = planet_sign * 30.0 + 10.0
        lagna_lon = 0 * 30.0 + 10.0
        expected_house = planet_sign + 1
        assert house_of(planet_lon, lagna_lon) == expected_house

    assert house_of(65.0, 62.0) == 1
    assert house_of(95.0, 62.0) == 2
    assert house_of(35.0, 62.0) == 12
    assert house_of(5.0, 62.0) == 11


def test_lagna_boundary_sensitivity() -> None:
    """Lagna boundary warning triggers within 0.5 degrees of sign edge, and not at 5 degrees."""
    assert is_lagna_boundary_sensitive(0.3) is True
    assert is_lagna_boundary_sensitive(30.2) is True
    assert is_lagna_boundary_sensitive(60.49) is True

    assert is_lagna_boundary_sensitive(29.7) is True
    assert is_lagna_boundary_sensitive(59.9) is True

    assert is_lagna_boundary_sensitive(5.0) is False
    assert is_lagna_boundary_sensitive(15.0) is False
    assert is_lagna_boundary_sensitive(25.0) is False
    assert is_lagna_boundary_sensitive(62.55) is False


def test_compute_lagna_fails_closed_on_bad_inputs_status_or_wrapper_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Negative swe_houses_ex status, NaN ascendant, bad coords, and exceptions fail closed."""
    with pytest.raises(CalculationError):
        compute_lagna(float("nan"), 26.45, 87.283)
    with pytest.raises(CalculationError):
        compute_lagna(2451545.0, 95.0, 87.283)
    with pytest.raises(CalculationError):
        compute_lagna(2451545.0, 26.45, 185.0)

    class _FakeSweNegHouses:
        def swe_set_sid_mode(self, _sid: int, _t0: float, _ayan_t0: float) -> None:
            pass

        def swe_houses_ex(self, *_args: Any) -> int:
            return -1

    monkeypatch.setattr(houses_mod, "get_swe_engine", lambda: _FakeSweNegHouses())
    with pytest.raises(CalculationError):
        compute_lagna(2451545.0, 26.45, 87.283)

    class _FakeSweNanAsc:
        def swe_set_sid_mode(self, _sid: int, _t0: float, _ayan_t0: float) -> None:
            pass

        def swe_houses_ex(
            self, _jd: Any, _fl: Any, _lat: Any, _lon: Any, _hsys: Any, _cusps: Any, ascmc: Any
        ) -> int:
            ascmc[0] = float("nan")
            return 0

    monkeypatch.setattr(houses_mod, "get_swe_engine", lambda: _FakeSweNanAsc())
    with pytest.raises(CalculationError):
        compute_lagna(2451545.0, 26.45, 87.283)

    class _FakeSweExcAsc:
        def swe_set_sid_mode(self, _sid: int, _t0: float, _ayan_t0: float) -> None:
            pass

        def swe_houses_ex(self, *_args: Any) -> int:
            raise RuntimeError("FFI crash")

    monkeypatch.setattr(houses_mod, "get_swe_engine", lambda: _FakeSweExcAsc())
    with pytest.raises(CalculationError):
        compute_lagna(2451545.0, 26.45, 87.283)
