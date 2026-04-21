# OHLCV Cache Contamination Defence — Design Spec

**Date:** 2026-04-21  
**Status:** Approved  
**Branch:** `claude/silly-meitner-37bb65`

---

## Problem

When `yf.download()` is called with a multi-ticker list (e.g. `["STM", "TSM"]`), yfinance returns a DataFrame with multi-level columns. If `multi_level_index` is not explicitly set to `False`, and the result is written to a single-ticker cache file (e.g. `STM-YFin-data-*.csv`), the file contains data for both tickers with duplicate columns (`Close`, `Close.1`, `High`, `High.1`, …).

When `stockstats` reads this file, it selects the first `Close` column — which is TSM's data, not STM's. This produces wildly incorrect SMA values (e.g. `close_50_sma = $170.54` for STM, a $31–41 stock).

### Root Cause Chain

```
yf.download(["STM", "TSM"])
  → multi-level index DataFrame
  → flattened to single-level with duplicate suffixes (.1, .2)
  → written to STM-YFin-data-YYYY-MM-DD.csv
  → stockstats reads first "Close" column (TSM's price)
  → SMA computed on wrong ticker data
  → market analyst reports TSM's $170 SMA for STM
```

### All `yf.download()` Call Sites (8 total)

| File | Function | Risk |
|------|----------|------|
| `tradingagents/dataflows/yfinance_utils.py` | `get_stock_data_window()` | HIGH — main OHLCV fetch |
| `tradingagents/dataflows/yfinance_utils.py` | `get_stock_data()` | HIGH — main OHLCV fetch |
| `tradingagents/dataflows/yfinance_scanner.py` | `get_market_movers()` | MEDIUM — bulk download |
| `tradingagents/dataflows/yfinance_scanner.py` | `get_sector_overview()` | MEDIUM — bulk download |
| `tradingagents/dataflows/yfinance_scanner.py` | `get_stock_sentiment()` | LOW — single ticker |
| `tradingagents/dataflows/yfinance_scanner.py` | `get_technical_indicators()` | LOW — single ticker |
| `tradingagents/dataflows/yfin_utils.py` (legacy) | various | MEDIUM — may be shared |
| `tradingagents/agents/utils/core_stock_tools.py` | `get_stock_data()` | HIGH — analyst tools |

---

## Solution: Four-Layer Defence

### Layer 1 — `safe_yf_download()` Central Wrapper

Create a single wrapper function in `tradingagents/dataflows/yfinance_utils.py` that all call sites use:

```python
def safe_yf_download(tickers, start, end, **kwargs) -> pd.DataFrame:
    """Central yf.download wrapper — enforces thread-safety and column hygiene."""
    kwargs.setdefault("threads", False)
    kwargs.setdefault("multi_level_index", False)
    return yf.download(tickers, start=start, end=end, **kwargs)
```

Replace all 8 `yf.download()` direct calls with `safe_yf_download()`.

**Why this works:** `multi_level_index=False` forces yfinance to return a flat single-level DataFrame even for multi-ticker inputs. `threads=False` prevents thread-unsafe concurrent downloads (already partially fixed on the scanner side).

### Layer 2 — Structural Column Validator in `_load_or_fetch_ohlcv()` (`stockstats_utils.py`)

After loading a CSV cache file, validate that no duplicate column suffixes are present before passing data to downstream consumers:

```python
def _has_contaminated_columns(df: pd.DataFrame) -> bool:
    """Return True if DataFrame has duplicate-ticker column suffixes (.1, .2, etc.)."""
    return any(re.search(r'\.\d+$', col) for col in df.columns)
```

If contamination is detected:
1. Log a warning with the filename and column names
2. Delete the cache file
3. Re-fetch from yfinance using `safe_yf_download()`
4. Proceed with fresh data

This acts as a self-healing mechanism for any existing contaminated cache files that survive Layer 3.

### Layer 3 — Purge `data_cache/` Directory

Since this is a development environment, purge the entire cache directory at deployment time. No migration script needed — just delete:

```bash
rm -rf data_cache/
```

