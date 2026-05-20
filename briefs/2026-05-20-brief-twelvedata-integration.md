---
date: 2026-05-20
tags: [brief, pricing, data-source, twelve-data]
---

# Brief: Twelve Data API Integration

**Date:** 2026-05-20
**Status:** Open
**Source:** User signal — Twelve Data free tier (800 calls/day, 8 credits/min)

---

## Objective

Integrate Twelve Data as a reliable US equity pricing source, replacing yfinance subprocess spawning for day-to-day price lookups. The free tier covers real-time US stocks, forex, and crypto with batch pricing and server-side technical indicators.

---

## Why Bother

| Problem with current setup | Twelve Data fix |
|---|---|
| yfinance is screen-scraping — inconsistent availability, rate limits, no SLA | Official API with documented endpoints and credit system |
| Python subprocess per ticker (N processes for N tickers) | Batch endpoint: 1 API call for N symbols, 1 credit consumed |
| Technical indicators computed ad-hoc in Python | 100+ indicators server-side (SMA, EMA, RSI, MACD, etc.) |
| No type safety across Python→JSON→TypeScript boundary | Official SDKs (Python + Node.js) with typed responses |

---

## What the Free Tier Gets Us

| Capability | Included |
|------------|----------|
| Real-time US stock quotes | ✅ All US exchanges |
| Historical OHLCV (all intervals) | ✅ Full depth |
| Technical indicators (100+) | ✅ Computed server-side |
| Batch requests (1 call = N symbols = 1 credit) | ✅ |
| Forex (140 pairs) | ✅ Real-time |
| Crypto | ✅ Real-time |
| EU/UK/Asia stocks | ❌ Grow plan ($29/mo) |
| Fundamentals (P/E, EPS, balance sheet) | ❌ Grow plan ($29/mo) |
| WebSocket streaming | ❌ Pro plan ($99/mo) |

**800 calls/day at 1 credit per batch = effectively unlimited for our watchlist.** A batch of 30 tickers consumes 1 credit, not 30.

---

## Implementation Plan

### Phase 1 — Bun-Side Client

**New file:** `src/server/lib/twelvedata.ts`

```typescript
// Singleton client wrapping the Twelve Data REST API
// Key from env: TWELVEDATA_API_KEY

interface PriceResult {
  ticker: string
  price: number | null
  currency: string
  previousClose: number | null
  dayHigh: number | null
  dayLow: number | null
  volume: number | null
  timestamp: string
}

// Single-ticker price
async function getPrice(ticker: string): Promise<PriceResult | null>

// Batch prices — 1 API call for all tickers
async function getBatchPrices(tickers: string[]): Promise<Map<string, PriceResult>>

// Historical OHLCV for pattern features / Markov engine
async function getHistorical(ticker: string, days: number): Promise<OHLCV[]>
```

### Phase 2 — Update Prices Router

Replace yfinance subprocess for US tickers in `src/server/routes/prices.ts`. Keep yfinance fallback for non-US tickers (EU, UK, crypto) until we have a paid plan covering them.

### Phase 3 (Future) — Technical Indicators

Replace `stockstats_utils.py` with Twelve Data's server-side indicators when the Python trading pipeline needs indicator data.

---

## Files to Touch

| File | Action |
|------|--------|
| `src/server/lib/twelvedata.ts` | Create — typed client, ticker mapping, batch helpers |
| `src/server/routes/prices.ts` | Modify — route US tickers through Twelve Data |
| `.env.example` | Add `TWELVEDATA_API_KEY` placeholder |
| `package.json` | Opt: add `twelvedata` npm SDK if preferred over raw REST |

---

## Not in Scope

- Python trading pipeline (`tradingagents/`) — stays on yfinance for its own data
- Fundamentals enrichment — requires Grow plan ($29/mo), separate decision
- WebSocket streaming — requires Pro plan ($99/mo)
- Non-US equities — requires Grow plan

---

## Verification

```bash
# Single ticker
curl http://localhost:3000/api/prices/AAPL
# Expect: { ticker: "AAPL", price: 297.84, currency: "USD" }

# Batch
curl -X POST /api/prices/batch -d '{"tickers":["AAPL","MSFT","GOOGL"]}'
# Expect: single API call, all prices returned

# Fallback: non-US ticker routes to yfinance
curl http://localhost:3000/api/prices/VWCE.DE
# Expect 200 via yfinance subprocess (Twelve Data free tier = US only)
```

---

## Exit Criteria

- US equity prices served via Twelve Data API (no yfinance subprocess)
- Batch endpoint uses Twelve Data batch (1 API call, not N)
- Non-US tickers fall back to yfinance without errors
- `TWELVEDATA_API_KEY` absent: falls back silently to yfinance
- `just check` green

---

*Scottish Enlightenment Note: The free tier is a gift. Use it for what it covers (US pricing) and don't try to stretch it into fundamentals or international coverage. One data source, one job.*
