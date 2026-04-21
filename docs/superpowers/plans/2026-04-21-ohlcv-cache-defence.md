# OHLCV Cache Contamination Defence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent yfinance multi-ticker cache contamination from producing wrong SMA values in the market analyst node, with six defensive layers covering all 9 `yf.download()` call sites.

**Architecture:** A central `safe_yf_download()` wrapper in `stockstats_utils.py` enforces `multi_level_index=False` and `threads=False` across all call sites. The existing `_load_or_fetch_ohlcv()` function gains four additional guards: contaminated-column detection, cache staleness check, row count assertion, and plausibility retry loop. Two new env-var-backed config keys control the guard thresholds.

**Tech Stack:** Python, yfinance 1.2+, pandas, pytest, unittest.mock

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `tradingagents/dataflows/stockstats_utils.py` | Modify | Add `safe_yf_download()`, `_has_contaminated_columns()`, `_is_close_plausible()`, `_assert_sufficient_rows()`, update `_load_or_fetch_ohlcv()` |
| `tradingagents/default_config.py` | Modify | Add `ohlcv_sma_plausibility_threshold` and `ohlcv_cache_max_age_days` config keys |
| `tradingagents/dataflows/peer_comparison.py` | Modify | Replace 2× `yf.download()` with `safe_yf_download()` |
| `tradingagents/dataflows/macro_regime.py` | Modify | Replace `yf.download()` with `safe_yf_download()` |
| `tradingagents/dataflows/market_prices.py` | Modify | Replace `yf.download()` with `safe_yf_download()` |
| `tradingagents/dataflows/yfinance_scanner.py` | Modify | Replace 3× `yf.download()` with `safe_yf_download()` |
| `tradingagents/portfolio/selection_reflector.py` | Modify | Replace `yf.download()` with `safe_yf_download()` |
| `tests/unit/test_stockstats_utils.py` | Modify | Add tests for all new helpers and guard logic |
| `tests/unit/test_ohlcv_cache_defence.py` | Create | Focused integration-style unit tests for `_load_or_fetch_ohlcv()` guard pipeline |

---

## Task 1: Add config keys to `default_config.py`

**Files:**
- Modify: `tradingagents/default_config.py`

- [ ] **Step 1: Add the two new keys to `build_default_config()`**

Open `tradingagents/default_config.py`. Find the line:

```python
        "trading_lookback_days": _env_int("TRADING_LOOKBACK_DAYS", 90, env=env),
```

Add the following two lines immediately after it:

```python
        "ohlcv_sma_plausibility_threshold": _env_float("TRADINGAGENTS_OHLCV_SMA_PLAUSIBILITY_THRESHOLD", 3.0, env=env),
        "ohlcv_cache_max_age_days": _env_int("TRADINGAGENTS_OHLCV_CACHE_MAX_AGE_DAYS", 2, env=env),
```

- [ ] **Step 2: Verify the keys are readable**

```bash
cd /Users/Ahmet/Repo/TradingAgents
python -c "
from tradingagents.default_config import DEFAULT_CONFIG
print('threshold:', DEFAULT_CONFIG.get('ohlcv_sma_plausibility_threshold'))
print('max_age_days:', DEFAULT_CONFIG.get('ohlcv_cache_max_age_days'))
"
```

Expected output:
```
threshold: 3.0
max_age_days: 2
```

- [ ] **Step 3: Verify env vars override the defaults**

```bash
TRADINGAGENTS_OHLCV_SMA_PLAUSIBILITY_THRESHOLD=5.0 TRADINGAGENTS_OHLCV_CACHE_MAX_AGE_DAYS=7 python -c "
import importlib, tradingagents.default_config as dc
cfg = dc.build_default_config(load_dotenv=False)
print('threshold:', cfg.get('ohlcv_sma_plausibility_threshold'))
print('max_age_days:', cfg.get('ohlcv_cache_max_age_days'))
"
```

Expected output:
```
threshold: 5.0
max_age_days: 7
```

- [ ] **Step 4: Commit**

