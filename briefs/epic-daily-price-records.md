# Epic: Daily Price Records for All Holdings

**Date:** 2026-05-04
**Epic ID:** PRICES-001
**Status:** Open
**Stories:** PRICES-001-S01 through PRICES-001-S04

---

## Vision

The dashboard is a monitoring system, not a snapshot view. Every holding needs a continuous price record from the day it was opened so that:

- Sparklines are always populated from real data
- Stop/invalidation prices can be evaluated against current price
- Unrealised P&L can be tracked over time
- Gaps in data are detected and caught up automatically

Without daily records, the dashboard shows partial truth. With them, it's an instrument panel.

---

## Stories

### PRICES-001-S01 — Prices Table + Historical Backfill

**What:** Add a `prices` table to the schema and backfill all open positions with historical daily closes via `get_price.ts`.

**Schema:**
```sql
CREATE TABLE prices (
    ticker    TEXT    NOT NULL,
    date      TEXT    NOT NULL,  -- YYYY-MM-DD
    open      REAL,
    high      REAL,
    low       REAL,
    close     REAL    NOT NULL,
    volume    INTEGER,
    currency  TEXT    DEFAULT 'GBP',
    PRIMARY KEY (ticker, date)
);
```

**Acceptance:**
- `prices` table added to `schema.sql`
- `DatabaseFactory` used for all writes (no raw `new Database()`)
- On `just seed-db --positions`: backfill each position from `entry_date` → today
  using `get_price.ts` → parse `history[]` → upsert into `prices`
- Prices seeded for all open positions (degiero, ibkr, test platforms)
- Upsert logic (INSERT OR REPLACE) — safe to re-run
- Currency normalisation: all prices stored in GBP
- `get_price.ts` already returns `history[]` with dates — use that

**Estimate:** 0.5d

---

### PRICES-001-S02 — sync-prices.ts: Nightly Catch-Up + Gap Fill

**What:** Write `scripts/sync-prices.ts` that can (a) catch up today's prices for all open positions, (b) backfill a single ticker from its entry date, (c) detect and fill gaps.

**Acceptance:**
- `just sync-prices` — catch up all open positions to today
  - Query `SELECT DISTINCT ticker FROM positions WHERE status = 'open'`
  - For each: fetch latest price via `get_price.ts` → upsert into `prices`
  - Skip if price for today already exists (idempotent)
- `just sync-prices --ticker AAPL` — backfill one ticker from entry_date → today
- `just sync-prices --all` — full catch-up (for cron / manual reset)
- Gap detection: find date gaps > 1 day in `prices` for each ticker → fetch and fill
- Uses existing `get_price.ts` (Yahoo Finance API)
- Runs in < 10s for 20 tickers (sequential fetch, acceptable for cron)
- Exit code 0 on success, non-zero on critical failure

**Estimate:** 1d

---

### PRICES-001-S03 — Holdings View: Real-Data Sparklines + Stop Monitoring

**What:** Holdings view reads `prices` table for sparklines. Also shows current price vs `invalidation_price` as a stop status indicator inline.

**Acceptance:**
- Sparklines in holdings view source from `prices` table, not `get_price.ts`
- Spread 20 data points evenly across `entry_date` → today (not consecutive last 20 days)
- Sparkline renders even if holding is older than 20 days (shows what exists)
- Stop monitoring column per row:
  - Current price fetched from `prices` (latest close for ticker)
  - `invalidation_price` from exit plan YAML
  - Indicator: 🟢 safe (>20% above invalidation), 🟡 watch (5–20%), 🔴 danger (<5%)
- Row sorted by urgency (danger first)
- "No price data" fallback shows "—" not broken chart

**Estimate:** 1d

---

### PRICES-001-S04 — Price Freshness Indicator

**What:** Track when each ticker's price was last updated. Show a freshness badge in the holdings row. Flag stale data (>1 day old).

**Acceptance:**
- `prices` table stores `date` — derive freshness from `MAX(date) WHERE ticker = ?`
- Freshness badge: 🟢 < 1 day, 🟡 1–2 days, 🔴 > 2 days (no recent data)
- Badge shown per ticker in holdings row (small inline span)
- On `sync-prices`: also updates freshness implicitly (today's price = today)

**Estimate:** 0.25d

---

## Done

| Story | Status |
|---|---|
| S01 — prices table + historical backfill | 🔲 |
| S02 — sync-prices.ts catch-up + gap fill | 🔲 |
| S03 — holdings view real sparklines + stop monitoring | 🔲 |
| S04 — price freshness indicator | 🔲 |

---

## Exit Criteria

All 4 stories complete. Every open position has a continuous price record in `prices`. Holdings view sparklines are populated from real data. Stop status is visible inline. `just sync-prices` can be run as a nightly cron without manual intervention.

---

## Technical Notes

- `scripts/get_price.ts` — already fetches `history[]` with dates and closes from Yahoo Finance
  - `history` field is `Array<{date: string, close: number}>`
  - 20-day window is sufficient for initial backfill
- `server/lib/db.ts` — `DatabaseFactory` for all DB writes
- `just sync-prices` — can be wired to a cron or a server-side job
- `get_price.ts` uses Yahoo Finance `https://query1.finance.yahoo.com/v8/finance/chart/`
- All prices stored in GBP — currency conversion handled by `get_price.ts` response
- Schema updates go through `schema.sql` only — no ad-hoc migrations

---

## Dependencies

- `scripts/get_price.ts` — must work correctly with `history[]` output (✅ confirmed)
- `server/lib/db.ts` — `DatabaseFactory` singleton (✅ existing)
- `scripts/positions.ts` — exit plan loading, `invalidation_price` extraction (✅ existing)
- `server/routes/holdings.ts` — holdings view query (needs modification in S03)

---

## Stretch

- Daily cron via `just sync-prices` → server-side job
- Add `close_pct` to positions (unrealised P&L %)
- Alpha sparkline (holding return vs benchmark return)