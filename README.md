# Kundali 🪐

**Transparent Vedic Astrology, Computed Then Interpreted**

> *Every number is computed. Every claim is cited. Every reading can be checked.*

Kundali is a full-stack web platform that generates astronomically computed Vedic
birth charts and provides AI-assisted interpretation grounded in the user's own
chart data and a curated, astrologer-verified knowledge base.

## Project Structure

```
kundali/
├── backend/       Python (FastAPI) — calculation engine, AI layer, API
├── frontend/      Next.js (App Router) — user, astrologer, admin panels
├── docs/          Architecture docs, ADRs, project plan
├── fixtures/      Reference charts and knowledge samples for testing
└── scripts/       Developer utilities
```

## Quick Start

See `docs/Kundali_Project_Plan.md` for the full specification.

```bash
# Load environment (PowerShell)
. .\scripts\env.ps1

# Backend
cd backend
uv venv .venv
uv sync --group dev
.venv\Scripts\uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

## License

Swiss Ephemeris: AGPL / commercial dual license (see pyswisseph docs).