```bash
git add tradingagents/default_config.py
git commit -m "feat(ohlcv): add ohlcv_sma_plausibility_threshold and ohlcv_cache_max_age_days config keys"
```

---

## Task 2: Add `safe_yf_download()` to `stockstats_utils.py` (Layer 1)

**Files:**
- Modify: `tradingagents/dataflows/stockstats_utils.py`
- Modify: `tests/unit/test_stockstats_utils.py`

- [ ] **Step 1: Write the failing tests**

Add to the bottom of `tests/unit/test_stockstats_utils.py`:

```python
import re
from unittest.mock import patch, MagicMock


def test_safe_yf_download_sets_multi_level_index_false():
    """safe_yf_download always passes multi_level_index=False to yf.download."""
    with patch("tradingagents.dataflows.stockstats_utils.yf.download") as mock_dl:
        mock_dl.return_value = pd.DataFrame({"Close": [100.0]})
        from tradingagents.dataflows.stockstats_utils import safe_yf_download
        safe_yf_download("AAPL", start="2024-01-01", end="2024-02-01")
        _, kwargs = mock_dl.call_args
        assert kwargs.get("multi_level_index") is False


def test_safe_yf_download_sets_threads_false_by_default():
    """safe_yf_download defaults threads=False."""
    with patch("tradingagents.dataflows.stockstats_utils.yf.download") as mock_dl:
        mock_dl.return_value = pd.DataFrame({"Close": [100.0]})
        from tradingagents.dataflows.stockstats_utils import safe_yf_download
        safe_yf_download("AAPL", start="2024-01-01", end="2024-02-01")
        _, kwargs = mock_dl.call_args
        assert kwargs.get("threads") is False


def test_safe_yf_download_caller_can_override_threads():
    """safe_yf_download allows callers to explicitly set threads=True."""
    with patch("tradingagents.dataflows.stockstats_utils.yf.download") as mock_dl:
        mock_dl.return_value = pd.DataFrame({"Close": [100.0]})
        from tradingagents.dataflows.stockstats_utils import safe_yf_download
        safe_yf_download("AAPL", start="2024-01-01", end="2024-02-01", threads=True)
        _, kwargs = mock_dl.call_args
        assert kwargs.get("threads") is True
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/unit/test_stockstats_utils.py::test_safe_yf_download_sets_multi_level_index_false -v
```

Expected: `FAILED` with `ImportError: cannot import name 'safe_yf_download'`

- [ ] **Step 3: Add `safe_yf_download()` to `stockstats_utils.py`**

Add this function after the `YFinanceError` class definition (before `_clean_dataframe`), around line 24:

```python
def safe_yf_download(tickers, start=None, end=None, **kwargs) -> pd.DataFrame:
    """Central yf.download wrapper — enforces thread-safety and column hygiene.

    Defaults threads=False (safe inside LangGraph's thread pool) and
    multi_level_index=False (prevents duplicate-ticker column contamination).
    Callers may override either default by passing explicit keyword arguments.
    """
    kwargs.setdefault("threads", False)
    kwargs.setdefault("multi_level_index", False)
    return yf.download(tickers, start=start, end=end, **kwargs)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/unit/test_stockstats_utils.py -k "safe_yf_download" -v
```

Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add tradingagents/dataflows/stockstats_utils.py tests/unit/test_stockstats_utils.py
git commit -m "feat(ohlcv): add safe_yf_download() wrapper enforcing multi_level_index=False"
```

---

## Task 3: Layer 2 — Contaminated column detector in `_load_or_fetch_ohlcv()`

**Files:**
- Modify: `tradingagents/dataflows/stockstats_utils.py`
- Modify: `tests/unit/test_stockstats_utils.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_stockstats_utils.py`:

```python
def test_has_contaminated_columns_detects_dot_suffix():
    """_has_contaminated_columns returns True when columns like Close.1 are present."""
    from tradingagents.dataflows.stockstats_utils import _has_contaminated_columns
    df = pd.DataFrame({"Date": [], "Close": [], "Close.1": [], "Volume": []})
    assert _has_contaminated_columns(df) is True


