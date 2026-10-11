# ADR 0007: Monorepo Repository Structure

## Status
Accepted

## Context
The Kundali system comprises a Python calculation and API backend, a Next.js web frontend, astronomical regression fixtures, architecture specifications, and operational utility scripts.

## Decision
Organize the project as a single monorepo with distinct top-level directories:
* `backend/`: Python application (`app/calc`, stubs for `app/ai`, `app/db`, `app/api`), dependencies, and test suite.
* `frontend/`: Next.js App Router application with TypeScript and Tailwind CSS.
* `docs/`: Architecture specifications, ADRs, database setup guides, and project plan.
* `fixtures/`: Public synthetic golden-master fixtures and private reference charts.
* `scripts/`: Developer utility scripts for environment setup, ephemeris download, and calculation CLI.

## Consequences
* Shared version control facilitates synchronized changes across calculation contracts, fixtures, and documentation.
* Tools and scripts remain unified in a single repository without cross-repository submodule complexity.
