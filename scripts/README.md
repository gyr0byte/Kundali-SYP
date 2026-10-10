# Developer Scripts & Tools

This directory contains developer utilities and operational scripts for the Kundali project. All scripts strictly respect the environment constraints (no writes to the `C:` drive).

---

## Environment Setup

### `scripts/env.ps1`
PowerShell environment setup script. Dot-source this script at the beginning of each terminal session:
```powershell
. .\scripts\env.ps1
```
It redirects all tool caches, temporary directories, and package installations to `D:\DevCache`:
* `$env:UV_CACHE_DIR`, `$env:UV_TOOL_DIR`, `$env:PIP_CACHE_DIR`
* `$env:npm_config_cache`, `$env:npm_config_prefix`
* `$env:TEMP`, `$env:TMP`
* `$env:HF_HOME`, `$env:TORCH_HOME`, `$env:XDG_CACHE_HOME`

### `scripts/verify_env.ps1`
Validates that the current environment is correctly configured and confirms that no cache environment variables point to the `C:` drive:
```powershell
powershell -File .\scripts\verify_env.ps1
```

---

## Astronomical Calculation Tools

### `scripts/chart_cli.py`
Command-line interface to the calculation engine (`app.calc`). Computes high-precision sidereal planetary positions, whole-sign houses, nakshatras, and emits a validated `ChartFacts` document:
```powershell
. .\scripts\env.ps1
uv run --directory backend python ..\scripts\chart_cli.py --date 2000-01-01 --time 12:00:00 --lat 27.7172 --lon 85.3240 --tz Asia/Kathmandu
```

### `scripts/download_ephemeris.py`
Downloads Swiss Ephemeris compressed ephemeris files (`sepl_18.se1`, `semo_18.se1`, `seas_18.se1`) directly to `backend/ephe/` on `D:`. These files provide sub-arcsecond accuracy covering years 1800–2399 AD:
```powershell
. .\scripts\env.ps1
uv run --directory backend python ..\scripts\download_ephemeris.py
```

---

## Infrastructure Tools

### `scripts/check_db.py`
Quick sanity check for the PostgreSQL database connection string and required extensions (e.g., `pgvector`).
```powershell
. .\scripts\env.ps1
uv run --directory backend python ..\scripts\check_db.py
```