def test_has_contaminated_columns_clean_df():
    """_has_contaminated_columns returns False for a normal single-ticker DataFrame."""
    from tradingagents.dataflows.stockstats_utils import _has_contaminated_columns
    df = pd.DataFrame({"Date": [], "Open": [], "High": [], "Low": [], "Close": [], "Volume": []})
    assert _has_contaminated_columns(df) is False
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/unit/test_stockstats_utils.py::test_has_contaminated_columns_detects_dot_suffix -v
```

Expected: `FAILED` with `ImportError: cannot import name '_has_contaminated_columns'`

- [ ] **Step 3: Add `_has_contaminated_columns()` to `stockstats_utils.py`**

Add this helper after `safe_yf_download()`:

```python
def _has_contaminated_columns(df: pd.DataFrame) -> bool:
    """Return True if any column name ends with .N (multi-ticker contamination)."""
    return any(
        bool(__import__("re").search(r"\.\d+$", str(col)))
        for col in df.columns
    )
```

- [ ] **Step 4: Wire the check into `_load_or_fetch_ohlcv()`**

In `_load_or_fetch_ohlcv()`, find the `else:` block that follows the `try/except` for CSV loading (currently around line 87). Replace:

```python
        else:
            # Validate: a 15-year daily file should have well over 100 rows
            if len(data) < 50:
                logger.warning(
                    "Cache file for %s has only %d rows — likely truncated, re-fetching.",
                    symbol, len(data),
                )
                os.remove(data_file)
                data = None
```

with:

```python
        else:
            # Validate: a 15-year daily file should have well over 100 rows
            if len(data) < 50:
                logger.warning(
                    "Cache file for %s has only %d rows — likely truncated, re-fetching.",
                    symbol, len(data),
                )
                os.remove(data_file)
                data = None
            elif _has_contaminated_columns(data):
                logger.warning(
                    "Cache file for %s has contaminated columns %s — deleting and re-fetching.",
                    symbol, [c for c in data.columns if __import__("re").search(r"\.\d+$", str(c))],
                )
                os.remove(data_file)
                data = None
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
pytest tests/unit/test_stockstats_utils.py -k "contaminated" -v
```

Expected: 2 tests PASS

- [ ] **Step 6: Commit**

```bash
git add tradingagents/dataflows/stockstats_utils.py tests/unit/test_stockstats_utils.py
git commit -m "feat(ohlcv): add contaminated-column detector (Layer 2)"
```

---

## Task 4: Layer 6 — Cache staleness check in `_load_or_fetch_ohlcv()`

**Files:**
- Modify: `tradingagents/dataflows/stockstats_utils.py`
- Modify: `tests/unit/test_stockstats_utils.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_stockstats_utils.py`:

```python
def test_load_or_fetch_ohlcv_purges_stale_cache(tmp_path, monkeypatch):
    """_load_or_fetch_ohlcv deletes a cache file whose last date is too old."""
    import pandas as pd
    from unittest.mock import patch, MagicMock
    from tradingagents.dataflows import stockstats_utils as su

    # Build a stale CSV: last row is 10 days ago
    old_date = (pd.Timestamp.today() - pd.Timedelta(days=10)).strftime("%Y-%m-%d")
    rows = pd.DataFrame({
        "Date": [old_date],
        "Open": [100.0], "High": [101.0], "Low": [99.0],
        "Close": [100.5], "Volume": [1000000],
    })
    # Write to a path that matches the expected cache file name
    today = pd.Timestamp.today()
    start = (today - pd.DateOffset(years=15)).strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")
    cache_file = tmp_path / f"STM-YFin-data-{start}-{end}.csv"
    rows.to_csv(cache_file, index=False)

    monkeypatch.setattr(su, "get_config", lambda: {"data_cache_dir": str(tmp_path)})

    fresh_rows = rows.copy()
    fresh_rows["Date"] = today.strftime("%Y-%m-%d")

    mock_raw = MagicMock()
    mock_raw.empty = False
    mock_raw.reset_index.return_value = fresh_rows

    with patch.object(su, "yf") as mock_yf:
        mock_yf.download.return_value = mock_raw
        su._load_or_fetch_ohlcv("STM")
        assert mock_yf.download.called, "Should have re-fetched stale cache"
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
pytest tests/unit/test_stockstats_utils.py::test_load_or_fetch_ohlcv_purges_stale_cache -v
```

Expected: `FAILED` (download is NOT called because stale check not yet implemented)

- [ ] **Step 3: Add staleness check to `_load_or_fetch_ohlcv()`**

In `_load_or_fetch_ohlcv()`, add the staleness check after the contaminated-column check. The full updated `else:` block should read:

```python
        else:
            # Validate: a 15-year daily file should have well over 100 rows
            if len(data) < 50:
                logger.warning(
                    "Cache file for %s has only %d rows — likely truncated, re-fetching.",
                    symbol, len(data),
                )
                os.remove(data_file)
                data = None
            elif _has_contaminated_columns(data):
                logger.warning(
                    "Cache file for %s has contaminated columns %s — deleting and re-fetching.",
                    symbol, [c for c in data.columns if __import__("re").search(r"\.\d+$", str(c))],
                )
                os.remove(data_file)
                data = None
            else:
                # Layer 6: staleness check
                date_col = "Date" if "Date" in data.columns else "date"
                if date_col in data.columns:
                    try:
                        last_date = pd.to_datetime(data[date_col]).max()
                        max_age = int(
                            get_config().get("ohlcv_cache_max_age_days")
                            or DEFAULT_CONFIG.get("ohlcv_cache_max_age_days")
                            or 2
                        )
                        if (pd.Timestamp.today() - last_date).days > max_age:
                            logger.warning(
                                "Cache file for %s is stale (last date %s, age %d days > %d) — re-fetching.",
                                symbol, last_date.date(), (pd.Timestamp.today() - last_date).days, max_age,
                            )
                            os.remove(data_file)
                            data = None
                    except Exception as exc:
                        logger.warning("Could not parse dates from cache for %s (%s) — re-fetching.", symbol, exc)
                        os.remove(data_file)
                        data = None
