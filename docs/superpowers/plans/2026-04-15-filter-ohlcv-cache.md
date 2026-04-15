# Filter OHLCV Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace three per-ticker yfinance HTTP calls in the filter stage with OHLCV cache lookups, eliminating rate limit errors that drop candidates before they reach the ranker.

**Architecture:** Load `download_ohlcv_cached()` once at the start of `CandidateFilter.filter()` for the ~60 candidate tickers, pass the resulting dict into `_filter_and_enrich_candidates()`, and replace all three yfinance call sites (current price, intraday check, recent-move check) with cache lookups. The existing `get_stock_price()` call remains as a fallback for tickers missing from the cache.

**Tech Stack:** Python, pandas, `tradingagents/dataflows/data_cache/ohlcv_cache.py` (`download_ohlcv_cached`), `tradingagents/dataflows/discovery/filter.py`

---

## File Map

| File | Change |
|---|---|
| `tradingagents/dataflows/discovery/filter.py` | Main changes: load cache in `filter()`, remove `_fetch_batch_prices()`, update `_filter_and_enrich_candidates()` signature and three call sites |
| `tests/test_filter_ohlcv_cache.py` | New test file |

---

### Task 1: Write failing tests

**Files:**
- Create: `tests/test_filter_ohlcv_cache.py`

- [ ] **Step 1: Create the test file**

```python
# tests/test_filter_ohlcv_cache.py
"""Tests for OHLCV-cache-backed filter enrichment."""
import pandas as pd
import pytest
from unittest.mock import MagicMock, patch


def _make_ohlcv(closes: list[float]) -> pd.DataFrame:
    """Build a minimal OHLCV DataFrame from a list of closing prices."""
    dates = pd.date_range("2026-01-01", periods=len(closes), freq="B")
    return pd.DataFrame(
        {
            "Open": closes,
            "High": closes,
            "Low": closes,
            "Close": closes,
            "Volume": [1_000_000] * len(closes),
        },
        index=dates,
    )


def _make_filter(config_overrides=None):
    """Instantiate a CandidateFilter with minimal config."""
    from tradingagents.dataflows.discovery.filter import CandidateFilter

    config = {
        "discovery": {
            "ohlcv_cache_dir": "data/ohlcv_cache",
            "filters": {
                "min_average_volume": 0,
                "volume_lookback_days": 10,
                "filter_same_day_movers": True,
                "intraday_movement_threshold": 10.0,
                "filter_recent_movers": True,
                "recent_movement_lookback_days": 7,
                "recent_movement_threshold": 10.0,
                "recent_mover_action": "filter",
                "volume_cache_key": "default",
                "min_market_cap": 0,
                "compression_atr_pct_max": 2.0,
                "compression_bb_width_max": 6.0,
                "compression_min_volume_ratio": 1.3,
                "filter_fundamental_risk": False,
                "min_z_score": None,
                "min_f_score": None,
            },
            "enrichment": {
                "batch_news_vendor": "google",
                "batch_news_batch_size": 150,
                "news_lookback_days": 0.5,
                "context_max_snippets": 2,
                "context_snippet_max_chars": 140,
            },
            "max_candidates_to_analyze": 200,
            "analyze_all_candidates": False,
            "final_recommendations": 15,
            "truncate_ranking_context": False,
            "max_news_chars": 500,
            "max_insider_chars": 300,
            "max_recommendations_chars": 300,
            "log_tool_calls": False,
            "log_tool_calls_console": False,
            "log_prompts_console": False,
            "tool_log_max_chars": 10_000,
            "tool_log_exclude": [],
        }
    }
    if config_overrides:
        config["discovery"]["filters"].update(config_overrides)
    return CandidateFilter(config)


def test_current_price_comes_from_ohlcv_cache():
    """current_price on the candidate should be the last close from the OHLCV cache."""
    closes = [100.0] * 210 + [123.45]  # last close = 123.45
    ohlcv_data = {"AAPL": _make_ohlcv(closes)}

    f = _make_filter()
    candidate = {"ticker": "AAPL", "source": "test", "context": "test", "priority": "medium"}

    price = f._price_from_cache("AAPL", ohlcv_data)
    assert price == pytest.approx(123.45)


def test_intraday_check_from_cache_not_moved():
    """intraday check: <10% day-over-day change → already_moved=False."""
    closes = [100.0] * 210 + [105.0]  # +5% last day — under threshold
    ohlcv_data = {"AAPL": _make_ohlcv(closes)}

    f = _make_filter()
    result = f._intraday_from_cache("AAPL", ohlcv_data, threshold=10.0)
    assert result["already_moved"] is False
    assert result["intraday_change_pct"] == pytest.approx(5.0)


def test_intraday_check_from_cache_moved():
    """intraday check: >10% day-over-day change → already_moved=True."""
    closes = [100.0] * 210 + [115.0]  # +15% last day — over threshold
    ohlcv_data = {"AAPL": _make_ohlcv(closes)}

    f = _make_filter()
    result = f._intraday_from_cache("AAPL", ohlcv_data, threshold=10.0)
    assert result["already_moved"] is True
    assert result["intraday_change_pct"] == pytest.approx(15.0)


def test_recent_move_check_from_cache_leading():
    """recent-move check: <10% change over 7 days → status=leading."""
    closes = [100.0] * 205 + [103.0] * 7  # flat last 7 days
    ohlcv_data = {"AAPL": _make_ohlcv(closes)}

    f = _make_filter()
    result = f._recent_move_from_cache("AAPL", ohlcv_data, lookback_days=7, threshold=10.0)
    assert result["status"] == "leading"
    assert abs(result["price_change_pct"]) < 10.0


def test_recent_move_check_from_cache_lagging():
    """recent-move check: >10% change over 7 days → status=lagging."""
    closes = [100.0] * 205 + [100.0] * 6 + [115.0]  # +15% in last day within window
    ohlcv_data = {"AAPL": _make_ohlcv(closes)}

    f = _make_filter()
    result = f._recent_move_from_cache("AAPL", ohlcv_data, lookback_days=7, threshold=10.0)
    assert result["status"] == "lagging"


def test_cache_miss_returns_none():
    """If ticker is not in ohlcv_data, helper returns None."""
    f = _make_filter()
    assert f._price_from_cache("MISSING", {}) is None
    assert f._intraday_from_cache("MISSING", {}, threshold=10.0) is None
    assert f._recent_move_from_cache("MISSING", {}, lookback_days=7, threshold=10.0) is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/youssefaitousarrah/Documents/TradingAgents
python -m pytest tests/test_filter_ohlcv_cache.py -v 2>&1 | tail -20
```

