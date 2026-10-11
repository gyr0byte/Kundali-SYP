# Developer Scripts & Tools

This directory contains operational scripts and developer utilities for the Kundali project. All scripts comply with environment isolation rules (no writes to the `C:` drive).

---

## Scripts Inventory

| Script | Purpose | Network Access | Status |
| :--- | :--- | :--- | :--- |
| `scripts/chart_cli.py` | Command-line tool to calculate sidereal positions, houses, and nakshatras from birth input using `app.calc`. | No | implemented, manual, not covered by tests |
| `scripts/check_db.py` | Database connectivity and pgvector check script. Never prints connection strings or passwords. | Yes (to hosted DB) | implemented, manual, not covered by tests; never run against a real database |
| `scripts/download_ephemeris.py` | Downloads Swiss Ephemeris .se1 data files from the official repository into `backend/ephe/`. | Yes (downloads from GitHub) | implemented, manual, not covered by tests |
| `scripts/env.ps1` | PowerShell environment script redirecting all tool, package, and temp caches to `D:\DevCache`. | No | implemented, manual, not covered by tests |
| `scripts/verify_env.ps1` | Environment diagnostics script verifying that all cache environment variables point to `D:\DevCache` and none point to `C:`. | No | implemented, manual, not covered by tests |

---

## Usage Instructions

### Environment Configuration
At the start of every PowerShell terminal session, dot-source `scripts/env.ps1`:
```powershell
. .\scripts\env.ps1
```
Verify the active configuration:
```powershell
powershell -File .\scripts\verify_env.ps1
```

### Chart Calculation CLI
Run the calculation engine against sample birth data:
```powershell
. .\scripts\env.ps1
uv run --directory backend python ..\scripts\chart_cli.py --date 2000-01-01 --time 12:00:00 --lat 27.7172 --lon 85.3240 --tz Asia/Kathmandu
```

### Ephemeris Data Download
To enable high-precision calculation, download the Swiss Ephemeris .se1 data files from the official repository to `backend/ephe/`:
```powershell
. .\scripts\env.ps1
uv run python scripts/download_ephemeris.py
```
*(Files in `backend/ephe/` are git-ignored).*

### Database Connectivity Check
```powershell
. .\scripts\env.ps1
uv run --directory backend python ..\scripts\check_db.py
```
*(Note: `check_db.py` is currently a stub and has never been run against a real database).*
