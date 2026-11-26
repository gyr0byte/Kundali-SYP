"""Unit tests for ayanamsha module, flag validation, and lock-based isolation."""

from __future__ import annotations

import concurrent.futures
import threading
from ctypes import c_double
from typing import Any

import pytest
from swisseph_ffi import (  # type: ignore[import-untyped]
    SE_SIDM_KRISHNAMURTI,
    SE_SIDM_LAHIRI,
    SE_SIDM_LAHIRI_1940,
    SE_SIDM_RAMAN,
    SEFLG_JPLEPH,
    SEFLG_MOSEPH,
    SEFLG_NONUT,
    SEFLG_RADIANS,
    SEFLG_SIDEREAL,
    SEFLG_SPEED,
    SEFLG_SWIEPH,
    SwissEph,
)

import app.calc.ayanamsha as ayanamsha_mod
from app.calc.ayanamsha import (
    AYANAMSHA_AUXILIARY_FLAGS,
    AyanamshaMode,
    CalculationError,
    classify_ephemeris_flag,
    get_ayanamsha_degrees,
    get_swe_engine,
)


def test_ayanamsha_near_j2000() -> None:
    """Lahiri ayanamsha near J2000 (2000-01-01 12:00 UT) is sane (~23.8° to 23.9°)."""
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


def test_ayanamsha_ex_preserves_swe_get_ayanamsa_ut_nutation_convention() -> None:
    """swe_get_ayanamsa_ex_ut with SEFLG_SWIEPH | SEFLG_NONUT matches swe_get_ayanamsa_ut."""
    jd = 2453949.3506944
    swe = SwissEph()
    swe.swe_set_ephe_path(str(ayanamsha_mod.EPHE_DIR).encode("utf-8"))

    mode_map = [
        (AyanamshaMode.LAHIRI, SE_SIDM_LAHIRI),
        (AyanamshaMode.LAHIRI_1940, SE_SIDM_LAHIRI_1940),
        (AyanamshaMode.RAMAN, SE_SIDM_RAMAN),
        (AyanamshaMode.KRISHNAMURTI, SE_SIDM_KRISHNAMURTI),
    ]
    for mode, c_sid_mode in mode_map:
        swe.swe_set_sid_mode(c_sid_mode, 0, 0)
        legacy_val = float(swe.swe_get_ayanamsa_ut(c_double(jd)))
        new_val = get_ayanamsha_degrees(jd, mode)
        assert new_val == pytest.approx(legacy_val, abs=1e-12)


def test_sidereal_mode_isolation_alternating() -> None:
    """Repeatedly alternating Lahiri and Raman calls must produce strictly identical values."""
    jd = 2453949.3506944  # 2006-08-01 20:25 UT

    expected_lahiri = get_ayanamsha_degrees(jd, AyanamshaMode.LAHIRI)
    expected_raman = get_ayanamsha_degrees(jd, AyanamshaMode.RAMAN)

    assert expected_lahiri != expected_raman

    for _ in range(50):
        val_l = get_ayanamsha_degrees(jd, AyanamshaMode.LAHIRI)
        val_r = get_ayanamsha_degrees(jd, AyanamshaMode.RAMAN)
        assert val_l == pytest.approx(expected_lahiri, abs=1e-12)
        assert val_r == pytest.approx(expected_raman, abs=1e-12)


def test_thread_safe_ayanamsha_concurrency() -> None:
    """Concurrent threads requesting different ayanamshas do not corrupt each other's output."""
    jd = 2453949.3506944
    expected_lahiri = get_ayanamsha_degrees(jd, AyanamshaMode.LAHIRI)
    expected_raman = get_ayanamsha_degrees(jd, AyanamshaMode.RAMAN)
    worker_count = 8
    barrier = threading.Barrier(worker_count)

    def task(mode: AyanamshaMode) -> float:
        barrier.wait(timeout=5.0)
        return get_ayanamsha_degrees(jd, mode)

    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [
            (
                AyanamshaMode.LAHIRI if i % 2 == 0 else AyanamshaMode.RAMAN,
                executor.submit(task, AyanamshaMode.LAHIRI if i % 2 == 0 else AyanamshaMode.RAMAN),
            )
            for i in range(worker_count)
        ]

        for mode, fut in futures:
            res = fut.result()
            expected = expected_lahiri if mode == AyanamshaMode.LAHIRI else expected_raman
            assert res == pytest.approx(expected, abs=1e-12)


def test_lahiri_1940_difference_at_jd() -> None:
    """LAHIRI_1940 differs from standard LAHIRI at JD 2453949.350694 by 0.010° to 0.020°."""
    jd = 2453949.350694
    val_lahiri = get_ayanamsha_degrees(jd, AyanamshaMode.LAHIRI)
    val_lahiri_1940 = get_ayanamsha_degrees(jd, AyanamshaMode.LAHIRI_1940)
    diff = abs(val_lahiri_1940 - val_lahiri)
    assert 0.010 <= diff <= 0.020, f"Expected diff between 0.010 and 0.020 deg, got {diff:.6f}"