```

Also add the import at the top of `stockstats_utils.py` (after `from .config import get_config`):

```python
from tradingagents.default_config import DEFAULT_CONFIG
```

- [ ] **Step 4: Run test to confirm it passes**

```bash
pytest tests/unit/test_stockstats_utils.py::test_load_or_fetch_ohlcv_purges_stale_cache -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tradingagents/dataflows/stockstats_utils.py tests/unit/test_stockstats_utils.py
git commit -m "feat(ohlcv): add cache staleness check (Layer 6)"
```

---

## Task 5: Layer 5 — Row count guard in `_load_or_fetch_ohlcv()`

**Files:**
- Modify: `tradingagents/dataflows/stockstats_utils.py`
- Modify: `tests/unit/test_stockstats_utils.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_stockstats_utils.py`:

```python
def test_assert_sufficient_rows_raises_when_too_few():
    """_assert_sufficient_rows raises RuntimeError when df has fewer rows than required."""
    from tradingagents.dataflows.stockstats_utils import _assert_sufficient_rows
    df = pd.DataFrame({"Close": range(10)})
    with pytest.raises(RuntimeError, match=r"\[OHLCV\] Insufficient data for THIN"):
        _assert_sufficient_rows(df, min_rows=50, ticker="THIN")


def test_assert_sufficient_rows_passes_when_enough():
    """_assert_sufficient_rows does not raise when df has enough rows."""
    from tradingagents.dataflows.stockstats_utils import _assert_sufficient_rows
    df = pd.DataFrame({"Close": range(60)})
    _assert_sufficient_rows(df, min_rows=50, ticker="AAPL")  # no exception
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/unit/test_stockstats_utils.py::test_assert_sufficient_rows_raises_when_too_few -v
```

Expected: `FAILED` with `ImportError: cannot import name '_assert_sufficient_rows'`

- [ ] **Step 3: Add `_assert_sufficient_rows()` to `stockstats_utils.py`**

Add this helper after `_has_contaminated_columns()`:

```python
def _assert_sufficient_rows(df: pd.DataFrame, min_rows: int, ticker: str) -> None:
    """Raise RuntimeError if df has fewer rows than the minimum required."""
    if len(df) < min_rows:
        raise RuntimeError(
            f"[OHLCV] Insufficient data for {ticker}: "
            f"need {min_rows} rows, got {len(df)}"
        )
