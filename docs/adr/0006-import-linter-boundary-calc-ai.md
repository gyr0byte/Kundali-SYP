# ADR 0006: Import-Linter Boundary Between Calculation and AI Layer

## Status
Accepted

## Context
A fundamental principle of the Kundali architecture is "Compute First, Interpret Second". The astronomical calculation engine (`backend/app/calc/`) produces pure, deterministic astronomical facts. It must never depend on, import from, or be influenced by the AI interpretation layer (`backend/app/ai/`).

## Decision
Enforce a static import contract using `import-linter` configured in `backend/.importlinter`:
```ini
[importlinter:contract:1]
name = Calculation engine must not import from AI layer
type = forbidden
source_modules = app.calc
forbidden_modules = app.ai
```
Run `lint-imports` as a required quality gate in testing and CI.

## Consequences
* The calculation engine remains completely independent, deterministic, and testable in isolation.
* Any accidental import from `app.ai` into `app.calc` fails the build immediately.
