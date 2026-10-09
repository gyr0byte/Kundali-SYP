# Reference Charts

This directory contains reference chart fixtures for regression testing.

## Format
Each fixture is a JSON file containing:
- `birth_data`: date (UTC), latitude, longitude, timezone
- `expected`: planetary positions, lagna, nakshatras, dashas
- `source`: the reference tool and version used to produce the expected values
- `notes`: any conventions (ayanamsha, node type, year length)
