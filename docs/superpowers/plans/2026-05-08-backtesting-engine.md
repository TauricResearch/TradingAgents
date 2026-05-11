# Backtesting Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `tradingagents/backtesting/` — a module that runs the full 9-agent pipeline against historical dates and reports signal quality, returns, alpha, and risk metrics.

**Architecture:** `BacktestEngine` orchestrates pipeline runs per `(ticker, date)` pair, writes results incrementally to JSONL (crash-safe, resumable). `BacktestReport` is a pure-computation layer that takes the saved results, fetches forward returns via yfinance, and computes all metrics without re-running the pipeline. CLI entry point is `python -m tradingagents backtest`.

**Tech Stack:** Python 3.10+, pandas (date generation), numpy (busday_count), yfinance (return fetching), tqdm (CLI progress), dataclasses, concurrent.futures, pytest

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `tradingagents/backtesting/__init__.py` | Create | Package exports |
| `tradingagents/backtesting/models.py` | Create | `BacktestResult`, `DIRECTION_MAP`, `derive_direction` |
| `tradingagents/backtesting/returns.py` | Create | `fetch_returns()` — yfinance I/O, extracted from `trading_graph.py` |
| `tradingagents/backtesting/engine.py` | Create | `BacktestEngine`, `generate_dates`, JSONL helpers |
| `tradingagents/backtesting/report.py` | Create | `BacktestReport`, `BacktestSummary`, `is_win`, `get_holding_days` |
| `tradingagents/backtesting/__main__.py` | Create | `python -m tradingagents.backtesting` entry |
| `tradingagents/backtesting/cli.py` | Create | `build_parser()`, `main()` |
| `tradingagents/__main__.py` | Create | Top-level dispatcher: `python -m tradingagents backtest` |
| `tests/backtesting/__init__.py` | Create | Empty — makes it a package |
| `tests/backtesting/test_models.py` | Create | Tests for models.py |
| `tests/backtesting/test_returns.py` | Create | Tests for returns.py (mock yfinance) |
| `tests/backtesting/test_engine.py` | Create | Tests for engine.py (mock propagate) |
| `tests/backtesting/test_report.py` | Create | Tests for report.py (mock fetch_returns) |
| `tests/backtesting/test_cli.py` | Create | Tests for CLI arg parsing |

---

## Task 1: models.py — BacktestResult and direction mapping

**Files:**
- Create: `tradingagents/backtesting/models.py`
- Create: `tests/backtesting/__init__.py`
- Create: `tests/backtesting/test_models.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/backtesting/__init__.py` (empty), then create `tests/backtesting/test_models.py`:

```python
# tests/backtesting/test_models.py
from datetime import datetime
import pytest

from tradingagents.backtesting.models import (
    DIRECTION_MAP, BacktestResult, derive_direction,
)


@pytest.mark.unit
class TestDeriveDirection:
    def test_buy(self):
        assert derive_direction("Buy") == +1

    def test_overweight(self):
        assert derive_direction("Overweight") == +1

    def test_hold(self):
        assert derive_direction("Hold") == 0

    def test_underweight(self):
        assert derive_direction("Underweight") == -1

    def test_sell(self):
        assert derive_direction("Sell") == -1

    def test_none_rating_returns_none(self):
        assert derive_direction(None) is None

    def test_unknown_rating_returns_none_not_zero(self):
        # Unknown string must return None — not 0 (which means Hold)
        assert derive_direction("StrongBuy") is None


@pytest.mark.unit
class TestBacktestResult:
    def test_defaults(self):
        r = BacktestResult(ticker="NVDA", trade_date="2024-01-15")
        assert r.rating is None
        assert r.direction is None
        assert r.error is None
        assert r.raw_output == ""
        assert r.run_duration_seconds == 0.0

    def test_trade_date_iso_parseable(self):
        r = BacktestResult(ticker="AAPL", trade_date="2024-06-01")
        # Must not raise — enforces ISO-8601 format contract
        datetime.strptime(r.trade_date, "%Y-%m-%d")

    def test_error_result_has_no_rating(self):
        r = BacktestResult(ticker="TSLA", trade_date="2024-03-01", error="timeout")
        assert r.rating is None
        assert r.direction is None
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/backtesting/test_models.py -v
```

Expected: `ModuleNotFoundError: No module named 'tradingagents.backtesting'`

- [ ] **Step 3: Create the package and implement models.py**

Create `tradingagents/backtesting/__init__.py` (empty for now):

```python
```

Create `tradingagents/backtesting/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

DIRECTION_MAP: dict[str, int] = {
    "Buy": +1, "Overweight": +1,
    "Hold": 0,
    "Underweight": -1, "Sell": -1,
}


def derive_direction(rating: Optional[str]) -> Optional[int]:
    """Return None for missing or unrecognised ratings — not 0 (which means Hold)."""
    if rating is None:
        return None
    return DIRECTION_MAP.get(rating, None)


@dataclass
class BacktestResult:
    ticker: str
    trade_date: str                       # ISO-8601 "YYYY-MM-DD" — always this format
    rating: Optional[str] = None          # 5-tier PM output: Buy/Overweight/Hold/Underweight/Sell
    direction: Optional[int] = None       # +1, 0, -1, or None for failed/unknown
    raw_output: str = ""                  # full Portfolio Manager markdown
    run_duration_seconds: float = 0.0
    error: Optional[str] = None           # exception message; rating/direction are None when set
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/backtesting/test_models.py -v
```

Expected: all 9 tests PASS

- [ ] **Step 5: Commit**

```
git add tradingagents/backtesting/__init__.py tradingagents/backtesting/models.py tests/backtesting/__init__.py tests/backtesting/test_models.py
git commit -m "feat(backtesting): add BacktestResult dataclass and direction mapping"
```

---

## Task 2: returns.py — standalone fetch_returns

**Files:**
- Create: `tradingagents/backtesting/returns.py`
- Create: `tests/backtesting/test_returns.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/backtesting/test_returns.py`:

