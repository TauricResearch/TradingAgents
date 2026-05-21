# Epic: Technical Indicator Scan Engine

**Date:** 2026-05-21
**Epic ID:** SCAN-001
**Status:** Open
**Stories:** SCAN-001-S01 through SCAN-001-S04

---

## Vision

Replace ad-hoc signal interpretation with a structured, reproducible scan engine. The system evaluates six entry gates against SPY/QQQ/IWM (configurable) and reports BUY/NO-BUY/sell signals. All indicator logic lives in reusable TypeScript — no ad-hoc calculations, no business logic in the CLI layer. The result is a CLI tool you can run manually, a DB layer you can query, and a foundation for dashboard integration.

---

## Stories

### SCAN-001-S01 — Indicator Library

**What:** Pure TypeScript indicator functions in `src/server/lib/indicators.ts`. No I/O, no side effects — input arrays of OHLCV, output computed values.

**Functions required:**
| Function | Signature | Period |
|----------|-----------|--------|
| `rsi(prices: number[], period: number)` | → number | 14 |
| `bollingerBands(prices: number[], period: number, stdDev: number)` | → `{ lower: number, middle: number, upper: number }` | 20 |
| `sma(prices: number[], period: number)` | → number | configurable (MA20, MA150) |
| `adx(highs: number[], lows: number[], closes: number[], period: number)` | → number | 14 |
| `macd(prices: number[], fast: number, slow: number, signal: number)` | → `{ macd: number, signal: number, histogram: number }` | 12/26/9 |
| `volumeConfirmation(volumes: number[], lookback: number)` | → boolean (today's vol > 20-day avg) | 20 |

**Acceptance:**
- [ ] All functions are pure (no network, no DB)
- [ ] Unit tests for each function using known inputs (RSI=30 threshold, Bollinger floor calculation)
- [ ] Exported as named exports from `indicators.ts`
- [ ] Type definitions for all inputs/outputs (no `any`)
- [ ] `just check` passes (biome + tsc)

**Estimate:** 0.5d

---

### SCAN-001-S02 — Scan CLI Command

**What:** `trading scan [ticker...] [--relax=GATE] [--json] [--plain]` that reads price history from DB, computes all indicators, evaluates all 6 entry gates, evaluates 3 exit triggers, and reports signal.

**Entry gates (all must pass for BUY):**
| # | Gate | Condition | `--relax` flag |
|---|------|-----------|----------------|
| 1 | RSI oversold | RSI(14) < 30 | `--relax=rsi` |
| 2 | Bollinger support | price ≤ lower Bollinger band | `--relax=bollinger` |
| 3 | Uptrend | price > MA(20) | `--relax=ma20` |
| 4 | Trending | ADX(14) > 20 | `--relax=adx` |
| 5 | Momentum shift | MACD histogram > 0 | `--relax=macd` |
| 6 | Volume confirmation | volume > 20-day avg volume | `--relax=volume` |

**Additional filter (always enforced, not relaxable):**
- price > MA(150) — structural uptrend guard

**Exit triggers (any one fires = SELL):**
| Trigger | Condition |
|---------|-----------|
| RSI overbought | RSI(14) > 70 |
| Upper Bollinger hit | price ≥ upper Bollinger band |
| MACD death cross | MACD line crosses below signal line |

**Output format (plain):**
```
=== SCAN: SPY ===
Date: 2026-05-21  |  Price: 582.34

GATE 1 RSI < 30         ✓ 22.4 (pass)
GATE 2 Bollinger lower  ✓ 576.10 (pass)
GATE 3 MA20 > price     ✗ 583.12 (FAIL)
GATE 4 ADX > 20         ✓ 28.3 (pass)
GATE 5 MACD hist > 0    ✓ +0.42 (pass)
GATE 6 Volume confirm   ✓ 62M > 45M avg (pass)

150-day MA filter       ✓ 545.00 (pass)

Signal: NO-BUY (GATE 3 failed)
Exit triggers: CLEAR (no triggers firing)
```

**Acceptance:**
- [ ] Reads price history from `prices` table in DB (via `DatabaseFactory`)
- [ ] Requires at least 150 bars of history (for MA150)
- [ ] Each gate shows ✓/✗ with actual value and threshold
- [ ] `--relax` flags disable individual gates (pass regardless of condition)
- [ ] `--json` outputs machine-readable `{ticker, date, gates[], signal, exits[], price}` 
- [ ] `--plain` suppresses gum, uses plain ANSI (fallback when gum unavailable)
- [ ] Works without gum installed
- [ ] Default tickers: SPY, QQQ, IWM (when no args given)
- [ ] `just check` passes

**Estimate:** 1d

---

### SCAN-001-S03 — Schema Additions: Indicator Readings

**What:** Add `indicator_readings` table and `scan_history` table to `schema.sql`. Store the latest reading for each ticker and a log of scan runs.

**Schema:**
```sql
CREATE TABLE indicator_readings (
    ticker         TEXT NOT NULL,
    date           TEXT NOT NULL,
    price          REAL NOT NULL,
    rsi_14         REAL,
    bb_lower       REAL,
    bb_middle      REAL,
    bb_upper       REAL,
    ma_20          REAL,
    ma_150         REAL,
    adx_14         REAL,
    macd_line      REAL,
    macd_signal    REAL,
    macd_histogram REAL,
    volume         INTEGER,
    volume_20avg   REAL,
    created_at     TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (ticker, date)
);

CREATE TABLE scan_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker     TEXT NOT NULL,
    date       TEXT NOT NULL,
    gates_passed INTEGER NOT NULL,
    gates_total  INTEGER NOT NULL,
    signal     TEXT NOT NULL CHECK(signal IN ('buy','no_buy','sell')),
    exit_trigger TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_readings_ticker ON indicator_readings(ticker);
CREATE INDEX IF NOT EXISTS idx_scan_date ON scan_history(date);
```

**Acceptance:**
- [ ] `schema.sql` updated with both tables
- [ ] Scan CLI writes readings on each run (upsert)
- [ ] Scan CLI appends to `scan_history`
- [ ] `--no-store` flag skips DB writes (for quick checks)
- [ ] `just check` passes

**Estimate:** 0.5d

---

### SCAN-001-S04 — Dashboard Integration (Stretch)

**What:** Add `/scan` route that runs the scan engine and renders current signal status for SPY/QQQ/IWM as a server-rendered HTML card.

**Acceptance:**
- [ ] `GET /scan` renders signal cards for all three ETFs
- [ ] Each card shows: ticker, price, signal, gate status (✓/✗ per gate), exit status
- [ ] Uses Datatype font for signal values
- [ ] Refreshes on page load (no client-side JS required)
- [ ] Falls back gracefully if prices table has insufficient data

**Estimate:** 0.5d (stretch — not in epic scope until S01-S03 verified)

---

## Done

| Story | Status |
|---|---|
| S01 — indicator library | 🔲 |
| S02 — scan CLI command | 🔲 |
| S03 — schema additions | 🔲 |
| S04 — dashboard integration | 🔲 |

---

## Exit Criteria

All mandatory stories (S01–S03) complete. `trading scan SPY` runs against live DB data, shows all 6 gate evaluations with values, and reports signal. Indicator functions are independently testable. `just check` passes. Schema updated without breaking existing tables.

---

## Technical Notes

- **TypeScript only** — no Python for indicator computation. The Python tier handles LLM/AI; TypeScript handles math/CLI/dashboard.
- **Pure functions** — indicators.ts is intentionally free of async, DB access, and env reads. It is a library, not a command.
- **Relaxable gates** — each gate can be disabled independently. This lets you test with fewer conditions and re-enable as confidence grows.
- **150-day MA** — always enforced, not relaxable. It is the load-bearing filter.
- **Price source** — `prices` table, not live API. Sync prices first with `trading prices sync --ticker SPY`.

---

## Dependencies

- `src/server/lib/db.ts` — `DatabaseFactory` for all DB reads/writes
- `prices` table — must have ≥150 rows for tickers being scanned
- `just check` — must pass before commit

---

## ADR Decisions (capture during implementation)

- ADR-009: TypeScript-only indicator library (vs Python)
- ADR-010: Configurable gates with `--relax` flags (vs hardcoded strict mode)