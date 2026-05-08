# Brief: Documentation & Quality Alignment

**Date:** 2026-05-08
**Status:** Open

---

## Context

Full documentation review (README, AGENTS.md, ARCHITECTURE.md, CHANGELOG, Justfile, pyproject.toml, schema.sql, playbooks, debriefs, handoff) completed 2026-05-08. The repo is in good shape overall but has documentation drift from the May 7 restructure (`server/` → `src/server/`, `cli/trading/` → `src/cli/`) and a few known gaps that are explicitly documented but unfixed.

---

## Task 1: Fix Documentation Path Drift from Restructure

**Objective:** Update all path references in documentation to reflect `src/server/` and `src/cli/` instead of `server/` and `cli/trading/`.

### What

- [ ] AGENTS.md — file map section: update all `server/` paths to `src/server/`
- [ ] AGENTS.md — file map section: update `cli/` path to `src/cli/`
- [ ] ARCHITECTURE.md — component map: update `server/` tree to `src/server/`
- [ ] README.md — project structure section: update `server/` and `scripts/` paths
- [ ] README.md — startup commands: `bun run server/index.tsx` → `bun run src/server/index.tsx`
- [ ] debriefs/plans/current.md — update path references if any
- [ ] debriefs/handoff-next-session.md — update path references
- [ ] package.json — verify `scripts.trading` entry (`src/cli/main.ts`)

### How to Verify

- [ ] Run `just check`
- [ ] `grep_files` for `server/index.tsx` and `server/lib` in .md files — zero results
- [ ] `grep_files` for `cli/trading` in .md files — zero results
- [ ] Manual: `cat AGENTS.md | grep "src/server"` shows correct paths

### Technical Notes

- The restructure commits (0fb04c4, fee21d7, 0030351, 7b876ac) moved files but didn't update docs.
- AGENTS.md line "bun run server/index.tsx" in the startup commands table must also change.
- `server/lib/schema.sql` → `src/server/lib/schema.sql`.

---

## Task 2: Wire TA_DASHBOARD_PORT Env Var

**Objective:** Fix the documented gap — `TA_DASHBOARD_PORT` is declared in docs and `.env` but `index.tsx` only reads `process.env.PORT`.

### What

- [ ] Read current port logic in `src/server/index.tsx`
- [ ] Add `TA_DASHBOARD_PORT` as the canonical env var, `PORT` as fallback
- [ ] Update ARCHITECTURE.md gap list — mark this as resolved

### How to Verify

- [ ] Run `just check`
- [ ] `TA_DASHBOARD_PORT=8080 bun run src/server/index.tsx` — server listens on 8080
- [ ] No `TA_DASHBOARD_PORT` set, `PORT=9090` — server listens on 9090 (fallback)
- [ ] Neither set — defaults to 3000

### Technical Notes

- Current code likely uses `process.env.PORT || 3000`. Change to `process.env.TA_DASHBOARD_PORT || process.env.PORT || 3000`.
- The `server-lifecycle.ts` script may also need to know about this env var.

---

## Task 3: Decompose td-56fd1b Hygiene Epic

**Objective:** Break the catch-all "Codebase hygiene epic" into concrete, completable child tasks.

### What

- [ ] Read `td-56fd1b` to understand current scope
- [ ] Create child TDs for each concrete hygiene item:
  - Path-reference cleanup (may be covered by Task 1 above)
  - Dead file removal (`playbooks/htmx-playbook.md.backup`)
  - Unused datatype.tsx — wire or remove
  - Types consolidation (already tracked as `td-984925`)
  - Any other stragglers found during review
- [ ] Link child TDs to parent epic via `td ws tag`
- [ ] Update `td-56fd1b` description to list children

### How to Verify

- [ ] `td list` shows each child task linked to `td-56fd1b`
- [ ] Each child has a clear acceptance criterion
- [ ] No "catch-all" language remains in the epic description

### Technical Notes

- Check if `htmx-playbook.md.backup` has any content not in `htmx-playbook.md` before deleting.
- `datatype.tsx` — if the inline approach is simpler and working, remove the unused helper. If the helper was created for a reason that's still valid, wire it.

---

## Task 4: Implement Prices Route

