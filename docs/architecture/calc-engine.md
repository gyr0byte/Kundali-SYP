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

## 2. Default Conventions & Presets

1. **Ayanamsha:** Default is `Lahiri` (Chitrapaksha default, `SE_SIDM_LAHIRI`).
2. **House System:** Default is `Whole Sign` (`b'W'`). The entire 30° zodiac sign containing the Ascendant is House 1; the next sign is House 2, wrapping through House 12.
3. **Lunar Nodes (Rahu / Ketu):**
   * Default: `Mean Node` (`SE_MEAN_NODE`), per standard textbook convention.
   * Configurable: `True Node` (`SE_TRUE_NODE`), used by popular South Asian apps such as Hamro Patro.
   * Ketu is strictly computed as $(Rahu + 180^\circ) \pmod{360^\circ}$.
   * Both nodes are always flagged as retrograde.
4. **Presets:** A documented `"hamro_patro_compat"` preset is available (`node_type: TRUE`, `ayanamsha: LAHIRI_1940`), but default remains standard Lahiri and Mean Node.
5. **Ephemeris Data Files:** Swiss Ephemeris .se1 data files from the official repository (`sepl_18.se1`, `semo_18.se1`, `seas_18.se1`) in `backend/ephe/`. If missing, the library falls back to Moshier analytical mode and reports `"moshier"` in the metadata.
6. **Thread-Safety Lock:** Swiss Ephemeris C-library maintains global sidereal state (`swe_set_sid_mode`). All calls mutating or reading sidereal mode are synchronized under a module-level lock (`SWE_LOCK` in `app/calc/ayanamsha.py`) to guarantee multi-threaded isolation.

---

## 3. Chart Facts Schema & Fact IDs

The engine emits an immutable `ChartFacts` document validated via Pydantic v2:

* **Chart Identification:** `chart_id`, `engine_version` (`"0.1.0"`).
* **Metadata Provenance (`ChartMetadata`):**
  * `ephemeris_source`: `"swieph"` (when `.se1` files are loaded) or `"moshier"` (fallback mode).
  * `julian_day`: Julian Day UT float.
  * `utc_offset_hours`: Explicit UTC offset.
  * `datetime_utc_iso`: ISO-8601 UTC timestamp.
* **Stable Fact IDs:**
  * `f_lagna`: Ascendant fact containing sign, sign index (0-11), degree in sign, absolute longitude, nakshatra, and pada.
  * `f_sun`, `f_moon`, `f_mars`, `f_mercury`, `f_jupiter`, `f_venus`, `f_saturn`, `f_rahu`, `f_ketu`: Planetary placement facts with sign, sign index, house (1-12), degree in sign, absolute longitude, nakshatra, pada, retrograde flag, and daily speed.
  * `f_lagna_sensitivity`: Conditional sensitivity fact emitted only when Lagna is within 0.5° of a sign boundary.

---

## 4. Tool Variance Analysis & Benchmark Findings

When Kundali outputs differ from third-party software (e.g. Hamro Patro, Jagannatha Hora, AstroSage), astronomical conventions account for observed differences.

### Third-Party Benchmark Audit (Hamro Patro)

Regression testing against Hamro Patro reference data revealed:
* **Planetary Longitudes (Sun, Moon, Mars, Mercury, Jupiter, Venus, Rahu, Ketu):** Constant offset of about 41 arcseconds under default Lahiri, about 11 arcseconds under LAHIRI_1940 with true node; remaining difference unexplained.
* **Saturn Discrepancy:** Engine matches direct library call; Hamro Patro's displayed value matches the engine's position three days later; cause unconfirmed. The discrepancy is explicitly documented in the private fixture (`known_discrepancy: true`) and asserted to exceed tolerance.
* **Lagna Discrepancy:** About 4 to 5 arcminutes, cause unconfirmed; engine matches stock Swiss Ephemeris. (Birth coordinates confirmed identical between tools, ruling out coordinate discrepancy).
* **External Checks:** Checked externally by the project author on 2026-10-10 (stock pyswisseph in Moshier mode; astropy's built-in ephemeris for Saturn); not reproduced by the repository's tests.

| Source of Variation | Typical Discrepancy | Architectural Resolution |
| :--- | :--- | :--- |
| **Ayanamsha Mode** | $\approx 30'' - 40''$ | Variations between historical Lahiri definitions (e.g. standard Lahiri vs Lahiri 1940). Supported via `ayanamsha: "lahiri" \| "lahiri_1940" \| "raman" \| "krishnamurti"`. |
| **Node Calculation** | Up to $1.5^\circ - 2.0^\circ$ | Mean nodes follow an averaged orbit; True nodes model instantaneous orbital wobble. Supported via `node_type: "mean" \| "true"`. |
| **Timezone Offset** | Hours / Sign shifts | Nepal Time (UTC+5:45) is non-standard. `timeconv.py` validates `Asia/Kathmandu` and rejects DST ambiguity. |
| **House Division** | House allocation changes | South Asian diamond charts use Whole Sign; Western and some Krishnamurti software use Placidus or Sripati. Default to Whole Sign. |
| **Ephemeris Engine** | Sub-arcsecond vs $\approx 1''$ | Sub-arcsecond accuracy requires Swiss Ephemeris `.se1` files; analytical approximations (Moshier) drift slightly over centuries. Provenance is tracked in metadata. |
