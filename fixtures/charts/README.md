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
* For engine snapshot fixtures, expectations are golden-master regression checks to guarantee determinism across code changes.
* For third-party tool comparisons (e.g. Hamro Patro), signs and nakshatra/pada are checked for exact matches, and convention variances (ayanamsha epoch, mean vs true nodes) are accounted for as user settings.
