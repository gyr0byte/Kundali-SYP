"""Validate fixture_001 against Swiss Ephemeris calculations."""

import json
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
    SE_SIDM_LAHIRI,
    SE_SUN,
    SE_TRUE_NODE,
    SE_VENUS,
    SEFLG_SIDEREAL,
    SEFLG_SPEED,
    SEFLG_SWIEPH,
    SwissEph,
)

EPHE_DIR = Path("D:/SYP/Kundali/backend/ephe")
FIXTURE_PATH = Path("D:/SYP/Kundali/fixtures/charts/fixture_001_builder.json")

RASHIS = [
    "Mesha", "Vrishabha", "Mithun", "Karkat",
    "Singh", "Kanya", "Tula", "Vrishchika",
    "Dhanu", "Makar", "Kumbha", "Meen"
]

NAKSHATRAS = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni",
    "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha",
    "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta", "Shatabhisha",
    "Purva Bhadrapada", "Uttara Bhadrapada", "Revati"
]


def dms_str(lon: float) -> tuple[str, int, int, int, int]:
    r_idx = int(lon // 30)
    rem = lon % 30
    d = int(rem)
    m = int((rem - d) * 60)
    s = int(((rem - d) * 60 - m) * 60)
    subs = round((((rem - d) * 60 - m) * 60 - s) * 60)
    return RASHIS[r_idx], d, m, s, subs


def main() -> None:
    swe = SwissEph()
    swe.swe_set_ephe_path(str(EPHE_DIR).encode("utf-8"))
    swe.swe_set_sid_mode(SE_SIDM_LAHIRI, 0, 0)

    # 2006-08-02 02:10:00 Nepal Time (+5:45) -> 2006-08-01 20:25:00 UTC
    jd = swe.swe_julday(2006, 8, 1, 20.0 + 25.0 / 60.0, SE_GREG_CAL)
    print(f"Julian Day (UT): {jd:.6f}")

    xx = (c_double * 6)()
    serr = create_string_buffer(256)

    bodies = {
        "surya": SE_SUN,
        "chandra": SE_MOON,
        "mangal": SE_MARS,
        "budh": SE_MERCURY,
        "brihaspati": SE_JUPITER,
        "shukra": SE_VENUS,
        "shani": SE_SATURN,
        "rahu": SE_TRUE_NODE,
    }

    computed: dict[str, dict] = {}
    for name, pid in bodies.items():
        swe.swe_calc_ut(c_double(jd), pid, SEFLG_SWIEPH | SEFLG_SPEED | SEFLG_SIDEREAL, xx, serr)
        lon = xx[0] % 360
        rashi, d, m, s, subs = dms_str(lon)
        computed[name] = {
            "lon": lon,
            "sign": rashi,
            "dms": f"{rashi} {d}:{m:02d}:{s:02d}:{subs:02d}",
        }

    # Ketu = Rahu + 180
    k_lon = (computed["rahu"]["lon"] + 180) % 360
    rashi, d, m, s, subs = dms_str(k_lon)
    computed["ketu"] = {
        "lon": k_lon,
        "sign": rashi,
        "dms": f"{rashi} {d}:{m:02d}:{s:02d}:{subs:02d}",
    }

    # Lagna
    cusps = (c_double * 13)()
    ascmc = (c_double * 10)()
    swe.swe_houses_ex(c_double(jd), SEFLG_SIDEREAL, c_double(26.45), c_double(87.283), ord("W"), cusps, ascmc)
    asc_lon = ascmc[0] % 360
    rashi, d, m, s, subs = dms_str(asc_lon)
    computed["lagna"] = {
        "lon": asc_lon,
        "sign": rashi,
        "dms": f"{rashi} {d}:{m:02d}:{s:02d}:{subs:02d}",
    }

    # Nakshatra for Chandra
    nak_idx = int(computed["chandra"]["lon"] / (360 / 27))
    nak_pada = int((computed["chandra"]["lon"] % (360 / 27)) / (360 / 108)) + 1
    computed["chandra"]["nakshatra"] = NAKSHATRAS[nak_idx]
    computed["chandra"]["pada"] = nak_pada

    # Load fixture
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    positions = fixture["positions"]

    print("\n" + "=" * 82)
    print(f"{'Graha/Lagna':12} | {'Hamro Patro (Reference)':24} | {'SwissEph (Computed)':24} | {'Diff':10}")
    print("=" * 82)

    for key in ["lagna", "surya", "chandra", "mangal", "budh", "brihaspati", "shukra", "shani", "rahu", "ketu"]:
        ref = positions[key]
        ref_dms = f"{ref['sign']} {ref['deg']}:{ref['min']:02d}:{ref['sec']:02d}:{ref['subsec']:02d}"
        c = computed[key]
        diff_deg = abs(c["lon"] - ref["sidereal_longitude"])
        diff_sec = diff_deg * 3600
        print(f"{key:12} | {ref_dms:24} | {c['dms']:24} | {diff_sec:7.1f}\" ({diff_deg:.4f}°)")

    print("=" * 82)
    print(f"Moon Nakshatra : Hamro Patro={positions['chandra']['nakshatra']} Pada {positions['chandra']['pada']} | Computed={computed['chandra']['nakshatra']} Pada {computed['chandra']['pada']}")
    print(f"Lagna Sign     : Hamro Patro={positions['lagna']['sign']} | Computed={computed['lagna']['sign']}")


if __name__ == "__main__":
    main()
