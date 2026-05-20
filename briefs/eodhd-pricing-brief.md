# EODHD Integration Brief (Pricing + Beyond)

**Date:** 2026-05-19  
**Scope:** Replace/supplement yfinance pricing with the official EODHD Node.js/TypeScript SDK  
**Status:** Draft — awaiting approval

---

## Game-Changer: Official SDK vs. Python Subprocess

The user surfaced the **official EODHD `eodhd` npm package** — a first-party, MIT-licensed TypeScript client. This changes the architecture entirely:

| Approach | Before (brief v1) | After (brief v2) |
|----------|-------------------|------------------|
| **Pricing** | Spawn `scripts/py/get_price.py` → yfinance subprocess | Call `eodhd` SDK directly in Bun server |
| **Batch pricing** | Loop subprocess per ticker (N processes) | `client.usQuoteDelayed({ s: 'AAPL,MSFT,GOOG' })` — 1 call |
| **Type safety** | None (Python → JSON → parse) | Full TypeScript types (`RealTimeQuote`, `EodDataPoint`, etc.) |
| **Error handling** | Manual retry logic in Python script | Built-in: retry on 429/5xx, `EODHDRateLimitError`, structured errors |
| **Dependencies** | yfinance, stockstats (Python) | `eodhd` only (zero runtime deps) |
| **Node/Bun compat** | Requires venv + Python 3.13 | Native Bun, no subprocess |

**The Python subprocess layer for pricing is eliminated entirely.** The Bun server becomes the single integration point.

### SDK Capabilities (beyond pricing)

The SDK covers the full EODHD surface — future phases can expand without adding packages:

| Capability | Method | Notes |
|------------|--------|-------|
| Live price | `client.realTime('AAPL.US')` | 15-20min delayed (free tier), multi-ticker in one call |
| Batch US quotes | `client.usQuoteDelayed({ s: 'AAPL,MSFT,GOOG' })` | Built for exactly our batch endpoint |
| EOD historical | `client.eod()` | Replaces `get_YFin_data_online` |
| Fundamentals | `client.fundamentals()` | Replaces Alpha Vantage fundamentals |
| Insider transactions | `client.insiderTransactions()` | SEC Form 4, not available anywhere else currently |
| News | `client.news()` | Replaces `alpha_vantage_news` |
| Technical indicators | `client.technical()` | SMA, EMA, RSI, MACD, Bollinger, 15+ more — replaces `stockstats_utils` |
| Calendar/earnings | `client.calendar.earnings()` | Upcoming + historical |
| Screener | `client.screener()` | Financial filters (P/E, market cap, etc.) |
| Macro data | `client.macroIndicator()` | GDP, inflation, unemployment |
| ESG (InvestVerte) | `client.marketplace.investverte.esg()` | Future governance/ESG portfolio view |
| WebSocket (live) | `client.websocket()` | Real-time US trades, forex, crypto feeds |

---

## Problem Statement

Current pricing relies entirely on yfinance, which:
- Has rate limits (HTTP 429) that cause `YFRateLimitError`
- Has inconsistent availability for non-US tickers (crypto, EU stocks)
- Returns delayed data for non-premium users

EODHD offers a unified API across 70+ exchanges with higher reliability and a batch endpoint.

---

## Implementation Plan

### Phase 1 — Bun-Side EODHD Client

**New file:** `src/server/lib/eodhd.ts`

