"""Audit script for Fixture #1: Hamro Patro comparison, node analysis, Saturn investigation, and Lagna coordinate sensitivity.

Reads dynamically from fixtures/charts_private/fixture_001.json.
Contains NO hardcoded birth dates, times, coordinates, or reference values.
"""

from __future__ import annotations

import datetime
import json
import sys
from ctypes import c_double, create_string_buffer
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from swisseph_ffi import (
    SE_JUPITER,
    SE_MARS,
    SE_MEAN_NODE,
    SE_MERCURY,
    SE_MOON,
    SE_SATURN,
    SE_SIDM_KRISHNAMURTI,
    SE_SIDM_LAHIRI,
    SE_SIDM_LAHIRI_1940,
    SE_SIDM_LAHIRI_ICRC,
    SE_SIDM_LAHIRI_VP285,
    SE_SIDM_RAMAN,
    SE_SIDM_TRUE_CITRA,
    SE_SUN,
    SE_TRUE_NODE,
    SEFLG_SIDEREAL,
    SEFLG_SPEED,
    SEFLG_SWIEPH,
    SEFLG_TRUEPOS,
    SwissEph,
)

from app.calc.ayanamsha import AyanamshaMode
from app.calc.ephemeris import NodeType
from app.calc.facts import ChartSettings, compute_chart_facts
from app.calc.houses import compute_lagna
from app.calc.timeconv import TimeInput, convert_local_to_utc_jd

EPHE_DIR = BACKEND_DIR / "ephe"
FIXTURE_PATH = PROJECT_ROOT / "fixtures" / "charts_private" / "fixture_001.json"


def load_fixture() -> tuple[dict, TimeInput, dict, float]:
    """Load private fixture data dynamically."""
    if not FIXTURE_PATH.exists():
        print(f"Private fixture not found at {FIXTURE_PATH}. Skipping audit.")
        sys.exit(0)

    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    b = data["birth"]
    tz = b.get("timezone")
    t_inp = TimeInput(
        date=datetime.date.fromisoformat(b["date"]),
        time=datetime.time.fromisoformat(b["time"]),
        latitude=b["latitude"],
        longitude=b["longitude"],
        timezone=tz,
        utc_offset_hours=b.get("utc_offset_hours") if tz is None else None,
    )
    time_res = convert_local_to_utc_jd(t_inp)
    jd_birth = time_res.julian_day

    # Build reference lookup dynamically
    exp = data["expected"]
    ref: dict[str, dict] = {}
    if "lagna" in exp and exp["lagna"] is not None:
        l = exp["lagna"]
        ref["lagna"] = {
            "sign": l.get("sign_rashi", l.get("sign", "")),
            "dms": l.get("dms", ""),
            "deg_in_sign": l.get("degree", l["longitude"] % 30.0),
            "abs_lon": l["longitude"],
        }
    if "moon" in exp and exp["moon"] is not None:
        m = exp["moon"]
        ref["moon"] = {
            "sign": m.get("sign_rashi", m.get("sign", "")),
            "dms": m.get("dms", ""),
            "deg_in_sign": m.get("degree", m["longitude"] % 30.0),
            "abs_lon": m["longitude"],
        }
    for p_name, p_data in exp.get("planets", {}).items():
        if p_data is not None:
            ref[p_name] = {
                "sign": p_data.get("sign_rashi", p_data.get("sign", "")),
                "dms": p_data.get("dms", ""),
                "deg_in_sign": p_data.get("degree", p_data["longitude"] % 30.0),
                "abs_lon": p_data["longitude"],
            }

    return data, t_inp, ref, jd_birth


