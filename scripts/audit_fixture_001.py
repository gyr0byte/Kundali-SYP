"""Audit script for Fixture #1: Hamro Patro comparison, node analysis, Saturn investigation, and Lagna coordinate sensitivity."""

from __future__ import annotations

import datetime
from ctypes import c_double, create_string_buffer
from pathlib import Path

from swisseph_ffi import (
    SE_GREG_CAL,
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
    SEFLG_MOSEPH,
    SEFLG_NOABERR,
    SEFLG_SIDEREAL,
    SEFLG_SPEED,
    SEFLG_SWIEPH,
    SEFLG_TOPOCTR,
    SEFLG_TRUEPOS,
    SwissEph,
)

import sys

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.calc.ayanamsha import AyanamshaMode
from app.calc.ephemeris import NodeType
from app.calc.facts import ChartSettings, compute_chart_facts
from app.calc.houses import compute_lagna
from app.calc.timeconv import TimeInput, convert_local_to_utc_jd

EPHE_DIR = Path("D:/SYP/Kundali/backend/ephe")

# Hamro Patro Reference values
# deg_in_sign = deg + min/60 + sec/3600
REF = {
    "lagna": {
        "sign": "Mithun",
        "dms": "2:33:20",
        "deg_in_sign": 2.0 + 33.0 / 60.0 + 20.0 / 3600.0,
        "abs_lon": 60.0 + 2.0 + 33.0 / 60.0 + 20.0 / 3600.0,
    },
    "sun": {
        "sign": "Karkat",
        "dms": "15:30:25",
        "deg_in_sign": 15.0 + 30.0 / 60.0 + 25.0 / 3600.0,
        "abs_lon": 90.0 + 15.0 + 30.0 / 60.0 + 25.0 / 3600.0,
    },
    "moon": {
        "sign": "Tula",
        "dms": "9:43:49",
        "deg_in_sign": 9.0 + 43.0 / 60.0 + 49.0 / 3600.0,
        "abs_lon": 180.0 + 9.0 + 43.0 / 60.0 + 49.0 / 3600.0,
    },
    "mars": {
        "sign": "Singh",
        "dms": "12:20:38",
        "deg_in_sign": 12.0 + 20.0 / 60.0 + 38.0 / 3600.0,
        "abs_lon": 120.0 + 12.0 + 20.0 / 60.0 + 38.0 / 3600.0,
    },
    "mercury": {
        "sign": "Mithun",
        "dms": "27:52:26",
        "deg_in_sign": 27.0 + 52.0 / 60.0 + 26.0 / 3600.0,
        "abs_lon": 60.0 + 27.0 + 52.0 / 60.0 + 26.0 / 3600.0,
    },
    "jupiter": {
        "sign": "Tula",
        "dms": "16:04:23",
        "deg_in_sign": 16.0 + 4.0 / 60.0 + 23.0 / 3600.0,
        "abs_lon": 180.0 + 16.0 + 4.0 / 60.0 + 23.0 / 3600.0,
    },
    "venus": {
        "sign": "Mithun",
        "dms": "22:40:32",
        "deg_in_sign": 22.0 + 40.0 / 60.0 + 32.0 / 3600.0,
        "abs_lon": 60.0 + 22.0 + 40.0 / 60.0 + 32.0 / 3600.0,
    },
    "saturn": {
        "sign": "Karkat",
        "dms": "20:33:33",
        "deg_in_sign": 20.0 + 33.0 / 60.0 + 33.0 / 3600.0,
        "abs_lon": 90.0 + 20.0 + 33.0 / 60.0 + 33.0 / 3600.0,
    },
    "rahu": {
        "sign": "Meen",
        "dms": "2:26:40",
        "deg_in_sign": 2.0 + 26.0 / 60.0 + 40.0 / 3600.0,
        "abs_lon": 330.0 + 2.0 + 26.0 / 60.0 + 40.0 / 3600.0,
    },
    "ketu": {
        "sign": "Kanya",
        "dms": "2:26:40",
        "deg_in_sign": 2.0 + 26.0 / 60.0 + 40.0 / 3600.0,
        "abs_lon": 150.0 + 2.0 + 26.0 / 60.0 + 40.0 / 3600.0,
    },
}


