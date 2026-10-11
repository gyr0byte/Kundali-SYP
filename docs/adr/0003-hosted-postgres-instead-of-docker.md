# ADR 0003: Hosted PostgreSQL with pgvector Instead of Docker

## Status
Accepted

## Context
The project architecture requires PostgreSQL with the `pgvector` extension for storing knowledge embeddings and structured chart facts. However, Docker is not installed in the local environment and must not be used.

## Decision
Use a hosted PostgreSQL service (such as Neon or Supabase) that provides `pgvector` natively. No local Docker daemon is required or permitted.

## Consequences
* All database connections require TLS/SSL encryption (`sslmode=require`).
* No database instance runs locally; development and testing do not require a live database connection unless explicitly executing database-specific tests.
* The test suite and calculation engine remain fully operational and testable using local JSON fixtures without database connectivity.
* Currently, database models and migration files remain stubs; no live database connections are initiated during standard development or testing.
