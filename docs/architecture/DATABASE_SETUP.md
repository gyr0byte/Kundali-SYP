# Database Setup (Hosted PostgreSQL + pgvector)

Kundali uses a **hosted PostgreSQL** instance — no local Docker daemon is required or supported.

> **Implementation Status:** No database code is implemented or tested yet. All database models (`app/db/models/`), session management (`app/db/session.py`), and migrations (`migrations/`) in this repository are currently stubs. This document describes the planned production and local configuration.

---

## 1. Create a Hosted Postgres Project

Choose a hosted PostgreSQL provider:
* **Neon** (<https://neon.tech>) — PostgreSQL with native `pgvector` support.
* **Supabase** (<https://supabase.com>) — PostgreSQL with `pgvector` support.

Create a new project and copy the connection string.

---

## 2. Enable the pgvector Extension

In the hosted provider's SQL Editor, execute:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```
This enables vector embedding storage and similarity search for knowledge chunks.

---

## 3. Configure the Connection String

Set `DATABASE_URL` in your local `.env` file (never committed to git):
```env
DATABASE_URL=postgresql://user:password@host:5432/dbname?sslmode=require
```

> **Security Rule:** Hosted connections must always use `sslmode=require`.

---

## 4. Run Migrations (When Implemented)

Alembic migration commands (planned once models are implemented):
```bash
cd backend
alembic upgrade head
```

---

## 5. Development Data Guidelines

* Use only **synthetic fixtures or fake birth data** during development.
* Never enter or store real personal birth data in development or test environments.
* Reference chart test fixtures are located in `fixtures/charts/`.
