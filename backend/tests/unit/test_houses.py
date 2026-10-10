"""Unit tests for houses and Lagna calculations."""

from __future__ import annotations

import pytest

from app.calc.houses import (
    degree_in_sign,
    house_of,
    is_lagna_boundary_sensitive,
    sign_of,
)


def test_sign_of_and_degree_in_sign() -> None:
    """Correct sign index 0..11 and degree within sign 0..30."""
    # Aries: 0 to 30
    assert sign_of(0.0) == 0
    assert degree_in_sign(0.0) == pytest.approx(0.0)
    assert sign_of(15.5) == 0
    assert degree_in_sign(15.5) == pytest.approx(15.5)

    # Taurus: 30 to 60
    assert sign_of(30.0) == 1
    assert degree_in_sign(30.0) == pytest.approx(0.0)
    assert sign_of(45.0) == 1
    assert degree_in_sign(45.0) == pytest.approx(15.0)

    # Pisces: 330 to 360
    assert sign_of(330.0) == 11
    assert degree_in_sign(330.0) == pytest.approx(0.0)
    assert sign_of(359.9) == 11
    assert degree_in_sign(359.9) == pytest.approx(29.9)


def test_whole_sign_houses_all_combinations() -> None:
    """house_of wraps 1..12 correctly for all sign combinations."""
    # When Lagna is Aries (sign 0):
    for planet_sign in range(12):
        planet_lon = planet_sign * 30.0 + 10.0
        lagna_lon = 0 * 30.0 + 10.0
        expected_house = planet_sign + 1
        assert house_of(planet_lon, lagna_lon) == expected_house

    # When Lagna is Gemini (sign 2):
    # Gemini -> 1st house
    assert house_of(65.0, 62.0) == 1
    # Cancer (sign 3) -> 2nd house
    assert house_of(95.0, 62.0) == 2
    # Taurus (sign 1) -> 12th house
    assert house_of(35.0, 62.0) == 12
    # Aries (sign 0) -> 11th house
    assert house_of(5.0, 62.0) == 11


def test_lagna_boundary_sensitivity() -> None:
    """Lagna boundary warning triggers within 0.5 degrees of sign edge, and not at 5 degrees."""
    # Near beginning of sign: < 0.5°
    assert is_lagna_boundary_sensitive(0.3) is True
    assert is_lagna_boundary_sensitive(30.2) is True
    assert is_lagna_boundary_sensitive(60.49) is True

    # Near end of sign: >= 29.5°
    assert is_lagna_boundary_sensitive(29.7) is True
    assert is_lagna_boundary_sensitive(59.9) is True

    # Well inside sign: does NOT trigger
    assert is_lagna_boundary_sensitive(5.0) is False
    assert is_lagna_boundary_sensitive(15.0) is False
    assert is_lagna_boundary_sensitive(25.0) is False
    assert is_lagna_boundary_sensitive(62.55) is False
