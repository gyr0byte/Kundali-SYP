"""Unit tests for ayanamsha module and lock-based isolation."""

from __future__ import annotations

import concurrent.futures

import pytest

from app.calc.ayanamsha import AyanamshaMode, get_ayanamsha_degrees


def test_ayanamsha_near_j2000() -> None:
    """Lahiri ayanamsha near J2000 (2000-01-01 12:00 UT = JD 2451545.0) is sane (~23.8° to 23.9°)."""
    jd_j2000 = 2451545.0
    deg = get_ayanamsha_degrees(jd_j2000, AyanamshaMode.LAHIRI)
    assert 23.8 <= deg <= 23.9, f"Unexpected Lahiri ayanamsha at J2000: {deg}"


def test_ayanamsha_modes_differ() -> None:
    """Lahiri, Raman, and Krishnamurti produce distinct ayanamsha values."""
    jd_j2000 = 2451545.0
    lahiri = get_ayanamsha_degrees(jd_j2000, AyanamshaMode.LAHIRI)
    raman = get_ayanamsha_degrees(jd_j2000, AyanamshaMode.RAMAN)
    kp = get_ayanamsha_degrees(jd_j2000, AyanamshaMode.KRISHNAMURTI)

    assert lahiri != raman
    assert lahiri != kp
    assert raman != kp

    # Raman is historically ~1.4° to 1.5° smaller than Lahiri
    assert raman < lahiri
    # Krishnamurti is slightly smaller than Lahiri (~5 to 6 arcminutes)
    assert kp < lahiri


def test_sidereal_mode_isolation_alternating() -> None:
    """Repeatedly alternating Lahiri and Raman calls must produce strictly identical values.

    Proves global Swiss Ephemeris sidereal mode state does not leak between calls.
    """
    jd = 2453949.3506944  # 2006-08-01 20:25 UT

    expected_lahiri = get_ayanamsha_degrees(jd, AyanamshaMode.LAHIRI)
    expected_raman = get_ayanamsha_degrees(jd, AyanamshaMode.RAMAN)

    assert expected_lahiri != expected_raman

    for _ in range(50):
        assert get_ayanamsha_degrees(jd, AyanamshaMode.LAHIRI) == pytest.approx(expected_lahiri, abs=1e-12)
        assert get_ayanamsha_degrees(jd, AyanamshaMode.RAMAN) == pytest.approx(expected_raman, abs=1e-12)


def test_thread_safe_ayanamsha_concurrency() -> None:
    """Concurrent threads requesting different ayanamshas do not corrupt each other's output."""
    jd = 2453949.3506944
    expected_lahiri = get_ayanamsha_degrees(jd, AyanamshaMode.LAHIRI)
    expected_raman = get_ayanamsha_degrees(jd, AyanamshaMode.RAMAN)

    def task(mode: AyanamshaMode) -> float:
        return get_ayanamsha_degrees(jd, mode)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = []
        for i in range(100):
            mode = AyanamshaMode.LAHIRI if i % 2 == 0 else AyanamshaMode.RAMAN
            futures.append((mode, executor.submit(task, mode)))

        for mode, fut in futures:
            res = fut.result()
            expected = expected_lahiri if mode == AyanamshaMode.LAHIRI else expected_raman
            assert res == pytest.approx(expected, abs=1e-12)
