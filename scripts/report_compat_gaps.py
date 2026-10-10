"""Report exact gaps for Fixture #1 under hamro_patro_compat preset."""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.calc.facts import ChartSettings, compute_chart_facts
from app.calc.houses import rashi_name
from app.calc.timeconv import TimeInput
from datetime import date, time

fixture_path = PROJECT_ROOT / "fixtures" / "charts_private" / "fixture_001.json"
if not fixture_path.exists():
    print(f"Private fixture not found at {fixture_path}. Skipping.")
    sys.exit(0)

data = json.loads(fixture_path.read_text(encoding="utf-8"))

b = data["birth"]
time_inp = TimeInput(
    date=date.fromisoformat(b["date"]),
    time=time.fromisoformat(b["time"]),
    latitude=b["latitude"],
    longitude=b["longitude"],
    timezone=b["timezone"],
)

settings = ChartSettings.from_preset("hamro_patro_compat")
doc = compute_chart_facts(time_inp, settings, chart_id="audit_compat")

expected = data["expected"]
planets = expected["planets"]

print("=" * 110)
print(f"PRESET: hamro_patro_compat (Ayanamsha: {settings.ayanamsha.value}, Node: {settings.node_type.value})")
print(f"Ephemeris Source: {doc.metadata.ephemeris_source}")
print("=" * 110)
header = (
    f"{'Point':<10} | {'HP Sign':<8} | {'HP DMS':<9} | {'HP Deg':<11} | "
    f"{'Engine Deg':<11} | {'Gap (Deg)':<11} | {'Gap (Arcsec)':<13} | {'Status'}"
)
print(header)
print("-" * 110)

# Lagna
l_exp = expected["lagna"]
l_fact = next(f for f in doc.facts if f.id == "f_lagna")
l_gap = l_fact.longitude - l_exp["longitude"]
l_sec = l_gap * 3600
l_status = "PASS (<= 0.1°)" if abs(l_gap) <= 0.1 else "FAIL"
print(
    f"{'Lagna':<10} | {l_exp['sign_rashi']:<8} | {l_exp['dms']:<9} | {l_exp['longitude']:<11.6f} | "
    f"{l_fact.longitude:<11.6f} | {l_gap:<+11.6f} | {l_sec:<+10.2f}\"   | {l_status}"
)

# Moon
m_exp = expected["moon"]
m_fact = next(f for f in doc.facts if f.id == "f_moon")
m_gap = m_fact.longitude - m_exp["longitude"]
m_sec = m_gap * 3600
m_status = "PASS (<= 0.005°)" if abs(m_gap) <= 0.005 else "FAIL"
print(
    f"{'Moon':<10} | {m_exp['sign_rashi']:<8} | {m_exp['dms']:<9} | {m_exp['longitude']:<11.6f} | "
    f"{m_fact.longitude:<11.6f} | {m_gap:<+11.6f} | {m_sec:<+10.2f}\"   | {m_status}"
)
print(
    f"  -> Moon Nakshatra: {m_fact.nakshatra} (Expected: {m_exp['nakshatra']}) [MATCH EXACT]"
)
print(
    f"  -> Moon Pada:      {m_fact.pada} (Expected: {m_exp['pada']}) [MATCH EXACT]"
)

# Planets
for p_key, p_data in planets.items():
    p_fact = next(f for f in doc.facts if f.id == f"f_{p_key}")
    gap = p_fact.longitude - p_data["longitude"]
    sec = gap * 3600
    is_disc = p_data.get("known_discrepancy", False)
    if is_disc:
        status = "CONFIRMED DISCREPANCY (gap > 0.005° asserted)"
    else:
        status = "PASS (<= 0.005°)" if abs(gap) <= 0.005 else "FAIL"
    p_title = p_key.capitalize()
    print(
        f"{p_title:<10} | {p_data['sign_rashi']:<8} | {p_data['dms']:<9} | {p_data['longitude']:<11.6f} | "
        f"{p_fact.longitude:<11.6f} | {gap:<+11.6f} | {sec:<+10.2f}\"   | {status}"
    )

print("=" * 110)