def run_item_1(t_inp: TimeInput, ref: dict) -> None:
    print("=" * 105)
    print("ITEM 1: FULL-PRECISION COMPARISON (6 DECIMALS) — ENGINE (DEFAULTS) VS REFERENCE")
    print("=" * 105)

    settings = ChartSettings(
        ayanamsha=AyanamshaMode.LAHIRI,
        house_system="whole_sign",
        node_type=NodeType.MEAN,
    )
    doc = compute_chart_facts(t_inp, settings, "audit_001")

    print(
        f"{'Point':8} | {'Ref Sign & DMS':20} | {'Ref Deg (6 dec)':16} | {'Engine Deg':14} | {'Gap (Deg)':14} | {'Gap (Arcsec)':12}"
    )
    print("-" * 105)

    for f in doc.facts:
        key = "lagna" if f.id == "f_lagna" else f.id.replace("f_", "")
        if key not in ref:
            continue
        r = ref[key]
        ref_deg = r["deg_in_sign"]
        ref_lon = r["abs_lon"]
        eng_deg = f.degree
        eng_lon = f.longitude
        gap_deg = eng_lon - ref_lon
        gap_sec = gap_deg * 3600.0

        ref_str = f"{r['sign']} {r['dms']}"
        print(
            f'{key.capitalize():8} | {ref_str:20} | {ref_deg:16.6f}° | {eng_deg:13.6f}° | {gap_deg:+13.6f}° | {gap_sec:+11.2f}"'
        )
    print("=" * 105)


def run_item_2(jd_birth: float, ref: dict) -> None:
    print("\n" + "=" * 105)
    print("ITEM 2: RAHU WITH NODE_TYPE = TRUE ACROSS AYANAMSHA MODES")
    print("=" * 105)

    if "rahu" not in ref:
        print("Rahu reference not present in fixture.")
        return

    swe = SwissEph()
    if EPHE_DIR.exists():
        swe.swe_set_ephe_path(str(EPHE_DIR).encode("utf-8"))

    modes = [
        ("Lahiri (SE_SIDM_LAHIRI - engine default)", SE_SIDM_LAHIRI),
        ("Raman (SE_SIDM_RAMAN)", SE_SIDM_RAMAN),
        ("Krishnamurti (SE_SIDM_KRISHNAMURTI)", SE_SIDM_KRISHNAMURTI),
        ("Lahiri 1940 (SE_SIDM_LAHIRI_1940)", SE_SIDM_LAHIRI_1940),
        ("Lahiri ICRC (SE_SIDM_LAHIRI_ICRC)", SE_SIDM_LAHIRI_ICRC),
        ("Lahiri VP285 (SE_SIDM_LAHIRI_VP285)", SE_SIDM_LAHIRI_VP285),
        ("True Citra (SE_SIDM_TRUE_CITRA)", SE_SIDM_TRUE_CITRA),
    ]

    ref_rahu_deg = ref["rahu"]["deg_in_sign"]
    ref_rahu_lon = ref["rahu"]["abs_lon"]

    flags = SEFLG_SWIEPH | SEFLG_SPEED | SEFLG_SIDEREAL
    xx = (c_double * 6)()
    serr = create_string_buffer(256)

    print(
        f"Reference Rahu: {ref['rahu']['sign']} {ref['rahu']['dms']} ({ref_rahu_deg:.6f}°, abs_lon: {ref_rahu_lon:.6f}°)\n"
    )
    print(
        f"{'Ayanamsha Mode':42} | {'Node':6} | {'Rahu Lon':12} | {'Deg in Sign':12} | {'Gap (Deg)':12} | {'Gap (Arcsec)':12}"
    )
    print("-" * 105)

    for mode_name, mode_id in modes:
        swe.swe_set_sid_mode(mode_id, 0, 0)
        swe.swe_calc_ut(c_double(jd_birth), SE_TRUE_NODE, flags, xx, serr)
        lon = xx[0] % 360.0
        deg_in_sign = lon % 30.0
        gap_deg = lon - ref_rahu_lon
        gap_sec = gap_deg * 3600.0
        print(
            f'{mode_name:42} | {"TRUE":6} | {lon:11.6f}° | {deg_in_sign:11.6f}° | {gap_deg:+11.6f}° | {gap_sec:+11.2f}"'
        )

    # Also compare MEAN node under Lahiri for contrast
    swe.swe_set_sid_mode(SE_SIDM_LAHIRI, 0, 0)
    swe.swe_calc_ut(c_double(jd_birth), SE_MEAN_NODE, flags, xx, serr)
    lon_mean = xx[0] % 360.0
    deg_mean = lon_mean % 30.0
    gap_mean_deg = lon_mean - ref_rahu_lon
    gap_mean_sec = gap_mean_deg * 3600.0
    print(
        f'{"Lahiri (SE_SIDM_LAHIRI) [MEAN node]":42} | {"MEAN":6} | {lon_mean:11.6f}° | {deg_mean:11.6f}° | {gap_mean_deg:+11.6f}° | {gap_mean_sec:+11.2f}"'
    )
    print("=" * 105)


