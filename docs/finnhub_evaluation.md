# Finnhub API Evaluation Report
## Fitness for TradingAgents Multi-Agent LLM Framework

**Date**: 2026-03-18
**Branch**: `feat/finnhub-evaluation`
**Status**: Evaluation only — no existing functionality modified

---

## Executive Summary

Finnhub is **not a drop-in replacement** for Alpha Vantage. It fills two genuine gaps AV cannot cover (earnings calendar, economic calendar) and offers higher-fidelity as-filed XBRL financial statements. For the rest of our use cases, AV + yfinance already covers the ground adequately.

**Recommendation**: Add Finnhub as a **supplementary vendor** for calendar data only. Keep AV for news sentiment and movers; keep yfinance as primary.

---

## 1. API Overview

| Feature | Finnhub Free Tier |
|---------|------------------|
| Rate limit | 60 calls/min |
| Daily limit | None (rate-limited only) |
| Data delay | 15-min delayed on free; real-time on paid |
| Python SDK | `finnhub-python` (pip install) — NOT used here (raw requests only) |
| Base URL | `https://finnhub.io/api/v1/` |
| Auth | `?token=<API_KEY>` query param |

---

## 2. Coverage Matrix vs Alpha Vantage

### Category 1: Core Stock Data

| Feature | Alpha Vantage | Finnhub | Winner |
|---------|--------------|---------|--------|
| Daily OHLCV | `TIME_SERIES_DAILY_ADJUSTED` | `/stock/candle?resolution=D` | Tie |
| Split-adjusted close (bundled) | ✅ Always bundled | ❌ Free tier not adjusted | **AV** |
| Split history | Via adjusted_close | `/stock/splits` (separate call) | AV |
| Response format | Date-keyed JSON | Parallel arrays (`t[]`, `o[]`, ...) | AV (more ergonomic) |

**Gap**: Finnhub free-tier candles are NOT split-adjusted. Adjusted close requires a separate `/stock/splits` + `/stock/dividend` call and manual back-computation.

---

### Category 2: Technical Indicators

| Indicator | Alpha Vantage | Finnhub |
|-----------|--------------|---------|
| SMA | `/SMA` endpoint | ❌ Not provided |
| EMA | `/EMA` endpoint | ❌ Not provided |
| MACD | `/MACD` endpoint | ❌ Not provided |
| RSI | `/RSI` endpoint | ❌ Not provided |
| BBANDS | `/BBANDS` endpoint | ❌ Not provided |
| ATR | `/ATR` endpoint | ❌ Not provided |

**Critical Gap**: Finnhub has a `/indicator` endpoint but it maps to the same indicator names — this was implemented in our integration layer to use it. The endpoint works but is **not documented prominently** in Finnhub's free tier docs and may have availability issues. Our `finnhub_indicators.py` module implements it with full fallback.

**Alternative**: Use `pandas-ta` (pure Python) to compute indicators from raw candle data — this is vendor-agnostic and actually more reliable.

---

### Category 3: Fundamentals

| Feature | Alpha Vantage | Finnhub |
|---------|--------------|---------|
| Company overview | `OVERVIEW` (40 fields, 1 call) | `/stock/profile2` + `/stock/metric` (2 calls) |
| Balance sheet | `BALANCE_SHEET` | `/financials?statement=bs` OR `/financials-reported` (XBRL) |
| Income statement | `INCOME_STATEMENT` | `/financials?statement=ic` |
| Cash flow | `CASH_FLOW` | `/financials?statement=cf` |
| As-filed XBRL data | ❌ Normalized only | ✅ `/financials-reported` |
| Earnings surprises | ❌ | ✅ `/stock/earnings` — beat/miss per quarter |
| Earnings quality score | ❌ | ✅ `/stock/earnings-quality-score` (paid) |
| Analyst target price | In `OVERVIEW` | In `/stock/metric` |

**Finnhub Advantage**: `/financials-reported` returns actual XBRL-tagged SEC filings — highest fidelity for compliance-grade fundamental analysis. AV only provides normalized/standardized statements.

**Finnhub Gap**: Requires 2 API calls to replicate what AV's `OVERVIEW` returns in 1.

---

### Category 4: News & Sentiment