**Objective:** Replace the stub `/api/prices/:ticker` route with a working implementation that queries the prices table.

### What

- [ ] Read current stub in routes (likely `src/server/routes/prices.ts` or inline in `index.tsx`)
- [ ] Query `prices` table for the given ticker, returning latest close + currency + gbp_rate
- [ ] Return JSON: `{ ticker, price, currency, gbp_rate, date }`
- [ ] Handle missing ticker with 404 + error/hint structure
- [ ] Update ARCHITECTURE.md gap list — mark as resolved

### How to Verify

- [ ] Run `just check`
- [ ] `curl http://localhost:3000/api/prices/AAPL` returns valid JSON
- [ ] `curl http://localhost:3000/api/prices/ZZZZZ` returns 404 with error/hint
- [ ] Price data matches `sqlite3 portfolio.db "SELECT * FROM prices WHERE ticker='AAPL' ORDER BY date DESC LIMIT 1"`

### Technical Notes

- The `prices` table schema is in `src/server/lib/schema.sql`. Columns: ticker, date, open, high, low, close, volume, currency, gbp_rate.
- `sync-prices.ts` populates this table. The route just reads.
- Use `DatabaseFactory.get()` — never `new Database()`.

---

## Task 5: Minimal Server Test Suite (td-9dbbac)

**Objective:** Add automated Bun tests for route health and data shape validation.

### What

- [ ] Route health: GET each tab route returns 200
- [ ] Route health: GET each API route returns 200
- [ ] Positions query returns array with correct shape (ticker, quantity, avg_cost)
- [ ] hledger parser smoke test — parse a known balance output

### How to Verify

- [ ] Run `bun test` — all tests pass
- [ ] Tests fail gracefully (no hanging) when server isn't running
- [ ] Test file in `tests/` directory (alongside existing `trade-calculator.test.ts`)

### Technical Notes

- Use `bun test` (already in use for trade calculator tests — see Justfile `test-trade-calc`).
- Server health tests need the server running. Consider `beforeAll` to start server on random port, `afterAll` to stop.
- hledger parse tests can run offline against a fixture string.

---

## Task 6: Add Analysis Error Boundary

**Objective:** Surface Python subprocess failures to the UI instead of silent SSE stream termination.

### What

- [ ] In `src/server/routes/analysis.ts` (or wherever SSE is managed), catch subprocess non-zero exits
- [ ] Emit an `error` SSE event with the actual stderr message
- [ ] Include hint text (e.g., "Check OPENROUTER_API_KEY" or "yfinance may be rate-limited")
- [ ] Update ARCHITECTURE.md gap list — mark as resolved

### How to Verify

- [ ] Run `just check`
- [ ] Trigger a deliberate failure (e.g., unset API key, invalid ticker) and confirm the UI shows a meaningful error, not a silent hang
- [ ] Error event follows the `{ event: "error", data: { message, hint } }` SSE schema from ARCHITECTURE.md

### Technical Notes

- ARCHITECTURE.md already defines the SSE error event shape: `{ event: "error"; data: { message: string; traceback?: string } }`. Extend with `hint` as per the project's API error convention.
- The subprocess is spawned by Bun — `child.on('exit', (code) => ...)` is the hook.

---

## Done

| Task | Status |
|------|--------|
| Task 1: Fix documentation path drift | ⬜ |
| Task 2: Wire TA_DASHBOARD_PORT | ⬜ |
| Task 3: Decompose td-56fd1b hygiene epic | ⬜ |
| Task 4: Implement prices route | ⬜ |
| Task 5: Minimal server test suite | ⬜ |
| Task 6: Add analysis error boundary | ⬜ |

## Priority Order

1. **Task 1** (path drift) — blocks agent effectiveness, mechanical, estimated 0.25d
2. **Task 2** (TA_DASHBOARD_PORT) — two lines, documented gap, estimated 0.1d
3. **Task 3** (hygiene decomposition) — unlocks remaining cleanup, estimated 0.25d
4. **Task 4** (prices route) — functional gap in the dashboard, estimated 0.5d
5. **Task 6** (error boundary) — UX gap for the main analysis feature, estimated 0.25d
6. **Task 5** (server tests) — quality investment, estimated 1d
