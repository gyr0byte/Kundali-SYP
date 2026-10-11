# Kundali Chart Fixtures Specification

This directory contains regression test fixtures for the Kundali calculation engine (`backend/app/calc`).

---

## Directory Structure

* `fixtures/charts/`: Public fixtures, including synthetic engine snapshots and textbook examples.
* `fixtures/charts_private/`: Private fixtures (git-ignored, personal charts). If absent, regression tests that reference private fixtures skip cleanly.

---

## Available Fixtures

### Public Engine Snapshots (`fixtures/charts/`)
These three synthetic charts are **engine snapshots (golden-master tests)** designed to detect calculation regressions across code modifications. Their expected values are derived from verified engine runs rather than independent external references:
* `fixture_north_london.json`: Northern hemisphere test case (London: 51.5074°N, 0.1278°W).
* `fixture_south_sydney.json`: Southern hemisphere test case (Sydney: 33.8688°S, 151.2093°E).
* `fixture_near_midnight_tokyo.json`: Local-time date boundary crossing test case (Tokyo: 35.6762°N, 139.6503°E).
* `fixture_001_builder.json`: Format reference schema.

### Private Reference Fixtures (`fixtures/charts_private/`)
* `fixture_001.json`: Evaluated against Hamro Patro reference data when present; skipped if absent.

---

## Fixture JSON Schema

Each fixture adheres to the following structure:

```json
{
  "id": "fixture_north_london",
  "name": "Northern Hemisphere Test Case (London)",
  "source_tool": "Engine Snapshot",
  "source_type": "golden_master",
  "_comment": "Engine snapshot (golden-master) test to detect calculation regressions. Expectations are from the engine itself, not an independent third-party reference.",
  "birth": {
    "date": "2015-05-15",
    "time": "14:30:00",
    "latitude": 51.5074,
    "longitude": -0.1278,
    "timezone": "Europe/London",
    "utc_offset_hours": 1.0
  },
  "settings": {
    "ayanamsha": "lahiri",
    "house_system": "whole_sign",
    "node_type": "mean"
  },
  "expected": {
    "lagna": {
      "sign": "Virgo",
      "longitude": 164.123456
    },
    "moon": {
      "sign": "Pisces",
      "longitude": 348.654321,
      "nakshatra": "Revati",
      "pada": 3
    },
    "planets": {
      "sun": { "sign": "Taurus", "longitude": 30.123456 },
      "mars": { "sign": "Taurus", "longitude": 39.654321 }
    }
  },
  "tolerances": {
    "planet_longitude_degrees": 0.01,
    "lagna_sign": "exact",
    "moon_nakshatra_pada": "exact"
  }
}
```

---

## Tolerances & Assertion Rules

1. **Skipping Null Values:** Any expected field left `null` is strictly **skipped** during test execution and never guessed.
2. **Tolerance Thresholds:**
   * `planet_longitude_degrees`: Maximum allowed difference in decimal degrees (typically `0.01°` for synthetic snapshots, `0.005°` for third-party planetary benchmarks).
   * `lagna_longitude_degrees`: Threshold for Ascendant comparison (e.g. `0.1°`).
   * `lagna_sign`: Asserts an exact string match for the zodiac sign.
   * `moon_nakshatra_pada`: Asserts exact matches for both the Nakshatra name and Pada number (1-4).
3. **Known Discrepancies:** When an expected entry has `"known_discrepancy": true` (e.g. Saturn in third-party comparisons), the test asserts that the engine is **not** within tolerance (`gap > planet_tol`), documenting the discrepancy rather than concealing it.

---

## Third-Party Comparison Findings (Hamro Patro Benchmark)

When running regression tests against Hamro Patro reference data under the `hamro_patro_compat` preset (`node_type = TRUE`, `ayanamsha = LAHIRI_1940`):
* **Planetary Longitudes:** Constant offset of about 41 arcseconds under default Lahiri, about 11 arcseconds under LAHIRI_1940 with true node; remaining difference unexplained.
* **Saturn Discrepancy:** Engine matches direct library call; Hamro Patro's displayed value matches the engine's position three days later; cause unconfirmed.
* **Lagna Gap:** About 4 to 5 arcminutes, cause unconfirmed; engine matches stock Swiss Ephemeris. (Birth coordinates confirmed identical between tools, ruling out coordinate discrepancy).
* **External Checks:** Checked externally by the project author on 2026-10-10 (stock pyswisseph in Moshier mode; astropy's built-in ephemeris for Saturn); not reproduced by the repository's tests.
