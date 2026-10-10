"""CLI tool for computing Vedic birth charts and inspecting Chart Facts.

Usage:
    python scripts/chart_cli.py --date 2006-08-02 --time 02:10:00 --lat 26.45 --lon 87.283 --tz Asia/Kathmandu
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

# Add backend directory to sys.path so app.calc can be imported directly
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.calc.ayanamsha import AyanamshaMode  # noqa: E402
from app.calc.ephemeris import NodeType  # noqa: E402
from app.calc.facts import ChartFactLagna, ChartSettings, compute_chart_facts  # noqa: E402
from app.calc.houses import rashi_name  # noqa: E402
from app.calc.timeconv import TimeInput  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Kundali Chart Calculation CLI")
    parser.add_argument("--date", required=True, help="Birth date (YYYY-MM-DD)")
    parser.add_argument("--time", required=True, help="Birth local time (HH:MM:SS or HH:MM)")
    parser.add_argument("--lat", type=float, required=True, help="Birth place latitude (-90..90)")
    parser.add_argument("--lon", type=float, required=True, help="Birth place longitude (-180..180)")
    parser.add_argument("--tz", default="Asia/Kathmandu", help="IANA timezone name (default: Asia/Kathmandu)")
    parser.add_argument("--offset", type=float, default=None, help="Explicit UTC offset in hours (overrides --tz)")
    parser.add_argument(
        "--ayanamsha",
        choices=["lahiri", "raman", "krishnamurti"],
        default="lahiri",
        help="Ayanamsha system (default: lahiri)",
    )
    parser.add_argument(
        "--node",
        choices=["mean", "true"],
        default="mean",
        help="Lunar node calculation method (default: mean)",
    )
    parser.add_argument("--chart-id", default="cli_chart_001", help="Identifier for output facts document")
    parser.add_argument("--json-only", action="store_true", help="Print only raw JSON output")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    date_val = datetime.date.fromisoformat(args.date)
    time_val = datetime.time.fromisoformat(args.time)

    time_inp = TimeInput(
        date=date_val,
        time=time_val,
        latitude=args.lat,
        longitude=args.lon,
        timezone=args.tz if args.offset is None else None,
        utc_offset_hours=args.offset,
    )

    settings = ChartSettings(
        ayanamsha=AyanamshaMode(args.ayanamsha),
        house_system="whole_sign",
        node_type=NodeType(args.node),
    )

    facts_doc = compute_chart_facts(time_inp, settings, chart_id=args.chart_id)

    if args.json_only:
        print(facts_doc.model_dump_json(indent=2))
        return

    # Print human-readable summary
    print("=" * 88)
    print(f"KUNDALI CHART FACTS — {facts_doc.chart_id}")
    print(f"Engine Version  : {facts_doc.engine_version}")
    print(f"Ephemeris Source: {facts_doc.metadata.ephemeris_source} (High precision: {facts_doc.metadata.ephemeris_source == 'swieph'})")
    print(f"Birth Local Time: {args.date} {args.time} ({args.tz if args.offset is None else f'UTC{args.offset:+0.2f}'})")
    print(f"Birth Place     : Lat {args.lat:.4f}°, Lon {args.lon:.4f}°")
    print(f"Julian Day (UT) : {facts_doc.metadata.julian_day:.6f}")
    print(f"Conventions     : Ayanamsha={settings.ayanamsha.value.upper()} | Houses={settings.house_system} | Nodes={settings.node_type.value.upper()}")
    print("=" * 88)

    print(f"{'Point':12} | {'Sign (Rashi)':22} | {'Degree':10} | {'House':6} | {'Nakshatra':16} | {'Pada':4} | {'Retrograde':10}")
    print("-" * 88)

    for f in facts_doc.facts:
        if f.id == "f_lagna":
            assert isinstance(f, ChartFactLagna)
            rashi = rashi_name(f.sign_index)
            sign_str = f"{f.sign} ({rashi})"
            deg_str = f"{f.degree:6.2f}°"
            print(f"{'Lagna':12} | {sign_str:22} | {deg_str:10} | {'1':6} | {f.nakshatra:16} | {f.pada:4d} | {'No':10}")
        elif f.id.startswith("f_") and f.id != "f_lagna_sensitivity":
            rashi = rashi_name(f.sign_index)
            sign_str = f"{f.sign} ({rashi})"
            deg_str = f"{f.degree:6.2f}°"
            retro_str = "Yes (R)" if f.retrograde else "No"
            print(f"{f.planet:12} | {sign_str:22} | {deg_str:10} | {f.house:6d} | {f.nakshatra:16} | {f.pada:4d} | {retro_str:10}")
        elif f.id == "f_lagna_sensitivity":
            print("-" * 88)
            print(f"⚠️  SENSITIVITY ALERT: {f.note}")
            print(f"    Degree in sign: {f.degree_in_sign:.4f}° (Distance to boundary: {f.boundary_distance_degrees:.4f}°)")

    print("=" * 88)
    print("\n[Raw JSON Output]")
    print(json.dumps(facts_doc.model_dump(), indent=2))


if __name__ == "__main__":
    main()