```typescript
import { EODHDClient, EODHDError, EODHDRateLimitError } from 'eodhd';

export interface PriceResult {
  ticker: string;
  price: number | null;
  currency: string;
  previousClose: number | null;
  dayHigh: number | null;
  dayLow: number | null;
  volume: number | null;
  history: { date: string; close: number }[];
  timestamp: string;
}

// Singleton client — reads EODHD_API_KEY from Skate via env
let _client: EODHDClient | null = null;

function client(): EODHDClient {
  if (!_client) {
    _client = new EODHDClient({
      apiToken: process.env.EODHD_API_KEY ?? process.env.EODHD_API_TOKEN,
      timeout: 15_000,
      maxRetries: 2,
    });
  }
  return _client;
}

/**
 * Map dashboard ticker format to EODHD SYMBOL.EXCHANGE format.
 * Covers: .DE → XFRA, .L → LSE, plain → US, crypto → CC, FX → FOREX
 */
export function toEodhdTicker(ticker: string): string {
  if (ticker.endsWith('=X')) return ticker.replace('=X', '.FOREX');
  if (ticker.endsWith('.DE')) return ticker.replace('.DE', '.XFRA');
  if (ticker.endsWith('.L')) return ticker.replace('.L', '.LSE');
  if (ticker.includes('-USD') || ticker.includes('-EUR')) return `${ticker}.CC`;
  // Plain US ticker
  return `${ticker}.US`;
}

/**
 * Fetch current price for a ticker via EODHD.
 * Falls back to yfinance subprocess on EODHD failure.
 */
export async function getPriceEodhd(
  ticker: string,
  fallbackFn: () => Promise<PriceResult | null>,
): Promise<PriceResult | null> {
  const symbol = toEodhdTicker(ticker);

  try {
    const quote = await client().realTime(symbol);
    return {
      ticker,
      price: quote.close ?? quote.last ?? null,
      currency: quote.currency ?? 'USD',
      previousClose: quote.previous_close ?? null,
      dayHigh: quote.high ?? null,
      dayLow: quote.low ?? null,
      volume: quote.volume ?? null,
      history: [],
      timestamp: new Date().toISOString(),
    };
  } catch (err) {
    if (err instanceof EODHDRateLimitError) {
      console.warn(`EODHD rate-limited for ${ticker}, falling back`);
    } else {
      console.warn(`EODHD error for ${ticker}: ${err instanceof EODHDError ? err.message : err}`);
    }
    return fallbackFn();
  }
}

/**
 * Batch fetch US delayed quotes — single API call for multiple tickers.
 * Returns map of ticker → PriceResult.
 */
export async function getBatchPricesUs(tickers: string[]): Promise<Map<string, PriceResult>> {
  const symbols = tickers.map(toEodhdTicker).join(',');
  const quotes = await client().usQuoteDelayed({ s: symbols });
  const map = new Map<string, PriceResult>();
  for (const quote of quotes) {
    map.set(quote.code ?? '', {
      ticker: quote.code ?? '',
      price: quote.close ?? null,
      currency: quote.currency ?? 'USD',
      previousClose: quote.previous_close ?? null,
      dayHigh: quote.high ?? null,
      dayLow: quote.low ?? null,
      volume: quote.volume ?? null,
      history: [],
      timestamp: new Date().toISOString(),
    });
  }
  return map;
}
```

### Phase 2 — Update Prices Router

**File:** `src/server/routes/prices.ts` — replace subprocess spawning with direct EODHD calls:

- Import `getPriceEodhd` from `src/server/lib/eodhd.ts`
- Import `runPython` fallback only for non-EODHD tickers (EU/UK/crypto not in US delayed quotes)
- For batch: use `getBatchPricesUs()` for US tickers, subprocess fallback for others

### Phase 3 — Retain yfinance Subprocess for Non-EODHD Tickers

The `scripts/py/get_price.py` stays for:
- Crypto (`.CC`)
- EU stocks (`.XFRA`)
- UK stocks (`.LSE`)
- FX (`.FOREX`)

The EODHD US delayed quotes (`usQuoteDelayed`) only covers US equities. EU/UK/crypto still route through yfinance subprocess — but this is the minority of tickers.

### Phase 4 (Future) — EODHD for Historical + Fundamentals

Once pricing is stable, a second brief covers:
- `client.eod()` → replaces `get_YFin_data_online` in `tradingagents/dataflows/y_finance.py`
- `client.fundamentals()` → supplements `alpha_vantage_fundamentals.py`
- `client.insiderTransactions()` → new signal source, not currently available
- `client.technical()` → 15+ indicators, can replace or supplement `stockstats_utils.py`

---

## Files to Create/Modify

| File | Action | Notes |
|------|--------|-------|
| `package.json` | Modify | Add `"eodhd": "^1.0.0"` |
| `src/server/lib/eodhd.ts` | Create | Typed EODHD client, ticker mapping, fallback helpers |
| `src/server/routes/prices.ts` | Modify | Replace subprocess spawning with EODHD client calls |
| `src/server/lib/subprocess.ts` | No change | `venvPython()` stays for crypto/EU/UK fallback |
| `scripts/py/get_price.py` | No change | Stays as fallback for non-US tickers |
| `.env.example` | Modify | Add `EODHD_API_TOKEN` placeholder |
| `playbooks/conventions-playbook.md` | Update | Document EODHD integration pattern |

