---
type: decision
status: active
date: 2026-03-31
agent_author: "codex"
tags: [portfolio, database, postgres, psycopg2, orm]
related_files:
  - tradingagents/portfolio/supabase_client.py
  - tradingagents/portfolio/repository.py
  - tradingagents/portfolio/migrations/001_initial_schema.sql
---

## Context

The current portfolio implementation persists transactional state in a Supabase-hosted PostgreSQL database, but it does so through a direct PostgreSQL connection string and `psycopg2`, not through `supabase-py` or an ORM.

This ADR records the implementation reality and the intended rule going forward.

## The Decision

Use direct PostgreSQL access via `psycopg2` for the portfolio data layer, without adding an ORM.

The layering is:

- `SupabaseClient` for low-level CRUD
- `PortfolioRepository` for business logic
- plain SQL migrations in `tradingagents/portfolio/migrations/`
- dataclass-style models in `tradingagents/portfolio/models.py`

## Why

1. The schema is still small and straightforward.
2. Direct SQL gives explicit control over inserts, updates, upserts, and snapshots.
3. The project stays Python-only and avoids ORM code-generation or extra runtime dependencies.
4. The business-logic boundary already exists in `PortfolioRepository`, so an ORM would add complexity without solving a real problem today.

## Constraints

- Do not add an ORM to the portfolio layer without revisiting this decision.
- Keep transactional database access behind `SupabaseClient` and `PortfolioRepository`.
- Keep schema evolution in SQL migrations.

## Actionable Rules

- Use `SUPABASE_CONNECTION_STRING` for portfolio DB access.
- Prefer explicit SQL and typed model conversion over ORM abstractions.
- Keep portfolio business logic in `PortfolioRepository`, not in API handlers or graph nodes.
