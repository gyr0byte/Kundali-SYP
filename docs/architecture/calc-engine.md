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
                            - Ephemeris source provenance ("swieph" | "moshier" | "mixed")
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
5. **Ephemeris Data Files:** Swiss Ephemeris .se1 data files from the official repository (`sepl_18.se1`, `semo_18.se1`, `seas_18.se1`) in `backend/ephe/`. When files are missing, the library can fall back to Moshier and reports the aggregate source in the metadata.
6. **Thread-Safety Lock:** Swiss Ephemeris C-library maintains global sidereal state (`swe_set_sid_mode`). All calls mutating or reading sidereal mode are synchronized under a module-level lock (`SWE_LOCK` in `app/calc/ayanamsha.py`) to guarantee multi-threaded isolation.

---

## 3. Chart Facts Schema & Fact IDs

The engine emits an immutable `ChartFacts` document validated via Pydantic v2:

* **Chart Identification:** `chart_id` and `engine_version`.
* **Metadata Provenance (`ChartMetadata`):**
  * `ephemeris_source`: `"swieph"`, `"moshier"`, or `"mixed"` when body results report both sources.
  * `julian_day`: Julian Day UT float.
  * `utc_offset_hours`: Explicit UTC offset.
  * `datetime_utc_iso`: ISO-8601 UTC timestamp.
* **Stable Fact IDs:**
  * `f_lagna`: Ascendant fact containing sign, sign index (0-11), degree in sign, absolute longitude, nakshatra, and pada.
  * `f_sun`, `f_moon`, `f_mars`, `f_mercury`, `f_jupiter`, `f_venus`, `f_saturn`, `f_rahu`, `f_ketu`: Planetary placement facts with sign, sign index, house (1-12), degree in sign, absolute longitude, nakshatra, pada, retrograde flag, and daily speed.
  * `f_lagna_sensitivity`: Conditional sensitivity fact emitted only when Lagna is within 0.5° of a sign boundary.

---

### Chart result identity

The profile chart endpoint returns `c_` followed by the first 32 lowercase hex digits
of SHA-256 over a versioned identity payload. The payload contains `identity_version`
(currently `1`), the Kundali engine version, resolved settings, chart metadata
(UTC birth instant, Julian Day UT, UTC offset, and aggregate ephemeris source),
normalized latitude and longitude, the ordered final chart facts at their existing
precision, and the native source flag reported for each body. Ketu inherits Rahu's
source. The per-body map distinguishes results that both report aggregate `"mixed"`.
The serialization is UTF-8 JSON with sorted object keys, compact separators, and
finite numeric values.

Profile and owner IDs, labels, persistence timestamps, installation paths, and the
chart ID itself are excluded. Equal effective birth inputs and chart results share
an ID, including across profiles. An edit to profile metadata alone leaves the ID
stable. The ID contains no plaintext birth values and carries no authorization.
Previous profile-calculation IDs use a different digest format and are not reused.
Callers should treat IDs as opaque strings. The CLI and fixtures can still supply
explicit IDs. Ephemeris file versions or byte content are not independently
fingerprinted when the reported native source and canonical result agree.

### Supported calculation dates

Profile calculation uses the normalized Gregorian instant. It accepts dates where
the configured Swiss files or Moshier fallback cover all required placements.
Profile storage keeps its existing validation. Installed data and the selected
calculation settings determine actual coverage.

Astrodienst describes the analytic fallback as covering roughly 3000 BCE through
3000 CE. The bundled Swiss Ephemeris 2.10.03 code uses TT Julian Day limits of
625000.5 and 2818000.5 when deciding whether to fall back for the planets and
Moon. With an empty file directory, local native checks succeeded on
0001-01-01 and 3003-04-28 at 22:00 UTC, and returned a coverage error on
3003-04-29 at 00:00 UTC. These sample instants explain the boundary in the tested
configuration. The API follows native coverage at the normalized instant.
[Astrodienst coverage overview](https://www.astro.com/swisseph/swephinfo_e.htm)
[Swiss Ephemeris 2.10.03 bounds](https://github.com/aloistr/swisseph/blob/v2.10.03/sweph.h#L199-L202)
[Native fallback implementation](https://github.com/aloistr/swisseph/blob/v2.10.03/sweph.c#L1589-L1603)

A confirmed range failure returns HTTP 409 with `CHART_DATE_OUT_OF_RANGE`.
This includes native date-limit diagnostics and missing or out-of-range Swiss
data when the instant is also outside the native fallback interval. Unknown
native failures return the generic HTTP 500. The response and operational logs
omit native messages, ephemeris paths, and birth inputs.

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
