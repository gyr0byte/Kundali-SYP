"""Unit tests for nakshatra and pada boundaries."""

from __future__ import annotations

from app.calc.nakshatra import NAKSHATRA_NAMES, nakshatra_of


def test_nakshatra_list_length_and_order() -> None:
    """Exactly 27 nakshatras in order from Ashwini to Revati."""
    assert len(NAKSHATRA_NAMES) == 27
    assert NAKSHATRA_NAMES[0] == "Ashwini"
    assert NAKSHATRA_NAMES[1] == "Bharani"
    assert NAKSHATRA_NAMES[14] == "Swati"
    assert NAKSHATRA_NAMES[26] == "Revati"


def test_boundary_0_degrees() -> None:
    """0.0 degrees is Ashwini pada 1."""
    idx, name, pada = nakshatra_of(0.0)
    assert idx == 0
    assert name == "Ashwini"
    assert pada == 1


def test_boundary_13_deg_20_min() -> None:
    """13° 20' (= 13.333333° degrees) is Bharani pada 1."""
    # 13 deg 20 min = 13 + 20/60 = 40/3 degrees
    deg = 40.0 / 3.0
    idx, name, pada = nakshatra_of(deg)
    assert idx == 1
    assert name == "Bharani"
    assert pada == 1

    # Just before 13° 20' is Ashwini pada 4
    idx_before, name_before, pada_before = nakshatra_of(deg - 1e-7)
    assert idx_before == 0
    assert name_before == "Ashwini"
    assert pada_before == 4


def test_boundary_359_999_degrees() -> None:
    """359.999 degrees is Revati pada 4."""
    idx, name, pada = nakshatra_of(359.999)
    assert idx == 26
    assert name == "Revati"
    assert pada == 4


def test_all_27_nakshatras_reachable() -> None:
    """Every nakshatra index 0..26 is reachable across the zodiac."""
    seen_indices = set()
    span = 360.0 / 27.0
    for i in range(27):
        test_lon = i * span + 1.0
        idx, name, pada = nakshatra_of(test_lon)
        assert idx == i
        assert name == NAKSHATRA_NAMES[i]
        assert 1 <= pada <= 4
        seen_indices.add(idx)

    assert len(seen_indices) == 27


def test_pada_width_3_deg_20_min() -> None:
    """Pada width is 3° 20' (10/3 degrees). All 4 padas are distinct."""
    pada_width = 10.0 / 3.0
    for pada_num in range(1, 5):
        lon = (pada_num - 1) * pada_width + 0.1
        idx, name, pada = nakshatra_of(lon)
        assert idx == 0
        assert name == "Ashwini"
        assert pada == pada_num
