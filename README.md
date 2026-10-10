# Kundali 🪐 — Transparent Vedic Astrology

> *"Every number is computed. Every claim is cited. Every reading can be checked."*

**Kundali** is an open-source, full-stack Vedic astrology web application built on the principle of **Compute First, Interpret Second**. It features a deterministic, high-precision astronomical calculation engine paired with an AI interpretation engine that is strictly grounded in computed chart facts and a curated, human-reviewed knowledge base.

---

## 🌟 Architecture & Highlights

* **Pure Astronomical Engine (`backend/app/calc`):**
  * Powered by Swiss Ephemeris (`swisseph_ffi`), DE441 compressed ephemeris data, and whole-sign house geometry.
  * Completely isolated from the AI layer by import-linter architectural contracts (`backend/.importlinter`).
  * Thread-safe execution under module locks to prevent C-library global state leakage.
  * Configurable presets including standard `lahiri` (mean node) and `hamro_patro_compat` (`LAHIRI_1940` + true node).
* **Grounded AI Interpretation (`backend/app/ai`):**
  * Retrieval-Augmented Generation (RAG) strictly grounded in validated `ChartFacts` documents and cited classical texts.
* **Three Operational Panels:**
  * **User Panel:** Interactive North Indian diamond charts, planetary placements, Dasha timelines, transits, and grounded Q&A.
  * **Astrologer Panel:** Review queue for human astrologers to verify, annotate, and approve AI readings.
  * **Admin Panel:** Credentialing, engine telemetry, and calculation accuracy auditing.
* **Regional South Asian Localization:**
  * Bikram Sambat (BS) date conversion, Nepal Time (NPT, UTC+5:45), Nepali language localization, and traditional chart formatting.

---

## ⚠️ Environment & Cache Redirection (`D:\DevCache`)

To ensure isolation and prevent polluting system drives:
* **All caches, virtual environments, and temporary files live on `D:`** (specifically `D:\DevCache`).
* Before running any commands in a PowerShell session, **dot-source the environment setup script**:
  ```powershell
  . .\scripts\env.ps1
  ```
  This redirects:
  * Python/uv: `$env:UV_CACHE_DIR`, `$env:UV_TOOL_DIR`, `$env:PIP_CACHE_DIR`
  * Node/npm: `$env:npm_config_cache`, `$env:npm_config_prefix`
  * System temp: `$env:TEMP`, `$env:TMP`
  * ML/Frameworks: `$env:HF_HOME`, `$env:TORCH_HOME`, `$env:XDG_CACHE_HOME`

Verify your environment configuration anytime with:
```powershell
powershell -File .\scripts\verify_env.ps1
```

---

## 🚀 Setup & Installation

### 1. Prerequisites
* **Python 3.12+** with [`uv`](https://docs.astral.sh/uv/) installed.
* **Node.js 20+** and `npm`.
* Hosted **PostgreSQL 16+** with the `pgvector` extension.

### 2. Backend Setup
From the repository root:
```powershell
# 1. Load environment variables
. .\scripts\env.ps1

# 2. Install dependencies into virtual environment
cd backend
uv sync --group dev
```

### 3. Swiss Ephemeris Data Files Download
The calculation engine supports sub-arcsecond precision when Swiss Ephemeris `.se1` files (`sepl_18.se1`, `semo_18.se1`, `seas_18.se1`) are present in `backend/ephe/`.

To download the ephemeris files (kept on `D:` and git-ignored):
```powershell
. .\scripts\env.ps1
uv run python scripts/download_ephemeris.py
```
*(If ephemeris files are absent, the engine falls back to Moshier analytical mode and explicitly reports `"moshier"` provenance in metadata).*

### 4. Database Setup (Hosted PostgreSQL + pgvector)
Configure your database connection string in `.env` (using SSL):
```env
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/kundali?ssl=require
```

Apply database migrations using Alembic:
```powershell
. .\scripts\env.ps1
cd backend
uv run alembic upgrade head
```

Verify database connectivity:
```powershell
. .\scripts\env.ps1
uv run --directory backend python ..\scripts\check_db.py
```

### 5. Frontend Setup
```powershell
. .\scripts\env.ps1
cd frontend
npm install
npm run dev
```
The application will be available at `http://localhost:3000`.

### 6. Running Backend Development Server
```powershell
. .\scripts\env.ps1
cd backend
uv run uvicorn app.main:app --reload --port 8000
```
Interactive API docs are available at `http://localhost:8000/docs`.

---

## 🧪 Testing & Quality Assurance

All quality and test gates can be executed from the repository root:

```powershell
# 1. Load environment
. .\scripts\env.ps1

# 2. Run test suite (regression and unit tests)
uv run --directory backend pytest

# 3. Code formatting and linting
uv run --directory backend ruff check .

# 4. Strict type checking on calculation engine
uv run --directory backend mypy --strict app/calc

# 5. Architecture boundary enforcement (calc engine must not import from AI)
uv run --directory backend lint-imports
```

---

## 🛠️ Developer CLI
Calculate any birth chart directly from the command line:
```powershell
. .\scripts\env.ps1
uv run --directory backend python ..\scripts\chart_cli.py --date 2000-01-01 --time 12:00:00 --lat 27.7172 --lon 85.3240 --tz Asia/Kathmandu
```

---

## 📄 License

This project is licensed under the **GNU Affero General Public License v3.0** (GNU AGPL-3.0). See the [LICENSE](LICENSE) file for the full license text.
