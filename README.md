# Kundali

Kundali is a full-stack Vedic astrology web application designed to generate astronomically accurate birth charts and provide transparent, verifiable interpretations. The system is architected around human-in-the-loop review, source provenance, and strict layer isolation between astronomical calculation and AI-assisted interpretation.

The core idea is "Compute First, Interpret Second". Every planetary position and house cusp is deterministically computed from raw birth data before any interpretation occurs, ensuring that AI reasoning operates solely on validated, immutable chart facts.

---

## Project Status

| Area | Component | Status |
| :--- | :--- | :--- |
| **Calculation Engine** | `app/calc/timeconv.py` (Local time to UTC, Julian Day, coordinate validation) | IMPLEMENTED |
| | `app/calc/ayanamsha.py` (Sidereal ayanamsha modes under thread-safe lock) | IMPLEMENTED |
| | `app/calc/ephemeris.py` (Sidereal longitudes, speed, retrograde, nodes) | IMPLEMENTED |
| | `app/calc/houses.py` (Whole-sign houses, Lagna, boundary sensitivity) | IMPLEMENTED |
| | `app/calc/nakshatra.py` (27 Nakshatras and 4 Padas mapping) | IMPLEMENTED |
| | `app/calc/facts.py` (Immutable `ChartFacts` Pydantic v2 document, presets) | IMPLEMENTED |
| | `app/calc/dasha.py` (Vimshottari Dasha timeline) | STUB |
| | `app/calc/transits.py` (Planetary transits and ingress) | STUB |
| | `app/calc/ashtakoota.py` (36-point compatibility scoring) | STUB |
| | `app/calc/yogas.py` (Yoga combination evaluation) | STUB |
| | `app/calc/bikram_sambat.py` (Bikram Sambat calendar conversion) | STUB |
| | `app/calc/divisional.py` (Divisional charts D9, etc.) | STUB |
| **AI Layer** | `app/ai/*` (Embeddings, retrieval, prompts, guardrails, validator) | STUB |
| **Database & Models** | `app/db/models/*`, `app/db/*` (ORM models, session factory, migrations) | STUB |
| **API Layer** | `app/main.py`, `app/api/v1/*` (FastAPI routes for charts, chat, admin) | STUB |
| **Background Jobs** | `app/jobs/*` (Scheduler, transit alert jobs) | STUB |
| **Knowledge Base** | `app/knowledge/*` (Chunking, ingestion, provenance tracking) | STUB |
| **Frontend** | `frontend/src/app/*` (Next.js App Router route groups) | STUB |
| | `frontend/src/i18n/*` (Message dictionaries `en.json`, `ne.json`) | STUB |
| **Developer Scripts** | `scripts/chart_cli.py` (Chart calculation command-line interface) | implemented, manual, not covered by tests |
| | `scripts/download_ephemeris.py` (Swiss Ephemeris data file downloader) | implemented, manual, not covered by tests |
| | `scripts/env.ps1` (PowerShell environment setup redirecting to D:) | implemented, manual, not covered by tests |
| | `scripts/verify_env.ps1` (Environment diagnostics verification) | implemented, manual, not covered by tests |
| | `scripts/check_db.py` (Database connectivity and pgvector check) | implemented, manual, not covered by tests; never run against a real database |

---

## What Works Today

* **Deterministic Sidereal Positions:** High-precision longitudes, speed, and retrograde flags for the Sun, Moon, Mars, Mercury, Jupiter, Venus, Saturn, Rahu, and Ketu (`Rahu + 180°`), supporting both Mean and True lunar nodes.
* **Whole-Sign House Allocation & Lagna:** Computes the Ascendant (Lagna) and allocates houses 1 through 12 across 30° zodiac signs, emitting a sensitivity warning when Lagna is within 0.5° of a sign boundary.
* **Nakshatra & Pada Mapping:** Maps 0–360° sidereal longitudes into 27 lunar mansions (13°20' each) and 4 quarters (Padas of 3°20' each).
* **Immutable Chart Facts Document:** Generates a structured, validated Pydantic v2 document with stable fact IDs (`f_lagna`, `f_sun`..`f_ketu`, `f_lagna_sensitivity`), provenance reporting (`"swieph"` vs `"moshier"`), and byte-for-byte deterministic JSON serialization.
* **Calculation Presets:** Documented `hamro_patro_compat` preset (`node_type = TRUE`, `ayanamsha = LAHIRI_1940`) alongside the default standard Lahiri and Mean Node conventions.
* **Developer CLI:** `scripts/chart_cli.py` calculates birth charts and outputs Chart Facts JSON or formatted tables from the terminal.
* **Automated Test Suite:** 40 passing tests (33 unit tests and 7 regression tests) validating calculation accuracy and regression baselines.

---

## Not Built Yet

