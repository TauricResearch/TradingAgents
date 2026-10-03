# Epic: Strategic Trade Calculator

**Date:** 2026-05-07
**Epic ID:** TRADE-CALC-001
**Status:** Open
**Priority:** P1
**Language:** TypeScript (Bun runtime)
**Location:** `server/lib/trade-calculator.ts`, `server/routes/trade-plan.ts`, `server/views/trade-plan.tsx`

---

## Objective

A pure-function trade calculator that converts historical price data into a complete bracket order plan: volatility-adjusted entry, technical profit targets, and a risk-managed stop loss based on institutional heuristics.

**Output format:** JSON (API) or HTML (dashboard) — both from the same core calculation.

---

## Calculation Documentation

### Minimum Inputs Required

| Input | Source | Default | Description |
|-------|--------|---------|-------------|
| `ticker` | User | — | Stock symbol (e.g., "AAPL") |
| `priceHistory` | `prices` table / `get_price.ts` | — | Array of `{date, open, high, low, close, volume}` |
| `accountBalance` | User / `settings.ts` | 50,000 | Total portfolio value in GBP |
| `riskPerTrade` | User / `settings.ts` | 0.02 (2%) | Max loss as fraction of account |
| `entryPrice` | User (optional) | — | Manual override; if omitted, uses last close |

### Calculated Outputs

| Output | Formula | Description |
|--------|---------|-------------|
| `atr14` | `mean(TR[0:14])` where `TR = max(high-low, abs(high-prev_close), abs(low-prev_close))` | 14-day Average True Range |
| `entry` | `entryPrice ?? priceHistory[-1].close` | Entry price (override or last close) |
| `stopLoss` | `entry - (2.0 × atr14)` | Initial stop: 2× ATR below entry |
| `target1` | `swingHigh + (swingHigh - swingLow) × 1.382` | 138.2% Fibonacci extension of AB move |
| `target2` | `max(swingHigh + (swingHigh - swingLow) × 1.618, entry + 2×(entry - stopLoss))` | 161.8% Fib extension OR 1:2 R/R minimum |
| `positionSize` | `(accountBalance × riskPerTrade) / (entry - stopLoss)` | Integer share count |
| `riskAmount` | `positionSize × (entry - stopLoss)` | Actual GBP at risk |
| `riskPercent` | `riskAmount / accountBalance` | Risk as % of account |
| `concentrationFlag` | `positionSize × entry > accountBalance × 0.05` | Warn if >5% of portfolio in one position |

### Swing Detection (AB Move)

**Minimum requirement:** 22 days of price history (for ATR validity and swing identification)

**Algorithm:**
1. Find Point A: lowest `low` in the last 22 days (swing low)
2. Find Point B: highest `high` between Point A and today (swing high)
3. Point C: current price (the retracement)
4. The "AB move" = `B - A`

**Edge case:** If no clear swing (trending strongly), use `B = max(high[0:22])` and `A = min(low[0:22])`.

---

## Platform Configuration

| Platform | Type | Tax Wrapper | Spread Bet | Notes |
|----------|------|-------------|------------|-------|
| AJBell | SIPP | Pension (25% tax-free at 55+) | ❌ | Personal pension. Tax relief on contributions. Stamp duty applies. Access restricted until 55. |
| Aviva | Company pension | Workplace pension | ❌ | Employer-matched contributions. Limited fund choice. May not allow direct equity. |
| IG | Personal | ISA available (£20k/year) | ✅ | No pension wrapper. Stocks, ETFs, spread betting. ISA for tax-free gains. CGT outside ISA. |
| NS&I | Cash savings | None | ❌ | Premium bonds. Not investments. Prize-based, no guaranteed return. Use as cash reserve only. |

**Critical rule:** Spread betting is IG-only. `--platform ajbell --mode spreadbet` should error.

## Architecture

```
server/lib/trade-calculator.ts    ← pure functions (ATR, Fib, sizing)
server/lib/platforms.ts           ← platform config + validation
server/routes/trade-plan.ts       ← thin route (fetch data → call calc → respond)
server/views/trade-plan.tsx       ← JSX bracket order view
scripts/trade-calculator.ts       ← CLI entry point (JSON stdout)
cli/trading/                      ← unified CLI (future — see epic UNIFIED-CLI)
tests/trade-calculator.test.ts    ← unit tests (known inputs → known outputs)
```

