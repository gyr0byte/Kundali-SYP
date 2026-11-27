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

### Persistent chart snapshots

`POST /api/v1/profiles/{profile_id}/chart` retains its calculation response body and returns an owner-scoped snapshot URL in `Location`. `GET /api/v1/charts/{snapshot_id}` reads the stored result by its opaque UUID, returns the typed `chart.facts` with their units, and marks whether the source profile revision is still current at read time. Responses use `Cache-Control: no-store`. Other owners receive `404` even if their own chart has the same deterministic fingerprint.

Each stored v1 document contains the original engine fingerprint, resolved settings, engine version, aggregate ephemeris provenance, and typed facts in engine order. Angles are in degrees and planetary speed is in degrees per day. The authenticated Fernet document includes its snapshot and profile identities. Keeping the versioned facts inline protects the whole result without duplicating raw profile fields or exposing per-fact metadata in plaintext. A keyed lookup digest includes the profile ID, so the storage index does not reveal equal fingerprints across profiles. The snapshot UUID, profile reference/revision, schema version, creation time and digest remain available to the database. Recovering or rotating the Fernet key must account for both ciphertext and its keyed lookup digest.

Repeated results reuse the same row within a profile revision and snapshot schema version. The preparation read transaction ends before native calculation. A short PostgreSQL parent-row lock serializes snapshot insertion with profile edits and deletions, and the uniqueness constraint is the final duplicate guard. Every successful profile PATCH advances the revision, including metadata-only edits. A stale calculation returns `409 PROFILE_CHANGED` and writes nothing. Historical snapshots remain until the parent profile is deleted, which cascades to snapshots and their embedded facts. Snapshot history is accessible by UUID only, with no listing UI. Several snapshots can match the current profile revision, including results from earlier engine versions or different settings. Direct SQL edits to birth data must preserve the revision contract. AI interpretation, Dasha calculations and knowledge retrieval remain unimplemented.

### Bikram Sambat civil dates

Birth profiles accept Gregorian (AD) and Nepali Bikram Sambat (BS) dates as
`YYYY-MM-DD`, including Devanagari digits. The backend stores the entered
calendar and date, canonicalized to ASCII digits, and encrypts both the entered
date and normalized Gregorian date. The calendar module provides conversion in
both directions. Calculation uses the normalized AD date and then applies the
existing local-time, timezone, and astronomical pipeline.

