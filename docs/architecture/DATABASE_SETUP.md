# Database Setup (Hosted PostgreSQL + pgvector)

Kundali uses a **hosted PostgreSQL** instance — no local Docker required.

## 1. Create a Hosted Postgres Project

Choose one of:

- **Neon** (<https://neon.tech>) — free tier, pgvector built-in
- **Supabase** (<https://supabase.com>) — free tier, pgvector available

Sign up and create a new project. Note the connection string.

## 2. Enable pgvector

In the hosted provider's **SQL Editor**, run:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

This enables the `VECTOR` column type used for knowledge-chunk embeddings.

## 3. Configure the Connection String

Copy the connection string from your provider's dashboard. It will look like:

```
postgresql://user:password@host:5432/dbname?sslmode=require
```

Add it to your local `.env` file (never committed):

```env
DATABASE_URL=postgresql://user:password@host:5432/dbname?sslmode=require
```

> **Important:** Always use `sslmode=require` for hosted connections.

## 4. Run Migrations

```bash
cd backend
alembic upgrade head
```

## 5. Development Data

- Use only **fixture or fake birth data** during development.
- Never use real personal birth data in dev/test environments.
- Reference chart fixtures live in `fixtures/charts/`.

## Notes

- Column-level encryption for birth data is handled at the application level (Fernet via `cryptography`).
- The `knowledge_chunks` table uses an HNSW index on the `embedding` column for vector similarity search.
- See the project plan (Section 11) for the full data model.