```

- [ ] **Step 4: Wire the guard into `_load_or_fetch_ohlcv()`**

At the end of `_load_or_fetch_ohlcv()`, just before `return data`, add:

```python
    _assert_sufficient_rows(data, min_rows=50, ticker=symbol)
    return data
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
pytest tests/unit/test_stockstats_utils.py -k "sufficient_rows" -v
```

Expected: 2 tests PASS

- [ ] **Step 6: Commit**

```bash
git add tradingagents/dataflows/stockstats_utils.py tests/unit/test_stockstats_utils.py
git commit -m "feat(ohlcv): add row count guard (Layer 5)"
```

---

## Task 6: Layer 4 — Plausibility guard with 3-retry loop

**Files:**
- Modify: `tradingagents/dataflows/stockstats_utils.py`
- Create: `tests/unit/test_ohlcv_cache_defence.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_ohlcv_cache_defence.py`:

```python
"""Tests for the OHLCV plausibility guard and retry loop in _load_or_fetch_ohlcv."""
import os
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock, call


def _make_df(close_values: list[float]) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=len(close_values), freq="B")
    return pd.DataFrame({
        "Date": dates.strftime("%Y-%m-%d"),
        "Open": close_values, "High": close_values,
        "Low": close_values, "Close": close_values, "Volume": [1_000_000] * len(close_values),
    })


def test_is_close_plausible_detects_contamination():
    """_is_close_plausible returns False when rolling mean is 5× the last close."""
    from tradingagents.dataflows.stockstats_utils import _is_close_plausible

    # Last close is $36, but rolling mean is $170 — contamination scenario
    closes = [170.0] * 49 + [36.0]
    df = _make_df(closes)
    assert _is_close_plausible(df, "STM") is False


def test_is_close_plausible_passes_normal_data():
    """_is_close_plausible returns True for stable close prices."""
    from tradingagents.dataflows.stockstats_utils import _is_close_plausible

    closes = [100.0 + i * 0.1 for i in range(60)]
    df = _make_df(closes)
    assert _is_close_plausible(df, "AAPL") is True


def test_load_or_fetch_ohlcv_retries_on_plausibility_failure(tmp_path, monkeypatch):
    """_load_or_fetch_ohlcv retries download up to 3 times when plausibility check fails."""
    from tradingagents.dataflows import stockstats_utils as su

    monkeypatch.setattr(su, "get_config", lambda: {"data_cache_dir": str(tmp_path)})

    bad_df = _make_df([170.0] * 49 + [36.0])  # contaminated: last close $36, mean $170
    mock_raw = MagicMock()
    mock_raw.empty = False
    mock_raw.reset_index.return_value = bad_df

    with patch.object(su, "yf") as mock_yf:
        mock_yf.download.return_value = mock_raw
        with pytest.raises(RuntimeError, match=r"\[OHLCV\] Plausibility check failed"):
            su._load_or_fetch_ohlcv("STM")
        assert mock_yf.download.call_count == 3, "Should have retried exactly 3 times"