This eliminates all existing contaminated files immediately. The pipeline regenerates cache on the next run using the fixed `safe_yf_download()` wrapper.

This should be run once as part of deploying this fix. Document in the implementation notes.

### Layer 4 — Plausibility Guard with 3-Retry Loop

After fetching OHLCV data (fresh or from cache), check that SMA values are plausible relative to the current close price:

```python
threshold = DEFAULT_CONFIG.get("ohlcv_sma_plausibility_threshold", 3.0)

def _sma_is_plausible(df: pd.DataFrame, close_col: str, sma_col: str) -> bool:
    last_close = df[close_col].iloc[-1]
    last_sma = df[sma_col].iloc[-1]
    if last_close <= 0 or last_sma <= 0:
        return False
    ratio = max(last_close, last_sma) / min(last_close, last_sma)
    return ratio <= threshold
```

**Retry loop:** If the plausibility check fails:
1. Delete the cache file
2. Re-fetch from yfinance
3. Retry up to 3 times
4. If all 3 attempts fail, raise `RuntimeError` with details (ticker, close, SMA, ratio, threshold)

The `RuntimeError` propagates up and halts the node cleanly — consistent with the pipeline's hard-crash-on-failure policy (per CLAUDE.md).

**Threshold config:**

New key in `default_config.py`:
```python
"ohlcv_sma_plausibility_threshold": _env_float("TRADINGAGENTS_OHLCV_SMA_PLAUSIBILITY_THRESHOLD", 3.0, env=env),
```

Default 3.0 means SMA may not exceed 3× the close price (or vice versa). This catches cross-ticker contamination (e.g. STM $36 vs TSM SMA $170 = ratio 4.7) while allowing normal volatility.

---

## Data Flow After Fix

```
yf.download([...])
  → safe_yf_download() [Layer 1]
    → threads=False, multi_level_index=False
    → flat single-level DataFrame
  → _load_or_fetch_ohlcv() [Layer 2]
    → check for .1/.2 column suffixes
    → if found: delete cache, re-fetch
  → plausibility guard [Layer 4]
    → SMA/close ratio check
    → if implausible: delete cache, retry (up to 3×)
    → if 3 failures: RuntimeError
  → downstream stockstats / indicator computation
```

---

## Config Keys Added

| Key | Env Var | Default | Purpose |
|-----|---------|---------|---------|
| `ohlcv_sma_plausibility_threshold` | `TRADINGAGENTS_OHLCV_SMA_PLAUSIBILITY_THRESHOLD` | `3.0` | Max ratio of SMA to close before flagging contamination |

---

## Files to Modify

| File | Change |
|------|--------|
| `tradingagents/dataflows/yfinance_utils.py` | Add `safe_yf_download()`, replace `yf.download()` calls |
| `tradingagents/dataflows/stockstats_utils.py` | Add Layer 2 column validator and Layer 4 plausibility guard in `_load_or_fetch_ohlcv()` |
| `tradingagents/dataflows/yfinance_scanner.py` | Replace `yf.download()` calls with `safe_yf_download()` |
| `tradingagents/agents/utils/core_stock_tools.py` | Replace `yf.download()` call with `safe_yf_download()` |
| `tradingagents/dataflows/yfin_utils.py` | Replace `yf.download()` calls if present |
| `tradingagents/default_config.py` | Add `ohlcv_sma_plausibility_threshold` key |

---

## Testing

1. **Unit test — `safe_yf_download` multi-ticker** : call with `["STM", "TSM"]`, assert no `.1`/`.2` columns in result
2. **Unit test — column validator**: create a mock DataFrame with `Close` and `Close.1` columns, assert `_has_contaminated_columns()` returns `True`
3. **Unit test — plausibility guard**: mock a DataFrame where SMA is 5× the close price, assert retry loop fires and `RuntimeError` is raised after 3 attempts
4. **Integration test**: run market analyst node for STM, assert `close_50_sma` is within 3× of last close price

---

## Out of Scope

- Fixing contamination in the `portfolio` graph's price fetching (separate data path — no evidence of the same bug there)
- Changing the yfinance version or switching to a different data vendor
- Caching architecture changes beyond self-healing on load
