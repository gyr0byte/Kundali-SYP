# Calculation Engine Architecture

The Kundali Calculation Engine is a deterministic astronomical pipeline. It computes Vedic birth charts and outputs structured **Chart Facts** without relying on heuristics or artificial intelligence. Per the project boundary rules, this engine never imports from or depends on the AI interpretation layer.

---

## 1. Calculation Pipeline

```
Birth Input (Date, Local Time, Lat/Lon, Timezone or Offset)
    │
    ▼
[timeconv.py]
    ├── Validate latitude (-90..90) & longitude (-180..180)
    ├── Disambiguate local time (reject DST gaps & overlaps)
    ├── Convert to UTC timestamp
    └── Compute Julian Day (UT) via Swiss Ephemeris (swe_julday)
    │
    ├──────────────────────────────┬──────────────────────────────┐
    ▼                              ▼                              ▼
[ayanamsha.py]             [ephemeris.py]                   [houses.py]
Select Sidereal Mode       Compute Sidereal Positions       Compute Sidereal Lagna
(Lahiri / Raman / KP)      Sun..Saturn, Rahu, Ketu          via Whole Sign system
under SWE_LOCK             Retrograde & Speed flags         under SWE_LOCK
    │                              │                              │
    └──────────────────────────────┼──────────────────────────────┘
                                   ▼
                            [nakshatra.py]
                            Map Longitudes to 27 Nakshatras & 4 Padas
                            (Ashwini..Revati, 13°20' span, 3°20' pada)
                                   │
                                   ▼
                              [facts.py]
                            Construct Immutable ChartFacts Document
                            - Stable fact IDs (f_lagna, f_sun..f_ketu)
                            - Boundary sensitivity flag (f_lagna_sensitivity)
                            - Ephemeris source provenance ("swieph" | "moshier")
```

---

## 2. Default Conventions

1. **Ayanamsha:** `Lahiri` (Chitrapaksha default, `SE_SIDM_LAHIRI`).
2. **House System:** `Whole Sign` (`b'W'`). The entire 30° zodiac sign containing the Ascendant is House 1; the next sign is House 2, wrapping through House 12.
3. **Lunar Nodes (Rahu / Ketu):**
   * Default: `Mean Node` (`SE_MEAN_NODE`), per standard textbook convention.
   * Configurable: `True Node` (`SE_TRUE_NODE`), used by popular South Asian apps such as Hamro Patro.
   * Ketu is strictly computed as $(Rahu + 180^\circ) \pmod{360^\circ}$.
   * Both nodes are always flagged as retrograde.
4. **Ephemeris Precision:** Swiss Ephemeris JPL DE441 compressed `.se1` files (`sepl_18.se1`, `semo_18.se1`, `seas_18.se1`) in `backend/ephe/`. If missing, the library falls back to Moshier analytical mode and reports `"moshier"` in the metadata.

---

## 3. Tool Variance Analysis (Causes of Disagreement)

When Kundali outputs differ from third-party software (e.g. Hamro Patro, Jagannatha Hora, AstroSage), the discrepancy is almost always attributable to configurable conventions:

| Source of Variation | Typical Discrepancy | Architectural Resolution |
| :--- | :--- | :--- |
| **Ayanamsha Epoch** | $\approx 40'' - 50''$ (0.011°) | Swiss Ephemeris Lahiri aligns Spica at 180° in 285 AD; older Indian panchang tables use historical fixed constants. Expose Ayanamsha setting. |
| **Node Calculation** | Up to $1.5^\circ - 2.0^\circ$ | Mean nodes follow an averaged orbit; True nodes model instantaneous orbital wobble. Supported via `node_type: "mean" \| "true"`. |
| **Timezone Offset** | Hours / Sign shifts | Nepal Time (UTC+5:45) is non-standard. `timeconv.py` validates `Asia/Kathmandu` and rejects DST ambiguity. |
| **House Division** | House allocation changes | South Asian diamond charts use Whole Sign; Western and some Krishnamurti software use Placidus or Sripati. Default to Whole Sign. |
| **Ephemeris Engine** | Sub-arcsecond vs $\approx 1''$ | Sub-arcsecond accuracy requires Swiss Ephemeris `.se1` files; analytical approximations (Moshier) drift slightly over centuries. Provenance is tracked in metadata. |
