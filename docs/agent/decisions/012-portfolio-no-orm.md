---
type: decision
status: active
date: 2026-03-20
agent_author: "claude"
tags: [portfolio, database, supabase, orm, prisma]
related_files:
  - tradingagents/portfolio/supabase_client.py
  - tradingagents/portfolio/repository.py
  - tradingagents/portfolio/migrations/001_initial_schema.sql
---

## Context

When designing the Portfolio Manager data layer (Phase 1), the question arose:
should we use an ORM (specifically **Prisma**) or keep the raw `supabase-py`
client that the scaffolding already plans to use?

The options considered were:

| Option | Description |
|--------|-------------|
| **Raw `supabase-py`** (chosen) | Direct Supabase PostgREST client, builder-pattern API |
| **Prisma Python** (`prisma-client-py`) | Code-generated type-safe ORM backed by Node.js |
| **SQLAlchemy** | Full ORM with Core + ORM layers, Alembic migrations |

## The Decision

**Use raw `supabase-py` without an ORM for the portfolio data layer.**

The data access layer (`supabase_client.py`) wraps the Supabase client directly.
Our own `Portfolio`, `Holding`, `Trade`, and `PortfolioSnapshot` dataclasses
provide the type-safety layer; serialisation is handled by `to_dict()` /
`from_dict()` on each model.

## Why Not Prisma

1. **Node.js runtime dependency** — `prisma-client-py` uses Prisma's Node.js
   engine at code-generation time.  This adds a non-Python runtime requirement
   to a Python-only project.

2. **Conflicts with Supabase's migration tooling** — the project already uses
   Supabase's SQL migration files (`migrations/001_initial_schema.sql`) and the
   Supabase dashboard for schema changes.  Prisma's `prisma migrate` maintains
   its own shadow database and migration state, creating two competing systems.

3. **Code generation build step** — every schema change requires running
   `prisma generate` before the Python code works.  This complicates CI, local
   setup, and agent-driven development.

4. **Overkill for 4 tables** — the portfolio schema has exactly 4 tables with
   straightforward CRUD.  Prisma's relationship traversal and complex query
   features offer no benefit here.

## Why Not SQLAlchemy

1. **Not using a local database** — the database is managed by Supabase (hosted
   PostgreSQL).  SQLAlchemy's connection-pooling and engine management are
   designed for direct database connections, which bypass Supabase's PostgREST
   API and Row Level Security.

2. **Extra dependency** — SQLAlchemy + Alembic would be significant new
   dependencies for a non-DB-heavy app.

## Why Raw `supabase-py` Is Sufficient

- `supabase-py` provides a clean builder-pattern API:
  `client.table("holdings").select("*").eq("portfolio_id", id).execute()`
- Our dataclasses already provide compile-time type safety and lossless
  serialisation; the client only handles transport.
- Migrations are plain SQL files — readable, versionable, Supabase-native.
- `SupabaseClient` is a thin singleton wrapper that translates HTTP errors into
  domain exceptions — this gives us the ORM-like error-handling benefit without
  the complexity.

## Constraints

- **Do not** add an ORM dependency (`prisma-client-py`, `sqlalchemy`, `tortoise-orm`)
  to `pyproject.toml` without revisiting this decision.
- **Do not** bypass `SupabaseClient` by importing `supabase` directly in other
  modules — always go through `PortfolioRepository`.
- If the schema grows beyond ~10 tables or requires complex multi-table joins,
  revisit this decision and consider SQLAlchemy Core (not the ORM layer) with
  direct `asyncpg` connections.

## Actionable Rules

- All DB access goes through `PortfolioRepository` → `SupabaseClient`.
- Migrations are `.sql` files in `tradingagents/portfolio/migrations/`, run via
  the Supabase SQL Editor or `supabase db push`.
- Type safety comes from dataclass `to_dict()` / `from_dict()` — not from a
  code-generated ORM schema.