* **Dasha Calculations:** Vimshottari dasha, antardasha, and pratyantardasha timeline computation.
* **Transits & Ingress:** Gochara transit tracking and planetary ingress detection.
* **Yogas & Compatibility:** Evaluation rules for classical planetary yogas and Ashtakoota compatibility scoring.
* **Bikram Sambat Support:** Date conversion routines between Gregorian (AD) and Bikram Sambat (BS).
* **AI Interpretation Layer:** Retrieval-augmented generation, prompt construction, LLM adapter, and guardrail validation.
* **Database & Persistence:** SQLAlchemy ORM models, migrations, and database session management.
* **HTTP API:** FastAPI application endpoints and route handlers.
* **Background Jobs:** Asynchronous transit alerts and scheduled jobs.
* **Knowledge Ingestion:** Ingestion pipelines and vector chunking for classical texts.
* **Frontend User Interface:** Interactive chart rendering, panels, and forms. (The frontend root page is currently the unmodified starter page from `create-next-app`).

---

## Quick Start

### 1. Environment Isolation (PowerShell on Windows)
All tool installations and package caches must be redirected to `D:\DevCache`.
```powershell
. .\scripts\env.ps1
powershell -File .\scripts\verify_env.ps1
```

### 2. Backend Setup & Tests
```powershell
# Sync dependencies
cd backend
uv sync --group dev

# Run automated tests (40 tests: 33 unit, 7 regression)
uv run pytest

# Run code style check
uv run ruff check .

# Run static type check (Note: strictly covers app/calc only)
uv run mypy --strict app/calc

# Run architecture boundary check
uv run lint-imports
```

### 3. Ephemeris Data Files (Optional but Recommended)
To run with sub-arcsecond precision, download the Swiss Ephemeris .se1 data files from the official repository into `backend/ephe/`:
```powershell
# From project root
. .\scripts\env.ps1
uv run python scripts/download_ephemeris.py
```
*(Without these files, the engine falls back to Moshier analytical mode and reports `"moshier"` provenance).*

### 4. Run the Calculation CLI
```powershell
# From project root
. .\scripts\env.ps1
uv run --directory backend python ..\scripts\chart_cli.py --date 2000-01-01 --time 12:00:00 --lat 27.7172 --lon 85.3240 --tz Asia/Kathmandu
```

### 5. Frontend Setup
```powershell
cd frontend
npm install
npm run dev
```
*(Note: `npm run lint` passes with 0 errors; `npm run build` was not run).*

---

## Repository Layout

```
kundali/
├── backend/                  Python calculation engine, stubs, and tests
│   ├── app/                  Source packages (calc, ai, db, api, core, jobs, knowledge)
│   ├── tests/                Unit and regression test suites
│   ├── pyproject.toml        Python project configuration and dependencies
│   └── uv.lock               Locked dependency tree
├── frontend/                 Next.js App Router web application
│   ├── src/                  App routes, placeholder panels, and i18n dictionaries
│   ├── package.json          Node.js dependencies and scripts
│   └── tsconfig.json         TypeScript compiler configuration
├── docs/                     Architecture specifications, ADRs, and guides
│   ├── adr/                  Architecture Decision Records (0001 through 0007)
│   ├── architecture/         Calculation engine, database setup, and pipeline docs
│   └── proposal/             SYP proposal notice
├── fixtures/                 Test fixtures for regression testing
│   ├── charts/               Public synthetic golden-master engine snapshots
│   ├── charts_private/       Private benchmark reference charts (git-ignored)
│   └── knowledge_samples/    Knowledge base test samples
└── scripts/                  Developer utilities and operational scripts
    ├── chart_cli.py          Birth chart calculation CLI
    ├── download_ephemeris.py Swiss Ephemeris data download utility
    ├── env.ps1               PowerShell cache redirection script
    ├── verify_env.ps1        Environment diagnostic check
    └── check_db.py           Database connectivity check stub
```

---

## Documentation

* [Architecture Index](docs/architecture/README.md)
* [Calculation Engine Specification](docs/architecture/calc-engine.md)
* [Database Setup Guide](docs/architecture/DATABASE_SETUP.md)
* [Architecture Decision Records](docs/adr/0001-record-decisions.md)
* [Original Project Plan](docs/Kundali_Project_Plan.md)
* [Changelog](CHANGELOG.md)

---

## Licence

This project is licensed under the **GNU Affero General Public License v3.0** (GNU AGPL-3.0). See [LICENSE](LICENSE) for the full license text.

**Why AGPL-3.0?**
The calculation engine uses `swisseph-ffi`, which incorporates the Swiss Ephemeris C library developed by Astrodienst AG. The Swiss Ephemeris is published under the GNU AGPL-3.0 (with dual-licensing options), requiring derivative applications and network services utilizing it under the open-source license to also be licensed under GNU AGPL-3.0.
