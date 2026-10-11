# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
* **Calculation Engine Core (`backend/app/calc`):**
  * Local time conversion to UTC and Julian Day (`timeconv.py`) with coordinate validation and DST gap/overlap disambiguation.
  * Sidereal ayanamsha computation under thread-safe lock (`ayanamsha.py`), supporting `lahiri`, `lahiri_1940`, `raman`, and `krishnamurti`.
  * Sidereal planetary positions, speed, and retrograde flags (`ephemeris.py`) for Sun through Saturn, Rahu, and Ketu (`Rahu + 180°`), with support for Mean and True lunar nodes.
  * Whole-sign house calculation and Ascendant (`houses.py`) with 0.5° sign boundary sensitivity detection.
  * Longitude mapping to 27 Nakshatras and 4 Padas (`nakshatra.py`).
  * Immutable Pydantic v2 `ChartFacts` document model with stable fact IDs (`f_lagna`, `f_sun`..`f_ketu`) and provenance tracking (`facts.py`).
  * Documented calculation preset `hamro_patro_compat` (`node_type = TRUE`, `ayanamsha = LAHIRI_1940`).
* **Test Suite & Fixtures:**
  * 40 automated tests (33 unit tests, 7 regression tests) covering all implemented calculation modules.
  * Public synthetic golden-master regression fixtures (`fixtures/charts/`) and private benchmark fixture schema (`fixtures/charts_private/`).
* **Developer Tools (`scripts/`):**
  * `scripts/chart_cli.py` for computing birth charts and emitting Chart Facts JSON from the command line.
  * `scripts/download_ephemeris.py` for fetching Swiss Ephemeris .se1 data files from the official repository.
  * `scripts/env.ps1` and `scripts/verify_env.ps1` for PowerShell environment isolation and cache redirection to `D:\DevCache`.
  * `scripts/check_db.py` stub for database connection checking.
* **Architecture Documentation (`docs/`):**
  * Architecture specifications (`docs/architecture/calc-engine.md`, `docs/architecture/DATABASE_SETUP.md`, `docs/architecture/README.md`).
  * Architecture Decision Records (`docs/adr/0001` through `0007`).
* **Scaffolding:**
  * Next.js App Router frontend scaffold (`frontend/`) with TypeScript, Tailwind CSS, placeholder route groups, and initial `next-intl` translation files.
  * Module stubs for Dasha, transits, yogas, compatibility scoring, Bikram Sambat date conversion, AI interpretation, database models, API routes, jobs, and knowledge ingestion.