| Feature | Alpha Vantage | Finnhub |
|---------|--------------|---------|
| Ticker news | `NEWS_SENTIMENT?tickers=X` | `/company-news?symbol=X&from=Y&to=Z` |
| Per-article NLP sentiment score | ✅ `ticker_sentiment_score` + `relevance_score` | ❌ Free tier: aggregate buzz only |
| Macro topic news | `economy_macro`, `economy_monetary` | ❌ Only: general, forex, crypto, merger |
| Aggregate sentiment | — | `/news-sentiment` (buzz metrics) |
| Social sentiment (Reddit/X) | ❌ | `/stock/social-sentiment` (paid) |
| Insider transactions | `INSIDER_TRANSACTIONS` | `/stock/insider-transactions` |
| Insider sentiment (MSPR) | ❌ | `/stock/insider-sentiment` (free) |

**Critical Gap**: AV's per-article `ticker_sentiment_score` with `relevance_score` weighting is a genuine differentiator. Our `news_analyst.py` and `social_media_analyst.py` agents consume these scores directly. Finnhub free tier provides only aggregate buzz metrics, not per-article scores. **Replacing AV news would degrade agent output quality.**

**Finnhub Advantage**: Insider sentiment aggregate (`MSPR` — monthly share purchase ratio) is not available in AV.

---

### Category 5: Market Scanner Data

| Feature | Alpha Vantage | Finnhub |
|---------|--------------|---------|
| Top gainers/losers | ✅ `TOP_GAINERS_LOSERS` | ❌ No equivalent on free tier |
| Real-time quote | `GLOBAL_QUOTE` | `/quote` (cleaner, more fields) |
| Market status | ❌ | ✅ `/market-status?exchange=US` |
| Stock screener | ❌ | `/stock/screener` (paid) |
| **Earnings calendar** | ❌ | ✅ `/calendar/earnings` — **unique, high value** |
| **Economic calendar** | ❌ | ✅ `/calendar/economic` (FOMC, CPI, NFP) — **unique, high value** |
| IPO calendar | ❌ | ✅ `/calendar/ipo` |
| Index constituents | ❌ | ✅ `/index/constituents` (S&P 500, NASDAQ 100) |
| Sector ETF performance | Via SPDR ETF proxies | Same SPDR ETF proxy approach |

**Critical Gap**: Finnhub has no `TOP_GAINERS_LOSERS` equivalent on the free tier. Our `finnhub_scanner.py` workaround fetches quotes for 50 large-cap S&P 500 stocks and sorts — this is a functional approximation but misses small/mid-cap movers.

**Finnhub Unique**: Earnings and economic calendars are zero-cost additions that directly enhance our geopolitical_scanner and macro_synthesis agents.

---

## 3. Unique Finnhub Capabilities (Not in Alpha Vantage)

These are additive value — things AV cannot provide at any tier:

| Capability | Endpoint | Value for TradingAgents |
|-----------|----------|------------------------|
| **Earnings Calendar** | `/calendar/earnings` | Event-driven triggers; pre-position before earnings volatility |
| **Economic Calendar** | `/calendar/economic` | FOMC, CPI, NFP dates for macro scanner context |
| **As-Filed XBRL Financials** | `/financials-reported` | Highest fidelity fundamental data for deep-think agents |
| **Earnings Surprise History** | `/stock/earnings` | Beat/miss rate — strong predictor signal for LLM reasoning |
| **Insider Sentiment (MSPR)** | `/stock/insider-sentiment` | Aggregated monthly buying pressure score |
| **Index Constituents** | `/index/constituents` | Know S&P 500 / NASDAQ 100 members without hardcoding |
| **Market Status** | `/market-status` | Gate scanner runs to market hours |
| **Options Chain** | `/stock/option-chain` (paid) | Put/call ratios, implied vol — not in AV at any tier |
| **Social Sentiment** | `/stock/social-sentiment` (paid) | Reddit/X structured signal |
| **Supply Chain Graph** | `/stock/supply-chain` (paid) | Peer/supplier/customer relationships |
| **Congressional Trading** | `/stock/usa-spending` | Insider signal from public officials |

---

## 4. Data Quality Assessment

| Dimension | Alpha Vantage | Finnhub | Notes |
|-----------|--------------|---------|-------|
| Real-time quotes | Delayed, occasionally stale | Delayed free / real-time paid; cleaner | Finnhub slightly better |
| Adjusted historical data | Known issues with reverse splits | More accurate back-adjustment | Finnhub better |
| Fundamental accuracy | Normalized, some restated-data lag | As-filed XBRL option is gold standard | Finnhub better for high-fidelity |
| News sentiment quality | ✅ Per-article NLP scores (genuine differentiator) | Aggregate only (free tier) | **AV wins** |
| API reliability | Generally stable; rate limits documented | Generally stable; free tier mostly reliable | Tie |

---

