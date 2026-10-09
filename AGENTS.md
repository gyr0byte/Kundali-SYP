# Kundali — Agent Rules

## Source of Truth
- The authoritative specification is `docs/Kundali_Project_Plan.md`.
- **Do not invent features outside that document.**

## Architecture Rules
- `backend/app/calc/` must **NEVER** import from `backend/app/ai/`.
  This is enforced by import-linter (see `backend/.importlinter`).
  The calculation engine is deterministic and independent of any AI component.

## Environment Rules
- **Never write to the C: drive.** All caches, tools, temp files, and project
  files live on D:. If unsure whether an operation writes to C:, stop and ask.
- Never install global packages (`npm -g`, `pip` outside the project venv).
- Never create a real `.env` file, connect to any database, or push to any remote.
- Never download ML models or LLMs (no Ollama pulls, no HuggingFace model downloads).
- Docker is not installed and must not be used.

## Code Standards
- Python: formatted with ruff, type-checked with mypy, tested with pytest.
- TypeScript: Next.js App Router, strict mode, ESLint enabled.
- All stubs should remain stubs until implementation is planned.