def run_item_1() -> None:
    print("=" * 105)
    print("ITEM 1: FULL-PRECISION COMPARISON (6 DECIMALS) — ENGINE (DEFAULTS) VS HAMRO PATRO")
    print("=" * 105)

    t_inp = TimeInput(
        date=datetime.date(2006, 8, 2),
        time=datetime.time(2, 10, 0),
        latitude=26.45,
        longitude=87.283,
        timezone="Asia/Kathmandu",
    )
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
        if key not in REF:
            continue
        r = REF[key]
        ref_deg = r["deg_in_sign"]
        ref_lon = r["abs_lon"]
        eng_deg = f.degree
        eng_lon = f.longitude
        gap_deg = eng_lon - ref_lon
        gap_sec = gap_deg * 3600.0

        ref_str = f"{r['sign']} {r['dms']}"
        print(
            f"{key.capitalize():8} | {ref_str:20} | {ref_deg:16.6f}° | {eng_deg:13.6f}° | {gap_deg:+13.6f}° | {gap_sec:+11.2f}\""
        )
    print("=" * 105)


def run_item_2() -> None:
    print("\n" + "=" * 105)
    print("ITEM 2: RAHU WITH NODE_TYPE = TRUE ACROSS AYANAMSHA MODES")
    print("=" * 105)

    swe = SwissEph()
    swe.swe_set_ephe_path(str(EPHE_DIR).encode("utf-8"))

    # 2006-08-02 02:10 NPT = 2006-08-01 20:25 UTC
    jd = swe.swe_julday(2006, 8, 1, 20.0 + 25.0 / 60.0, SE_GREG_CAL)

    modes = [
        ("Lahiri (SE_SIDM_LAHIRI - engine default)", SE_SIDM_LAHIRI),
        ("Raman (SE_SIDM_RAMAN)", SE_SIDM_RAMAN),
        ("Krishnamurti (SE_SIDM_KRISHNAMURTI)", SE_SIDM_KRISHNAMURTI),
        ("Lahiri 1940 (SE_SIDM_LAHIRI_1940)", SE_SIDM_LAHIRI_1940),
        ("Lahiri ICRC (SE_SIDM_LAHIRI_ICRC)", SE_SIDM_LAHIRI_ICRC),
        ("Lahiri VP285 (SE_SIDM_LAHIRI_VP285)", SE_SIDM_LAHIRI_VP285),
        ("True Citra (SE_SIDM_TRUE_CITRA)", SE_SIDM_TRUE_CITRA),
    ]

    ref_rahu_deg = REF["rahu"]["deg_in_sign"]  # 2.444444° in Meen
    ref_rahu_lon = REF["rahu"]["abs_lon"]  # 332.444444°

    flags = SEFLG_SWIEPH | SEFLG_SPEED | SEFLG_SIDEREAL
    xx = (c_double * 6)()
    serr = create_string_buffer(256)

    print(f"Hamro Patro Reference Rahu: Meen 2:26:40 ({ref_rahu_deg:.6f}° in Meen, abs_lon: {ref_rahu_lon:.6f}°)\n")
    print(
        f"{'Ayanamsha Mode':42} | {'Node':6} | {'Rahu Lon':12} | {'Deg in Meen':12} | {'Gap (Deg)':12} | {'Gap (Arcsec)':12}"
    )
    print("-" * 105)

    for mode_name, mode_id in modes:
        swe.swe_set_sid_mode(mode_id, 0, 0)
        swe.swe_calc_ut(c_double(jd), SE_TRUE_NODE, flags, xx, serr)
        lon = xx[0] % 360.0
        deg_in_sign = lon % 30.0
        gap_deg = lon - ref_rahu_lon
        gap_sec = gap_deg * 3600.0
        print(
            f"{mode_name:42} | {'TRUE':6} | {lon:11.6f}° | {deg_in_sign:11.6f}° | {gap_deg:+11.6f}° | {gap_sec:+11.2f}\""
        )

    # Also compare MEAN node under Lahiri for contrast
    swe.swe_set_sid_mode(SE_SIDM_LAHIRI, 0, 0)
    swe.swe_calc_ut(c_double(jd), SE_MEAN_NODE, flags, xx, serr)
    lon_mean = xx[0] % 360.0
    deg_mean = lon_mean % 30.0
    gap_mean_deg = lon_mean - ref_rahu_lon
    gap_mean_sec = gap_mean_deg * 3600.0
    print(
        f"{'Lahiri (SE_SIDM_LAHIRI) [MEAN node]':42} | {'MEAN':6} | {lon_mean:11.6f}° | {deg_mean:11.6f}° | {gap_mean_deg:+11.6f}° | {gap_mean_sec:+11.2f}\""
    )
    print("=" * 105)


