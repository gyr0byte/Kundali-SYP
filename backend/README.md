# Kundali Backend

The backend provides the deterministic astronomical calculation engine for Kundali.

---

## Status

* **Implemented:**
  * Astronomical calculation pipeline (`app/calc`: `timeconv`, `ayanamsha`, `ephemeris`, `houses`, `nakshatra`, `facts`).
  * Core configuration and cryptographic security (`app/core`: `config`, `security`, `permissions`, `rate_limit`, `mailer`, `clock`, `dependencies`).
  * Authentication, user management, astrologer credentialing, and audit logging services (`app/services`).
  * Database ORM models (`app/db/models`: `User`, `AstrologerProfile`, `RefreshToken`, `PasswordResetToken`, `AuditLog`) and initial Alembic migration (`migrations/versions/0001_initial_auth_tables.py`).
  * API v1 routers (`app/api/v1`: `auth`, `admin`, `astrologer`) and FastAPI application entry point (`app/main.py`).
  * Covered by 161 automated tests (unit, regression, and integration).
* **Stubs:** Dasha (`dasha.py`), transits (`transits.py`), yogas (`yogas.py`), compatibility (`ashtakoota.py`), calendar conversion (`bikram_sambat.py`), AI interpretation layer (`app/ai/`), background jobs (`app/jobs/`), knowledge ingestion (`app/knowledge/`), and non-auth API routes (`charts.py`, `chat.py`, `milan.py`, `profiles.py`, `transits.py`) are currently stubs.

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
# 1. Run test suite (161 tests: unit, regression, integration)
uv run pytest

# 2. Linting and code style checks
uv run ruff check .
uv run ruff format --check .

# 3. Type checking (configured per module in pyproject.toml)
uv run mypy app/core app/calc app/db app/api app/services app/main.py

# 4. Architecture boundary checks
uv run lint-imports
```

> **Architecture Boundary Rules:**
> - `app.calc` must **NEVER** import from `app.ai`.
> - `app.calc` must **NEVER** import from `app.api`, `app.db`, or `app.core`.
> These boundaries are enforced automatically by `lint-imports` via `backend/.importlinter`.
