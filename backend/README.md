# Kundali Backend

The backend provides the deterministic astronomical calculation engine for Kundali.

---

## Status

* **Implemented:** Astronomical calculation pipeline (`app/calc`: `timeconv`, `ayanamsha`, `ephemeris`, `houses`, `nakshatra`, `facts`) covered by 40 tests (33 unit, 7 regression).
* **Stubs:** Dasha (`dasha.py`), transits (`transits.py`), yogas (`yogas.py`), compatibility (`ashtakoota.py`), calendar conversion (`bikram_sambat.py`), AI interpretation layer (`app/ai/`), database models (`app/db/`), API routes (`app/api/`), background jobs (`app/jobs/`), and knowledge ingestion (`app/knowledge/`) are currently stubs.

---

## Environment Setup (Windows with `uv`)

All package installations and cache directories must reside on `D:\DevCache`.

1. **Configure Environment:**
   Dot-source the environment script before running commands:
   ```powershell
   . ..\scripts\env.ps1
   ```

2. **Sync Dependencies:**
   ```powershell
   cd backend
   uv sync --group dev
   ```

---

## Ephemeris Data Files

The calculation engine uses Swiss Ephemeris .se1 data files from the official repository (`sepl_18.se1`, `semo_18.se1`, `seas_18.se1`).

* **Download Script:** `scripts/download_ephemeris.py`
* **Execution:** Must be run manually from the project root:
  ```powershell
  . .\scripts\env.ps1
  uv run python scripts/download_ephemeris.py
  ```
* **Storage Location:** `backend/ephe/` (files are git-ignored and remain on `D:`).
* **Fallback:** If `.se1` files are missing, the engine automatically falls back to Moshier analytical mode and records `"moshier"` in calculation metadata.

---

## Quality Gates & Verification

Run all checks from the `backend/` directory:

```powershell
# 1. Run test suite (40 tests: 33 unit, 7 regression)
uv run pytest

# 2. Linting and code style checks
uv run ruff check .

# 3. Type checking (Note: strictly covers app/calc only)
uv run mypy --strict app/calc

# 4. Architecture boundary check
uv run lint-imports
```

> **Architecture Boundary Rule:** `app/calc/` must **NEVER** import from `app/ai/`. This is enforced automatically by `lint-imports` via `backend/.importlinter`.