def test_load_or_fetch_ohlcv_accepts_data_after_retry(tmp_path, monkeypatch):
    """_load_or_fetch_ohlcv succeeds on the second attempt after one plausibility failure."""
    from tradingagents.dataflows import stockstats_utils as su

    monkeypatch.setattr(su, "get_config", lambda: {"data_cache_dir": str(tmp_path)})

    bad_df = _make_df([170.0] * 49 + [36.0])
    good_df = _make_df([36.0] * 60)

    call_count = {"n": 0}
    def fake_download(*args, **kwargs):
        call_count["n"] += 1
        m = MagicMock()
        m.empty = False
        m.reset_index.return_value = bad_df if call_count["n"] == 1 else good_df
        return m

    with patch.object(su, "yf") as mock_yf:
        mock_yf.download.side_effect = fake_download
        result = su._load_or_fetch_ohlcv("STM")
        assert mock_yf.download.call_count == 2
        assert len(result) == 60
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/unit/test_ohlcv_cache_defence.py -v
```

Expected: `FAILED` with `ImportError: cannot import name '_is_close_plausible'`

- [ ] **Step 3: Add `_is_close_plausible()` helper to `stockstats_utils.py`**

Add after `_assert_sufficient_rows()`:

```python
def _is_close_plausible(df: pd.DataFrame, ticker: str) -> bool:
    """Return False if the 50-day rolling mean of Close deviates too far from the last close.

    Catches cross-ticker contamination where a high-priced ticker's data was
    mixed into a low-priced ticker's cache (e.g. TSM $170 in STM's $36 file).
    """
    close_col = "Close" if "Close" in df.columns else "close"
    if close_col not in df.columns:
        return True
    closes = pd.to_numeric(df[close_col], errors="coerce").dropna()
    if len(closes) < 10:
        return True
    last_close = closes.iloc[-1]
    rolling_mean = closes.tail(50).mean()
    if last_close <= 0 or rolling_mean <= 0:
        logger.warning("[OHLCV] %s: non-positive close value detected (last=%.2f, mean=%.2f)", ticker, last_close, rolling_mean)
        return False
    threshold = DEFAULT_CONFIG.get("ohlcv_sma_plausibility_threshold") or 3.0
    ratio = max(last_close, rolling_mean) / min(last_close, rolling_mean)
    if ratio > threshold:
        logger.warning(
            "[OHLCV] Plausibility check failed for %s: last_close=%.2f, rolling_mean_50=%.2f, ratio=%.2f > %.1f",
            ticker, last_close, rolling_mean, ratio, threshold,
        )
        return False
    return True
```

- [ ] **Step 4: Restructure the download section of `_load_or_fetch_ohlcv()` to add the retry loop**

Replace the existing download block:

```python
    # ── Download from yfinance if cache miss / corrupt ────────────────────────
    if data is None:
        raw = yf.download(
            symbol,
            start=start_date_str,
            end=end_date_str,
            multi_level_index=False,
            progress=False,
            auto_adjust=True,
        )
        if raw.empty:
            raise YFinanceError(
                f"yfinance returned no data for symbol '{symbol}' "
                f"({start_date_str} → {end_date_str})"
            )
        data = raw.reset_index()
        data.to_csv(data_file, index=False)
        logger.debug("Downloaded and cached OHLCV for %s → %s", symbol, data_file)
```

with:

```python
    # ── Download from yfinance if cache miss / corrupt (with plausibility retry) ──
    _MAX_PLAUSIBILITY_RETRIES = 3
    for _attempt in range(_MAX_PLAUSIBILITY_RETRIES):
        if data is None:
            raw = yf.download(
                symbol,
                start=start_date_str,
                end=end_date_str,
                multi_level_index=False,
                progress=False,
                auto_adjust=True,
            )
            if raw.empty:
                raise YFinanceError(
                    f"yfinance returned no data for symbol '{symbol}' "
                    f"({start_date_str} → {end_date_str})"
                )
            data = raw.reset_index()
            data.to_csv(data_file, index=False)
            logger.debug("Downloaded and cached OHLCV for %s → %s (attempt %d)", symbol, data_file, _attempt + 1)

        if not _is_close_plausible(data, symbol):
            if os.path.exists(data_file):
                os.remove(data_file)
            data = None
            if _attempt == _MAX_PLAUSIBILITY_RETRIES - 1:
                raise RuntimeError(
                    f"[OHLCV] Plausibility check failed for {symbol} after "
                    f"{_MAX_PLAUSIBILITY_RETRIES} attempts — possible persistent data "
                    f"contamination. Delete data_cache/ and retry."
                )
            logger.warning("[OHLCV] Plausibility failure for %s on attempt %d — retrying.", symbol, _attempt + 1)
            continue
        break