def run_item_3(jd_birth: float, ref: dict) -> None:
    print("\n" + "=" * 105)
    print("ITEM 3: INDEPENDENT SATURN INVESTIGATION (DIRECT C LIBRARY CALLS)")
    print("=" * 105)

    if "saturn" not in ref:
        print("Saturn reference not present in fixture.")
        return

    swe = SwissEph()
    if EPHE_DIR.exists():
        swe.swe_set_ephe_path(str(EPHE_DIR).encode("utf-8"))
    swe.swe_set_sid_mode(SE_SIDM_LAHIRI, 0, 0)

    ref_saturn_dms = ref["saturn"]["dms"]
    ref_saturn_deg = ref["saturn"]["deg_in_sign"]
    ref_saturn_lon = ref["saturn"]["abs_lon"]

    xx = (c_double * 6)()
    serr = create_string_buffer(256)

    # Direct library call with standard SWIEPH sidereal
    iflag = swe.swe_calc_ut(
        c_double(jd_birth), SE_SATURN, SEFLG_SWIEPH | SEFLG_SPEED | SEFLG_SIDEREAL, xx, serr
    )
    lon_direct = xx[0] % 360.0
    deg_direct = lon_direct % 30.0
    speed_direct = xx[3]

    print(
        f"Reference Saturn: {ref['saturn']['sign']} {ref_saturn_dms} ({ref_saturn_deg:.6f}°, lon: {ref_saturn_lon:.6f}°)"
    )
    print(
        f"Direct SwissEph : {int(deg_direct)}:{int((deg_direct % 1) * 60):02d}:{int(((deg_direct % 1) * 60 % 1) * 60):02d} ({deg_direct:.6f}°, lon: {lon_direct:.6f}°)"
    )
    print(
        f"Direct Library iflag: {iflag} (SEFLG_SWIEPH={bool(iflag & SEFLG_SWIEPH)}), speed: {speed_direct:.6f}°/day"
    )
    gap = lon_direct - ref_saturn_lon
    print(f'Gap: {gap:+.6f}° ({gap * 3600.0:+.2f}" = {abs(gap * 60):.2f} arcminutes)')

    # Test variations to investigate offset days relative to jd_birth
    print("\nHypothesis Tests for Reference Saturn Value:")
    print("--- Testing adjacent dates relative to birth Julian Day ---")
    for offset_days in [-1, 0, 1, 2, 3]:
        for desc, h_delta in [
            ("Same time", 0.0),
            ("-2 hours", -2.0 / 24.0),
            ("+3 hours", 3.0 / 24.0),
            ("+10 hours", 10.0 / 24.0),
        ]:
            test_jd = jd_birth + offset_days + h_delta
            swe.swe_calc_ut(
                c_double(test_jd), SE_SATURN, SEFLG_SWIEPH | SEFLG_SPEED | SEFLG_SIDEREAL, xx, serr
            )
            t_lon = xx[0] % 360.0
            t_deg = t_lon % 30.0
            m_arc = int((t_deg % 1) * 60)
            s_arc = int(((t_deg % 1) * 60 % 1) * 60)
            diff = abs(t_deg - ref_saturn_deg)
            if diff < 0.05:
                print(
                    f'  >>> MATCH FOUND: Offset {offset_days:+d}d, {desc:15} -> {int(t_deg)}:{m_arc:02d}:{s_arc:02d} ({t_deg:.4f}°) | diff={diff * 3600:.1f}"'
                )

    # Tropical position
    swe.swe_calc_ut(c_double(jd_birth), SE_SATURN, SEFLG_SWIEPH | SEFLG_SPEED, xx, serr)
    trop_lon = xx[0] % 360.0
    print(f"\nTropical Saturn: {trop_lon:.6f}° ({int(trop_lon // 30)}:{trop_lon % 30:.4f}°)")

    # Truepos
    swe.swe_calc_ut(
        c_double(jd_birth),
        SE_SATURN,
        SEFLG_SWIEPH | SEFLG_SPEED | SEFLG_SIDEREAL | SEFLG_TRUEPOS,
        xx,
        serr,
    )
    truepos_lon = xx[0] % 360.0
    print(
        f'Truepos (geometric, no light-time) Saturn: {truepos_lon:.6f}° (diff: {(truepos_lon - lon_direct) * 3600:.2f}")'
    )


