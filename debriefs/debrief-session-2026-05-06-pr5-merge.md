# Debrief: PR #5 Forward-Port + Final HTML Builder Elimination + Merge to Main

**Date:** 2026-05-06
**Scope:** Forward-port PR #5 features into refactored JSX architecture; eliminate last HTML string builders; merge to main
**Outcome:** PR #7 merged. All HTML string builders eliminated. Zero residual JSX extractions. Branch deleted.

---

## What We Did

### 1. PR #5 Forward-Port (3 hours)

PR #5 (`feat: Portfolio Intelligence — accounts, allocation bar, cash breakdown, spread bets`) contained valuable features but was written against the old string-concatenation architecture. A direct merge would have been catastrophic (50+ conflict regions between old `.ts` string builders and our new `.tsx` JSX components).

**Decision:** Abort the 3-way merge. Cherry-pick ideas, rewrite into JSX architecture.

#### Schema additions
- `accounts` table (isa, shares, sipp, spreadbet, savings, cash)
- `account_id` FK on `positions`
- `spreadbet_positions` table (direction, stake, entry/stop/target, P&L)
- `account_balances` history table
- Corresponding indexes + DB migrations in `server/index.tsx` and `scripts/seed_database.ts`

#### Data layer expansion (`server/lib/portfolio-intel-data.ts`)
- Fetch accounts, spread bets, research queue (approved watchlist)
- Compute allocation bar (cash/deployed/spreadbet vs targets 10%/70%/20%)
- Compute cash breakdown (reserve, spreadbet alloc, investable)
- Account-level aggregation with hledger cash fusion
- Spread bet P&L with live prices + FX conversion

#### New JSX components (`server/views/portfolio-intel.tsx`)
- `AllocationBarSection` — target vs actual with colour bars
- `CashBreakdownPanel` — reserve, spreadbet alloc, investable cash
- `AccountsTable` — per-account cash/deployed/spreadbet totals
- `SpreadBetTable` — direction, stake, entry/current, P&L, notional
- `ResearchQueue` — approved-stage watchlist items

#### New route (`server/routes/portfolio-balance.ts`)
- POST `/api/portfolio/balance` — update account balance + history
- Uses UPDATE (not INSERT OR REPLACE) to preserve NOT NULL columns
- Returns 404 if account not found

#### Seed data (`scripts/seed_database.ts`)
- 7 accounts (IG ISA, Shares, Spread Bet, Aviva, AJ Bell, NS&I, Cash)
- 2 spread bet positions (AAPL short, BTC long)
- 4 account balance history entries
- New CLI flags: `--accounts`, `--spread-bets`, `--account-balances`

#### Infrastructure
- `scripts/py/get_price.py` (Python price fetcher)
- Unified all `get_price.py` references to `scripts/py/` path (9 files updated)

### 2. Final HTML Builder Eliminations (45 minutes)

#### `portfolio.ts` → `portfolio-data.ts` + `portfolio-summary.tsx`
- Extracted `computePortfolioSummary` + `batchFetchPrices` + types → `server/lib/portfolio-data.ts`
- Converted `buildPortfolioHtml` (~90 lines of string concatenation) → `PortfolioSummaryView` JSX component
- Route renamed `.ts` → `.tsx` (required for JSX in route handlers)
- Removed 228 lines of duplicated `findProjectRoot`, `PriceData`, `PositionEnriched`, `PortfolioSummary` interfaces

#### `analyses-db.ts` → `analysis-data.ts` + `analysis-report.tsx`
- Extracted `DbAnalysis` + `fmtDate` → `server/lib/analysis-data.ts`
- Converted `renderEventSection` (~80 lines) → `EventSection` JSX component (7 event types)
- Converted `buildAnalysisReportHtml` (~40 lines) → `AnalysisReportView` component
- Converted inline `/list/html` builder → `AnalysesListView` component
- Converted `/:id/card` wrapper → `AnalysisCardView` component
- Route renamed `.ts` → `.tsx`
- Removed 282 lines of string concatenation

### 3. Merge & Cleanup (15 minutes)

- Created PR #7 from branch `fix/portfolio-reset-and-seed-alignment`
- PR merged to `main`
- Branch deleted locally and remotely
- Verified `just check` passes on `main`

---

## Files Created This Session

**Data layers (2):**
- `server/lib/portfolio-data.ts`
- `server/lib/analysis-data.ts`

**JSX views (2):**
- `server/views/portfolio-summary.tsx`
- `server/views/analysis-report.tsx`

**Routes (2):**
- `server/routes/portfolio.tsx` (renamed from `.ts`)
- `server/routes/analyses-db.tsx` (renamed from `.ts`)
- `server/routes/portfolio-balance.ts` (new)

**Infrastructure (1):**
- `scripts/py/get_price.py`

**Schema (1):**
- `server/lib/schema.sql` — accounts, spreadbet_positions, account_balances tables + indexes

**Seed (1):**
- `scripts/seed_database.ts` — seedAccounts, seedSpreadBets, seedAccountBalances functions

**Plan updates (1):**
- `debriefs/plans/current.md`

## Files Removed This Session

- `server/routes/portfolio.ts` (390 lines → deleted)
- `server/routes/analyses-db.ts` (282 lines → deleted)