def test_classify_ephemeris_flag_auxiliary_and_failure_cases() -> None:
    """Permits explicit auxiliary flags and rejects unknown, negative, JPL, or bad bits."""
    planetary_aux = SEFLG_SPEED | SEFLG_SIDEREAL | SEFLG_NONUT

    assert (
        classify_ephemeris_flag(
            SEFLG_SWIEPH | planetary_aux,
            subject="sun",
            allowed_auxiliary_flags=planetary_aux,
        )
        == "swieph"
    )
    assert (
        classify_ephemeris_flag(
            SEFLG_MOSEPH | planetary_aux,
            subject="moon",
            allowed_auxiliary_flags=planetary_aux,
        )
        == "moshier"
    )
    assert (
        classify_ephemeris_flag(
            SEFLG_SWIEPH | SEFLG_NONUT,
            subject="ayanamsha",
            allowed_auxiliary_flags=AYANAMSHA_AUXILIARY_FLAGS,
        )
        == "swieph"
    )

    # Disallowed/unsupported bits fail closed even alongside valid source bits
    unexpected_high_bit = 1 << 24
    for bad_flag, aux_mask in (
        (-1, planetary_aux),
        (-5, planetary_aux),
        (SEFLG_SPEED | SEFLG_SIDEREAL, planetary_aux),
        (SEFLG_JPLEPH | planetary_aux, planetary_aux),
        (SEFLG_SWIEPH | SEFLG_MOSEPH | planetary_aux, planetary_aux),
        (SEFLG_SWIEPH | planetary_aux | unexpected_high_bit, planetary_aux),
        (SEFLG_MOSEPH | planetary_aux | unexpected_high_bit, planetary_aux),
        (SEFLG_SWIEPH | planetary_aux | SEFLG_RADIANS, planetary_aux),
        (SEFLG_SWIEPH | SEFLG_SPEED, AYANAMSHA_AUXILIARY_FLAGS),
        (SEFLG_SWIEPH | SEFLG_NONUT | unexpected_high_bit, AYANAMSHA_AUXILIARY_FLAGS),
    ):
        with pytest.raises(CalculationError):
            classify_ephemeris_flag(
                bad_flag,
                subject="test_body",
                allowed_auxiliary_flags=aux_mask,
            )


def test_ayanamsha_rejects_unexpected_return_bits(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_ayanamsha_degrees fails closed if swe_get_ayanamsa_ex_ut returns extra bits."""

    class _FakeSweExtraBit:
        def swe_set_ephe_path(self, _path: bytes) -> None:
            pass

        def swe_set_sid_mode(self, _sid: int, _t0: float, _ayan_t0: float) -> None:
            pass

        def swe_get_ayanamsa_ex_ut(self, _jd: Any, _flag: int, aya_ptr: Any, _serr: Any) -> int:
            aya_ptr._obj.value = 23.9
            # Return SEFLG_SPEED (unrequested for ayanamsha) alongside SWIEPH | NONUT
            return int(SEFLG_SWIEPH | SEFLG_NONUT | SEFLG_SPEED)

    monkeypatch.setattr(ayanamsha_mod, "get_swe_engine", lambda: _FakeSweExtraBit())
    with pytest.raises(CalculationError, match="Unexpected ephemeris return flags"):
        get_ayanamsha_degrees(2451545.0)


def test_ayanamsha_fails_closed_on_invalid_jd_and_wrapper_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-finite JD, negative status, NaN ayanamsha, and FFI exceptions fail closed."""
    for bad_jd in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(CalculationError):
            get_ayanamsha_degrees(bad_jd)

    class _FakeSweErrorStatus:
        def swe_set_ephe_path(self, _path: bytes) -> None:
            pass

        def swe_set_sid_mode(self, _sid: int, _t0: float, _ayan_t0: float) -> None:
            pass

        def swe_get_ayanamsa_ex_ut(self, _jd: Any, _flag: int, _aya: Any, _serr: Any) -> int:
            return -1

    monkeypatch.setattr(ayanamsha_mod, "get_swe_engine", lambda: _FakeSweErrorStatus())
    with pytest.raises(CalculationError):
        get_ayanamsha_degrees(2451545.0)

    class _FakeSweNan:
        def swe_set_ephe_path(self, _path: bytes) -> None:
            pass

        def swe_set_sid_mode(self, _sid: int, _t0: float, _ayan_t0: float) -> None:
            pass

        def swe_get_ayanamsa_ex_ut(self, _jd: Any, _flag: int, aya_ptr: Any, _serr: Any) -> int:
            aya_ptr._obj.value = float("nan")
            return int(SEFLG_SWIEPH | SEFLG_NONUT)

    monkeypatch.setattr(ayanamsha_mod, "get_swe_engine", lambda: _FakeSweNan())
    with pytest.raises(CalculationError):
        get_ayanamsha_degrees(2451545.0)


def test_get_swe_engine_synchronized_lazy_init(monkeypatch: pytest.MonkeyPatch) -> None:
    """Lazy SwissEph singleton construction and path setup execute once under SWE_LOCK."""
    init_calls = 0

    class _CountingSwissEph:
        def __init__(self) -> None:
            nonlocal init_calls
            init_calls += 1

        def swe_set_ephe_path(self, _path: bytes) -> None:
            pass

    monkeypatch.setattr(ayanamsha_mod, "SwissEph", _CountingSwissEph)
    monkeypatch.setattr(ayanamsha_mod, "_SWE_INSTANCE", None)
    monkeypatch.setattr(ayanamsha_mod, "_CONFIGURED_EPHE_PATH", None)
    monkeypatch.setattr(ayanamsha_mod, "_EPHE_PATH_CONFIGURED", False)

    worker_count = 8
    barrier = threading.Barrier(worker_count)

    def worker() -> Any:
        barrier.wait(timeout=5.0)
        return get_swe_engine()

    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
        engines = [fut.result() for fut in [executor.submit(worker) for _ in range(worker_count)]]

    assert init_calls == 1
    assert len({id(eng) for eng in engines}) == 1
