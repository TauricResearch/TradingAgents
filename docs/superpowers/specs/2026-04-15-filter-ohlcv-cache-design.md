# Filter Stage OHLCV Cache Design

**Date:** 2026-04-15
**Status:** Approved

## Problem

The discovery filter stage fires ~120 sequential per-ticker yfinance HTTP calls for each run (~60 candidates × 2 calls each), causing "Too Many Requests" rate limit errors. In the 2026-04-15 run, only 36/61 candidates got prices — the rest were silently dropped, leaving the ranker with just 11 candidates and producing only 2 final picks.

The three offending call sites in `filter.py`:
1. `get_stock_price(ticker)` — fallback per-ticker price fetch
2. `check_intraday_movement(ticker)` — `yf.Ticker().history(period="1d", interval="1m")`
3. `check_if_price_reacted(ticker)` — `yf.Ticker().history(period="1mo")`

The OHLCV cache (1y daily bars, populated nightly) already contains all the data these checks need. Since discovery runs at 7:30am ET (pre-market), yesterday's close is the correct "current price" anyway.

## Solution

Load the OHLCV cache once at the start of the filter stage for the ~60 candidate tickers, then replace all three yfinance call sites with cache lookups.

## Scope

**File changed:** `tradingagents/dataflows/discovery/filter.py` only.

**Unchanged:** `_fetch_batch_volume()`, `_fetch_batch_news()`, `get_fundamentals()`, scanner code, OHLCV cache internals.

## Design

### Cache load

At the top of `CandidateFilter.filter()`, before the per-candidate loop:

```python
cache_dir = self.config.get("discovery", {}).get("ohlcv_cache_dir", "data/ohlcv_cache")
candidate_tickers = [c["ticker"] for c in candidates if c.get("ticker")]
ohlcv_data = download_ohlcv_cached(candidate_tickers, period="1y", cache_dir=cache_dir)
```

`ohlcv_data` is `Dict[str, DataFrame]` — ticker → daily OHLCV. Loading ~60 tickers from the parquet cache takes under 1 second.

### Replacement map

| Was | Becomes |
|---|---|
| `_fetch_batch_prices()` + `get_stock_price()` fallback | `ohlcv_data[ticker]["Close"].iloc[-1]` |
| `check_intraday_movement()` via `history(1d, 1m)` | `(close[-1] - close[-2]) / close[-2] * 100` (last 2 daily closes) |
| `check_if_price_reacted()` via `history(1mo)` | `(close[-1] - close[-N]) / close[-N] * 100` where N = `recent_movement_lookback_days` |

### Fallback

If a ticker is missing from `ohlcv_data` (e.g. newly listed, not yet in nightly prefetch), fall through to the existing `get_stock_price()` call. No candidates are lost that weren't already being lost before this change.

### Remove

`_fetch_batch_prices()` method — no longer needed once the cache covers current price.

## Expected outcome

- Zero yfinance rate limit errors during filter enrichment
- All candidates that pass the scan reach the ranker (was 11/63, should be ~60)
- No change to filter logic or thresholds — only the data source changes
