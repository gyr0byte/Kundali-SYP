# ADR 0003: Hosted PostgreSQL with pgvector Instead of Docker

## Status
Accepted

## Context
The project architecture requires PostgreSQL with the `pgvector` extension for storing knowledge embeddings and structured chart facts. However, Docker is not installed in the local environment and must not be used.

## Decision
Use a hosted PostgreSQL service (such as Neon or Supabase) that provides `pgvector` natively. No local Docker daemon is required or permitted.

## Consequences
* Hosted PostgreSQL requires certificate and hostname verification (`sslmode=verify-full`). The Windows workflow uses an explicit trusted PEM CA bundle on D: and a direct DNS endpoint.
* Managed PostgreSQL remains preferred. Native PostgreSQL is an alternative when it meets the same integration requirements. Applications run natively on Windows.
* Standard tests remain offline. Live PostgreSQL tests require an explicit opt-in and a separately identified disposable database.
* Alembic tracks pgvector enablement. The extension is intentionally retained on downgrade.
* The [database setup runbook](../architecture/DATABASE_SETUP.md) defines private configuration, target checks and live verification.
