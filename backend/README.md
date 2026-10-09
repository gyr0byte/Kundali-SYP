# Kundali Backend

Vedic astrology platform backend — FastAPI + Swiss Ephemeris + grounded RAG.

See `docs/Kundali_Project_Plan.md` for the full specification.

## Setup

```bash
# From this directory
uv venv .venv
uv sync --group dev
```

## Run

```bash
.venv/Scripts/uvicorn app.main:app --reload
```