Expected: All 5 tests FAIL with `AttributeError: 'CandidateFilter' object has no attribute '_price_from_cache'`

---

### Task 2: Add the three cache helper methods

**Files:**
- Modify: `tradingagents/dataflows/discovery/filter.py`

- [ ] **Step 1: Add import at top of filter.py**

In `tradingagents/dataflows/discovery/filter.py`, add to the existing imports block (after line 6, `import pandas as pd`):

```python
from tradingagents.dataflows.data_cache.ohlcv_cache import download_ohlcv_cached
```

- [ ] **Step 2: Add the three helper methods to `CandidateFilter`**

Add these three methods to `CandidateFilter` class, just before the `_fetch_batch_volume` method (around line 301):

```python
def _price_from_cache(
    self, ticker: str, ohlcv_data: Dict[str, Any]
) -> Any:
    """Return last closing price from OHLCV cache, or None if ticker missing."""
    df = ohlcv_data.get(ticker.upper())
    if df is None or df.empty or "Close" not in df.columns:
        return None
    close = df["Close"].dropna()
    if close.empty:
        return None
    return float(close.iloc[-1])

def _intraday_from_cache(
    self, ticker: str, ohlcv_data: Dict[str, Any], threshold: float
) -> Any:
    """Compute day-over-day % change from last two daily closes.

    Returns dict with 'already_moved' (bool) and 'intraday_change_pct' (float),
    or None if ticker missing from cache or insufficient data.
    """
    df = ohlcv_data.get(ticker.upper())
    if df is None or df.empty or "Close" not in df.columns:
        return None
    close = df["Close"].dropna()
    if len(close) < 2:
        return None
    prev_close = float(close.iloc[-2])
    last_close = float(close.iloc[-1])
    if prev_close <= 0:
        return None
    pct = (last_close - prev_close) / prev_close * 100
    return {
        "already_moved": pct > threshold,
        "intraday_change_pct": round(pct, 2),
    }

def _recent_move_from_cache(
    self, ticker: str, ohlcv_data: Dict[str, Any], lookback_days: int, threshold: float
) -> Any:
    """Compute % change over last N daily closes.

    Returns dict with 'status' ('leading'|'lagging') and 'price_change_pct' (float),
    or None if ticker missing from cache or insufficient data.
    """
    df = ohlcv_data.get(ticker.upper())
    if df is None or df.empty or "Close" not in df.columns:
        return None
    close = df["Close"].dropna()
    if len(close) < lookback_days + 1:
        return None
    price_start = float(close.iloc[-(lookback_days + 1)])
    price_end = float(close.iloc[-1])
    if price_start <= 0:
        return None
    pct = (price_end - price_start) / price_start * 100
    reacted = abs(pct) >= threshold
    return {
        "status": "lagging" if reacted else "leading",
        "price_change_pct": round(pct, 2),
    }
```

