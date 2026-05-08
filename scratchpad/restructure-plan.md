# Restructure Plan: labs → scripts → src

## Current State

```
cli/                        # Python CLI (frozen)
  main.py
  trading/                  # TS CLI — imports ../../../server/lib/
    commands/
    lib/

server/                     # Hono dashboard
  index.tsx
  routes/
  views/
  static/
  lib/                      # ← shared modules imported by scripts/ and cli/trading/
    db.ts                   # DatabaseFactory — imported by 5 scripts + cli
    trade-calculator.ts     # calculateTradePlan — imported by scripts + cli
    types.ts                # likely shared
    markup.ts               # likely shared
    ...

scripts/                    # Support code
  lab/                      # Experiments
  lib/                      # Shared helpers
  seed_database.ts          # → ../server/lib/db.ts
  db-backup.ts            # → ../server/lib/db.ts
  trade-calculator.ts     # → ../server/lib/db.ts, trade-calculator.ts
  sync-prices.ts          # → ../server/lib/db.ts
  seed_real_portfolio.ts  # → ../server/lib/db.ts
  check-database-usage.ts # hardcodes "server/lib/db.ts"
  ...

src/                        # EMPTY — claimed as production root but unused
```

## Target State

```
cli/                        # Python CLI (frozen — leave alone)

src/                        # Production TS code (strict)
  server/                   # from server/
    index.tsx
    routes/
    views/
    static/
  cli/                      # from cli/trading/
    commands/
    lib/
  lib/                      # extracted shared modules (from server/lib/)
    db.ts
    trade-calculator.ts
    types.ts
    markup.ts
    ...

scripts/                    # Support code (loose)
  lab/                      # Experiments (loosest)
  lib/                      # Shared helpers
  *.ts                      # Standalone scripts (import from src/lib/)
```

## GitNexus Validation

`gitnexus context DatabaseFactory` confirms symbol exists at `server/lib/db.ts`.
Manual `grep` confirms ONLY TWO files in `server/lib/` have external dependents:

| Module | External Imports | Importers |
|--------|-----------------|-----------|
| `db.ts` | 8 | scripts/seed_database.ts, db-backup.ts, trade-calculator.ts, sync-prices.ts, seed_real_portfolio.ts, cli/trading/commands/plan.ts, tests/trade-calculator.test.ts, tests/trade-calculator-integration.test.ts |
| `trade-calculator.ts` | 4 | scripts/trade-calculator.ts, cli/trading/commands/plan.ts, tests/trade-calculator.test.ts, tests/trade-calculator-integration.test.ts |

All other `server/lib/*.ts` files are ONLY imported inside `server/`. Safe to move with the directory.

## Cross-Directory Couplings to Break

| Importer | Imported | Count |
|----------|----------|-------|
| `cli/trading/commands/plan.ts` | `../../../server/lib/db.ts` | 1 |
| `cli/trading/commands/plan.ts` | `../../../server/lib/trade-calculator.ts` | 1 |
| `scripts/seed_database.ts` | `../server/lib/db.ts` | 1 |
| `scripts/db-backup.ts` | `../server/lib/db.ts` | 1 |
| `scripts/trade-calculator.ts` | `../server/lib/db.ts` | 1 |
| `scripts/trade-calculator.ts` | `../server/lib/trade-calculator.ts` | 1 |
| `scripts/sync-prices.ts` | `../server/lib/db.ts` | 1 |
| `scripts/seed_real_portfolio.ts` | `../server/lib/db.ts` | 1 |
| `tests/trade-calculator.test.ts` | `../server/lib/trade-calculator.ts` | 1 |
| `tests/trade-calculator-integration.test.ts` | `../server/lib/db.ts` | 1 |
| `tests/trade-calculator-integration.test.ts` | `../server/lib/trade-calculator.ts` | 1 |
| `scripts/check-database-usage.ts` | hardcodes `"server/lib/db.ts"` | 1 |

## Phases

### Phase 0: Extract Shared Substrate (BREAK CROSS-DIRECTORY IMPORTS)

1. Identify ALL modules in `server/lib/` that are imported outside `server/`
   → VALIDATED: only `db.ts` (8 refs) and `trade-calculator.ts` (4 refs)
2. Create `src/lib/` (new shared production library)
3. Move `server/lib/db.ts` → `src/lib/db.ts`
4. Move `server/lib/trade-calculator.ts` → `src/lib/trade-calculator.ts`
5. Update imports inside `server/` (`./lib/db.ts` → `./../lib/db.ts` or `@/lib/db.ts`)
6. Update imports inside `scripts/` (`../server/lib/db.ts` → `../src/lib/db.ts`)
7. Update imports inside `cli/trading/` (`../../../server/lib/db.ts` → `../../../src/lib/db.ts`)
8. Update imports inside `tests/` (`../server/lib/db.ts` → `../src/lib/db.ts`)
9. Update `scripts/check-database-usage.ts` hardcoded path
10. Run `just check` — must pass
11. Verify: `grep -rn "server/lib" scripts/ cli/trading/ tests/` returns zero

### Phase 1: Move Production Directories

1. Move `server/` → `src/server/` (now self-contained)
2. Move `cli/trading/` → `src/cli/` (now self-contained)
3. Update `tsconfig.json` include: `src/**/*.ts`, `src/**/*.tsx`
4. Update `package.json` scripts entry point
5. Run `just check` — must pass

### Phase 2: Update Wiring

1. Update `justfile` paths (`server/index.tsx` → `src/server/index.tsx`)
2. Update `scripts/init-test-db.sh` schema path
3. Update `scripts/check-view-scripts.ts` serveStatic path
4. Update docs references
5. Run `just check` — must pass
6. Verify server starts and responds

## Startup Ritual (Before Any Work)

Bun makes GitNexus re-indexing fast enough to be routine. A stale knowledge graph is a barnacle — it misleads every query.

```bash
gitnexus analyze        # Full re-index (~10-30s for this repo)
just check              # Type check + lint + DB usage gate
```

Only after both pass do you touch code. This is the "clear graph, clear mind" rule.

## Checkpoint After Each Phase

| Phase | Gate | Check |
|-------|------|-------|
| 0 | Cross-directory imports eliminated | `grep -rn "server/lib" scripts/ cli/trading/ tests/` = 0 |
| 0 | Graph spot-check | `gitnexus context DatabaseFactory` finds symbol at new path |
| 1 | Directories moved | `ls src/server/index.tsx src/cli/main.ts` exists |
| 1 | Type check passes | `tsc --noEmit` |
| 1 | Graph spot-check | `gitnexus context calculateTradePlan` finds symbol in src/lib/ |
| 2 | Wiring updated | Server starts, health check passes |
| 2 | Graph spot-check | `gitnexus status` shows indexed files match new structure |

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Missed import | `grep -rn "server/lib"` gate before Phase 1 |
| tsconfig path break | `tsc --noEmit` gate after each phase |
| Justfile path break | `just check` gate after each phase |
| Server startup fail | Health check gate after Phase 2 |