```

- [ ] **Step 5: Run all new tests**

```bash
pytest tests/unit/test_ohlcv_cache_defence.py -v
```

Expected: 4 tests PASS

- [ ] **Step 6: Run full stockstats test suite to confirm no regressions**

```bash
pytest tests/unit/test_stockstats_utils.py tests/unit/test_ohlcv_cache_defence.py -v
```

Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add tradingagents/dataflows/stockstats_utils.py tests/unit/test_ohlcv_cache_defence.py
git commit -m "feat(ohlcv): add plausibility guard with 3-retry loop (Layer 4)"
```

---

## Task 7: Migrate all remaining call sites to `safe_yf_download()`

**Files:**
- Modify: `tradingagents/dataflows/peer_comparison.py` (lines 150, 292)
- Modify: `tradingagents/dataflows/macro_regime.py` (line 39)
- Modify: `tradingagents/dataflows/market_prices.py` (line 48)
- Modify: `tradingagents/dataflows/yfinance_scanner.py` (lines 426, 512, 615)
- Modify: `tradingagents/portfolio/selection_reflector.py` (line 57)

Note: `tradingagents/dataflows/stockstats_utils.py` line 101 already has `multi_level_index=False`. Migrate it to `safe_yf_download()` for consistency too.

- [ ] **Step 1: Add the import to each file that doesn't already import from `stockstats_utils`**

For `peer_comparison.py`, `macro_regime.py`, `market_prices.py`, `yfinance_scanner.py`:

Check current imports at the top of each file. Add this line where appropriate:

```python
from .stockstats_utils import safe_yf_download
```

For `portfolio/selection_reflector.py`:

```python
from tradingagents.dataflows.stockstats_utils import safe_yf_download
```

- [ ] **Step 2: Replace in `stockstats_utils.py`** (line ~101)

Replace:
```python
        raw = yf.download(
            symbol,
            start=start_date_str,
            end=end_date_str,
            multi_level_index=False,
            progress=False,
            auto_adjust=True,
        )
```

with:
```python
        raw = safe_yf_download(
            symbol,
            start=start_date_str,
            end=end_date_str,
            progress=False,
            auto_adjust=True,
        )
```

- [ ] **Step 3: Replace in `peer_comparison.py`** (line ~150)

Replace:
```python
        hist = yf.download(
            all_symbols,
            period="6mo",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
```

with:
```python
        hist = safe_yf_download(
            all_symbols,
            period="6mo",
            auto_adjust=True,
            progress=False,
        )
```

Replace the second call (line ~292):
```python
        hist = yf.download(
            symbols,
            period="6mo",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
```

with:
```python
        hist = safe_yf_download(
            symbols,
            period="6mo",
            auto_adjust=True,
            progress=False,
        )
```

- [ ] **Step 4: Replace in `macro_regime.py`** (line ~39)

Replace:
```python
        hist = yf.download(symbols, period=period, auto_adjust=True, progress=False, threads=True)
```

with:
```python
        hist = safe_yf_download(symbols, period=period, auto_adjust=True, progress=False)
```

- [ ] **Step 5: Replace in `market_prices.py`** (line ~48)

Replace:
```python
            prices_df = yf.download(
                symbols,
                period="5d",
                auto_adjust=False,
                progress=False,
                threads=True,
            )
```

with:
```python
            prices_df = safe_yf_download(
                symbols,
                period="5d",
                auto_adjust=False,
                progress=False,
            )
```

- [ ] **Step 6: Replace in `yfinance_scanner.py`** (lines ~426, ~512, ~615)

Line ~426:
```python
        indices_history = yf.download(symbols, period="2d", auto_adjust=True, progress=False, threads=False)
```
→
```python
        indices_history = safe_yf_download(symbols, period="2d", auto_adjust=True, progress=False)
```