---

## Environment Variables

```bash
# EODHD_API_KEY — stored in Skate secrets manager
# Fallback chain in client init: EODHD_API_KEY → EODHD_API_TOKEN
# Both keys present: EODHD_API_KEY takes priority
EODHD_API_KEY=<from Skate>
```

**Skate key:** `EODHD_API_KEY`

The `EODHDClient` is initialized with `apiToken: process.env.EODHD_API_KEY ?? process.env.EODHD_API_TOKEN` to handle the Skate-sourced key without requiring env aliasing.

---

## Testing Plan

### Unit Tests (TypeScript)

```typescript
// Test ticker mapping
import { toEodhdTicker } from './lib/eodhd';
assert.equal(toEodhdTicker('AAPL'), 'AAPL.US');
assert.equal(toEodhdTicker('VWCE.DE'), 'VWCE.XFRA');
assert.equal(toEodhdTicker('BTC-USD'), 'BTC-USD.CC');
assert.equal(toEodhdTicker('GBPEUR=X'), 'GBPEUR.FOREX');
console.log('Ticker mapping OK');
```

### Integration Tests

```bash
# Install eodhd
bun add eodhd

# Manual verification (requires EODHD_API_TOKEN or uses demo automatically)
curl http://localhost:3000/api/prices/AAPL
# Expect: { ticker: "AAPL", price: <number>, currency: "USD", ... }

# EU ticker (falls back to yfinance subprocess — EODHD US quotes only)
curl http://localhost:3000/api/prices/VWCE.DE

# Crypto (falls back to yfinance subprocess)
curl http://localhost:3000/api/prices/BTC-USD
```

### Fallback Tests

```bash
# With no EODHD_API_TOKEN, should fall back to yfinance via subprocess silently
unset EODHD_API_TOKEN
curl http://localhost:3000/api/prices/AAPL
# Expect 200 with price data, not 500

# With invalid token, EODHD throws → falls back to subprocess
# (EODHDError is non-retryable for auth errors, but 429/5xx would retry)
```

### Batch Load Test

```bash
# US batch uses EODHD's single usQuoteDelayed() call
curl -X POST http://localhost:3000/api/prices/batch \
  -H "Content-Type: application/json" \
  -d '{"tickers": ["AAPL","MSFT","GOOGL"]}'
# Expect <500ms (single API call)

# Mixed batch: US tickers via EODHD, EU/crypto via subprocess (parallel)
curl -X POST http://localhost:3000/api/prices/batch \
  -H "Content-Type: application/json" \
  -d '{"tickers": ["AAPL","MSFT","VWCE.DE","BTC-USD"]}'
```

---

## Success Criteria

1. [ ] `GET /api/prices/AAPL` returns price via EODHD SDK (no subprocess)
2. [ ] `POST /api/prices/batch` with US tickers uses `usQuoteDelayed()` — single API call
3. [ ] EU/UK/crypto tickers fall back to yfinance subprocess without errors
4. [ ] `EODHD_API_TOKEN` absent: falls back silently, no 500s
5. [ ] `just check` passes (biome + tsc)
6. [ ] No new error logs in dashboard when EODHD is unavailable

---

## Risks & Mitigations

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| EODHD demo key limited to 6 tickers | High | Test with known tickers (AAPL, TSLA, VTI, AMZN, BTC-USD, EURUSD.FOREX) only; full key required for CI |
| `usQuoteDelayed` only covers US tickers | High | EU/UK/crypto continue via yfinance subprocess; map covers known cases |
| EODHD latency > yfinance for US stocks | Medium | SDK built-in retry handles transient latency; benchmark post-merge |
| SDK requires Node.js >= 20 (Bun is fine) | Low | Bun is >= 20; no issue |
| Rate limit errors in CI | Medium | SDK handles with backoff; set `maxRetries: 2` |
| TypeScript types from SDK mismatch actual API | Low | SDK is v1.0.1, uses strict TypeScript; verify with smoke test |
| Token exposed in logs | Low | EODHD SDK reads from env, doesn't echo it; no change to logging |

## SDK Verification Checklist (pre-merge)

