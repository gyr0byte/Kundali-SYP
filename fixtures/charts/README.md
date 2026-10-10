# Kundali Chart Fixtures Specification

This directory contains regression test fixtures for the Kundali calculation engine.

## Directory Structure

* `fixtures/charts/`: Public fixtures, including synthetic charts and published textbook examples.
* `fixtures/charts_private/`: Private fixtures (git-ignored, personal charts). If absent, tests that reference private fixtures will skip cleanly.

## Fixture JSON Schema

Each fixture file has the following JSON structure:

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

### Ground Rules for Assertions
* Any field set to `null` is **skipped**, never guessed.
* For engine snapshot fixtures, expectations are golden-master regression checks to guarantee determinism across code changes.
* For third-party tool comparisons (e.g. Hamro Patro in `fixture_001.json`):
  - **Planetary Longitudes:** Constant offset of about 41 arcseconds under the default Lahiri, reduced to about 11 arcseconds under LAHIRI_1940 with true node; remaining difference unexplained.
  - **Saturn:** Engine confirmed by direct library call, stock pyswisseph and an independent analytic ephemeris; Hamro Patro's displayed value matches the engine's position three days later; cause unconfirmed. Asserted in tests as a known discrepancy (`known_discrepancy: true`) exceeding tolerance.
  - **Lagna Gap:** About 4.1 arcminutes, cause unconfirmed; engine matches stock Swiss Ephemeris. (Birth coordinates confirmed identical, ruling out coordinate discrepancy).
  - Signs and Moon nakshatra/pada are checked for exact matches under the `hamro_patro_compat` preset.