Line ~512:
```python
        hist = yf.download(symbols, period="6mo", auto_adjust=True, progress=False, threads=False)
```
→
```python
        hist = safe_yf_download(symbols, period="6mo", auto_adjust=True, progress=False)
```

Line ~615:
```python
            hist = yf.download(
                tickers, period="1mo", auto_adjust=True, progress=False, threads=False,
            )
```
→
```python
            hist = safe_yf_download(
                tickers, period="1mo", auto_adjust=True, progress=False,
            )
```

- [ ] **Step 7: Replace in `selection_reflector.py`** (line ~57)

Replace:
```python
        hist = yf.download(
            [ticker, "SPY"],
            start=start_date,
            end=end_date,
            auto_adjust=True,
            progress=False
        )
```

with:
```python
        hist = safe_yf_download(
            [ticker, "SPY"],
            start=start_date,
            end=end_date,
            auto_adjust=True,
            progress=False,
        )
```

- [ ] **Step 8: Verify no bare `yf.download(` calls remain (excluding comments)**

```bash
grep -rn "yf\.download(" tradingagents/ --include="*.py" | grep -v "#"
```

Expected: zero results (or only the definition inside `safe_yf_download` itself)

- [ ] **Step 9: Run the unit test suite**

```bash
pytest tests/unit/ -v -m "not integration"
```

Expected: All tests PASS (no import errors, no regressions)

- [ ] **Step 10: Commit**

```bash
git add tradingagents/dataflows/peer_comparison.py \
        tradingagents/dataflows/macro_regime.py \
        tradingagents/dataflows/market_prices.py \
        tradingagents/dataflows/yfinance_scanner.py \
        tradingagents/portfolio/selection_reflector.py \
        tradingagents/dataflows/stockstats_utils.py
git commit -m "feat(ohlcv): migrate all yf.download() call sites to safe_yf_download()"
```

---

## Task 8: Purge stale cache and verify end-to-end

**Files:** None (manual operation + verification)

- [ ] **Step 1: Delete the entire `data_cache/` directory**

```bash
rm -rf data_cache/
echo "Cache purged."
```

This removes all existing cache files, including any contaminated CSVs. The pipeline regenerates cache on next run.

- [ ] **Step 2: Run the full unit test suite**

```bash
pytest tests/unit/ -v -m "not integration"
```

Expected: All tests PASS

- [ ] **Step 3: Smoke-test `_load_or_fetch_ohlcv` locally (optional, requires network)**

```bash
python -c "
from tradingagents.dataflows.stockstats_utils import _load_or_fetch_ohlcv
df = _load_or_fetch_ohlcv('STM')
print('Rows:', len(df))
print('Columns:', list(df.columns))
print('Last close:', df['Close'].iloc[-1] if 'Close' in df.columns else 'N/A')
"
```

Expected: ~3700+ rows, no `.1`/`.2` column suffixes, last close in the $30–50 range for STM.

- [ ] **Step 4: Final commit**

```bash
git commit --allow-empty -m "chore(ohlcv): purge data_cache/ to remove contaminated files"
```

---

## Self-Review Checklist

- [x] **Spec coverage:** Layer 1 (Task 2), Layer 2 (Task 3), Layer 3 (Task 8 - manual purge), Layer 4 (Task 6), Layer 5 (Task 5), Layer 6 (Task 4) — all 6 layers covered
- [x] **All 9 call sites:** stockstats_utils, peer_comparison ×2, macro_regime, market_prices, yfinance_scanner ×3, selection_reflector — all in Task 7
- [x] **Config keys:** Both keys added in Task 1 with env-var override verification
- [x] **No placeholders:** Every step has exact code, commands, and expected output
- [x] **Type consistency:** `safe_yf_download()` defined in Task 2, used in Task 7; `_has_contaminated_columns()` defined in Task 3; `_assert_sufficient_rows()` defined in Task 5; `_is_close_plausible()` defined in Task 6 — all names are consistent
- [x] **Tests use monkeypatch/mock only** — no network calls (pytest-socket blocks network in unit tests)