**No Python.** All data comes from:
- `prices` SQLite table (populated by `sync-prices.ts`)
- `get_price.ts` (Yahoo Finance via Bun fetch)
- User input via dashboard form or CLI flags

---

## Stories

### TRADE-CALC-001-S01: Core Calculator Module

**What:** Implement `server/lib/trade-calculator.ts` with pure functions:
- `calculateATR(bars, n=14)` — standard ATR
- `findSwingHighLow(bars)` — AB move detection
- `fibonacciExtension(a, b, ratios=[1.382, 1.618])`
- `calculateTradePlan(inputs)` — orchestrator returning `TradePlan`

**Acceptance:**
- All functions are pure (no side effects, no I/O)
- Unit tests pass with hand-verified examples (e.g., known ATR values from TradingView)
- Handles edge cases: insufficient history (<22 days), zero ATR, negative R/R

**Estimate:** 1d

---

### TRADE-CALC-001-S02: CLI Script

**What:** `scripts/trade-calculator.ts` for quick terminal use.

**Usage:**
```bash
bun scripts/trade-calculator.ts AAPL --account 50000 --risk 0.02
bun scripts/trade-calculator.ts TKA.DE --entry 45.50 --account 25000
```

**Acceptance:**
- Fetches price history from `prices` table or `get_price.ts`
- Outputs JSON to stdout
- Exit code 0 on success, 1 on error (with stderr message)

**Estimate:** 0.5d

---

### TRADE-CALC-001-S03: Dashboard Route and View

**What:** `server/routes/trade-plan.ts` + `server/views/trade-plan.tsx`

**Endpoints:**
- `GET /api/trade-plan/:ticker?account=50000&risk=0.02` → JSON `TradePlan`
- `GET /api/trade-plan/:ticker/html?account=50000&risk=0.02` → HTML bracket order

**View components:**
- Entry zone (±ATR band)
- Stop loss (red, with % and GBP distance)
- Target 1 (amber, 50% scale-out suggestion)
- Target 2 (green, full exit)
- Position size (shares + notional)
- Risk summary (X% of account, Y GBP)
- Concentration warning (if >5%)

**Acceptance:**
- Uses `pageOrPartial()` for HTMX + direct navigation
- Links from holdings view (each row gets a "Plan" button)
- Mobile-friendly layout

**Estimate:** 1d

---

### TRADE-CALC-001-S04: Settings Integration

**What:** Wire calculator defaults to `server/lib/settings.ts`

**Settings:**
- `defaultAccountBalance` — user's typical account size
- `defaultRiskPerTrade` — typically 0.01 or 0.02
- `concentrationLimit` — typically 0.05 (5%)

**Acceptance:**
- Route uses settings as defaults when params omitted
- CLI script reads settings on startup
- Settings editable via dashboard (future)

**Estimate:** 0.5d

---

## Exit Criteria

- S01: Calculator passes unit tests with known verified examples
- S02: CLI script runs end-to-end for any ticker in `prices` table
- S03: Dashboard renders bracket order with all fields
- S04: Defaults wired to settings, no hardcoded account sizes in routes

---

## Dependencies

- `server/lib/db.ts` — `DatabaseFactory` for price queries
- `scripts/get_price.ts` — fallback if `prices` table stale
- `server/lib/settings.ts` — default account/risk params
- `server/lib/markdown.ts` — if adding explanatory text to view

---

## Risks

- **Insufficient history:** New tickers or recently added positions may have <22 days. Fallback: use `get_price.ts` to backfill.
- **Zero ATR:** Flat stock (e.g., halted). Fallback: use `avg(high-low)` as proxy.
- **Currency mismatch:** `prices` table stores in GBP; account balance is GBP. No conversion needed unless holding foreign stocks.

---

## Stretch

- Add ` POST /api/trade-plan` — save plan to `trade_plans` table for audit
- Add hLedger integration — record planned vs executed trades
- Add portfolio heat map — sum of all `riskAmount` / `accountBalance`