## Stats

- **Commits this session:** 6
- **New files:** 9
- **Files removed:** 2
- **Lines removed:** ~672 (string concatenation + duplication)
- **Lines added:** ~1,200 (typed JSX + data layers + new features)
- **Net:** Feature-richer, more maintainable codebase

---

## Decisions Made

### 1. Abort 3-way merge, forward-port instead

The merge base between our JSX-refactored branch and PR #5 had 9 conflict regions in `scripts/seed_database.ts` alone. Forward-porting the *ideas* (not the code) into our clean structure was faster and produced better code.

**Verdict:** Correct. Took ~3 hours total. A resolved merge would have taken 4+ hours and left us with hybrid string-concat/JSX mess.

### 2. PR #5 set to draft → closed as redundant

After forward-porting all features, PR #5 had no unique code left to merge. Closing it with an explanation prevented future confusion.

**Verdict:** Correct. Clean history, no dangling PRs.

### 3. UPDATE instead of INSERT OR REPLACE for balance updates

PR #5's original code used `INSERT OR REPLACE INTO accounts` which would wipe `provider`, `account_type`, `name`, `currency`, `notes` (all NOT NULL or valuable) on every balance update. Fixed to `SELECT ... WHERE id = ?` then `UPDATE`.

**Verdict:** Critical bugfix. The original PR would have destroyed account metadata on every balance update.

### 4. Index on `positions(account_id)` deferred to migration

Added `idx_positions_account` index in `server/index.tsx` migration rather than `schema.sql` (where it would fail on fresh DBs because `account_id` column doesn't exist yet in the CREATE TABLE). The migration runs after schema application.

**Verdict:** Correct. Fresh DBs need column before index.

---

## Lessons Learned

### 1. The forward-port heuristic

When a PR is written against old architecture that you've since refactored:
- If conflicts are <5 regions → resolve merge
- If conflicts are 5-15 regions → evaluate forward-port
- If conflicts are >15 regions → **always forward-port**

The decision threshold is not just conflict count but *semantic distance* between the old and new architecture. String-concat vs JSX is a chasm, not a gap.

### 2. Script path unification pays dividends immediately

PR #5 moved `get_price.py` from `scripts/` to `scripts/py/`. Our branch had 9 references to the old path. Updating all at once (not lazily) prevented a class of runtime "file not found" errors that would have surfaced only in production.

**Pattern:** When a script moves, update *all* references in a single commit, not piecemeal.

### 3. `scripts/seed_database.ts` is high-friction

The seed script had 1,300+ lines and mixed concerns (clearTable, seed functions, CLI parsing, price fetching). Adding 3 new seed functions required navigating a dense file. Future work: split into `scripts/seed/` directory with one file per domain.

### 4. DB migrations in `server/index.tsx` are a smell

The migration block in `index.tsx` is now 20+ lines. It runs on every server start. This is fine for dev but will slow startup in production. Consider:
- A proper migration tool (e.g. `bun migrate up`)
- Or at least extract migrations to `server/lib/migrations.ts`

### 5. The `PortfolioIntel` type is too large

The `PortfolioIntel` interface has 16 fields. This makes the view component props unwieldy and couples the data layer to the presentation layer. Future refactor: split into smaller view-specific types or use nested objects.

### 6. `.ts` → `.tsx` rename is still the #1 gotcha

Even after 10 routes, we still hit this: `portfolio.ts` and `analyses-db.ts` both needed renaming. The Biome error messages are actively misleading ("expected `>` but found `data`"). The fix is mechanical but easy to forget.

**Recommendation:** Add a pre-commit check that warns if `.ts` files contain JSX syntax (`<` followed by capital letter).

---

## Verification

| Endpoint | Status |
|----------|--------|
| `/api/portfolio/intelligence` | ✅ JSON with allocation_bar, cash_breakdown, accounts, spreadbets |
| `/api/portfolio/intelligence/html` | ✅ Renders allocation bar + accounts table + spread bets |
| `/api/portfolio/balance` (POST) | ✅ Updates balance + records history |
| `/api/portfolio/summary/html` | ✅ JSX-rendered portfolio summary + positions table |
| `/api/analyses/list/html` | ✅ JSX-rendered analyses table rows |
| `/api/analyses/:id/card` | ✅ JSX-rendered analysis card with back button |
| `bun run scripts/seed_database.ts --accounts --spread-bets --account-balances` | ✅ 7 accounts, 2 bets, 4 balances |
| `just check` | ✅ Biome + tsc pass |

---

## What's Next

From `debriefs/plans/current.md`:

1. **Codebase hygiene** (`td-56fd1b`) — split `portfolio.ts` is now done; remaining:
   - Types consolidation: `server/lib/types.ts` vs inline route interfaces
   - Settings extraction: `server/lib/settings.ts` duplication

2. **Price freshness badge** (`td-18e84e`) — per-ticker `last_updated` in holdings table

3. **Server tests** (`td-9dbbac`) — route health checks, positions query, hledger parsing

4. **Migration tooling** — extract ad-hoc ALTER TABLE blocks from `server/index.tsx`

5. **Seed script split** — `scripts/seed/` directory, one seed file per domain