- [ ] **Step 3: Run tests — should pass now**

```bash
python -m pytest tests/test_filter_ohlcv_cache.py -v 2>&1 | tail -20
```

Expected: All 5 tests PASS

- [ ] **Step 4: Commit**

```bash
git add tradingagents/dataflows/discovery/filter.py tests/test_filter_ohlcv_cache.py
git commit -m "feat(filter): add OHLCV cache helper methods for price/intraday/recent-move"
```

---

### Task 3: Load OHLCV cache in `filter()` and wire into `_filter_and_enrich_candidates()`

**Files:**
- Modify: `tradingagents/dataflows/discovery/filter.py:151-188` (the `filter()` method)
- Modify: `tradingagents/dataflows/discovery/filter.py:409` (`_filter_and_enrich_candidates()` signature)

- [ ] **Step 1: Update `filter()` to load OHLCV cache and remove `_fetch_batch_prices` call**

Replace lines 172-188 in `filter()`:

```python
        # Was:
        volume_by_ticker = self._fetch_batch_volume(state, candidates)
        news_by_ticker = self._fetch_batch_news(start_date, end_date, candidates)
        price_by_ticker = self._fetch_batch_prices(candidates)

        (
            filtered_candidates,
            filtered_reasons,
            failed_tickers,
            delisted_cache,
        ) = self._filter_and_enrich_candidates(
            state=state,
            candidates=candidates,
            volume_by_ticker=volume_by_ticker,
            news_by_ticker=news_by_ticker,
            price_by_ticker=price_by_ticker,
            end_date=end_date,
        )
```

With:

```python
        volume_by_ticker = self._fetch_batch_volume(state, candidates)
        news_by_ticker = self._fetch_batch_news(start_date, end_date, candidates)

        # Load OHLCV cache for candidate tickers — replaces per-ticker yfinance calls
        cache_dir = self.config.get("discovery", {}).get("ohlcv_cache_dir", "data/ohlcv_cache")
        candidate_tickers = [c["ticker"].upper() for c in candidates if c.get("ticker")]
        logger.info(f"Loading OHLCV cache for {len(candidate_tickers)} candidate tickers...")
        ohlcv_data = download_ohlcv_cached(candidate_tickers, period="1y", cache_dir=cache_dir)
        logger.info(f"OHLCV cache loaded for {len(ohlcv_data)}/{len(candidate_tickers)} tickers")

        (
            filtered_candidates,
            filtered_reasons,
            failed_tickers,
            delisted_cache,
        ) = self._filter_and_enrich_candidates(
            state=state,
            candidates=candidates,
            volume_by_ticker=volume_by_ticker,
            news_by_ticker=news_by_ticker,
            ohlcv_data=ohlcv_data,
            end_date=end_date,
        )
```

- [ ] **Step 2: Update `_filter_and_enrich_candidates()` signature**

Change the method signature at line ~409 from:

```python
    def _filter_and_enrich_candidates(
        self,
        state: Dict[str, Any],
        candidates: List[Dict[str, Any]],
        volume_by_ticker: Dict[str, Any],
        news_by_ticker: Dict[str, Any],
        price_by_ticker: Dict[str, float],
        end_date: str,
    ):
```