## 5. Free Tier Viability

### Scanner call budget analysis

| Scanner Stage | AV Calls | Finnhub Equivalent | Notes |
|--------------|----------|-------------------|-------|
| Market movers (1 endpoint) | 1 | 50 `/quote` calls | Workaround — massively more expensive |
| Per-mover fundamentals (5 tickers) | 5 `OVERVIEW` | 10 (profile2 + metric × 5) | 2× call count |
| News (3 topics) | 3 | 2 `/news` categories | Reduced topic coverage |
| Sector ETFs (11) | 11 | 11 `/quote` | 1:1 |
| **Total per scan** | ~30 | ~73 | Over free tier per-minute budget |

**Verdict**: Finnhub as a **full replacement** exceeds the 60 calls/min free tier budget for a complete scan. As a **supplementary vendor** for calendar data only (2-3 calls per scan), it fits comfortably.

---

## 6. What We Built

### New files (all in `tradingagents/dataflows/`)

| File | Purpose |
|------|---------|
| `finnhub_common.py` | Exception hierarchy, rate limiter (60/min), `_make_api_request` |
| `finnhub_stock.py` | `get_stock_candles`, `get_quote` |
| `finnhub_fundamentals.py` | `get_company_profile`, `get_financial_statements`, `get_basic_financials` |
| `finnhub_news.py` | `get_company_news`, `get_market_news`, `get_insider_transactions` |
| `finnhub_scanner.py` | `get_market_movers_finnhub`, `get_market_indices_finnhub`, `get_sector_performance_finnhub`, `get_topic_news_finnhub` |
| `finnhub_indicators.py` | `get_indicator_finnhub` (SMA, EMA, MACD, RSI, BBANDS, ATR) |
| `finnhub.py` | Facade re-exporting all public functions |

### Test files (in `tests/`)

| File | Tests | Type |
|------|-------|------|
| `test_finnhub_integration.py` | 100 | Offline (mocked HTTP) — always runs |
| `test_finnhub_live_integration.py` | 41 | Live API — skips if `FINNHUB_API_KEY` unset |

---

## 7. Integration Architecture (Proposed for Future PR)

If we proceed with adding Finnhub as a supplementary vendor, the changes to existing code would be minimal:

```python
# default_config.py — add Finnhub to calendar-specific routes
"vendor_calendar_data": "finnhub",   # earnings + economic calendars (new category)
"vendor_filings_data": "finnhub",    # as-filed XBRL (optional deep mode)
```

```python
# interface.py — extend fallback error types
except (AlphaVantageError, FinnhubError, ConnectionError, TimeoutError):
```

```python
# .env.example — add new key
FINNHUB_API_KEY=your_finnhub_api_key_here
```

New tools to add in a follow-up PR:
- `get_upcoming_earnings(from_date, to_date)` → `/calendar/earnings`
- `get_economic_calendar(from_date, to_date)` → `/calendar/economic`

---

## 8. Recommendation Summary

| Category | Decision | Rationale |
|----------|----------|-----------|
| Daily OHLCV | Keep yfinance primary | Free, no split-adjust issue, already working |
| Technical Indicators | Compute locally (`pandas-ta`) | Neither AV nor Finnhub is reliable; local is better |
| Fundamentals (quick) | Keep AV `OVERVIEW` | 1 call vs 2; sufficient for screening |
| Fundamentals (deep) | Add Finnhub `/financials-reported` | XBRL as-filed for debate rounds / deep-think agents |
| News sentiment | Keep AV | Per-article NLP scores are irreplaceable for agents |
| Market movers | Keep AV `TOP_GAINERS_LOSERS` | No viable Finnhub free alternative |
| **Earnings calendar** | **Add Finnhub** | Not available in AV — high signal, low cost (1 call) |
| **Economic calendar** | **Add Finnhub** | Not available in AV — critical macro context |
| Insider transactions | Either AV or Finnhub | Finnhub has additional `insider-sentiment` MSPR |

**Bottom line**: Add Finnhub's free calendar endpoints as a zero-cost enhancement to the macro scanner. Everything else stays as-is. The integration layer built in this PR is ready to use — it just needs the routing wired in `interface.py` and the calendar tool functions added to `scanner_tools.py`.

---

## 9. Running the Tests

```bash
# Offline tests (no API key needed)
conda activate tradingagents
pytest tests/test_finnhub_integration.py -v

# Live integration tests (requires FINNHUB_API_KEY)
FINNHUB_API_KEY=your_key pytest tests/test_finnhub_live_integration.py -v -m integration
```