def run_item_3() -> None:
    print("\n" + "=" * 105)
    print("ITEM 3: INDEPENDENT SATURN INVESTIGATION (DIRECT C LIBRARY CALLS)")
    print("=" * 105)

    swe = SwissEph()
    swe.swe_set_ephe_path(str(EPHE_DIR).encode("utf-8"))
    swe.swe_set_sid_mode(SE_SIDM_LAHIRI, 0, 0)

    # 2006-08-02 02:10 NPT = 2006-08-01 20:25:00 UTC
    jd_birth = swe.swe_julday(2006, 8, 1, 20.0 + 25.0 / 60.0, SE_GREG_CAL)

    ref_saturn_dms = REF["saturn"]["dms"]
    ref_saturn_deg = REF["saturn"]["deg_in_sign"]
    ref_saturn_lon = REF["saturn"]["abs_lon"]

    xx = (c_double * 6)()
    serr = create_string_buffer(256)

    # Direct library call with standard SWIEPH sidereal
    iflag = swe.swe_calc_ut(c_double(jd_birth), SE_SATURN, SEFLG_SWIEPH | SEFLG_SPEED | SEFLG_SIDEREAL, xx, serr)
    lon_direct = xx[0] % 360.0
    deg_direct = lon_direct % 30.0
    speed_direct = xx[3]

    print(f"Hamro Patro Saturn Reference: Karkat {ref_saturn_dms} ({deg_direct:.6f}° in Karkat, lon: {ref_saturn_lon:.6f}°)")
    print(f"Direct SwissEph (at 02:10 NPT) : Karkat {int(deg_direct)}:{int((deg_direct%1)*60):02d}:{int(((deg_direct%1)*60%1)*60):02d} ({deg_direct:.6f}°, lon: {lon_direct:.6f}°)")
    print(f"Direct Library iflag: {iflag} (SEFLG_SWIEPH={bool(iflag & SEFLG_SWIEPH)}), speed: {speed_direct:.6f}°/day")
    gap = lon_direct - ref_saturn_lon
    print(f"Gap: {gap:+.6f}° ({gap * 3600.0:+.2f}\" = {abs(gap*60):.2f} arcminutes)")

    # Test variations to understand where Hamro Patro gets 20:33:33
    print("\nHypothesis Tests for Hamro Patro's Saturn Value (20:33:33):")

    # Hypothesis A: Did Hamro Patro calculate for a different time of day on 2006-08-02?
    print("\n--- Testing different times on 2006-08-02 / adjacent dates ---")
    for offset_days in [-1, 0, 1, 2, 3]:
        # Test 02:10, 00:00, 05:30 (sunrise), 12:00
        for desc, h_utc in [("02:10 NPT (20:25 UT prev)", 20.0 + 25.0/60.0), ("00:00 NPT (18:15 UT prev)", 18.25), ("Sunrise ~05:15 NPT (23:30 UT)", 23.5), ("12:00 NPT (06:15 UT)", 6.25)]:
            test_jd = swe.swe_julday(2006, 8, 1 + offset_days, h_utc, SE_GREG_CAL)
            swe.swe_calc_ut(c_double(test_jd), SE_SATURN, SEFLG_SWIEPH | SEFLG_SPEED | SEFLG_SIDEREAL, xx, serr)
            t_lon = xx[0] % 360.0
            t_deg = t_lon % 30.0
            m_arc = int((t_deg % 1) * 60)
            s_arc = int(((t_deg % 1) * 60 % 1) * 60)
            diff = abs(t_deg - ref_saturn_deg)
            if diff < 0.05:
                print(f"  >>> MATCH FOUND: Offset {offset_days:+d}d, {desc:25} -> Karkat {int(t_deg)}:{m_arc:02d}:{s_arc:02d} ({t_deg:.4f}°) | diff={diff*3600:.1f}\"")
            else:
                if offset_days in (0, 3) and "02:10" in desc:
                    print(f"      Offset {offset_days:+d}d, {desc:25} -> Karkat {int(t_deg)}:{m_arc:02d}:{s_arc:02d} ({t_deg:.4f}°)")

    # Hypothesis B: Tropical position?
    swe.swe_calc_ut(c_double(jd_birth), SE_SATURN, SEFLG_SWIEPH | SEFLG_SPEED, xx, serr)
    trop_lon = xx[0] % 360.0
    print(f"\nTropical Saturn: {trop_lon:.6f}° ({int(trop_lon//30)}:{trop_lon%30:.4f}°)")

    # Hypothesis C: Astrometric / Truepos / Topocentric
    swe.swe_calc_ut(c_double(jd_birth), SE_SATURN, SEFLG_SWIEPH | SEFLG_SPEED | SEFLG_SIDEREAL | SEFLG_TRUEPOS, xx, serr)
    truepos_lon = xx[0] % 360.0
    print(f"Truepos (geometric, no light-time) Saturn: {truepos_lon:.6f}° (diff: {(truepos_lon - lon_direct)*3600:.2f}\")")