To:

```python
    def _filter_and_enrich_candidates(
        self,
        state: Dict[str, Any],
        candidates: List[Dict[str, Any]],
        volume_by_ticker: Dict[str, Any],
        news_by_ticker: Dict[str, Any],
        ohlcv_data: Dict[str, Any],
        end_date: str,
    ):
```

- [ ] **Step 3: Run existing tests to make sure nothing is broken**

```bash
python -m pytest tests/test_filter_ohlcv_cache.py -v 2>&1 | tail -10
```

Expected: All 5 PASS (the helper methods don't depend on the signature change)

- [ ] **Step 4: Commit**

```bash
git add tradingagents/dataflows/discovery/filter.py
git commit -m "feat(filter): load OHLCV cache in filter() and update _filter_and_enrich_candidates signature"
```

---

### Task 4: Replace the three yfinance call sites in `_filter_and_enrich_candidates`

**Files:**
- Modify: `tradingagents/dataflows/discovery/filter.py:435-534`

- [ ] **Step 1: Replace `check_intraday_movement` call site**

Find this block (around line 440):

```python
                if self.filter_same_day_movers:
                    from tradingagents.dataflows.y_finance import check_intraday_movement

                    try:
                        intraday_check = check_intraday_movement(
                            ticker=ticker, movement_threshold=self.intraday_movement_threshold
                        )

                        # Skip if already moved significantly today
                        if intraday_check.get("already_moved"):
                            filtered_reasons["intraday_moved"] += 1
                            intraday_pct = intraday_check.get("intraday_change_pct", 0)
                            logger.info(
                                f"Filtered {ticker}: Already moved {intraday_pct:+.1f}% today (stale)"
                            )
                            continue

                        # Add intraday data to candidate metadata for ranking
                        cand["intraday_change_pct"] = intraday_check.get("intraday_change_pct", 0)

                    except Exception as e:
                        # Don't filter out if check fails, just log
                        logger.warning(f"Could not check intraday movement for {ticker}: {e}")
```

Replace with:

```python
                if self.filter_same_day_movers:
                    intraday_check = self._intraday_from_cache(
                        ticker, ohlcv_data, self.intraday_movement_threshold
                    )
                    if intraday_check is not None:
                        if intraday_check.get("already_moved"):
                            filtered_reasons["intraday_moved"] += 1
                            intraday_pct = intraday_check.get("intraday_change_pct", 0)
                            logger.info(
                                f"Filtered {ticker}: Already moved {intraday_pct:+.1f}% today (stale)"
                            )
                            continue
                        cand["intraday_change_pct"] = intraday_check.get("intraday_change_pct", 0)
```

- [ ] **Step 2: Replace `check_if_price_reacted` call site**

Find this block (around line 465):

```python
                if self.filter_recent_movers:
                    from tradingagents.dataflows.y_finance import check_if_price_reacted

                    try:
                        reaction = check_if_price_reacted(
                            ticker=ticker,
                            lookback_days=self.recent_movement_lookback_days,
                            reaction_threshold=self.recent_movement_threshold,
                        )
                        cand["recent_change_pct"] = reaction.get("price_change_pct")
                        cand["recent_move_status"] = reaction.get("status")

                        if reaction.get("status") == "lagging":
                            if self.recent_mover_action == "filter":
                                filtered_reasons["recent_moved"] += 1
                                change_pct = reaction.get("price_change_pct", 0)
                                logger.info(
                                    f"Filtered {ticker}: Already moved {change_pct:+.1f}% in last "
                                    f"{self.recent_movement_lookback_days} days"
                                )
                                continue
                            if self.recent_mover_action == "deprioritize":
                                cand["priority"] = "low"
                                existing_context = cand.get("context", "")
                                change_pct = reaction.get("price_change_pct", 0)
                                cand["context"] = (
                                    f"{existing_context} | ⚠️ Recent move: {change_pct:+.1f}% "
                                    f"over {self.recent_movement_lookback_days}d"
                                )
                    except Exception as e:
                        logger.warning(f"Could not check recent movement for {ticker}: {e}")
```

Replace with:

```python
                if self.filter_recent_movers:
                    reaction = self._recent_move_from_cache(
                        ticker,
                        ohlcv_data,
                        self.recent_movement_lookback_days,
                        self.recent_movement_threshold,
                    )
                    if reaction is not None:
                        cand["recent_change_pct"] = reaction.get("price_change_pct")
                        cand["recent_move_status"] = reaction.get("status")

                        if reaction.get("status") == "lagging":
                            if self.recent_mover_action == "filter":
                                filtered_reasons["recent_moved"] += 1
                                change_pct = reaction.get("price_change_pct", 0)
                                logger.info(
                                    f"Filtered {ticker}: Already moved {change_pct:+.1f}% in last "
                                    f"{self.recent_movement_lookback_days} days"
                                )
                                continue
                            if self.recent_mover_action == "deprioritize":
                                cand["priority"] = "low"
                                existing_context = cand.get("context", "")
                                change_pct = reaction.get("price_change_pct", 0)
                                cand["context"] = (
                                    f"{existing_context} | ⚠️ Recent move: {change_pct:+.1f}% "
                                    f"over {self.recent_movement_lookback_days}d"
                                )
```

- [ ] **Step 3: Replace `get_stock_price` / `price_by_ticker` call site**

Find this block (around line 520):

```python
                try:
                    from tradingagents.dataflows.y_finance import get_fundamentals, get_stock_price

                    # Get current price — prefer batch result, fall back to per-ticker
                    current_price = price_by_ticker.get(ticker.upper())
                    if current_price is None:
                        current_price = get_stock_price(ticker)
                    cand["current_price"] = current_price
```

Replace with:

```python
                try:
                    from tradingagents.dataflows.y_finance import get_fundamentals, get_stock_price

                    # Get current price — prefer OHLCV cache, fall back to per-ticker yfinance
                    current_price = self._price_from_cache(ticker, ohlcv_data)
                    if current_price is None:
                        current_price = get_stock_price(ticker)
                    cand["current_price"] = current_price
```

- [ ] **Step 4: Run all filter tests**

```bash
python -m pytest tests/test_filter_ohlcv_cache.py -v 2>&1 | tail -10
```

Expected: All 5 PASS

- [ ] **Step 5: Commit**

```bash
git add tradingagents/dataflows/discovery/filter.py
git commit -m "feat(filter): replace per-ticker yfinance calls with OHLCV cache lookups"
```

---

### Task 5: Remove `_fetch_batch_prices` method

**Files:**
- Modify: `tradingagents/dataflows/discovery/filter.py:357-407`

- [ ] **Step 1: Delete `_fetch_batch_prices`**

Remove the entire method from line 357 to 407:

```python
    def _fetch_batch_prices(self, candidates: List[Dict[str, Any]]) -> Dict[str, float]:
        """Batch-fetch current prices for all candidates in one request.
        ...
        """
        # ... entire method body
```

The method is no longer called from anywhere after Task 3.

- [ ] **Step 2: Verify tests still pass**

```bash
python -m pytest tests/test_filter_ohlcv_cache.py -v 2>&1 | tail -10
```

Expected: All 5 PASS

- [ ] **Step 3: Commit**

```bash
git add tradingagents/dataflows/discovery/filter.py
git commit -m "refactor(filter): remove _fetch_batch_prices (replaced by OHLCV cache)"
```

---

### Task 6: Push and trigger a discovery run to validate

- [ ] **Step 1: Push all commits**

```bash
git push origin main
```

- [ ] **Step 2: Trigger a discovery run**

```bash
gh workflow run "Daily Discovery" --repo Aitous/TradingAgents --ref main
```

- [ ] **Step 3: Monitor and verify**

```bash
gh run list --repo Aitous/TradingAgents --workflow "Daily Discovery" --limit 1
```

Watch for:
- Zero `"Too Many Requests"` errors in the filter stage
- `"OHLCV cache loaded for X/Y tickers"` log line showing high hit rate (expect >95%)
- `"Starting candidates: N"` in filter summary — should be close to the full scan count (~60), not 11
- Ranker receiving more than 11 candidates
- Final recommendations > 2 picks