- [ ] `bun add eodhd` succeeds
- [ ] `import { EODHDClient } from 'eodhd'` compiles
- [ ] `client().realTime('AAPL.US')` returns `RealTimeQuote` type
- [ ] `client().usQuoteDelayed({ s: 'AAPL,MSFT' })` returns array of quotes
- [ ] `EODHDError`, `EODHDRateLimitError` are catchable
- [ ] `EODHD_API_KEY` from Skate is aliased as `EODHD_API_TOKEN` and read by SDK
- [ ] Token from `EODHD_API_TOKEN` env var is used (no explicit arg needed)
- [ ] `toEodhdTicker()` handles all known ticker patterns

---

## Insights from "Momentum Trading App with Claude Code + EODHD" (Kevin Meneses, 2026-05-01)

The article demonstrates EODHD in a momentum screener context. Useful patterns for our project:

### Exchange Code Corrections (from article)

The article uses raw REST endpoints with plain exchange names (`"US"`, `"LSE"`, `"XETRA"`, `"TSX"`). The SDK uses a different format — verify these mappings:

| Raw REST (article) | SDK format (needs confirmation) | Notes |
|--------------------|--------------------------------|-------|
| `GET /api/eod/AAPL.US` | `client.eod('AAPL.US')` | ✓ SDK uses SYMBOL.EXCHANGE |
| `"LSE"` (London Stock Exchange) | `.LSE` or `.UK`? | Article uses `"LSE"` raw |
| `"XETRA"` (Germany) | `.XFRA` (Frankfurt) | Article uses `"XETRA"` raw |
| `"TSX"` (Toronto) | `.TSX`? | Needs verification |

**Action:** Confirm `.L`, `.DE` → `.LSE` / `.XETRA` mapping is correct. Run `client.exchanges.list()` to enumerate supported codes before Phase 1 closes.

### Momentum Signals (Phase 2 Candidate)

The article's strategy — **SMA 20/50 crossover** + **Rate of Change (ROC-10)** — is a concrete signal model our market analyst could adopt:

```
BUY:  SMA_20 > SMA_50  AND  ROC_10 > +5%
SELL: SMA_20 < SMA_50  AND  ROC_10 < -5%
HOLD: everything else
```

**Opportunity:** `client.screener()` with financial filters (P/E, market cap) + `client.eod()` for price history could power a momentum-ranked watchlist — a step toward the "Prospects" pipeline becoming signal-driven.

**Phase 2 candidate:** Add momentum scoring to `src/server/routes/prospects.ts` — pull historical EOD via `client.eod()`, compute SMA + ROC server-side, sort prospects by momentum score.

### Historical Data for Backtesting

The article fetches 6 months of daily data per ticker via raw REST. The SDK equivalent:

```typescript
// 6-month EOD history for SMA/ROC calculation
const eod = await client.eod('AAPL.US', {
  from: (today - 180days).toISOString().split('T')[0],
  to: today.toISOString().split('T')[0],
  period: 'd',
  order: 'a',
});
// eod[0]: { date, open, high, low, close, adjusted_close, volume }
```

This replaces the Python `get_YFin_data_online` call in `tradingagents/dataflows/y_finance.py` — directly, without Python subprocess.

---

## Not in Scope (Phase 1)

This brief covers **pricing only via the Bun server SDK**:

- **Python package unchanged** — `tradingagents/` remains on yfinance + Alpha Vantage for now
- **Fundamentals** — `client.fundamentals()`, `client.insiderTransactions()` — separate brief (Phase 2)
- **Historical OHLCV for trading agents** — `client.eod()` — Phase 2 integration
- **Technical indicators** — `client.technical()` for 15+ indicators — Phase 2
- **Momentum signals** — Phase 2 candidate (SMA/ROC screener for Prospects pipeline)
- **WebSocket streaming** — `client.websocket()` — Phase 3 (real-time feeds)
- **Marketplace** (options, PRAAMS, ESG) — Phase 4 or later

**The Python bridge (`scripts/py/analyze_stream.py`) is untouched.** TradingAgents continues to use yfinance for its own analysis pipeline. Only the dashboard's price lookups move to EODHD.

---

*Scottish Enlightenment Note: The prudent agent integrates new data sources with fallback chains, not wholesale replacement. Let the market (in this case, latency and error rates) be the final arbiter.*