def run_item_6() -> None:
    print("\n" + "=" * 105)
    print("ITEM 6: LAGNA SENSITIVITY TO COORDINATE VARIATION (±0.01° AND DISTRICT SHIFTS)")
    print("=" * 105)

    swe = SwissEph()
    swe.swe_set_ephe_path(str(EPHE_DIR).encode("utf-8"))
    swe.swe_set_sid_mode(SE_SIDM_LAHIRI, 0, 0)
    jd_birth = swe.swe_julday(2006, 8, 1, 20.0 + 25.0 / 60.0, SE_GREG_CAL)

    base_lat = 26.45
    base_lon = 87.283
    base_lagna = compute_lagna(jd_birth, base_lat, base_lon, AyanamshaMode.LAHIRI)
    base_deg = base_lagna % 30.0

    ref_lagna_deg = REF["lagna"]["deg_in_sign"]  # 2.555556° (2:33:20)
    ref_lagna_lon = REF["lagna"]["abs_lon"]  # 62.555556°

    print(f"Base Coordinates : Lat {base_lat:.4f}°, Lon {base_lon:.4f}°")
    print(f"Base Engine Lagna: Mithun {base_deg:.6f}° (lon: {base_lagna:.6f}°)")
    print(f"Hamro Patro Ref  : Mithun {ref_lagna_deg:.6f}° (2:33:20, lon: {ref_lagna_lon:.6f}°)")
    gap_base = base_lagna - ref_lagna_lon
    print(f"Initial Gap      : {gap_base:+.6f}° ({gap_base * 3600.0:+.2f}\" = {gap_base * 60.0:+.2f} arcminutes)\n")

    print(f"{'Variation':32} | {'Lat':8} | {'Lon':8} | {'Lagna Lon':12} | {'Deg in Mithun':14} | {'Delta vs Base':13} | {'Gap vs Ref':12}")
    print("-" * 105)

    variations = [
        ("Base", base_lat, base_lon),
        ("Lat +0.01°", base_lat + 0.01, base_lon),
        ("Lat -0.01°", base_lat - 0.01, base_lon),
        ("Lon +0.01°", base_lat, base_lon + 0.01),
        ("Lon -0.01°", base_lat, base_lon - 0.01),
        ("Both +0.01°", base_lat + 0.01, base_lon + 0.01),
        ("Both -0.01°", base_lat - 0.01, base_lon - 0.01),
        ("Biratnagar City (26.456, 87.280)", 26.456, 87.280),
        ("Morang Center (26.65, 87.45)", 26.65, 87.45),
        ("Coordinates matching Ref exactly", 26.45, base_lon - (gap_base)),  # What longitude would yield exact ref?
    ]

    for label, lat, lon in variations:
        lagna = compute_lagna(jd_birth, lat, lon, AyanamshaMode.LAHIRI)
        deg = lagna % 30.0
        delta_base = (lagna - base_lagna) * 3600.0
        gap_ref = (lagna - ref_lagna_lon) * 3600.0
        print(f"{label:30} | {lat:8.4f} | {lon:8.4f} | {lagna:11.6f}° | {deg:13.6f}° | {delta_base:+10.1f}\" | {gap_ref:+10.1f}\"")

    print("=" * 105)


if __name__ == "__main__":
    run_item_1()
    run_item_2()
    run_item_3()
    run_item_6()
