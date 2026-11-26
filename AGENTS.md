# Kundali — Agent Rules

## Current Status
- Core calculation engine (`app/calc`: timeconv, ayanamsha, ephemeris, houses, nakshatra, facts) is implemented with 40 tests.
- AI, database, API, background jobs, knowledge, and frontend layers remain stubs or scaffolding. Architectural decisions are documented in `docs/adr/`.

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
- Never create a real `.env` file or connect to any database.
- Never download ML models or LLMs (no Ollama pulls, no HuggingFace model downloads).
- Docker is not installed and must not be used.

## Git Workflow
- Meaningful local commits and remote pushes to the configured GitHub repository (`origin`, current working branch) are authorized after coherent, tested milestones.
- Use Conventional Commits (`feat:`, `fix:`, `ui:`, `refactor:`, `test:`, `docs:`, `chore:`) describing actual changes.
- Before committing and pushing: review modified files and `git diff`; run relevant tests, linting, and type checks; confirm no secrets, credentials, API keys, `.env` files, personal data, local caches, virtual environments, or build artifacts are included; stage only the files belonging to the milestone (never blind `git add .`); and verify remote, branch, and upstream.
- Never force-push, rewrite remote history, push to an unrelated branch, bypass failing checks, discard uncommitted user work, or run destructive resets/checkouts. If a push fails, report the exact reason without destructive recovery.

## Code Standards
- Python: formatted with ruff, type-checked with mypy, tested with pytest.
- TypeScript: Next.js App Router, strict mode, ESLint enabled.
- All stubs should remain stubs until implementation is planned.

## Frontend UI Standards
- Whenever working on frontend UI, design, layout, styling, localization, or browser verification, read:
  - `frontend/DESIGN.md` (canonical Observatory Timetable visual spec, skill hierarchy, and verification standard)
  - `PRODUCT.md` and `docs/Kundali_Project_Plan.md` (authoritative product boundaries and role scope)
  - `.impeccable/surfaces/` (relevant surface briefs, such as `.impeccable/surfaces/frontend-src-app-user-page-tsx.md`)
  - `frontend/AGENTS.md` and the installed Next.js 16 documentation under `frontend/node_modules/next/dist/docs/` before modifying App Router code.