Kundali calendar data version `kundali-bs-v1` uses the 11 KiB CSV distributed
with [sambat 0.1.0](https://pypi.org/project/sambat/0.1.0/), pinned to
[`32014630fb0fd63937736f4fe3b9d81d519b0d17`](https://github.com/rjach/sambat/tree/32014630fb0fd63937736f4fe3b9d81d519b0d17/data).
The CSV is redistributed under Apache License 2.0 with the upstream LICENSE
and NOTICE. Python's standard library reads the local file at runtime. The
backend wheel and source distribution include all three files. The upstream
project has a short release history, so Kundali pins the data and checks
reference dates before changing versions.

Upstream checked BS 2081 against Surya Panchanga and 2082–2083 against Nepal's
national Panchang. Earlier rows largely reflect agreement among published
software tables, many of which share ancestry. The supported span is
**BS 1975-01-01 through 2083-12-30**, corresponding to
**AD 1918-04-13 through 2027-04-13**, inclusive. Both directions reject the
following intervals because the source tables disagree on their month
boundaries.

| Excluded BS months | Excluded AD dates, inclusive |
| --- | --- |
| 1989 months 7–8 | 1932-10-17 to 1932-12-14 |
| 1991 months 8–9 | 1934-11-16 to 1935-01-13 |
| 1993 months 3–4 | 1936-06-14 to 1936-08-15 |
| 2004 months 9–10 | 1947-12-16 to 1948-02-12 |

Nepal Rastra Bank's Jestha 2062 interest-rate report pairs `2062/02/01`
with May 15, 2005, in two bank entries and `2062/02/05` with May 19,
2005, in another. It also pairs `2062/01/01` with April 14, 2005. This
contemporaneous official record supports the pinned civil boundary of May 14
as Baishakh 31 and May 15 as Jestha 1. The NTA archive lists a Baishakh
report ending May 14, but its listing starts April 15, so it does not
establish the starting day. Dates beyond the table are rejected without
extrapolation.
[Nepal Rastra Bank report](https://www.nrb.org.np/contents/uploads/2019/12/Interest_Rate_Structure_of_Commercial_Banks-2062-02.pdf),
[NTA report index](https://old.nta.gov.np/mispdf),
[Upstream provenance and discrepancies](https://github.com/rjach/sambat/blob/32014630fb0fd63937736f4fe3b9d81d519b0d17/data/README.md).

Reference tests use published dates from the UNCTAD/ICC Nepal holiday
schedule, Nepal Rastra Bank, Nepal's Ministry of Foreign Affairs, and Nepal's
diplomatic missions in Tokyo, Cairo and Kolkata. Round-trip tests also cover
every supported day. These checks verify the reference dates and internal
consistency. Most early dates remain supported by table consensus.
[UNCTAD/ICC holiday schedule](https://unctad.org/system/files/official-document/iteiia20032_en.pdf),
[Ministry earthquake report](https://mofa.gov.np/content/211/post-earthquake-relief--rehabilitation-and-reconstruction-measures-government/),
[Tokyo holiday schedule](https://giwmscdnone.gov.np/media/pdf_upload/Holidays_tfzd83p.pdf),
[Cairo holiday schedule](https://eg.nepalembassy.gov.np/pages/holidays/),
[Kolkata holiday schedule](https://giwmscdntwo.gov.np/media/pdf_upload/Image_003_6ifesjj.pdf).

Initial verification passed 97 backend tests and 23 frontend tests. The
targeted calendar review passed 31 tests and verified the CSV and attribution
files in the source distribution, direct wheel, and wheel rebuilt from the
source distribution. An isolated wheel import successfully converted
`2062-02-01` to `2005-05-15`.

A legacy BS profile without an encrypted AD date remains pending until its
owner reviews and successfully saves it. Unsupported dates return a safe
validation error and leave the profile unchanged. A successful save uses the
existing revision mechanism. Historical snapshots retain their recorded facts.

### Birthplace selection and historical timezones

The authenticated `POST /api/v1/birthplaces/search` accepts a JSON `query`
of 2–80 characters with at least one letter and returns up to 12 results with
`Cache-Control: no-store`. It searches the packaged Nepal subset by primary or
alternate name, then prefix or word prefix. A name followed by an
administrative area, such as `Rampur Udayapur`, narrows matching places.
Population, normalized name and
GeoNames ID break ties. Administrative names and coordinates distinguish
places with the same name. Devanagari names come from the source's untagged
alternate-name field and can include variants from more than one language.

The source is the GeoNames Nepal country extract dated 2026-11-27, licensed
under CC BY 4.0. The 3,459,581-byte archive produces a 282,413-byte compressed
table of 10,284 populated places. The extraction retains named towns, villages
and selected localities with aliases or population, along with available
administrative context from the same archive. Places missing from the subset,
including border records whose source timezone is outside Nepal, can be added
manually with verified coordinates and an IANA timezone.
[Dataset attribution and source checksum](../../backend/app/geo/data/ATTRIBUTION.md),
[reproducible extraction](../../scripts/build_nepal_gazetteer.py).

`POST /api/v1/profiles` and `PATCH /api/v1/profiles/{profile_id}` accept an
optional numeric `location_id`. The server replaces any submitted location
name, coordinates, and timezone with the resolved record. Manual entry retains
the existing validation rules. Profiles store the same encrypted fields and
revision as before. Saved profiles and chart calculations are independent of
the gazetteer. No database migration is needed.

After BS-to-AD normalization, the time conversion layer uses Python
`zoneinfo` with pinned `tzdata==2026.5` (IANA release 2026e). The same data is
read on Windows and deployment hosts regardless of the system timezone
database. IANA records `Asia/Kathmandu` as UTC+05:41:16 before 1920,
UTC+05:30 until 1986, and UTC+05:45 from 1986. The 1920 rollback repeats
23:48:44 through 23:59:59 on December 31, 1919. The 1986 change skips
00:00:00 through 00:14:59 on January 1. The same validation rejects
international clock gaps and overlaps. Kundali does not choose a fold for
an ambiguous birth time.

Historical rules describe representative locations. Coverage is less
complete before 1970 and can be corrected in later releases. A tzdata
upgrade that changes the resolved UTC instant also changes the chart
fingerprint and its snapshot lookup key, even within the same profile
revision. Snapshots record the resolved UTC instant and offset. The tzdata
release is pinned for the deployment but is not recorded per snapshot or
included independently in the fingerprint. A release change that produces
the same result can reuse the same snapshot. Historical snapshot contents
remain as recorded.
[IANA Nepal rules](https://data.iana.org/time-zones/tzdb-2026e/asia),
[IANA data scope](https://data.iana.org/time-zones/tzdb-2026e/theory.html).

Search covers Nepal. International locations require manual entry.
Settlement coordinates represent the named place. Use manual entry for
verified coordinates of the actual birth location. Nepali aliases depend on
source availability.

Offline verification passed 127 backend tests, 23 frontend tests, and two
mocked Playwright checks. The source distribution and wheels contained the
dataset and attribution, and search and timezone lookup passed from an
extracted wheel.

Live Playwright verification used the restricted development PostgreSQL role
at 1440 × 900 in English and 375 × 812 in Nepali. Keyboard and touch
selection, trusted coordinates and timezone, and AD and BS creation passed.
Equivalent profiles produced identical chart facts. A birthplace edit cleared
the displayed chart and preserved its historical snapshot. A label-only edit
preserved the saved location. Manual international entry, reopening and
calculating a saved profile, historical Nepal gap rejection, and international
DST overlap rejection passed. The browser reported zero uncaught JavaScript
errors, network failures, or horizontal overflow.

The three synthetic profiles were deleted and all four known snapshot URLs
returned HTTP 404. One synthetic development account and its audit history
remain. The browser verification did not independently query audit records.

### Unknown birth time

After BS normalization, the lunar mode uses the complete UTC preimage of the
saved local date. It enumerates the three UTC days that can overlap the date
on the integral-second grid used by IANA TZif. It merges consecutive matching
seconds into half-open intervals. This retains repeated clock times and dates
with disjoint UTC spans, and rejects skipped dates such as Apia 2011-12-30.
The model treats each UTC day as 86,400 seconds, consistent with Python
`datetime` and the existing chart pipeline. Lunar mode supports Gregorian
dates from 1801-01-01 through 2199-12-31, subject to ephemeris coverage.

The calculation evaluates the geocentric sidereal Moon with the existing Swiss
Ephemeris flags and selected ayanamsha. Each UTC span is divided into cells of
at most ten minutes. Each midpoint is surrounded by an angular radius equal to
half the cell duration multiplied by 30 degrees per day, plus 0.01 degree.
The 30 degrees per day is a conservative engineering bound for lunar motion
in this date range, informed by lunar orbital speed, distance, and inclination.
It is an assumption about the model inside each cell, not a measured maximum
from the sample grid. The 0.01 degree margin covers floating-point boundaries
and provides headroom over documented ephemeris discrepancies. It is not a
certified error bound. The samples and edge checks reject mixed ephemeris
sources, speeds exceeding the bound, or adjacent motion inconsistent with
the bound and margin. In those cases categories are unavailable.

Possible values are the union of all zodiac, nakshatra and pada bins
intersected by the enclosures, including across 0/360 degrees. A series is
stable only if this union has one bin. Otherwise the series is uncertain.
Conservative bounds can include neighboring bins that the true trajectory
does not reach, including at the exclusive end of the local date. The
interval boundaries are civil-time limits, not a birth time. An independent
offline fixture checks three tropical Moon samples against JPL Horizons DE441
before the application-specific sidereal convention is applied.
[NASA lunar orbital context](https://eclipse.gsfc.nasa.gov/SEhelp/moonorbit.html),
[Swiss Ephemeris accuracy](https://www.astro.com/swisseph/swisseph.htm),
[JPL Horizons](https://ssd.jpl.nasa.gov/horizons/).

`POST /api/v1/profiles/{profile_id}/chart` uses the saved certainty. The
known-time response retains its `chart` field and version 1 encrypted
snapshot document. Unknown time returns a `moon` field with the UTC spans,
duration, source, ayanamsha, method, and typed possible sets. It has no
ascendant, houses, natal fact IDs, or exact lunar position. It uses a domain
distinct `m_` fingerprint and an encrypted version 2 snapshot. The existing
ownership, profile revision, and idempotency checks apply. No schema migration
is required. Future interpretation consumers must handle this result as
interval evidence separately from the natal fact allowlist.

Offline verification passed 65 backend tests, 22 frontend tests, two mocked
Playwright checks, and three independent JPL longitude comparisons within
0.01 degree. Live verification used the restricted development PostgreSQL
role at 1440 × 900 in English and 375 × 812 in Nepali. It confirmed equivalent
AD and BS Moon results, idempotent version 2 persistence, cross-user 404s,
and profile revision tracking through both directions of a birth-time edit.
The version 1 compatibility check used a newly created synthetic natal
snapshot. The unknown-time views showed the limited result without an
ascendant, houses, an exact birth instant, or a natal chart. The browser
reported zero unexpected errors, network failures, or horizontal overflow.

The numerical guarantee is conditional on the motion bound and margin.
The enclosures give conservative possibilities. Unknown-time results are
ineligible for exact Dasha calculations. The three timing probes used
146–160 Swiss Ephemeris calls and observed about 6–135 ms for the locked
calculation. These observations do not guarantee latency. Concurrent
request performance remains unverified.

Both synthetic profiles were deleted, and all four associated snapshots
returned HTTP 404. The two synthetic accounts and their audit history remain.
The live verification did not independently query audit rows.

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