def run_item_6(jd_birth: float, t_inp: TimeInput, ref: dict) -> None:
    print("\n" + "=" * 105)
    print("ITEM 6: LAGNA SENSITIVITY TO COORDINATE VARIATION (±0.01° AND LOCAL SHIFTS)")
    print("=" * 105)

    if "lagna" not in ref:
        print("Lagna reference not present in fixture.")
        return

    base_lat = t_inp.latitude
    base_lon = t_inp.longitude
    base_lagna = compute_lagna(jd_birth, base_lat, base_lon, AyanamshaMode.LAHIRI)
    base_deg = base_lagna % 30.0

    ref_lagna_deg = ref["lagna"]["deg_in_sign"]
    ref_lagna_lon = ref["lagna"]["abs_lon"]

    print(f"Base Coordinates : Lat {base_lat:.4f}°, Lon {base_lon:.4f}°")
    print(f"Base Engine Lagna: {ref['lagna']['sign']} {base_deg:.6f}° (lon: {base_lagna:.6f}°)")
    print(
        f"Reference Lagna  : {ref['lagna']['sign']} {ref_lagna_deg:.6f}° (lon: {ref_lagna_lon:.6f}°)"
    )
    gap_base = base_lagna - ref_lagna_lon
    print(
        f'Initial Gap      : {gap_base:+.6f}° ({gap_base * 3600.0:+.2f}" = {gap_base * 60.0:+.2f} arcminutes)\n'
    )

    print(
        f"{'Variation':32} | {'Lat':8} | {'Lon':8} | {'Lagna Lon':12} | {'Deg in Sign':14} | {'Delta vs Base':13} | {'Gap vs Ref':12}"
    )
    print("-" * 105)

    variations = [
        ("Base", base_lat, base_lon),
        ("Lat +0.01°", base_lat + 0.01, base_lon),
        ("Lat -0.01°", base_lat - 0.01, base_lon),
        ("Lon +0.01°", base_lat, base_lon + 0.01),
        ("Lon -0.01°", base_lat, base_lon - 0.01),
        ("Both +0.01°", base_lat + 0.01, base_lon + 0.01),
        ("Both -0.01°", base_lat - 0.01, base_lon - 0.01),
        ("Coordinates matching Ref exactly", base_lat, base_lon - (gap_base)),
    ]

    for label, lat, lon in variations:
        lagna = compute_lagna(jd_birth, lat, lon, AyanamshaMode.LAHIRI)
        deg = lagna % 30.0
        delta_base = (lagna - base_lagna) * 3600.0
        gap_ref = (lagna - ref_lagna_lon) * 3600.0
        print(
            f'{label:32} | {lat:8.4f} | {lon:8.4f} | {lagna:11.6f}° | {deg:13.6f}° | {delta_base:+10.1f}" | {gap_ref:+10.1f}"'
        )

    print("=" * 105)


if __name__ == "__main__":
    _, t_inp, ref, jd_birth = load_fixture()
    run_item_1(t_inp, ref)
    run_item_2(jd_birth, ref)
    run_item_3(jd_birth, ref)
    run_item_6(jd_birth, t_inp, ref)