```python
# tests/backtesting/test_returns.py
import pandas as pd
import pytest
from unittest.mock import MagicMock, patch


def _make_prices(prices: list[float]) -> pd.DataFrame:
    dates = pd.date_range(start="2024-01-15", periods=len(prices), freq="B")
    return pd.DataFrame({"Close": prices}, index=dates)


@pytest.mark.unit
class TestFetchReturns:
    def test_basic_long_gain(self):
        from tradingagents.backtesting.returns import fetch_returns

        stock = _make_prices([100.0, 110.0, 108.0])
        spy = _make_prices([400.0, 404.0, 402.0])

        def side_effect(sym):
            m = MagicMock()
            m.history.return_value = stock if sym == "NVDA" else spy
            return m

        with patch("tradingagents.backtesting.returns.yf.Ticker", side_effect=side_effect):
            raw, alpha, days = fetch_returns("NVDA", "2024-01-15", holding_days=1)

        assert raw == pytest.approx(0.10)          # (110-100)/100
        assert alpha == pytest.approx(0.10 - 0.01) # stock 10% - SPY 1%
        assert days == 1

    def test_insufficient_stock_data_returns_none(self):
        from tradingagents.backtesting.returns import fetch_returns

        with patch("tradingagents.backtesting.returns.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.history.return_value = pd.DataFrame()
            raw, alpha, days = fetch_returns("DELISTED", "2024-01-15", holding_days=5)

        assert (raw, alpha, days) == (None, None, None)

    def test_network_exception_returns_none(self):
        from tradingagents.backtesting.returns import fetch_returns

        with patch("tradingagents.backtesting.returns.yf.Ticker") as mock_ticker:
            mock_ticker.side_effect = Exception("connection refused")
            raw, alpha, days = fetch_returns("NVDA", "2024-01-15", holding_days=5)

        assert (raw, alpha, days) == (None, None, None)

    def test_actual_days_clamped_to_available_data(self):
        from tradingagents.backtesting.returns import fetch_returns

        # Only 2 rows available — actual_days must be min(holding_days, len-1)
        stock = _make_prices([100.0, 105.0])
        spy = _make_prices([400.0, 402.0])

        def side_effect(sym):
            m = MagicMock()
            m.history.return_value = stock if sym == "NVDA" else spy
            return m

        with patch("tradingagents.backtesting.returns.yf.Ticker", side_effect=side_effect):
            raw, alpha, days = fetch_returns("NVDA", "2024-01-15", holding_days=10)

        assert days == 1   # only 1 usable interval in 2-row series
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/backtesting/test_returns.py -v
```

Expected: `ImportError: cannot import name 'fetch_returns'`

- [ ] **Step 3: Implement returns.py**

Create `tradingagents/backtesting/returns.py`:

```python
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple

import yfinance as yf

logger = logging.getLogger(__name__)


def fetch_returns(
    ticker: str,
    trade_date: str,
    holding_days: int,
) -> Tuple[Optional[float], Optional[float], Optional[int]]:
    """Fetch (raw_return, alpha_vs_spy, actual_holding_days) via yfinance.

    Requires network access. Returns (None, None, None) when price data is
    unavailable — ticker too recent, delisted, or a network error occurred.
    When mocking in tests, patch at tradingagents.backtesting.returns.fetch_returns.
    """
    try:
        start = datetime.strptime(trade_date, "%Y-%m-%d")
        end = start + timedelta(days=holding_days + 7)  # buffer for weekends/holidays
        end_str = end.strftime("%Y-%m-%d")

        stock = yf.Ticker(ticker).history(start=trade_date, end=end_str)
        spy = yf.Ticker("SPY").history(start=trade_date, end=end_str)

        if len(stock) < 2 or len(spy) < 2:
            return None, None, None

        actual_days = min(holding_days, len(stock) - 1, len(spy) - 1)
        raw = float(
            (stock["Close"].iloc[actual_days] - stock["Close"].iloc[0])
            / stock["Close"].iloc[0]
        )
        spy_ret = float(
            (spy["Close"].iloc[actual_days] - spy["Close"].iloc[0])
            / spy["Close"].iloc[0]
        )
        alpha = raw - spy_ret
        return raw, alpha, actual_days
    except Exception as exc:
        logger.warning(
            "Could not fetch returns for %s on %s: %s", ticker, trade_date, exc
        )
        return None, None, None
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/backtesting/test_returns.py -v
```

Expected: all 4 tests PASS

- [ ] **Step 5: Commit**

```
git add tradingagents/backtesting/returns.py tests/backtesting/test_returns.py
git commit -m "feat(backtesting): add standalone fetch_returns (extracted from trading_graph)"
```

---

## Task 3: engine.py — JSONL helpers and date generation

**Files:**
- Create: `tradingagents/backtesting/engine.py` (partial — helpers only)
- Create: `tests/backtesting/test_engine.py` (helpers section)

- [ ] **Step 1: Write the failing tests**

Create `tests/backtesting/test_engine.py`:

```python
# tests/backtesting/test_engine.py
import json
from datetime import datetime
import pytest

from tradingagents.backtesting.models import BacktestResult


@pytest.mark.unit
class TestGenerateDates:
    def test_monthly(self):
        from tradingagents.backtesting.engine import generate_dates
        dates = generate_dates("2024-01-01", "2024-03-31", "monthly")
        assert dates == ["2024-01-01", "2024-02-01", "2024-03-01"]

    def test_weekly_all_mondays(self):
        from tradingagents.backtesting.engine import generate_dates
        dates = generate_dates("2024-01-01", "2024-01-29", "weekly")
        for d in dates:
            assert datetime.strptime(d, "%Y-%m-%d").weekday() == 0  # Monday

    def test_biweekly(self):
        from tradingagents.backtesting.engine import generate_dates
        dates = generate_dates("2024-01-01", "2024-02-28", "biweekly")
        assert len(dates) == 2

    def test_invalid_freq_raises(self):
        from tradingagents.backtesting.engine import generate_dates
        with pytest.raises(ValueError, match="Unsupported freq"):
            generate_dates("2024-01-01", "2024-12-31", "daily")


@pytest.mark.unit
class TestJSONLHelpers:
    def test_load_completed_pairs_missing_file(self, tmp_path):
        from tradingagents.backtesting.engine import load_completed_pairs
        result = load_completed_pairs(str(tmp_path / "missing.jsonl"))
        assert result == set()

    def test_load_completed_pairs_skips_errors(self, tmp_path):
        from tradingagents.backtesting.engine import load_completed_pairs
        f = tmp_path / "results.jsonl"
        f.write_text(
            '{"ticker":"NVDA","trade_date":"2024-01-01","error":null,"rating":"Buy",'
            '"direction":1,"raw_output":"","run_duration_seconds":10.0}\n'
            '{"ticker":"NVDA","trade_date":"2024-02-01","error":"timeout","rating":null,'
            '"direction":null,"raw_output":"","run_duration_seconds":0.0}\n',
            encoding="utf-8",
        )
        completed = load_completed_pairs(str(f))
        assert ("NVDA", "2024-01-01") in completed
        assert ("NVDA", "2024-02-01") not in completed  # failed → retry on resume

    def test_append_result_writes_valid_json(self, tmp_path):
        from tradingagents.backtesting.engine import append_result
        f = tmp_path / "out.jsonl"
        r = BacktestResult(ticker="AAPL", trade_date="2024-01-15", rating="Buy", direction=1)
        append_result(str(f), r)
        lines = f.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        obj = json.loads(lines[0])
        assert obj["ticker"] == "AAPL"
        assert obj["rating"] == "Buy"
        assert obj["error"] is None

    def test_append_result_creates_parent_dirs(self, tmp_path):
        from tradingagents.backtesting.engine import append_result
        nested = str(tmp_path / "deep" / "path" / "out.jsonl")
        append_result(nested, BacktestResult(ticker="X", trade_date="2024-01-01"))
        assert (tmp_path / "deep" / "path" / "out.jsonl").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/backtesting/test_engine.py -v
```

Expected: `ImportError: cannot import name 'generate_dates'`

- [ ] **Step 3: Implement engine.py helpers**

Create `tradingagents/backtesting/engine.py`:

```python
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Optional, Set, Tuple

import pandas as pd

from .models import BacktestResult

logger = logging.getLogger(__name__)

FREQ_MAP: dict[str, str] = {
    "monthly": "MS",
    "weekly": "W-MON",
    "biweekly": "2W-MON",
}


def generate_dates(start_date: str, end_date: str, freq: str) -> list[str]:
    """Return business-day-aligned ISO date strings for the backtest range."""
    pd_freq = FREQ_MAP.get(freq)
    if pd_freq is None:
        raise ValueError(f"Unsupported freq {freq!r}. Use: {list(FREQ_MAP)}")
    dates = pd.date_range(start=start_date, end=end_date, freq=pd_freq)
    aligned = []
    for d in dates:
        if d.dayofweek >= 5:  # Saturday=5, Sunday=6
            d = d + pd.offsets.BDay(1)
        aligned.append(d.strftime("%Y-%m-%d"))
    return aligned


def load_completed_pairs(output_file: str) -> Set[Tuple[str, str]]:
    """Return (ticker, trade_date) pairs that completed without error."""
    path = Path(output_file)
    if not path.exists():
        return set()
    completed: Set[Tuple[str, str]] = set()
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if obj.get("error") is None:
                    completed.add((obj["ticker"], obj["trade_date"]))
            except json.JSONDecodeError:
                continue
    return completed


def append_result(output_file: str, result: BacktestResult) -> None:
    """Append one BacktestResult as a newline-delimited JSON record."""
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(result)) + "\n")
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/backtesting/test_engine.py::TestGenerateDates tests/backtesting/test_engine.py::TestJSONLHelpers -v
```

Expected: all 8 tests PASS

- [ ] **Step 5: Commit**

```
git add tradingagents/backtesting/engine.py tests/backtesting/test_engine.py
git commit -m "feat(backtesting): add JSONL helpers and date generation"
```

---

## Task 4: engine.py — BacktestEngine class

