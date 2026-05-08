# Decision: DatabaseFactory Singleton for SQLite Access

**Date:** 2026-05-06
**Status:** Accepted

## Context

The initial dashboard used `new Database()` directly in route handlers. This caused three problems: WAL mode wasn't consistently enabled, multiple connections created locking contention under concurrent SSE streams, and connection lifecycle wasn't managed (no `PRAGMA optimize` on shutdown). The `check-database-usage.ts` gate was added to enforce the factory, but the factory itself needed a design decision.

## Decision

A `DatabaseFactory` singleton that enforces WAL mode, busy timeout, foreign keys, and synchronous pragmas on every connection. Called once at startup (`connect`), retrieved everywhere via `get()`, closed once at shutdown (`close` with `PRAGMA optimize`).

## Alternatives Considered

| Alternative | Why Rejected |
|-------------|-------------|
| `new Database()` in every route | WAL mode not guaranteed; multiple connections cause locking; no lifecycle management |
| Connection pool | Overkill for single-user dashboard; Bun's SQLite bindings are synchronous and fast enough |
| ORM (Drizzle, Prisma) | Adds dependency and build step; raw SQL is more transparent for a dashboard with ~10 queries |

## Consequences

**What became easier:**
- Consistent connection settings across all routes
- Graceful shutdown with WAL checkpoint and optimize
- Enforceable via `check-database-usage.ts` gate (122 files scanned, zero raw `Database()`)
- TEST_MODE switching (`portfolio.db` vs `test_portfolio.db`) handled in one place

**What became harder:**
- Every new file that needs a database must import `DatabaseFactory` — but the gate catches violations
- SQLite REAL columns return strings — `parseFloat()` must be called everywhere (convention, not enforced)
- No async queries — Bun's SQLite is synchronous, which is fine for a single-user dashboard but would block under concurrent load

**Constraints this imposes:**
- `new Database()` forbidden anywhere outside `src/server/lib/db.ts` (enforced by gate)
- `DatabaseFactory.connect()` must be called before any route handler runs
- `DatabaseFactory.close()` must be called on server shutdown
- All SQLite REAL column reads must call `parseFloat()` before arithmetic

## Related

- Debrief: `debriefs/debrief-session-2026-05-06-hygiene.md`
- Playbook: `playbooks/sqlite-playbook.md`
- Playbook: `playbooks/database-lifecycle-playbook.md`
- Script: `scripts/check-database-usage.ts`