**Files:**
- Modify: `tradingagents/backtesting/engine.py` (add BacktestEngine class)
- Modify: `tests/backtesting/test_engine.py` (add engine tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/backtesting/test_engine.py`:

```python
@pytest.mark.unit
class TestBacktestEngine:
    def test_run_calls_propagate_once_per_date(self, tmp_path):
        from unittest.mock import MagicMock, patch
        from tradingagents.backtesting.engine import BacktestEngine

        with patch("tradingagents.backtesting.engine.TradingAgentsGraph") as MockGraph:
            instance = MockGraph.return_value
            instance.propagate.return_value = (
                {"final_trade_decision": "**Rating**: Buy\n"},
                "Buy",
            )
            engine = BacktestEngine(
                tickers=["NVDA"],
                start_date="2024-01-01",
                end_date="2024-01-31",
                freq="monthly",
                output_file=str(tmp_path / "out.jsonl"),
            )
            results = engine.run()

        assert len(results) == 1
        assert results[0].ticker == "NVDA"
        assert results[0].rating == "Buy"
        assert results[0].direction == 1
        assert results[0].error is None

    def test_run_records_error_without_aborting(self, tmp_path):
        from unittest.mock import MagicMock, patch
        from tradingagents.backtesting.engine import BacktestEngine

        with patch("tradingagents.backtesting.engine.TradingAgentsGraph") as MockGraph:
            instance = MockGraph.return_value
            instance.propagate.side_effect = RuntimeError("LLM unavailable")
            engine = BacktestEngine(
                tickers=["NVDA"],
                start_date="2024-01-01",
                end_date="2024-01-31",
                freq="monthly",
                output_file=str(tmp_path / "out.jsonl"),
            )
            results = engine.run()

        assert len(results) == 1
        assert results[0].error == "LLM unavailable"
        assert results[0].rating is None
        assert results[0].direction is None

    def test_resume_skips_completed_pairs(self, tmp_path):
        from unittest.mock import MagicMock, patch
        from tradingagents.backtesting.engine import BacktestEngine

        out = tmp_path / "out.jsonl"
        out.write_text(
            '{"ticker":"NVDA","trade_date":"2024-01-01","error":null,"rating":"Buy",'
            '"direction":1,"raw_output":"","run_duration_seconds":5.0}\n',
            encoding="utf-8",
        )
        with patch("tradingagents.backtesting.engine.TradingAgentsGraph") as MockGraph:
            instance = MockGraph.return_value
            engine = BacktestEngine(
                tickers=["NVDA"],
                start_date="2024-01-01",
                end_date="2024-01-31",
                freq="monthly",
                output_file=str(out),
            )
            results = engine.run(resume=True)

        instance.propagate.assert_not_called()
        assert results == []

    def test_results_written_to_jsonl(self, tmp_path):
        from unittest.mock import patch
        from tradingagents.backtesting.engine import BacktestEngine
        import json

        out = tmp_path / "out.jsonl"
        with patch("tradingagents.backtesting.engine.TradingAgentsGraph") as MockGraph:
            instance = MockGraph.return_value
            instance.propagate.return_value = ({"final_trade_decision": ""}, "Hold")
            engine = BacktestEngine(
                tickers=["AAPL"],
                start_date="2024-01-01",
                end_date="2024-01-31",
                freq="monthly",
                output_file=str(out),
            )
            engine.run()

        lines = out.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        obj = json.loads(lines[0])
        assert obj["ticker"] == "AAPL"
        assert obj["rating"] == "Hold"
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/backtesting/test_engine.py::TestBacktestEngine -v
```

Expected: `AttributeError: module 'tradingagents.backtesting.engine' has no attribute 'BacktestEngine'`

- [ ] **Step 3: Implement BacktestEngine**

Append to `tradingagents/backtesting/engine.py`:

```python
import hashlib
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from itertools import groupby

from .models import BacktestResult, derive_direction


class BacktestEngine:
    def __init__(
        self,
        tickers: list[str],
        start_date: str,
        end_date: str,
        freq: str = "monthly",
        config: Optional[dict] = None,
        analysts: Optional[list[str]] = None,
        max_workers: int = 2,
        output_file: Optional[str] = None,
    ) -> None:
        self.tickers = tickers
        self.start_date = start_date
        self.end_date = end_date
        self.freq = freq
        self.config = config or {}
        self.analysts = analysts or ["market", "social", "news", "fundamentals"]
        self.max_workers = max_workers

        if output_file is None:
            key = f"{sorted(tickers)}-{start_date}-{end_date}-{freq}"
            h = hashlib.md5(key.encode()).hexdigest()[:8]
            home = os.path.expanduser("~")
            output_file = os.path.join(
                home, ".tradingagents", "backtests", f"{h}.jsonl"
            )
        self.output_file = output_file

    def run(self, resume: bool = False) -> list[BacktestResult]:
        all_dates = generate_dates(self.start_date, self.end_date, self.freq)
        completed = load_completed_pairs(self.output_file) if resume else set()

        # Group remaining (ticker, date) pairs by ticker to preserve date order
        ticker_dates: dict[str, list[str]] = {t: [] for t in self.tickers}
        for ticker in self.tickers:
            for d in all_dates:
                if (ticker, d) not in completed:
                    ticker_dates[ticker].append(d)

        results: list[BacktestResult] = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {
                pool.submit(self._run_ticker, ticker, dates): ticker
                for ticker, dates in ticker_dates.items()
                if dates
            }
            for future in as_completed(futures):
                results.extend(future.result())
        return results

    def _run_ticker(self, ticker: str, dates: list[str]) -> list[BacktestResult]:
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        graph = TradingAgentsGraph(
            selected_analysts=self.analysts,
            config=self.config,
        )
        results = []
        for trade_date in dates:
            result = self._run_one(graph, ticker, trade_date)
            append_result(self.output_file, result)
            results.append(result)
        return results

    def _run_one(
        self, graph, ticker: str, trade_date: str
    ) -> BacktestResult:
        max_retries = 5
        backoff = 1.0
        start = time.monotonic()

        for attempt in range(max_retries):
            try:
                state, rating = graph.propagate(ticker, trade_date)
                duration = time.monotonic() - start
                return BacktestResult(
                    ticker=ticker,
                    trade_date=trade_date,
                    rating=rating,
                    direction=derive_direction(rating),
                    raw_output=state.get("final_trade_decision", ""),
                    run_duration_seconds=round(duration, 2),
                )
            except Exception as exc:
                err_str = str(exc)
                if "429" in err_str and attempt < max_retries - 1:
                    time.sleep(min(backoff, 60.0))
                    backoff *= 2
                    continue
                duration = time.monotonic() - start
                return BacktestResult(
                    ticker=ticker,
                    trade_date=trade_date,
                    error=err_str,
                    run_duration_seconds=round(duration, 2),
                )

        return BacktestResult(
            ticker=ticker,
            trade_date=trade_date,
            error="Max retries exceeded",
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/backtesting/test_engine.py -v
```

Expected: all 12 tests PASS

- [ ] **Step 5: Commit**

```
git add tradingagents/backtesting/engine.py tests/backtesting/test_engine.py
git commit -m "feat(backtesting): add BacktestEngine with resume and rate-limit backoff"
```

---

## Task 5: report.py — helpers

**Files:**
- Create: `tradingagents/backtesting/report.py` (helpers only)
- Create: `tests/backtesting/test_report.py` (helpers section)

- [ ] **Step 1: Write the failing tests**

Create `tests/backtesting/test_report.py`:

```python
# tests/backtesting/test_report.py
import pytest
from typing import Optional


@pytest.mark.unit
class TestIsWin:
    def test_long_up(self):
        from tradingagents.backtesting.report import is_win
        assert is_win(+1, 0.05) is True

    def test_long_down(self):
        from tradingagents.backtesting.report import is_win
        assert is_win(+1, -0.03) is False

    def test_short_down(self):
        from tradingagents.backtesting.report import is_win
        assert is_win(-1, -0.04) is True

    def test_short_up(self):
        from tradingagents.backtesting.report import is_win
        assert is_win(-1, 0.02) is False

    def test_hold_excluded(self):
        from tradingagents.backtesting.report import is_win
        assert is_win(0, 0.05) is None

    def test_tie_excluded(self):
        from tradingagents.backtesting.report import is_win
        assert is_win(+1, 0.0) is None


@pytest.mark.unit
class TestGetHoldingDays:
    def test_override_takes_precedence(self):
        from tradingagents.backtesting.report import get_holding_days
        assert get_holding_days("2024-01-01", "2024-02-01", hold_days_override=5) == 5

    def test_next_signal_date_used(self):
        from tradingagents.backtesting.report import get_holding_days
        # 2024-01-01 (Mon) to 2024-01-08 (Mon) = 5 business days
        days = get_holding_days("2024-01-01", "2024-01-08", hold_days_override=None)
        assert days == 5

    def test_fallback_for_last_date(self):
        from tradingagents.backtesting.report import get_holding_days
        days = get_holding_days("2024-12-01", None, hold_days_override=None)
        assert days == 21

    def test_minimum_one_day(self):
        from tradingagents.backtesting.report import get_holding_days
        # Same date — should not return 0 or negative
        days = get_holding_days("2024-01-01", "2024-01-01", hold_days_override=None)
        assert days >= 1


@pytest.mark.unit
class TestBusinessDaysBetween:
    def test_monday_to_monday(self):
        from tradingagents.backtesting.report import business_days_between
        # 2024-01-01 (Mon) to 2024-01-08 (Mon) = 5 business days
        assert business_days_between("2024-01-01", "2024-01-08") == 5

    def test_same_date_is_zero(self):
        from tradingagents.backtesting.report import business_days_between
        assert business_days_between("2024-01-01", "2024-01-01") == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/backtesting/test_report.py::TestIsWin tests/backtesting/test_report.py::TestGetHoldingDays tests/backtesting/test_report.py::TestBusinessDaysBetween -v
```

Expected: `ImportError: cannot import name 'is_win'`

- [ ] **Step 3: Implement helpers in report.py**

Create `tradingagents/backtesting/report.py`:

```python
from __future__ import annotations

import math
import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np

from .models import BacktestResult, DIRECTION_MAP

logger = logging.getLogger(__name__)


def business_days_between(start_date: str, end_date: str) -> int:
    """Count business days between two ISO-8601 date strings (exclusive of end)."""
    return int(np.busday_count(start_date, end_date))


def get_holding_days(
    current_date: str,
    next_signal_date: Optional[str],
    hold_days_override: Optional[int],
    max_fallback_days: int = 21,
) -> int:
    """Return the number of trading days to hold a signal for return measurement."""
    if hold_days_override is not None:
        return hold_days_override
    if next_signal_date is not None:
        return max(1, business_days_between(current_date, next_signal_date))
    return max_fallback_days


def is_win(direction: int, raw_return: float) -> Optional[bool]:
    """Return True if direction matched return sign, None for HOLD or tie."""
    if direction == 0:
        return None
    if raw_return == 0.0:
        return None
    return (direction > 0) == (raw_return > 0)
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/backtesting/test_report.py::TestIsWin tests/backtesting/test_report.py::TestGetHoldingDays tests/backtesting/test_report.py::TestBusinessDaysBetween -v
```

Expected: all 10 tests PASS

- [ ] **Step 5: Commit**

```
git add tradingagents/backtesting/report.py tests/backtesting/test_report.py
git commit -m "feat(backtesting): add report helpers (is_win, get_holding_days, business_days_between)"
```

---

## Task 6: report.py — BacktestReport and BacktestSummary

**Files:**
- Modify: `tradingagents/backtesting/report.py` (add BacktestReport, BacktestSummary)
- Modify: `tests/backtesting/test_report.py` (add report tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/backtesting/test_report.py`:

```python
from tradingagents.backtesting.models import BacktestResult


def _make_results():
    return [
        BacktestResult(ticker="NVDA", trade_date="2024-01-01", rating="Buy", direction=1),
        BacktestResult(ticker="NVDA", trade_date="2024-02-01", rating="Sell", direction=-1),
        BacktestResult(ticker="NVDA", trade_date="2024-03-01", rating="Hold", direction=0),
    ]


def _return_map(ticker, trade_date, holding_days):
    data = {
        ("NVDA", "2024-01-01"): (0.05, 0.02, 21),   # Buy → +5% → win
        ("NVDA", "2024-02-01"): (-0.03, -0.01, 21),  # Sell dir=-1, ret=-3% → win
        ("NVDA", "2024-03-01"): (0.01, 0.00, 21),    # Hold → excluded from win rate
    }
    return data.get((ticker, trade_date), (None, None, None))


@pytest.mark.unit
class TestBacktestReport:
    def test_win_rate_excludes_hold(self):
        from unittest.mock import patch
        from tradingagents.backtesting.report import BacktestReport

        with patch("tradingagents.backtesting.report.fetch_returns", side_effect=_return_map):
            summary = BacktestReport(_make_results()).compute(hold_days_override=21)

        assert summary.win_rate == pytest.approx(1.0)  # both decisive signals correct
        assert summary.hold_count == 1

    def test_signal_counts(self):
        from unittest.mock import patch
        from tradingagents.backtesting.report import BacktestReport

        with patch("tradingagents.backtesting.report.fetch_returns", side_effect=_return_map):
            summary = BacktestReport(_make_results()).compute(hold_days_override=21)

        assert summary.signal_counts == {"Buy": 1, "Sell": 1, "Hold": 1}

    def test_no_resolvable_returns_none_metrics(self):
        from unittest.mock import patch
        from tradingagents.backtesting.report import BacktestReport

        results = [BacktestResult(ticker="X", trade_date="2024-01-01", rating="Buy", direction=1)]
        with patch("tradingagents.backtesting.report.fetch_returns", return_value=(None, None, None)):
            summary = BacktestReport(results).compute(hold_days_override=5)

        assert summary.win_rate is None
        assert summary.total_return is None
        assert summary.error_count == 1

    def test_error_results_excluded_from_metrics(self):
        from unittest.mock import patch
        from tradingagents.backtesting.report import BacktestReport

        results = [
            BacktestResult(ticker="NVDA", trade_date="2024-01-01", rating="Buy", direction=1),
            BacktestResult(ticker="NVDA", trade_date="2024-02-01", error="timeout"),
        ]
        with patch("tradingagents.backtesting.report.fetch_returns", return_value=(0.05, 0.02, 21)):
            summary = BacktestReport(results).compute(hold_days_override=21)

        assert summary.error_count >= 1
        assert "Buy" in summary.signal_counts

    def test_equity_curve_starts_at_one(self):
        from unittest.mock import patch
        from tradingagents.backtesting.report import BacktestReport

        with patch("tradingagents.backtesting.report.fetch_returns", side_effect=_return_map):
            summary = BacktestReport(_make_results()).compute(hold_days_override=21)

        assert summary.cumulative_equity[0] == pytest.approx(1.0)
        assert len(summary.cumulative_equity) > 1

    def test_max_drawdown_non_positive(self):
        from unittest.mock import patch
        from tradingagents.backtesting.report import BacktestReport

        with patch("tradingagents.backtesting.report.fetch_returns", side_effect=_return_map):
            summary = BacktestReport(_make_results()).compute(hold_days_override=21)

        assert summary.max_drawdown is not None
        assert summary.max_drawdown <= 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/backtesting/test_report.py::TestBacktestReport -v
```

Expected: `ImportError: cannot import name 'BacktestReport'`

- [ ] **Step 3: Implement BacktestReport and BacktestSummary**

Append to `tradingagents/backtesting/report.py`:

```python
from tradingagents.backtesting.returns import fetch_returns


@dataclass
class BacktestSummary:
    # Always check signal_counts first — a backtest with 40 HOLDs and 2 Buys
    # produces a meaningless win rate.
    signal_counts: dict          # {"Buy": 3, "Hold": 8, ...}
    error_count: int             # pipeline failures + unresolvable return fetches
    hold_count: int              # HOLD signals (excluded from directional win rate)

    # Raw returns (direction-neutral — raw asset move, not strategy P&L)
    total_return: Optional[float]
    mean_return: Optional[float]
    cumulative_equity: list      # strategy equity curve starting at 1.0

    # Alpha
    mean_alpha: Optional[float]
    pct_beat_spy: Optional[float]

    # Signal quality
    win_rate: Optional[float]            # directional accuracy; excludes HOLD and ties
    precision_recall_per_tier: dict      # per-tier {"count": N, "win_rate": float|None}

    # Risk (annualised using periods_per_year)
    sharpe_ratio: Optional[float]
    max_drawdown: Optional[float]        # <= 0.0; peak-to-trough as fraction of peak
    volatility: Optional[float]


class BacktestReport:
    def __init__(
        self,
        results: list[BacktestResult],
        risk_free_rate: float = 0.0,
        periods_per_year: int = 12,
    ) -> None:
        self.results = results
        self.risk_free_rate = risk_free_rate
        self.periods_per_year = periods_per_year

    def compute(self, hold_days_override: Optional[int] = None) -> BacktestSummary:
        from collections import Counter

        signal_counts = dict(
            Counter(r.rating for r in self.results if r.error is None and r.rating)
        )
        error_count = sum(1 for r in self.results if r.error is not None)

        # Sort valid results by (ticker, trade_date) for holding period calculation
        valid = sorted(
            [r for r in self.results if r.error is None],
            key=lambda r: (r.ticker, r.trade_date),
        )

        # Resolve forward returns for each valid result
        from itertools import groupby as _groupby

        resolved = []  # list of (result, raw_return, alpha)
        for _ticker, group in _groupby(valid, key=lambda r: r.ticker):
            ticker_results = list(group)
            for i, result in enumerate(ticker_results):
                next_date = (
                    ticker_results[i + 1].trade_date
                    if i + 1 < len(ticker_results)
                    else None
                )
                holding = get_holding_days(result.trade_date, next_date, hold_days_override)
                raw, alpha, _days = fetch_returns(result.ticker, result.trade_date, holding)
                if raw is None:
                    error_count += 1
                else:
                    resolved.append((result, raw, alpha))

        hold_count = signal_counts.get("Hold", 0)

        if not resolved:
            return BacktestSummary(
                signal_counts=signal_counts, error_count=error_count, hold_count=hold_count,
                total_return=None, mean_return=None, cumulative_equity=[1.0],
                mean_alpha=None, pct_beat_spy=None,
                win_rate=None, precision_recall_per_tier={},
                sharpe_ratio=None, max_drawdown=None, volatility=None,
            )

        returns = [raw for _, raw, _ in resolved]
        alphas = [a for _, _, a in resolved]

        # Equity curve — direction-adjusted P&L
        equity = [1.0]
        for result, raw, _ in resolved:
            d = result.direction or 0
            equity.append(equity[-1] * (1 + d * raw))

        # Win rate (excludes HOLD and ties)
        decisive = [
            is_win(result.direction, raw)
            for result, raw, _ in resolved
            if result.direction is not None
        ]
        decisive_bools = [w for w in decisive if w is not None]
        win_rate = (
            sum(decisive_bools) / len(decisive_bools) if decisive_bools else None
        )

        # Per-tier stats
        tier_stats: dict = {}
        for rating in ["Buy", "Overweight", "Hold", "Underweight", "Sell"]:
            tier = [(r, raw, a) for r, raw, a in resolved if r.rating == rating]
            if not tier:
                continue
            if rating == "Hold":
                tier_stats[rating] = {"count": len(tier)}
                continue
            d = DIRECTION_MAP.get(rating, 0)
            tier_wins = [is_win(d, raw) for _, raw, _ in tier]
            decisive_tier = [w for w in tier_wins if w is not None]
            tier_stats[rating] = {
                "count": len(tier),
                "win_rate": (
                    sum(decisive_tier) / len(decisive_tier) if decisive_tier else None
                ),
            }

        # Risk metrics
        mean_r = sum(returns) / len(returns)
        vol: Optional[float] = None
        sharpe: Optional[float] = None
        if len(returns) > 1:
            variance = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
            vol = math.sqrt(variance) if variance > 0 else 0.0
            rf_per_period = self.risk_free_rate / self.periods_per_year
            if vol and vol > 0:
                sharpe = (
                    (mean_r - rf_per_period)
                    / vol
                    * math.sqrt(self.periods_per_year)
                )

        # Max drawdown
        peak = equity[0]
        max_dd = 0.0
        for val in equity:
            peak = max(peak, val)
            dd = (peak - val) / peak
            max_dd = max(max_dd, dd)

        return BacktestSummary(
            signal_counts=signal_counts,
            error_count=error_count,
            hold_count=hold_count,
            total_return=sum(returns),
            mean_return=mean_r,
            cumulative_equity=equity,
            mean_alpha=sum(alphas) / len(alphas),
            pct_beat_spy=sum(1 for a in alphas if a > 0) / len(alphas),
            win_rate=win_rate,
            precision_recall_per_tier=tier_stats,
            sharpe_ratio=sharpe,
            max_drawdown=-max_dd,
            volatility=vol,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/backtesting/test_report.py -v
```

Expected: all 16 tests PASS

- [ ] **Step 5: Commit**

```
git add tradingagents/backtesting/report.py tests/backtesting/test_report.py
git commit -m "feat(backtesting): add BacktestReport and BacktestSummary with full metrics"
```

---

## Task 7: Package exports and __init__.py

**Files:**
- Modify: `tradingagents/backtesting/__init__.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/backtesting/test_models.py`:

```python
def test_public_exports():
    from tradingagents import backtesting
    assert hasattr(backtesting, "BacktestEngine")
    assert hasattr(backtesting, "BacktestReport")
    assert hasattr(backtesting, "BacktestResult")
    assert hasattr(backtesting, "BacktestSummary")
    assert hasattr(backtesting, "DIRECTION_MAP")
    assert hasattr(backtesting, "derive_direction")
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/backtesting/test_models.py::test_public_exports -v
```

Expected: FAIL — `BacktestEngine` not exported

- [ ] **Step 3: Implement exports**

Replace the contents of `tradingagents/backtesting/__init__.py`:

```python
from .engine import BacktestEngine
from .models import DIRECTION_MAP, BacktestResult, derive_direction
from .report import BacktestReport, BacktestSummary

__all__ = [
    "BacktestEngine",
    "BacktestReport",
    "BacktestResult",
    "BacktestSummary",
    "DIRECTION_MAP",
    "derive_direction",
]
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/backtesting/test_models.py::test_public_exports -v
```

Expected: PASS

- [ ] **Step 5: Run the full test suite**

```
pytest tests/backtesting/ -v
```

Expected: all tests PASS

- [ ] **Step 6: Commit**

```
git add tradingagents/backtesting/__init__.py tests/backtesting/test_models.py
git commit -m "feat(backtesting): wire up package exports"
```

---

## Task 8: CLI — build_parser, main, and entry points

**Files:**
- Create: `tradingagents/backtesting/cli.py`
- Create: `tradingagents/backtesting/__main__.py`
- Create: `tradingagents/__main__.py`
- Create: `tests/backtesting/test_cli.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/backtesting/test_cli.py`:

```python
# tests/backtesting/test_cli.py
import pytest


@pytest.mark.unit
class TestBuildParser:
    def test_required_args(self):
        from tradingagents.backtesting.cli import build_parser
        parser = build_parser()
        args = parser.parse_args([
            "--ticker", "NVDA",
            "--start", "2024-01-01",
            "--end", "2024-12-31",
        ])
        assert args.ticker == ["NVDA"]
        assert args.start == "2024-01-01"
        assert args.end == "2024-12-31"

    def test_defaults(self):
        from tradingagents.backtesting.cli import build_parser
        parser = build_parser()
        args = parser.parse_args([
            "--ticker", "NVDA",
            "--start", "2024-01-01",
            "--end", "2024-12-31",
        ])
        assert args.freq == "monthly"
        assert args.workers == 2
        assert args.risk_free_rate == 0.0
        assert args.hold_days is None
        assert args.resume is False
        assert args.output is None

    def test_multiple_tickers(self):
        from tradingagents.backtesting.cli import build_parser
        parser = build_parser()
        args = parser.parse_args([
            "--ticker", "NVDA", "AAPL", "MSFT",
            "--start", "2024-01-01",
            "--end", "2024-12-31",
        ])
        assert args.ticker == ["NVDA", "AAPL", "MSFT"]

    def test_all_optional_flags(self):
        from tradingagents.backtesting.cli import build_parser
        parser = build_parser()
        args = parser.parse_args([
            "--ticker", "NVDA",
            "--start", "2024-01-01",
            "--end", "2024-12-31",
            "--freq", "weekly",
            "--hold-days", "5",
            "--workers", "4",
            "--risk-free-rate", "0.045",
            "--resume",
            "--output", "results.jsonl",
            "--analysts", "market", "news",
        ])
        assert args.freq == "weekly"
        assert args.hold_days == 5
        assert args.workers == 4
        assert args.risk_free_rate == pytest.approx(0.045)
        assert args.resume is True
        assert args.output == "results.jsonl"
        assert args.analysts == ["market", "news"]

    def test_missing_ticker_exits(self):
        from tradingagents.backtesting.cli import build_parser
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--start", "2024-01-01", "--end", "2024-12-31"])
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/backtesting/test_cli.py -v
```

Expected: `ImportError: cannot import name 'build_parser'`

- [ ] **Step 3: Implement cli.py**

Create `tradingagents/backtesting/cli.py`:

```python
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tradingagents backtest",
        description="Run the TradingAgents pipeline against historical dates.",
    )
    p.add_argument("--ticker", nargs="+", required=True, metavar="TICKER",
                   help="One or more ticker symbols (e.g. NVDA AAPL)")
    p.add_argument("--start", required=True, metavar="YYYY-MM-DD",
                   help="Backtest start date (inclusive)")
    p.add_argument("--end", required=True, metavar="YYYY-MM-DD",
                   help="Backtest end date (inclusive)")
    p.add_argument("--freq", default="monthly",
                   choices=["monthly", "weekly", "biweekly"],
                   help="Signal frequency (default: monthly)")
    p.add_argument("--output", default=None, metavar="PATH",
                   help="JSONL output path (default: ~/.tradingagents/backtests/<hash>.jsonl)")
    p.add_argument("--resume", action="store_true",
                   help="Skip (ticker, date) pairs already in --output with no error")
    p.add_argument("--hold-days", type=int, default=None, metavar="N",
                   help="Override holding period in trading days (default: until next signal)")
    p.add_argument("--workers", type=int, default=2, metavar="N",
                   help="Parallel ticker workers (default: 2)")
    p.add_argument("--risk-free-rate", type=float, default=0.0, metavar="FLOAT",
                   help="Annualised risk-free rate for Sharpe (default: 0.0)")
    p.add_argument("--analysts", nargs="+",
                   choices=["market", "social", "news", "fundamentals"],
                   default=None, metavar="ANALYST",
                   help="Analyst subset (default: all four)")
    return p


def main(argv=None) -> None:
    from tradingagents.backtesting import BacktestEngine, BacktestReport

    parser = build_parser()
    args = parser.parse_args(argv)

    engine = BacktestEngine(
        tickers=args.ticker,
        start_date=args.start,
        end_date=args.end,
        freq=args.freq,
        analysts=args.analysts,
        max_workers=args.workers,
        output_file=args.output,
    )

    print(
        f"Backtesting {args.ticker}  {args.start} → {args.end}  "
        f"freq={args.freq}  workers={args.workers}"
    )
    results = engine.run(resume=args.resume)

    if not results:
        print("No new results — all dates already completed. Use --resume to skip.")
        return

    report = BacktestReport(results, risk_free_rate=args.risk_free_rate)
    summary = report.compute(hold_days_override=args.hold_days)

    print("\n=== Backtest Summary ===")
    print(f"Signals:   {summary.signal_counts}")
    print(f"Errors:    {summary.error_count}")
    if summary.win_rate is not None:
        print(f"Win rate:  {summary.win_rate:.1%}")
    if summary.mean_return is not None:
        print(f"Mean ret:  {summary.mean_return:.2%}")
    if summary.mean_alpha is not None:
        print(f"Mean α:    {summary.mean_alpha:.2%}")
    if summary.sharpe_ratio is not None:
        print(f"Sharpe:    {summary.sharpe_ratio:.2f}")
    if summary.max_drawdown is not None:
        print(f"Max DD:    {summary.max_drawdown:.2%}")

    output_path = Path(engine.output_file)
    summary_path = output_path.with_name(output_path.stem + "_summary.json")
    summary_path.write_text(json.dumps(asdict(summary), indent=2), encoding="utf-8")
    print(f"\nResults:  {engine.output_file}")
    print(f"Summary:  {summary_path}")
```

- [ ] **Step 4: Create entry point files**

Create `tradingagents/backtesting/__main__.py`:

```python
from .cli import main
main()
```

Create `tradingagents/__main__.py`:

```python
import sys

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "backtest":
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        from tradingagents.backtesting.cli import main as backtest_main
        backtest_main()
    else:
        print(f"Usage: python -m tradingagents backtest [options]")
        print(f"       python -m tradingagents.backtesting [options]")
        sys.exit(1)

main()
```

- [ ] **Step 5: Run tests to verify they pass**

```
pytest tests/backtesting/test_cli.py -v
```

Expected: all 5 tests PASS

- [ ] **Step 6: Smoke-test the CLI help**

```
python -m tradingagents backtest --help
```

Expected: help text listing all flags with no import errors

- [ ] **Step 7: Run the full test suite**

```
pytest tests/backtesting/ -v
```

Expected: all tests PASS

- [ ] **Step 8: Commit**

```
git add tradingagents/backtesting/cli.py tradingagents/backtesting/__main__.py tradingagents/__main__.py tests/backtesting/test_cli.py
git commit -m "feat(backtesting): add CLI with --resume, --hold-days, --workers, --risk-free-rate"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Covered by task |
|---|---|
| `tradingagents/backtesting/` module layout | Tasks 1–8 |
| `BacktestResult` dataclass with all fields | Task 1 |
| `trade_date` ISO-8601 contract | Task 1 |
| `DIRECTION_MAP` + `derive_direction` (None for unknown) | Task 1 |
| `fetch_returns` standalone, patches at `returns.fetch_returns` | Task 2 |
| `generate_dates` with business-day alignment | Task 3 |
| JSONL incremental writes | Task 3 |
| Resume: skip completed, retry errors | Tasks 3 & 4 |
| Per-run exception catch → `BacktestResult.error` | Task 4 |
| 429 backoff — same pair, inline, order preserved | Task 4 |
| `is_win` with HOLD=None, tie=None | Task 5 |
| `get_holding_days` with override → next signal → fallback 21 | Task 5 |
| `business_days_between` via numpy | Task 5 |
| `BacktestSummary` all four metric groups | Task 6 |
| `fetch_returns(None,None,None)` counted in `error_count` | Task 6 |
| `BacktestReport(risk_free_rate, periods_per_year)` | Task 6 |
| `max_drawdown <= 0` | Task 6 |
| `__init__.py` exports including `BacktestSummary` | Task 7 |
| CLI `--output`, `--resume`, `--hold-days`, `--workers`, `--risk-free-rate` | Task 8 |
| `python -m tradingagents backtest` | Task 8 |
| Summary table to stdout + `_summary.json` alongside JSONL | Task 8 |
