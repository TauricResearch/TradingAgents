# IIC-FORGE-05 — F2 Forward-Test Harness + Leaderboard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship F2 of the IIC-FORGE program — a forward-testing harness with two invocation modes (watchlist and brief-scoped), a real-time leaderboard, deterministic Markdown reports, a multi-source price layer (yfinance ships, polygon/alpha_vantage/futu stubbed), and the persona prompt + risk-weight wiring that makes per-persona comparison meaningful.

**Architecture:** A new `tradingagents.backtest` package owns the forward-test lifecycle; it calls into `TradingAgentsGraph` for fresh decisions (watchlist mode) and reads from F1's persisted `runs` table (brief-scoped mode). All lifecycle state lives in the JSON `backtest_runs.metrics` column F1 already designed — no schema changes. Persona overlays inject `system_prompt_fragment` into agent factories and weight the risk-debate at the Portfolio Manager.

**Tech Stack:** Python 3.10+, LangChain / LangGraph (existing), SQLite stdlib + `sqlite-vec` (existing), yfinance (existing), pytest with `unit`/`smoke`/`integration` markers. **No new pip dependencies.**

**Prerequisites:**
- F1 complete on `main` (`v1-f1` tag not yet cut; commits up to `4d5b0b5` shipped).
- Approved spec: [docs/superpowers/specs/2026-05-26-iic-forge-05-f2-backtest-benchmark-design.md](../specs/2026-05-26-iic-forge-05-f2-backtest-benchmark-design.md).
- DeepSeek API key configured in `.env`.
- Working tree clean.

**Pre-flight (one-time):**

```bash
cd /home/ziwei-huang/TradingAgents/TradingAgents
git checkout main && git pull --ff-only
git checkout -b feat/iic-forge-05-f2
python -c "import sys; print(sys.version_info >= (3, 10))"  # True
pytest --version                                              # >= 7.0
```

---

## File Structure (locked in before tasks start)

**Created in this plan:**

| Path | Responsibility |
|---|---|
| `tradingagents/backtest/__init__.py` | Package marker |
| `tradingagents/backtest/prices.py` | `Resolution` enum, `Bars` dataclass, `PriceSource` Protocol, `PriceFallbackChain`, `PriceDataUnavailable` exception |
| `tradingagents/backtest/sources/__init__.py` | Package marker + source registry |
| `tradingagents/backtest/sources/yfinance_source.py` | yfinance `PriceSource` (DAILY only) |
| `tradingagents/backtest/sources/polygon_source.py` | Polygon stub `PriceSource` (raises NotImplementedError) |
| `tradingagents/backtest/sources/alpha_vantage_source.py` | Alpha Vantage stub |
| `tradingagents/backtest/sources/futu_source.py` | Futu stub |
| `tradingagents/backtest/strict_historical.py` | `assert_no_lookahead` wrapper around bars |
| `tradingagents/backtest/simulator.py` | Pure functions: position from decision; return series; Sharpe; max drawdown; win rate |
| `tradingagents/backtest/reflection.py` | `write_outcome_log_on_close()` — persona-aware outcome_log writer |
| `tradingagents/backtest/harness.py` | `BacktestHarness` — watchlist + brief-scoped modes; auto-maturation when `end_date <= today` |
| `tradingagents/backtest/leaderboard.py` | Read-only aggregations over backtest_runs with lazy MTM |
| `tradingagents/backtest/report.py` | Deterministic Markdown report renderer |
| `tradingagents/backtest/sweep.py` | Stateless maturation pass — entry point for `sweep` and `watch` CLI |
| `tradingagents/personas/prompt_overlay.py` | `apply_fragment(base_prompt, persona) -> str` |
| `tradingagents/personas/risk_weights.py` | `format_weighted_risk_debate(state, persona) -> str` |
| `cli/forge.py` | `forge` Typer sub-app with `backtest start/leaderboard/report/sweep/watch/close` |
| `tests/backtest/__init__.py` | empty |
| `tests/backtest/test_prices.py` | Resolution + Bars + PriceSource Protocol + PriceFallbackChain |
| `tests/backtest/test_yfinance_source.py` | yfinance adapter — historical bars round-trip |
| `tests/backtest/test_stub_sources.py` | Polygon/AV/Futu stubs raise NotImplementedError |
| `tests/backtest/test_strict_historical.py` | Assertion fires on future-dated bars; disabled OK |
| `tests/backtest/test_simulator.py` | Position math, return series, Sharpe, drawdown, win rate |
| `tests/backtest/test_reflection.py` | On-close writes one outcome_log row, persona-tagged |
| `tests/backtest/test_harness.py` | Watchlist mode + brief-scoped mode with mocked graph |
| `tests/backtest/test_leaderboard.py` | Open-row MTM + closed-row aggregation + persona grouping |
| `tests/backtest/test_report.py` | Byte-equality on rerun (modulo `generated_ts` line) |
| `tests/backtest/test_sweep.py` | Sweep matures only `scheduled_close_date <= today` |
| `tests/personas/test_prompt_overlay.py` | `apply_fragment` concatenation + None passthrough |
| `tests/personas/test_risk_weights.py` | Format includes weight values; None passthrough |
| `tests/graph/test_persona_threaded_to_factories.py` | Persona reaches market analyst's system_message |
| `tests/cli/test_forge.py` | Typer command wiring smoke |
| `tests/smoke/test_f2_exit_gate.py` | 5 tickers × 3 personas back-dated 30d; byte-equal report |

**Modified in this plan:**

| Path | Change |
|---|---|
| `tradingagents/default_config.py` | Add `backtest_price_sources`, `backtest_resolution_default`, `sweep_interval_seconds`, `backtest_max_concurrent_graph_runs`, `backtest_strict_historical` keys |
| `tradingagents/agents/analysts/market_analyst.py` | Accept `persona=None`; append `system_prompt_fragment` |
| `tradingagents/agents/analysts/news_analyst.py` | same |
| `tradingagents/agents/analysts/social_media_analyst.py` | same |
| `tradingagents/agents/analysts/fundamentals_analyst.py` | same |
| `tradingagents/agents/analysts/derivative_analyst.py` | same |
| `tradingagents/agents/analysts/sentiment_analyst.py` | same |
| `tradingagents/agents/researchers/bull_researcher.py` | same |
| `tradingagents/agents/researchers/bear_researcher.py` | same |
| `tradingagents/agents/managers/research_manager.py` | same |
| `tradingagents/agents/managers/portfolio_manager.py` | same + format risk-debate history via `risk_weights.format_weighted_risk_debate` |
| `tradingagents/agents/trader/trader.py` | same |
| `tradingagents/agents/risk_mgmt/aggressive_debator.py` | same |
| `tradingagents/agents/risk_mgmt/conservative_debator.py` | same |
| `tradingagents/agents/risk_mgmt/neutral_debator.py` | same |
| `tradingagents/graph/setup.py` | `GraphSetup.__init__` gains `persona`; factory calls pass it through; PM gets persona too |
| `tradingagents/graph/trading_graph.py` | Load Persona from `config["persona_id"]`; pass to `GraphSetup` |
| `cli/main.py` | Register the `forge` sub-app |

---

## Cross-cutting conventions

- **Tests:** pytest with markers `unit` (default, fast, isolated), `integration` (real API / external state), `smoke` (quick end-to-end).
- **Commits:** one per task. Format: `feat(<scope>): <subject>` matching repo style (see `git log --oneline -5`).
- **Cost guards:** every guard ships with `enabled: bool = False` default. Measurement always on. (See [saved memory](../../../.claude/projects/-home-ziwei-huang-TradingAgents/memory/cost-guards-disabled-by-default.md).)
- **Imports:** absolute, rooted at `tradingagents.` and `cli.`.
- **Markdown artifacts** live on disk; SQLite stores paths + small metadata.
- **No schema changes** — `backtests`/`backtest_runs` from F1 are used unchanged. All lifecycle state in `backtest_runs.metrics` JSON.

---

## Task 1: F2 default_config keys

**Files:**
- Modify: `tradingagents/default_config.py`
- Test: `tests/test_default_config_f2.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_default_config_f2.py`:

```python
import pytest


@pytest.mark.unit
def test_default_config_has_f2_keys():
    from tradingagents.default_config import DEFAULT_CONFIG as C
    assert "backtest_price_sources" in C
    assert C["backtest_price_sources"] == ["yfinance", "polygon", "alpha_vantage", "futu"]
    assert "backtest_resolution_default" in C
    assert C["backtest_resolution_default"] == "1d"
    assert "sweep_interval_seconds" in C
    assert C["sweep_interval_seconds"] == 300
    assert "backtest_max_concurrent_graph_runs" in C
    assert C["backtest_max_concurrent_graph_runs"] == 5
    assert "backtest_strict_historical" in C
    # Auto-on by date check; documented default is None (auto)
    assert C["backtest_strict_historical"] in (None, "auto")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_default_config_f2.py -v
```

Expected: FAIL — keys don't exist.

- [ ] **Step 3: Add the keys**

In `tradingagents/default_config.py`, near the existing F1 IIC-FORGE block (around `iic_db_path` / `iic_data_dir`), add:

```python
    # IIC-FORGE F2 — backtest harness
    "backtest_price_sources": ["yfinance", "polygon", "alpha_vantage", "futu"],
    "backtest_resolution_default": "1d",       # "1d" | "1m"
    "sweep_interval_seconds": 300,             # forge backtest watch default loop
    "backtest_max_concurrent_graph_runs": 5,   # measurement only when cost_guard_enabled=False
    "backtest_strict_historical": None,        # None=auto (on iff start_date<today); True/False=force
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_default_config_f2.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/default_config.py tests/test_default_config_f2.py
git commit -m "config: add F2 backtest defaults (sources, resolution, sweep, strict-historical)"
```

---

## Task 2: Resolution enum, Bars dataclass, PriceSource Protocol, PriceDataUnavailable

**Files:**
- Create: `tradingagents/backtest/__init__.py`
- Create: `tradingagents/backtest/prices.py`
- Test: `tests/backtest/__init__.py` (empty)
- Test: `tests/backtest/test_prices.py`

- [ ] **Step 1: Create empty package marker for tests**

Create `tests/backtest/__init__.py` as an empty file.

- [ ] **Step 2: Write the failing tests**

Create `tests/backtest/test_prices.py`:

```python
import pytest
from datetime import datetime, date


@pytest.mark.unit
def test_resolution_enum_values():
    from tradingagents.backtest.prices import Resolution
    assert Resolution.DAILY.value == "1d"
    assert Resolution.ONE_MIN.value == "1m"


@pytest.mark.unit
def test_bars_dataclass_round_trip():
    from tradingagents.backtest.prices import Bars, Resolution
    b = Bars(
        ticker="AAPL",
        resolution=Resolution.DAILY,
        bars=[(datetime(2026, 4, 26), 213.45), (datetime(2026, 4, 27), 214.10)],
        source="yfinance",
    )
    assert b.ticker == "AAPL"
    assert b.resolution is Resolution.DAILY
    assert len(b.bars) == 2
    assert b.bars[0][1] == pytest.approx(213.45)
    assert b.source == "yfinance"


@pytest.mark.unit
def test_bars_is_frozen():
    from tradingagents.backtest.prices import Bars, Resolution
    b = Bars(ticker="A", resolution=Resolution.DAILY, bars=[], source="x")
    with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
        b.ticker = "B"  # type: ignore


@pytest.mark.unit
def test_price_data_unavailable_is_exception():
    from tradingagents.backtest.prices import PriceDataUnavailable
    assert issubclass(PriceDataUnavailable, Exception)
    err = PriceDataUnavailable("AAPL", date(2026, 4, 26), date(2026, 5, 26),
                                tried_sources=["yfinance", "polygon"])
    assert "AAPL" in str(err)
    assert err.tried_sources == ["yfinance", "polygon"]


@pytest.mark.unit
def test_price_source_protocol_has_required_attrs():
    """A class with name/supports/get_bars should satisfy the Protocol."""
    from tradingagents.backtest.prices import PriceSource, Resolution, Bars

    class FakeSource:
        name = "fake"
        supports = {Resolution.DAILY}
        def get_bars(self, ticker, start, end, resolution):
            return Bars(ticker=ticker, resolution=resolution, bars=[], source=self.name)

    # Protocol is runtime-checkable in F2 — this should pass without raising.
    src: PriceSource = FakeSource()
    assert src.name == "fake"
    assert src.get_bars("AAPL", date(2026, 4, 26), date(2026, 5, 26),
                        Resolution.DAILY).source == "fake"
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/backtest/test_prices.py -v
```

Expected: ImportError.

- [ ] **Step 4: Create the package marker**

Create `tradingagents/backtest/__init__.py`:

```python
"""IIC-FORGE F2 forward-test harness.

See ADR / design in:
docs/superpowers/specs/2026-05-26-iic-forge-05-f2-backtest-benchmark-design.md
"""
```

- [ ] **Step 5: Implement `prices.py`**

Create `tradingagents/backtest/prices.py`:

```python
"""Price-data abstraction for the F2 backtest harness.

A ``PriceSource`` is anything that can return historical OHLC bars for a
ticker over a window at a given resolution. The ``PriceFallbackChain``
(Task 3) tries each registered source in priority order.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import List, Protocol, Set, Tuple, runtime_checkable


class Resolution(StrEnum):
    DAILY = "1d"
    ONE_MIN = "1m"


@dataclass(frozen=True)
class Bars:
    """A frozen container of (timestamp, close_price) tuples for one ticker."""
    ticker: str
    resolution: Resolution
    bars: List[Tuple[datetime, float]]
    source: str  # name of the producing PriceSource, e.g. "yfinance"


class PriceDataUnavailable(Exception):
    """Raised when every source in the fallback chain failed.

    Caught by the harness, which then marks the affected forward test
    ``status=errored`` with ``errored_sources`` recorded in metrics.
    """

    def __init__(self, ticker: str, start: date, end: date,
                 tried_sources: List[str]):
        self.ticker = ticker
        self.start = start
        self.end = end
        self.tried_sources = list(tried_sources)
        super().__init__(
            f"No price data for {ticker} {start}..{end}; "
            f"tried sources: {self.tried_sources}"
        )


@runtime_checkable
class PriceSource(Protocol):
    """One adapter to a price-data provider."""
    name: str
    supports: Set[Resolution]

    def get_bars(
        self,
        ticker: str,
        start: date,
        end: date,
        resolution: Resolution,
    ) -> Bars:
        """Fetch close-price bars for ``ticker`` from ``start`` to ``end``.

        Returns a ``Bars`` with ``source = self.name``. Raises if the source
        cannot produce data for this window/resolution.
        """
        ...
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/backtest/test_prices.py -v
```

Expected: 5 passing.

- [ ] **Step 7: Commit**

```bash
git add tradingagents/backtest/__init__.py tradingagents/backtest/prices.py \
        tests/backtest/__init__.py tests/backtest/test_prices.py
git commit -m "feat(backtest): Resolution, Bars, PriceSource protocol, PriceDataUnavailable"
```

---

## Task 3: PriceFallbackChain

**Files:**
- Modify: `tradingagents/backtest/prices.py`
- Modify: `tests/backtest/test_prices.py`

- [ ] **Step 1: Append the failing tests**

Append to `tests/backtest/test_prices.py`:

```python
@pytest.mark.unit
def test_fallback_chain_returns_first_successful_source():
    from tradingagents.backtest.prices import (
        Bars, PriceFallbackChain, Resolution
    )
    from datetime import datetime as dt

    class Failing:
        name = "failing"
        supports = {Resolution.DAILY}
        def get_bars(self, *a, **kw):
            raise RuntimeError("simulated failure")

    class Working:
        name = "working"
        supports = {Resolution.DAILY}
        def get_bars(self, ticker, start, end, resolution):
            return Bars(ticker=ticker, resolution=resolution,
                        bars=[(dt(2026, 4, 26), 100.0)], source=self.name)

    chain = PriceFallbackChain([Failing(), Working()])
    result = chain.get_bars("AAPL", date(2026, 4, 26), date(2026, 5, 26),
                             Resolution.DAILY)
    assert result.source == "working"


@pytest.mark.unit
def test_fallback_chain_skips_sources_that_do_not_support_resolution():
    from tradingagents.backtest.prices import (
        Bars, PriceFallbackChain, Resolution
    )

    class DailyOnly:
        name = "daily_only"
        supports = {Resolution.DAILY}
        called = False
        def get_bars(self, *a, **kw):
            self.called = True
            raise AssertionError("should have been skipped")

    class MinuteCapable:
        name = "minute_capable"
        supports = {Resolution.ONE_MIN}
        def get_bars(self, ticker, start, end, resolution):
            from datetime import datetime as dt
            return Bars(ticker=ticker, resolution=resolution,
                        bars=[(dt(2026, 4, 26, 9, 30), 100.0)],
                        source=self.name)

    daily_only = DailyOnly()
    chain = PriceFallbackChain([daily_only, MinuteCapable()])
    chain.get_bars("AAPL", date(2026, 4, 26), date(2026, 4, 26),
                    Resolution.ONE_MIN)
    assert daily_only.called is False


@pytest.mark.unit
def test_fallback_chain_raises_when_all_sources_fail():
    from tradingagents.backtest.prices import (
        PriceDataUnavailable, PriceFallbackChain, Resolution
    )

    class Failing:
        name = "f1"
        supports = {Resolution.DAILY}
        def get_bars(self, *a, **kw):
            raise RuntimeError("nope")

    class Failing2:
        name = "f2"
        supports = {Resolution.DAILY}
        def get_bars(self, *a, **kw):
            raise RuntimeError("also nope")

    chain = PriceFallbackChain([Failing(), Failing2()])
    with pytest.raises(PriceDataUnavailable) as exc_info:
        chain.get_bars("AAPL", date(2026, 4, 26), date(2026, 5, 26),
                        Resolution.DAILY)
    assert exc_info.value.tried_sources == ["f1", "f2"]


@pytest.mark.unit
def test_fallback_chain_empty_raises_immediately():
    from tradingagents.backtest.prices import (
        PriceDataUnavailable, PriceFallbackChain, Resolution
    )
    chain = PriceFallbackChain([])
    with pytest.raises(PriceDataUnavailable):
        chain.get_bars("AAPL", date(2026, 4, 26), date(2026, 5, 26),
                        Resolution.DAILY)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/backtest/test_prices.py -v
```

Expected: 4 new failures (ImportError on `PriceFallbackChain`).

- [ ] **Step 3: Append `PriceFallbackChain` to `prices.py`**

Append to `tradingagents/backtest/prices.py`:

```python
class PriceFallbackChain:
    """Ordered chain of ``PriceSource`` implementations.

    ``get_bars()`` tries each source that supports the requested resolution
    in order; returns the first success. Sources whose ``supports`` does
    not include the resolution are skipped (never called). Raises
    ``PriceDataUnavailable`` if every supporting source fails or no source
    supports the resolution.
    """

    def __init__(self, sources: List[PriceSource]):
        self._sources = list(sources)

    def get_bars(
        self,
        ticker: str,
        start: date,
        end: date,
        resolution: Resolution = Resolution.DAILY,
    ) -> Bars:
        tried: List[str] = []
        for src in self._sources:
            if resolution not in src.supports:
                continue
            tried.append(src.name)
            try:
                return src.get_bars(ticker, start, end, resolution)
            except Exception:  # noqa: BLE001 — any failure → try next source
                continue
        raise PriceDataUnavailable(ticker, start, end, tried)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/backtest/test_prices.py -v
```

Expected: 9 total passing.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/backtest/prices.py tests/backtest/test_prices.py
git commit -m "feat(backtest): PriceFallbackChain with skip-on-unsupported semantics"
```

---

## Task 4: yfinance PriceSource adapter (DAILY only)

**Files:**
- Create: `tradingagents/backtest/sources/__init__.py`
- Create: `tradingagents/backtest/sources/yfinance_source.py`
- Test: `tests/backtest/test_yfinance_source.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/backtest/test_yfinance_source.py`:

```python
import pytest
from datetime import date, datetime
from unittest.mock import patch, MagicMock


@pytest.mark.unit
def test_yfinance_source_supports_only_daily():
    from tradingagents.backtest.sources.yfinance_source import YFinanceSource
    from tradingagents.backtest.prices import Resolution
    s = YFinanceSource()
    assert s.name == "yfinance"
    assert s.supports == {Resolution.DAILY}


@pytest.mark.unit
def test_yfinance_source_returns_bars(monkeypatch):
    """When yf.Ticker(...).history returns a DataFrame, we extract Close bars."""
    from tradingagents.backtest.sources.yfinance_source import YFinanceSource
    from tradingagents.backtest.prices import Resolution
    import pandas as pd

    fake_index = pd.DatetimeIndex(
        [pd.Timestamp("2026-04-26"), pd.Timestamp("2026-04-27")]
    )
    fake_df = pd.DataFrame({"Close": [213.45, 214.10]}, index=fake_index)

    mock_history = MagicMock(return_value=fake_df)
    mock_ticker = MagicMock(history=mock_history)
    with patch("yfinance.Ticker", return_value=mock_ticker):
        s = YFinanceSource()
        bars = s.get_bars("AAPL", date(2026, 4, 26), date(2026, 4, 27),
                          Resolution.DAILY)

    assert bars.ticker == "AAPL"
    assert bars.source == "yfinance"
    assert len(bars.bars) == 2
    assert bars.bars[0][1] == pytest.approx(213.45)
    assert bars.bars[1][1] == pytest.approx(214.10)


@pytest.mark.unit
def test_yfinance_source_one_min_raises(monkeypatch):
    """ONE_MIN is unsupported; yfinance is limited to ~7 days at 1m."""
    from tradingagents.backtest.sources.yfinance_source import YFinanceSource
    from tradingagents.backtest.prices import Resolution
    s = YFinanceSource()
    with pytest.raises(NotImplementedError):
        s.get_bars("AAPL", date(2026, 4, 26), date(2026, 4, 27),
                    Resolution.ONE_MIN)


@pytest.mark.unit
def test_yfinance_source_empty_dataframe_raises():
    """Empty history (delisted / future / vendor error) must raise."""
    from tradingagents.backtest.sources.yfinance_source import YFinanceSource
    from tradingagents.backtest.prices import Resolution
    import pandas as pd

    mock_history = MagicMock(return_value=pd.DataFrame())
    mock_ticker = MagicMock(history=mock_history)
    with patch("yfinance.Ticker", return_value=mock_ticker):
        s = YFinanceSource()
        with pytest.raises(RuntimeError, match="empty"):
            s.get_bars("ZZZZ", date(2026, 4, 26), date(2026, 5, 26),
                        Resolution.DAILY)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/backtest/test_yfinance_source.py -v
```

Expected: ImportError.

- [ ] **Step 3: Create the sources package marker**

Create `tradingagents/backtest/sources/__init__.py`:

```python
"""F2 PriceSource adapters.

F2 ships only yfinance; polygon/alpha_vantage/futu are registered as stubs
so the fallback chain is wired from day one. Users (or F3) replace the
stubs with real implementations as needed.
"""
```

- [ ] **Step 4: Implement the yfinance adapter**

Create `tradingagents/backtest/sources/yfinance_source.py`:

```python
"""yfinance ``PriceSource`` adapter. Supports DAILY only."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Set

import yfinance as yf

from tradingagents.backtest.prices import Bars, Resolution


class YFinanceSource:
    name = "yfinance"
    supports: Set[Resolution] = {Resolution.DAILY}

    def get_bars(
        self,
        ticker: str,
        start: date,
        end: date,
        resolution: Resolution,
    ) -> Bars:
        if resolution is not Resolution.DAILY:
            raise NotImplementedError(
                f"yfinance adapter supports only DAILY; got {resolution!r}. "
                "Register a Polygon or Alpha Vantage source for 1-min data."
            )

        # yfinance's history(end=...) is exclusive — add one day so the
        # caller's `end` is included.
        df = yf.Ticker(ticker).history(
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
        )
        if df.empty or "Close" not in df.columns:
            raise RuntimeError(
                f"yfinance returned empty bars for {ticker} "
                f"{start}..{end}"
            )

        bars = [
            (idx.to_pydatetime() if hasattr(idx, "to_pydatetime") else idx,
             float(close))
            for idx, close in zip(df.index, df["Close"])
        ]
        return Bars(
            ticker=ticker,
            resolution=Resolution.DAILY,
            bars=bars,
            source=self.name,
        )
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/backtest/test_yfinance_source.py -v
```

Expected: 4 passing.

- [ ] **Step 6: Commit**

```bash
git add tradingagents/backtest/sources/__init__.py \
        tradingagents/backtest/sources/yfinance_source.py \
        tests/backtest/test_yfinance_source.py
git commit -m "feat(backtest): yfinance PriceSource adapter (DAILY)"
```

---

## Task 5: Stub adapters — Polygon, Alpha Vantage, Futu

**Files:**
- Create: `tradingagents/backtest/sources/polygon_source.py`
- Create: `tradingagents/backtest/sources/alpha_vantage_source.py`
- Create: `tradingagents/backtest/sources/futu_source.py`
- Test: `tests/backtest/test_stub_sources.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/backtest/test_stub_sources.py`:

```python
import pytest
from datetime import date


@pytest.mark.unit
@pytest.mark.parametrize("module_name,class_name,source_name", [
    ("tradingagents.backtest.sources.polygon_source", "PolygonSource", "polygon"),
    ("tradingagents.backtest.sources.alpha_vantage_source", "AlphaVantageSource", "alpha_vantage"),
    ("tradingagents.backtest.sources.futu_source", "FutuSource", "futu"),
])
def test_stub_source_metadata(module_name, class_name, source_name):
    import importlib
    mod = importlib.import_module(module_name)
    cls = getattr(mod, class_name)
    inst = cls()
    assert inst.name == source_name
    # Stubs declare DAILY support so the fallback chain considers them;
    # they raise NotImplementedError when called.
    from tradingagents.backtest.prices import Resolution
    assert Resolution.DAILY in inst.supports


@pytest.mark.unit
@pytest.mark.parametrize("module_name,class_name", [
    ("tradingagents.backtest.sources.polygon_source", "PolygonSource"),
    ("tradingagents.backtest.sources.alpha_vantage_source", "AlphaVantageSource"),
    ("tradingagents.backtest.sources.futu_source", "FutuSource"),
])
def test_stub_source_raises_on_get_bars(module_name, class_name):
    import importlib
    mod = importlib.import_module(module_name)
    cls = getattr(mod, class_name)
    inst = cls()
    from tradingagents.backtest.prices import Resolution
    with pytest.raises(NotImplementedError):
        inst.get_bars("AAPL", date(2026, 4, 26), date(2026, 5, 26),
                       Resolution.DAILY)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/backtest/test_stub_sources.py -v
```

Expected: ImportError on each of 3 modules.

- [ ] **Step 3: Implement the three stubs**

Create `tradingagents/backtest/sources/polygon_source.py`:

```python
"""Polygon ``PriceSource`` — stub. Replace with a real implementation when
Polygon API access is wired up."""

from __future__ import annotations

from datetime import date
from typing import Set

from tradingagents.backtest.prices import Bars, Resolution


class PolygonSource:
    name = "polygon"
    supports: Set[Resolution] = {Resolution.DAILY}  # advertise; raise on call

    def get_bars(self, ticker: str, start: date, end: date,
                 resolution: Resolution) -> Bars:
        raise NotImplementedError(
            "PolygonSource is a stub in F2. Register a real adapter when "
            "Polygon API access is wired up; see "
            "docs/superpowers/specs/2026-05-26-iic-forge-05-f2-backtest-benchmark-design.md D7."
        )
```

Create `tradingagents/backtest/sources/alpha_vantage_source.py`:

```python
"""Alpha Vantage ``PriceSource`` — stub."""

from __future__ import annotations

from datetime import date
from typing import Set

from tradingagents.backtest.prices import Bars, Resolution


class AlphaVantageSource:
    name = "alpha_vantage"
    supports: Set[Resolution] = {Resolution.DAILY}

    def get_bars(self, ticker: str, start: date, end: date,
                 resolution: Resolution) -> Bars:
        raise NotImplementedError(
            "AlphaVantageSource is a stub in F2."
        )
```

Create `tradingagents/backtest/sources/futu_source.py`:

```python
"""Futu OpenD ``PriceSource`` — stub."""

from __future__ import annotations

from datetime import date
from typing import Set

from tradingagents.backtest.prices import Bars, Resolution


class FutuSource:
    name = "futu"
    supports: Set[Resolution] = {Resolution.DAILY}

    def get_bars(self, ticker: str, start: date, end: date,
                 resolution: Resolution) -> Bars:
        raise NotImplementedError(
            "FutuSource is a stub in F2."
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/backtest/test_stub_sources.py -v
```

Expected: 6 passing (3 metadata + 3 raises).

- [ ] **Step 5: Commit**

```bash
git add tradingagents/backtest/sources/polygon_source.py \
        tradingagents/backtest/sources/alpha_vantage_source.py \
        tradingagents/backtest/sources/futu_source.py \
        tests/backtest/test_stub_sources.py
git commit -m "feat(backtest): stub Polygon / AlphaVantage / Futu PriceSource adapters"
```

---

## Task 6: strict_historical assertion wrapper

**Files:**
- Create: `tradingagents/backtest/strict_historical.py`
- Test: `tests/backtest/test_strict_historical.py`

This is R-F2-1's mitigation. Wraps a `PriceFallbackChain` and asserts every bar's timestamp is `<= trade_date`. Default behaviour depends on the harness — auto-on when `start_date < today`.

- [ ] **Step 1: Write the failing tests**

Create `tests/backtest/test_strict_historical.py`:

```python
import pytest
from datetime import date, datetime
from unittest.mock import MagicMock


@pytest.mark.unit
def test_assert_no_lookahead_passes_when_all_bars_in_window():
    from tradingagents.backtest.strict_historical import assert_no_lookahead
    from tradingagents.backtest.prices import Bars, Resolution
    b = Bars(
        ticker="AAPL",
        resolution=Resolution.DAILY,
        bars=[(datetime(2026, 4, 26), 213.0),
              (datetime(2026, 5, 26), 219.0)],
        source="yfinance",
    )
    # cutoff = end of window — bars within OK.
    assert_no_lookahead(b, cutoff=date(2026, 5, 26))


@pytest.mark.unit
def test_assert_no_lookahead_raises_on_future_bar():
    from tradingagents.backtest.strict_historical import (
        assert_no_lookahead, LookaheadDataError,
    )
    from tradingagents.backtest.prices import Bars, Resolution
    b = Bars(
        ticker="AAPL",
        resolution=Resolution.DAILY,
        bars=[(datetime(2026, 4, 26), 213.0),
              (datetime(2026, 7, 1), 999.0)],   # past the cutoff
        source="evil",
    )
    with pytest.raises(LookaheadDataError) as exc:
        assert_no_lookahead(b, cutoff=date(2026, 5, 26))
    assert "AAPL" in str(exc.value)
    assert "evil" in str(exc.value)


@pytest.mark.unit
def test_strict_chain_wraps_and_asserts():
    """The StrictHistoricalChain returns bars iff every bar is in-window."""
    from tradingagents.backtest.strict_historical import (
        StrictHistoricalChain, LookaheadDataError,
    )
    from tradingagents.backtest.prices import Bars, Resolution

    class GoodInner:
        def get_bars(self, ticker, start, end, resolution):
            return Bars(ticker=ticker, resolution=resolution,
                        bars=[(datetime(2026, 4, 26), 100.0),
                              (datetime(2026, 5, 26), 110.0)],
                        source="yfinance")

    class CheatingInner:
        def get_bars(self, ticker, start, end, resolution):
            return Bars(ticker=ticker, resolution=resolution,
                        bars=[(datetime(2099, 1, 1), 999.0)],  # cheat
                        source="liar")

    good = StrictHistoricalChain(GoodInner(), cutoff=date(2026, 5, 26))
    assert good.get_bars("AAPL", date(2026, 4, 26), date(2026, 5, 26),
                          Resolution.DAILY).source == "yfinance"

    bad = StrictHistoricalChain(CheatingInner(), cutoff=date(2026, 5, 26))
    with pytest.raises(LookaheadDataError):
        bad.get_bars("AAPL", date(2026, 4, 26), date(2026, 5, 26),
                      Resolution.DAILY)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/backtest/test_strict_historical.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `strict_historical.py`**

Create `tradingagents/backtest/strict_historical.py`:

```python
"""Look-ahead assertion for back-dated backtest runs (R-F2-1).

When the harness runs a forward test with ``start_date < today``, every
bar returned by the price layer MUST have ``timestamp.date() <= cutoff``
(typically ``cutoff = end_date``). A bar past the cutoff means a data
source ignored the cutoff and leaked future data into the agent's view,
which would silently inflate measured alpha.
"""

from __future__ import annotations

from datetime import date
from typing import Set

from tradingagents.backtest.prices import Bars, PriceSource, Resolution


class LookaheadDataError(Exception):
    """A PriceSource returned a bar past the configured cutoff."""


def assert_no_lookahead(bars: Bars, *, cutoff: date) -> None:
    """Raise ``LookaheadDataError`` if any bar's date is past ``cutoff``."""
    for ts, _close in bars.bars:
        if ts.date() > cutoff:
            raise LookaheadDataError(
                f"Source {bars.source!r} returned a bar at {ts.isoformat()} "
                f"for {bars.ticker} which is past the cutoff {cutoff.isoformat()}. "
                "This is a look-ahead leak — fix the source or stub it for backtests."
            )


class StrictHistoricalChain:
    """Wraps any object with ``get_bars(...)`` and asserts no look-ahead."""

    def __init__(self, inner, *, cutoff: date):
        self._inner = inner
        self._cutoff = cutoff

    # `supports` lookup falls through for callers that need it (PriceFallbackChain)
    @property
    def supports(self) -> Set[Resolution]:
        return getattr(self._inner, "supports", {Resolution.DAILY})

    @property
    def name(self) -> str:
        return f"strict({getattr(self._inner, 'name', 'inner')})"

    def get_bars(self, ticker, start, end, resolution) -> Bars:
        bars = self._inner.get_bars(ticker, start, end, resolution)
        assert_no_lookahead(bars, cutoff=self._cutoff)
        return bars
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/backtest/test_strict_historical.py -v
```

Expected: 3 passing.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/backtest/strict_historical.py tests/backtest/test_strict_historical.py
git commit -m "feat(backtest): strict_historical wrapper asserts no look-ahead in back-dated runs"
```

---

## Task 7: simulator.py — pure return-series math

**Files:**
- Create: `tradingagents/backtest/simulator.py`
- Test: `tests/backtest/test_simulator.py`

Pure functions. No I/O. Takes a `Bars` (entry + exit window) and a decision; returns the metrics dict that lands in `backtest_runs.metrics`.

- [ ] **Step 1: Write the failing tests**

Create `tests/backtest/test_simulator.py`:

```python
import pytest
from datetime import datetime
from math import isclose


@pytest.mark.unit
@pytest.mark.parametrize("decision,expected", [
    ("BUY", 1), ("buy", 1), ("Buy", 1),
    ("HOLD", 0), ("hold", 0),
    ("SELL", -1), ("sell", -1),
])
def test_position_from_decision(decision, expected):
    from tradingagents.backtest.simulator import position_from_decision
    assert position_from_decision(decision) == expected


@pytest.mark.unit
def test_position_from_decision_rejects_unknown():
    from tradingagents.backtest.simulator import position_from_decision
    with pytest.raises(ValueError):
        position_from_decision("MOON")


@pytest.mark.unit
def test_compute_returns_long_position():
    from tradingagents.backtest.simulator import compute_returns
    from tradingagents.backtest.prices import Bars, Resolution
    bars = Bars(ticker="A", resolution=Resolution.DAILY, source="x",
                bars=[(datetime(2026, 4, 26), 100.0),
                      (datetime(2026, 4, 27), 101.0),
                      (datetime(2026, 4, 28),  99.0),
                      (datetime(2026, 4, 29), 105.0)])
    returns = compute_returns(bars, position=1)
    # day-over-day signed returns (no return for the first bar)
    assert len(returns) == 3
    assert isclose(returns[0], 0.01, rel_tol=1e-9)
    assert isclose(returns[1], (99 - 101) / 101, rel_tol=1e-9)
    assert isclose(returns[2], (105 - 99) / 99, rel_tol=1e-9)


@pytest.mark.unit
def test_compute_returns_short_position_inverts_sign():
    from tradingagents.backtest.simulator import compute_returns
    from tradingagents.backtest.prices import Bars, Resolution
    bars = Bars(ticker="A", resolution=Resolution.DAILY, source="x",
                bars=[(datetime(2026, 4, 26), 100.0),
                      (datetime(2026, 4, 27), 110.0)])
    returns = compute_returns(bars, position=-1)
    # Long would be +0.10; short flips to -0.10.
    assert isclose(returns[0], -0.10, rel_tol=1e-9)


@pytest.mark.unit
def test_compute_returns_flat_position_is_all_zeros():
    from tradingagents.backtest.simulator import compute_returns
    from tradingagents.backtest.prices import Bars, Resolution
    bars = Bars(ticker="A", resolution=Resolution.DAILY, source="x",
                bars=[(datetime(2026, 4, 26), 100.0),
                      (datetime(2026, 4, 27), 110.0)])
    returns = compute_returns(bars, position=0)
    assert returns == [0.0]


@pytest.mark.unit
def test_total_return_long_simple():
    from tradingagents.backtest.simulator import total_return
    assert isclose(total_return(entry=100.0, exit=110.0, position=1),
                   0.10, rel_tol=1e-9)


@pytest.mark.unit
def test_total_return_short_inverts():
    from tradingagents.backtest.simulator import total_return
    assert isclose(total_return(entry=100.0, exit=110.0, position=-1),
                   -0.10, rel_tol=1e-9)


@pytest.mark.unit
def test_total_return_flat_is_zero():
    from tradingagents.backtest.simulator import total_return
    assert total_return(entry=100.0, exit=110.0, position=0) == 0.0


@pytest.mark.unit
def test_sharpe_known_series():
    """Sharpe = mean(r) / stdev(r) * annualization_factor."""
    from tradingagents.backtest.simulator import sharpe_ratio
    from tradingagents.backtest.prices import Resolution
    # constant positive returns → stdev=0 → defined as 0 (no risk-free reward)
    assert sharpe_ratio([0.01] * 5, resolution=Resolution.DAILY) == 0.0
    # known series: alternating ±1% → mean=0 → Sharpe=0
    assert sharpe_ratio([0.01, -0.01] * 5, resolution=Resolution.DAILY) == 0.0
    # mean > 0, stdev > 0 → positive
    s = sharpe_ratio([0.01, 0.02, 0.005, 0.015], resolution=Resolution.DAILY)
    assert s > 0


@pytest.mark.unit
def test_max_drawdown_known_curve():
    from tradingagents.backtest.simulator import max_drawdown
    # Returns: +10%, -20%, +5%
    # Cumulative: 1.0 -> 1.10 -> 0.88 -> 0.924
    # Peak before dd: 1.10; trough: 0.88; dd = (0.88/1.10) - 1 = -0.2
    dd = max_drawdown([0.10, -0.20, 0.05])
    assert isclose(dd, -0.2, rel_tol=1e-9)


@pytest.mark.unit
def test_max_drawdown_no_drawdown_returns_zero():
    from tradingagents.backtest.simulator import max_drawdown
    assert max_drawdown([0.01, 0.02, 0.005]) == 0.0


@pytest.mark.unit
def test_win_rate():
    from tradingagents.backtest.simulator import win_rate
    assert win_rate([0.01, -0.01, 0.02, 0.0, -0.005]) == pytest.approx(2 / 5)
    assert win_rate([]) == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/backtest/test_simulator.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `simulator.py`**

Create `tradingagents/backtest/simulator.py`:

```python
"""Pure forward-test math — signal → position → return series → aggregate metrics.

Resolution-agnostic. Callers pass a ``Bars`` with N close prices; this module
produces an N-1-length return series and reduces it to scalar metrics.
"""

from __future__ import annotations

import math
import statistics
from typing import List

from tradingagents.backtest.prices import Bars, Resolution


_DECISION_TO_POSITION = {"BUY": 1, "HOLD": 0, "SELL": -1}


def position_from_decision(decision: str) -> int:
    """Map BUY/HOLD/SELL → +1/0/-1. Raises ValueError on unknown."""
    key = decision.strip().upper()
    if key not in _DECISION_TO_POSITION:
        raise ValueError(
            f"Unknown decision {decision!r}; expected BUY / HOLD / SELL"
        )
    return _DECISION_TO_POSITION[key]


def compute_returns(bars: Bars, *, position: int) -> List[float]:
    """Signal-adjusted bar-over-bar return series.

    For N bars returns a list of length N-1. Each element is
    ``position * (close[i+1] - close[i]) / close[i]``. When ``position == 0``
    the series is all zeros (flat).
    """
    if len(bars.bars) < 2:
        return []
    out: List[float] = []
    for (_, prev_close), (_, this_close) in zip(bars.bars, bars.bars[1:]):
        raw = (this_close - prev_close) / prev_close
        out.append(position * raw)
    return out


def total_return(*, entry: float, exit: float, position: int) -> float:
    """Signal-adjusted total return over the window."""
    if entry <= 0:
        raise ValueError(f"entry price must be positive; got {entry}")
    return position * (exit - entry) / entry


_ANNUALIZATION = {
    Resolution.DAILY: math.sqrt(252),
    Resolution.ONE_MIN: math.sqrt(252 * 390),  # ~390 1-min bars per US session
}


def sharpe_ratio(returns: List[float], *, resolution: Resolution) -> float:
    """Annualised Sharpe (zero risk-free rate). Returns 0 for degenerate inputs."""
    if len(returns) < 2:
        return 0.0
    mean = statistics.fmean(returns)
    try:
        std = statistics.stdev(returns)
    except statistics.StatisticsError:
        return 0.0
    if std == 0:
        return 0.0
    return (mean / std) * _ANNUALIZATION[resolution]


def max_drawdown(returns: List[float]) -> float:
    """Largest peak-to-trough decline in the cumulative-return curve.

    Returns a non-positive value. ``0.0`` means no drawdown.
    """
    if not returns:
        return 0.0
    equity = 1.0
    peak = 1.0
    worst = 0.0
    for r in returns:
        equity *= 1.0 + r
        if equity > peak:
            peak = equity
        dd = equity / peak - 1.0
        if dd < worst:
            worst = dd
    return worst


def win_rate(returns: List[float]) -> float:
    """Fraction of bar-returns strictly greater than zero."""
    if not returns:
        return 0.0
    wins = sum(1 for r in returns if r > 0)
    return wins / len(returns)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/backtest/test_simulator.py -v
```

Expected: ~14 passing.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/backtest/simulator.py tests/backtest/test_simulator.py
git commit -m "feat(backtest): simulator math — position, returns, Sharpe, drawdown, win rate"
```

---

## Task 8: personas.prompt_overlay.apply_fragment

**Files:**
- Create: `tradingagents/personas/prompt_overlay.py`
- Test: `tests/personas/test_prompt_overlay.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/personas/test_prompt_overlay.py`:

```python
import pytest


@pytest.fixture
def macro_persona():
    from tradingagents.personas.loader import load_persona_from_string
    return load_persona_from_string("""
id: macro
name: Macro
description: top-down
system_prompt_fragment: |
  You think top-down. Stretch your horizon to quarters.
llm: {deep_think_llm: m, quick_think_llm: m}
analysts: {include: [market], exclude: []}
risk_debate: {weights: {aggressive: 0.5, conservative: 1.5, neutral: 1.0}}
memory_scope: hybrid
""")


@pytest.mark.unit
def test_apply_fragment_appends_to_base(macro_persona):
    from tradingagents.personas.prompt_overlay import apply_fragment
    base = "You are a market analyst. Pick 8 indicators."
    result = apply_fragment(base, macro_persona)
    assert base in result
    assert "You think top-down" in result
    # Order: base first, fragment after — analyst-specific instructions stay primary.
    assert result.index("market analyst") < result.index("top-down")


@pytest.mark.unit
def test_apply_fragment_none_is_passthrough():
    from tradingagents.personas.prompt_overlay import apply_fragment
    base = "You are an analyst."
    assert apply_fragment(base, None) == base


@pytest.mark.unit
def test_apply_fragment_strips_trailing_whitespace(macro_persona):
    """No trailing blank lines after concatenation."""
    from tradingagents.personas.prompt_overlay import apply_fragment
    result = apply_fragment("base.\n\n", macro_persona)
    assert not result.endswith("\n\n\n")


@pytest.mark.unit
def test_apply_fragment_empty_fragment_returns_base(macro_persona):
    """A persona with an empty fragment is treated like None."""
    from tradingagents.personas.loader import load_persona_from_string
    p = load_persona_from_string("""
id: blank
name: Blank
description: x
system_prompt_fragment: ""
llm: {deep_think_llm: m, quick_think_llm: m}
analysts: {include: [market], exclude: []}
risk_debate: {weights: {aggressive: 1.0, conservative: 1.0, neutral: 1.0}}
memory_scope: hybrid
""")
    from tradingagents.personas.prompt_overlay import apply_fragment
    base = "You are an analyst."
    assert apply_fragment(base, p) == base
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/personas/test_prompt_overlay.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `prompt_overlay.py`**

Create `tradingagents/personas/prompt_overlay.py`:

```python
"""Persona system-prompt overlay helper.

Used by every agent factory (analysts, researchers, managers, trader, PM,
risk debators) to append the active persona's ``system_prompt_fragment``
to its base system prompt. Passthrough when ``persona is None``.
"""

from __future__ import annotations

from typing import Optional

from tradingagents.personas.loader import Persona


def apply_fragment(base_prompt: str, persona: Optional[Persona]) -> str:
    """Return ``base_prompt`` with the persona's fragment appended.

    No-op when ``persona is None`` or the persona's fragment is empty/blank.
    Inserts one blank line between the base and the fragment; strips any
    trailing whitespace at the end of the combined result.
    """
    if persona is None:
        return base_prompt
    fragment = (persona.system_prompt_fragment or "").strip()
    if not fragment:
        return base_prompt
    combined = f"{base_prompt.rstrip()}\n\n{fragment}"
    return combined.rstrip()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/personas/test_prompt_overlay.py -v
```

Expected: 4 passing.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/personas/prompt_overlay.py tests/personas/test_prompt_overlay.py
git commit -m "feat(personas): apply_fragment helper for persona system-prompt overlay"
```

---

## Task 9: personas.risk_weights.format_weighted_risk_debate

**Files:**
- Create: `tradingagents/personas/risk_weights.py`
- Test: `tests/personas/test_risk_weights.py`

The Portfolio Manager reads the risk debate as a formatted string. Persona weights bias which side the PM emphasises by labelling each side with its weight.

- [ ] **Step 1: Write the failing tests**

Create `tests/personas/test_risk_weights.py`:

```python
import pytest


@pytest.fixture
def macro_persona():
    from tradingagents.personas.loader import load_persona_from_string
    return load_persona_from_string("""
id: macro
name: Macro
description: top-down
system_prompt_fragment: "x"
llm: {deep_think_llm: m, quick_think_llm: m}
analysts: {include: [market], exclude: []}
risk_debate: {weights: {aggressive: 0.5, conservative: 1.5, neutral: 1.0}}
memory_scope: hybrid
""")


@pytest.fixture
def debate_state():
    return {
        "aggressive_history": "Aggressive view: rate hikes will spike growth tickers.",
        "conservative_history": "Conservative view: rate path uncertain; trim risk.",
        "neutral_history":      "Neutral view: data is mixed, hold positions.",
    }


@pytest.mark.unit
def test_format_includes_each_side_and_weights(macro_persona, debate_state):
    from tradingagents.personas.risk_weights import format_weighted_risk_debate
    out = format_weighted_risk_debate(debate_state, macro_persona)
    assert "Aggressive" in out and "0.5" in out
    assert "Conservative" in out and "1.5" in out
    assert "Neutral" in out and "1.0" in out
    assert "rate hikes" in out and "trim risk" in out and "Hold positions".lower() in out.lower()


@pytest.mark.unit
def test_format_none_persona_omits_weights(debate_state):
    """No persona → no weight annotations; sections still present."""
    from tradingagents.personas.risk_weights import format_weighted_risk_debate
    out = format_weighted_risk_debate(debate_state, None)
    assert "weight" not in out.lower()
    assert "Aggressive" in out
    assert "Conservative" in out
    assert "Neutral" in out


@pytest.mark.unit
def test_format_missing_history_keys_are_safe(macro_persona):
    """A risk_debate_state missing some keys should not raise."""
    from tradingagents.personas.risk_weights import format_weighted_risk_debate
    out = format_weighted_risk_debate({"aggressive_history": "x"}, macro_persona)
    assert "Aggressive" in out
    # Missing sides render as empty (or "(no entries)") — either is acceptable;
    # the assertion is just that no exception was raised.
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/personas/test_risk_weights.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `risk_weights.py`**

Create `tradingagents/personas/risk_weights.py`:

```python
"""Persona-weighted risk-debate formatter (ADR-NEW-2 / spec §7).

The Portfolio Manager consumes the risk-debate history as a formatted
string. When a persona is active, each side is labelled with its weight
so the PM naturally emphasises higher-weighted views.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from tradingagents.personas.loader import Persona


def _section(label: str, body: str, weight: Optional[float]) -> str:
    body = (body or "").strip() or "(no entries)"
    if weight is None:
        return f"### {label}\n{body}"
    return f"### {label} (weight {weight:.2f})\n{body}"


def format_weighted_risk_debate(
    state: Mapping[str, Any],
    persona: Optional[Persona],
) -> str:
    """Render the three risk-debate sides as a single string.

    When ``persona`` is set, prefixes each side's header with its weight
    from ``persona.risk_debate.weights``. When ``None``, omits the weight.
    """
    aggr = state.get("aggressive_history", "")
    cons = state.get("conservative_history", "")
    neut = state.get("neutral_history", "")

    w = persona.risk_debate.weights if persona is not None else {}
    return (
        _section("Aggressive",     aggr, w.get("aggressive")) + "\n\n" +
        _section("Conservative",   cons, w.get("conservative")) + "\n\n" +
        _section("Neutral",        neut, w.get("neutral"))
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/personas/test_risk_weights.py -v
```

Expected: 3 passing.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/personas/risk_weights.py tests/personas/test_risk_weights.py
git commit -m "feat(personas): format_weighted_risk_debate (persona-tagged PM input)"
```

---

## Task 10: Add `persona` parameter to all agent factories

**Files:**
- Modify: `tradingagents/agents/analysts/market_analyst.py`
- Modify: `tradingagents/agents/analysts/news_analyst.py`
- Modify: `tradingagents/agents/analysts/social_media_analyst.py`
- Modify: `tradingagents/agents/analysts/fundamentals_analyst.py`
- Modify: `tradingagents/agents/analysts/derivative_analyst.py`
- Modify: `tradingagents/agents/analysts/sentiment_analyst.py`
- Modify: `tradingagents/agents/researchers/bull_researcher.py`
- Modify: `tradingagents/agents/researchers/bear_researcher.py`
- Modify: `tradingagents/agents/managers/research_manager.py`
- Modify: `tradingagents/agents/trader/trader.py`
- Modify: `tradingagents/agents/risk_mgmt/aggressive_debator.py`
- Modify: `tradingagents/agents/risk_mgmt/conservative_debator.py`
- Modify: `tradingagents/agents/risk_mgmt/neutral_debator.py`
- Test: `tests/graph/test_persona_threaded_to_factories.py`

Pattern is identical across all factories: add `persona: Optional[Persona] = None` to the factory signature; wrap the existing system-prompt string with `apply_fragment`. Test asserts the fragment text reaches the captured prompt.

- [ ] **Step 1: Write the failing test**

Create `tests/graph/test_persona_threaded_to_factories.py`:

```python
"""Boundary test for D4: when a persona is active, its system_prompt_fragment
must appear in the LLM call's messages for every agent role."""

import pytest
from unittest.mock import MagicMock


@pytest.fixture
def persona():
    from tradingagents.personas.loader import load_persona_from_string
    return load_persona_from_string("""
id: macro_test
name: Macro Test
description: x
system_prompt_fragment: |
  PERSONA-FRAGMENT-SENTINEL-XYZ123
llm: {deep_think_llm: m, quick_think_llm: m}
analysts: {include: [market], exclude: []}
risk_debate: {weights: {aggressive: 0.5, conservative: 1.5, neutral: 1.0}}
memory_scope: hybrid
""")


def _captured_prompt_contains(captured, sentinel):
    """Search every captured call argument for the sentinel substring."""
    for call in captured:
        # call is a tuple (args, kwargs) or just args; flatten everything.
        for piece in call.args:
            if isinstance(piece, str) and sentinel in piece:
                return True
            if isinstance(piece, list):
                for msg in piece:
                    text = getattr(msg, "content", str(msg))
                    if sentinel in text:
                        return True
        for v in call.kwargs.values():
            if isinstance(v, str) and sentinel in v:
                return True
    return False


@pytest.mark.unit
@pytest.mark.parametrize("module_name,factory_name", [
    ("tradingagents.agents.analysts.market_analyst",       "create_market_analyst"),
    ("tradingagents.agents.analysts.news_analyst",         "create_news_analyst"),
    ("tradingagents.agents.analysts.social_media_analyst", "create_social_media_analyst"),
    ("tradingagents.agents.analysts.fundamentals_analyst", "create_fundamentals_analyst"),
    ("tradingagents.agents.analysts.derivative_analyst",   "create_derivative_analyst"),
    ("tradingagents.agents.analysts.sentiment_analyst",    "create_sentiment_analyst"),
    ("tradingagents.agents.researchers.bull_researcher",   "create_bull_researcher"),
    ("tradingagents.agents.researchers.bear_researcher",   "create_bear_researcher"),
    ("tradingagents.agents.managers.research_manager",     "create_research_manager"),
    ("tradingagents.agents.trader.trader",                 "create_trader"),
    ("tradingagents.agents.risk_mgmt.aggressive_debator",  "create_aggressive_debator"),
    ("tradingagents.agents.risk_mgmt.conservative_debator","create_conservative_debator"),
    ("tradingagents.agents.risk_mgmt.neutral_debator",     "create_neutral_debator"),
])
def test_factory_accepts_persona_kwarg(module_name, factory_name, persona):
    """All factories must accept ``persona=...`` without raising."""
    import importlib
    import inspect
    mod = importlib.import_module(module_name)
    factory = getattr(mod, factory_name)
    sig = inspect.signature(factory)
    assert "persona" in sig.parameters, (
        f"{factory_name} must accept a `persona` kwarg"
    )
    # Calling with persona=None should match the pre-F2 behaviour (no error).
    node = factory(MagicMock(), persona=None)
    assert callable(node)
    # Calling with the persona should also not raise at construction.
    node = factory(MagicMock(), persona=persona)
    assert callable(node)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/graph/test_persona_threaded_to_factories.py -v
```

Expected: All 13 parametrized cases FAIL (`persona` param doesn't exist on any factory yet).

- [ ] **Step 3: Modify each factory — apply the same pattern**

For EACH of the 13 factory files, apply this transformation:

**Before** (example from `market_analyst.py`):
```python
def create_market_analyst(llm):

    def market_analyst_node(state):
        ...
        system_message = (
            """You are a trading assistant..."""
        )
        ...
```

**After**:
```python
from typing import Optional
from tradingagents.personas.loader import Persona
from tradingagents.personas.prompt_overlay import apply_fragment


def create_market_analyst(llm, persona: Optional[Persona] = None):

    def market_analyst_node(state):
        ...
        system_message = apply_fragment(
            """You are a trading assistant...""",
            persona,
        )
        ...
```

**Apply the same shape to every factory.** If a factory builds its system prompt inside the node closure (so `apply_fragment` must run on each invocation), call it there. If the prompt is constant for the factory, call it once at factory-construction time and capture the result.

For factories that build their prompt as multi-piece strings (e.g., PM's f-string with embedded state), wrap the **system-instruction portion only** — not the dynamic state-dependent context. The fragment goes onto the standing instructions.

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/graph/test_persona_threaded_to_factories.py -v
```

Expected: All 13 cases PASS.

- [ ] **Step 5: Run the full existing test suite to confirm no regressions**

```bash
pytest -m "not integration" --tb=short -q
```

Expected: previously-passing tests still pass. Mocked-LLM call sites in older tests don't pass `persona`, but the kwarg has a default of `None`, so existing call sites continue to compile and run unchanged.

- [ ] **Step 6: Commit**

```bash
git add tradingagents/agents/ tests/graph/test_persona_threaded_to_factories.py
git commit -m "feat(agents): thread persona kwarg through all 13 agent factories"
```

---

## Task 11: Apply risk-weight formatting at Portfolio Manager

**Files:**
- Modify: `tradingagents/agents/managers/portfolio_manager.py`
- Test: `tests/graph/test_pm_risk_weights.py`

The PM reads `risk_debate_state["history"]` directly today. F2 replaces that with the persona-weighted format. When no persona is active, behaviour matches the pre-F2 unweighted format.

- [ ] **Step 1: Write the failing test**

Create `tests/graph/test_pm_risk_weights.py`:

```python
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def persona():
    from tradingagents.personas.loader import load_persona_from_string
    return load_persona_from_string("""
id: macro_test
name: Macro Test
description: x
system_prompt_fragment: ""
llm: {deep_think_llm: m, quick_think_llm: m}
analysts: {include: [market], exclude: []}
risk_debate: {weights: {aggressive: 0.5, conservative: 1.5, neutral: 1.0}}
memory_scope: hybrid
""")


def _fake_state():
    return {
        "company_of_interest": "AAPL",
        "investment_plan": "research plan",
        "trader_investment_plan": "trader plan",
        "past_context": "",
        "risk_debate_state": {
            "history": "<should be ignored when persona overrides format>",
            "aggressive_history": "Aggressive: buy.",
            "conservative_history": "Conservative: hold.",
            "neutral_history": "Neutral: monitor.",
            "current_aggressive_response": "",
            "current_conservative_response": "",
            "current_neutral_response": "",
            "latest_speaker": "Neutral",
            "count": 0,
        },
    }


@pytest.mark.unit
def test_pm_uses_weighted_format_when_persona_set(persona):
    from tradingagents.agents.managers.portfolio_manager import (
        create_portfolio_manager,
    )

    captured = {}

    def fake_invoke(structured_llm, llm, prompt, render, role_label):
        captured["prompt"] = prompt
        return "FINAL TRANSACTION PROPOSAL: **HOLD**"

    fake_llm = MagicMock()
    with patch("tradingagents.agents.managers.portfolio_manager.bind_structured",
               return_value=MagicMock()), \
         patch("tradingagents.agents.managers.portfolio_manager.invoke_structured_or_freetext",
               side_effect=fake_invoke):
        node = create_portfolio_manager(fake_llm, persona=persona)
        node(_fake_state())

    prompt = captured["prompt"]
    assert "Aggressive" in prompt and "0.50" in prompt
    assert "Conservative" in prompt and "1.50" in prompt
    assert "Neutral" in prompt and "1.00" in prompt


@pytest.mark.unit
def test_pm_unweighted_when_no_persona():
    from tradingagents.agents.managers.portfolio_manager import (
        create_portfolio_manager,
    )

    captured = {}

    def fake_invoke(structured_llm, llm, prompt, render, role_label):
        captured["prompt"] = prompt
        return "FINAL TRANSACTION PROPOSAL: **HOLD**"

    fake_llm = MagicMock()
    with patch("tradingagents.agents.managers.portfolio_manager.bind_structured",
               return_value=MagicMock()), \
         patch("tradingagents.agents.managers.portfolio_manager.invoke_structured_or_freetext",
               side_effect=fake_invoke):
        node = create_portfolio_manager(fake_llm, persona=None)
        node(_fake_state())

    prompt = captured["prompt"]
    assert "weight" not in prompt.lower()
    # The three sides still appear because format_weighted_risk_debate writes
    # them regardless of persona; just without weight annotations.
    assert "Aggressive" in prompt
    assert "Conservative" in prompt
    assert "Neutral" in prompt
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/graph/test_pm_risk_weights.py -v
```

Expected: 2 FAILs (the weight numbers won't appear, since the existing PM emits `history` not the weighted format).

- [ ] **Step 3: Modify `portfolio_manager.py`**

Open `tradingagents/agents/managers/portfolio_manager.py` and:

1. Add imports near the top:
```python
from typing import Optional
from tradingagents.personas.loader import Persona
from tradingagents.personas.prompt_overlay import apply_fragment
from tradingagents.personas.risk_weights import format_weighted_risk_debate
```

2. Change the factory signature:
```python
def create_portfolio_manager(llm, persona: Optional[Persona] = None):
```

3. Inside `portfolio_manager_node`, replace the line that reads `history = state["risk_debate_state"]["history"]` and the line that builds the f-string `**Risk Analysts Debate History:**\n{history}` with:
```python
        risk_debate_state = state["risk_debate_state"]
        weighted_debate = format_weighted_risk_debate(risk_debate_state, persona)
        # ... in the prompt f-string, replace `{history}` with `{weighted_debate}`
```

4. Wrap the standing PM instructions through `apply_fragment`. The simplest approach: assemble the static instructions (everything except the dynamic context block) into one variable, run it through `apply_fragment(..., persona)`, then concatenate with the dynamic context. Concrete shape:

```python
        base_instructions = """As the Portfolio Manager, synthesize the risk analysts' debate ...
**Rating Scale** (use exactly one): ..."""   # the parts that are constant per persona
        base_instructions = apply_fragment(base_instructions, persona)

        prompt = f"""{base_instructions}

{instrument_context}

**Context:**
- Research Manager's investment plan: **{research_plan}**
- Trader's transaction proposal: **{trader_plan}**
{lessons_line}
**Risk Analysts Debate History:**
{weighted_debate}

---

Be decisive and ground every conclusion in specific evidence from the analysts.{get_language_instruction()}"""
```

Keep the existing `bind_structured` + `invoke_structured_or_freetext` invocation untouched.

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/graph/test_pm_risk_weights.py -v
```

Expected: 2 PASS.

- [ ] **Step 5: Run the broader suite**

```bash
pytest -m "not integration" --tb=short -q
```

Expected: previously-passing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add tradingagents/agents/managers/portfolio_manager.py tests/graph/test_pm_risk_weights.py
git commit -m "feat(pm): format risk debate with persona weights (D4 wiring)"
```

---

## Task 12: Thread persona through GraphSetup and TradingAgentsGraph

**Files:**
- Modify: `tradingagents/graph/setup.py`
- Modify: `tradingagents/graph/trading_graph.py`
- Test: `tests/graph/test_persona_threaded_end_to_end.py`

This is the call-site change that makes the wiring from Tasks 10–11 actually fire when `config["persona_id"]` is set. `TradingAgentsGraph.__init__` loads the `Persona` from `config["persona_id"]` (falling back to `None`) and passes it to `GraphSetup`. `GraphSetup` then threads it into every factory call.

- [ ] **Step 1: Write the failing test**

Create `tests/graph/test_persona_threaded_end_to_end.py`:

```python
"""End-to-end: setting config['persona_id'] reaches every factory invocation."""

import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.unit
def test_graph_setup_accepts_persona():
    from tradingagents.graph.setup import GraphSetup
    sig = __import__("inspect").signature(GraphSetup.__init__)
    assert "persona" in sig.parameters


@pytest.mark.unit
def test_trading_agents_graph_loads_persona_from_config(tmp_path, monkeypatch):
    """When config['persona_id']='macro', TradingAgentsGraph loads macro.yaml
    and forwards a Persona to GraphSetup."""
    from tradingagents.default_config import DEFAULT_CONFIG
    config = dict(DEFAULT_CONFIG)
    config["iic_db_path"] = str(tmp_path / "iic.db")
    config["iic_data_dir"] = str(tmp_path / "data")
    config["persona_id"] = "macro"
    # Avoid heavy LLM construction.
    with patch("tradingagents.graph.trading_graph.create_llm_client",
               return_value=MagicMock(get_llm=MagicMock(return_value=MagicMock()))), \
         patch("tradingagents.graph.trading_graph.GraphSetup") as mock_setup:
        mock_setup.return_value.setup_graph.return_value = MagicMock()
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        TradingAgentsGraph(selected_analysts=["market"], config=config)

    # GraphSetup must have been called with persona=<a Persona whose id=='macro'>
    call = mock_setup.call_args
    persona = call.kwargs.get("persona") or (call.args[-1] if call.args else None)
    assert persona is not None
    assert persona.id == "macro"


@pytest.mark.unit
def test_graph_setup_threads_persona_into_factory_calls():
    """GraphSetup.setup_graph must pass persona into the analyst & PM factories."""
    from tradingagents.personas.loader import load_persona_from_string
    p = load_persona_from_string("""
id: macro_test
name: Macro Test
description: x
system_prompt_fragment: "X"
llm: {deep_think_llm: m, quick_think_llm: m}
analysts: {include: [market], exclude: []}
risk_debate: {weights: {aggressive: 0.5, conservative: 1.5, neutral: 1.0}}
memory_scope: hybrid
""")

    from tradingagents.graph.setup import GraphSetup
    from tradingagents.graph.conditional_logic import ConditionalLogic

    captured = {}
    real_market = __import__("tradingagents.agents.analysts.market_analyst",
                              fromlist=["create_market_analyst"]).create_market_analyst
    real_pm = __import__("tradingagents.agents.managers.portfolio_manager",
                          fromlist=["create_portfolio_manager"]).create_portfolio_manager

    def spy_market(llm, persona=None):
        captured["market_persona"] = persona
        return real_market(MagicMock(), persona=None)  # avoid touching real LLMs

    def spy_pm(llm, persona=None):
        captured["pm_persona"] = persona
        return real_pm(MagicMock(), persona=None)

    with patch("tradingagents.graph.setup.create_market_analyst", side_effect=spy_market), \
         patch("tradingagents.graph.setup.create_portfolio_manager", side_effect=spy_pm):
        gs = GraphSetup(
            quick_thinking_llm=MagicMock(),
            deep_thinking_llm=MagicMock(),
            tool_nodes={"market": MagicMock()},
            conditional_logic=ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1),
            persona=p,
        )
        gs.setup_graph(selected_analysts=["market"])

    assert captured["market_persona"] is p
    assert captured["pm_persona"] is p
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/graph/test_persona_threaded_end_to_end.py -v
```

Expected: 3 FAILs.

- [ ] **Step 3: Modify `GraphSetup`**

In `tradingagents/graph/setup.py`:

1. Add imports near top:
```python
from typing import Optional
from tradingagents.personas.loader import Persona
```

2. Change `GraphSetup.__init__` signature to:
```python
    def __init__(
        self,
        quick_thinking_llm: Any,
        deep_thinking_llm: Any,
        tool_nodes: Dict[str, ToolNode],
        conditional_logic: ConditionalLogic,
        analyst_concurrency_limit: int = 1,
        persona: Optional[Persona] = None,
    ):
        ...
        self.persona = persona
```

3. Inside `setup_graph`, change the `analyst_factories` dict so every factory is called with `persona=self.persona`. Same for the researcher / manager / trader / debator / PM lines. Example:
```python
        analyst_factories = {
            "market":       lambda: create_market_analyst(self.quick_thinking_llm, persona=self.persona),
            "social":       lambda: create_sentiment_analyst(self.quick_thinking_llm, persona=self.persona),
            "news":         lambda: create_news_analyst(self.quick_thinking_llm, persona=self.persona),
            "fundamentals": lambda: create_fundamentals_analyst(self.quick_thinking_llm, persona=self.persona),
            "derivatives":  lambda: create_derivative_analyst(self.quick_thinking_llm, persona=self.persona),
        }

        bull_researcher_node      = create_bull_researcher(self.quick_thinking_llm, persona=self.persona)
        bear_researcher_node      = create_bear_researcher(self.quick_thinking_llm, persona=self.persona)
        research_manager_node     = create_research_manager(self.deep_thinking_llm, persona=self.persona)
        trader_node               = create_trader(self.quick_thinking_llm, persona=self.persona)
        aggressive_analyst        = create_aggressive_debator(self.quick_thinking_llm, persona=self.persona)
        neutral_analyst           = create_neutral_debator(self.quick_thinking_llm, persona=self.persona)
        conservative_analyst      = create_conservative_debator(self.quick_thinking_llm, persona=self.persona)
        portfolio_manager_node    = create_portfolio_manager(self.deep_thinking_llm, persona=self.persona)
```

- [ ] **Step 4: Modify `TradingAgentsGraph`**

In `tradingagents/graph/trading_graph.py`:

1. Add helper near top:
```python
from typing import Optional as _Optional
from tradingagents.personas.loader import Persona, load_persona_from_file
from pathlib import Path as _Path


def _load_persona_from_config(config: Dict[str, Any]) -> _Optional[Persona]:
    pid = config.get("persona_id")
    if not pid:
        return None
    yaml_path = (
        _Path(__file__).resolve().parent.parent / "personas" / f"{pid}.yaml"
    )
    if not yaml_path.exists():
        return None
    return load_persona_from_file(str(yaml_path))
```

2. Inside `TradingAgentsGraph.__init__`, after `self.config = config or DEFAULT_CONFIG`, add:
```python
        self.persona = _load_persona_from_config(self.config)
```

3. Update the `GraphSetup` construction to pass `persona`:
```python
        self.graph_setup = GraphSetup(
            self.quick_thinking_llm,
            self.deep_thinking_llm,
            self.tool_nodes,
            self.conditional_logic,
            analyst_concurrency_limit=self.config.get("analyst_concurrency_limit", 1),
            persona=self.persona,
        )
```

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/graph/test_persona_threaded_end_to_end.py -v
```

Expected: 3 PASS.

- [ ] **Step 6: Run the broader suite**

```bash
pytest -m "not integration" --tb=short -q
```

Expected: previously-passing tests still pass.

- [ ] **Step 7: Commit**

```bash
git add tradingagents/graph/setup.py tradingagents/graph/trading_graph.py \
        tests/graph/test_persona_threaded_end_to_end.py
git commit -m "feat(graph): thread Persona from config through GraphSetup to all factories"
```

---

## Task 13: backtest.reflection — outcome_log on-close hook

**Files:**
- Create: `tradingagents/backtest/reflection.py`
- Test: `tests/backtest/test_reflection.py`

Writes one persona-aware `outcome_log` row when a forward test matures.

- [ ] **Step 1: Write the failing tests**

Create `tests/backtest/test_reflection.py`:

```python
import json
import uuid
from datetime import datetime, timezone

import pytest


@pytest.fixture
def conn(tmp_path):
    from tradingagents.persistence.db import connect
    return connect(str(tmp_path / "iic.db"))


@pytest.fixture
def seeded_run(conn):
    """Insert one runs row so the FK from outcome_log is satisfied."""
    from tradingagents.persistence import store
    run_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    store.insert_run(conn, run_id=run_id, ticker="AAPL", persona_id="macro",
                     started_ts=now, artifact_dir=f"runs/{run_id}")
    return run_id


@pytest.mark.unit
def test_write_outcome_log_on_close_writes_one_row(conn, seeded_run):
    from tradingagents.backtest.reflection import write_outcome_log_on_close

    write_outcome_log_on_close(
        conn,
        run_id=seeded_run,
        ticker="AAPL",
        persona_id="macro",
        decision="BUY",
        alpha=0.0123,
        total_return=0.0274,
        backtest_id=42,
        close_date="2026-05-26",
        benchmark="SPY",
    )

    rows = list(conn.execute(
        "SELECT * FROM outcome_log WHERE run_id = ?", (seeded_run,)
    ))
    assert len(rows) == 1
    row = rows[0]
    assert row["ticker"] == "AAPL"
    assert row["decision"] == "BUY"
    assert row["pnl_proxy"] == pytest.approx(0.0123)
    tags = json.loads(row["tags"])
    assert tags["persona_id"] == "macro"
    assert tags["backtest_id"] == 42
    assert tags["source"] == "forward_test"
    assert "alpha" in row["outcome_md"].lower() or "2026-05-26" in row["outcome_md"]


@pytest.mark.unit
def test_write_outcome_log_on_close_is_idempotent_by_design(conn, seeded_run):
    """Two calls write two rows — uniqueness is the caller's job (close fires once)."""
    from tradingagents.backtest.reflection import write_outcome_log_on_close
    for _ in range(2):
        write_outcome_log_on_close(
            conn, run_id=seeded_run, ticker="AAPL", persona_id="macro",
            decision="HOLD", alpha=0.0, total_return=0.0,
            backtest_id=1, close_date="2026-05-26", benchmark="SPY",
        )
    rows = list(conn.execute(
        "SELECT * FROM outcome_log WHERE run_id = ?", (seeded_run,)
    ))
    assert len(rows) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/backtest/test_reflection.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `reflection.py`**

Create `tradingagents/backtest/reflection.py`:

```python
"""F2 reflection — write a persona-aware outcome_log row when a forward
test matures. The existing _resolve_pending_entries reflection loop is
untouched; this is the second, persona-aware scoring path."""

from __future__ import annotations

import sqlite3
from typing import Optional

from tradingagents.persistence.memory import OutcomeLog


def write_outcome_log_on_close(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    ticker: str,
    persona_id: Optional[str],
    decision: str,
    alpha: float,
    total_return: float,
    backtest_id: int,
    close_date: str,
    benchmark: str,
) -> int:
    """Append one row to outcome_log tagged with persona/backtest context."""
    outcome_md = (
        f"forward-test close {close_date}: "
        f"decision={decision}, total_return={total_return:+.4f}, "
        f"alpha vs {benchmark}={alpha:+.4f}"
    )
    log = OutcomeLog(conn)
    return log.append(
        run_id=run_id,
        ticker=ticker,
        decision=decision,
        outcome_md=outcome_md,
        pnl_proxy=alpha,
        tags={
            "persona_id": persona_id,
            "backtest_id": backtest_id,
            "source": "forward_test",
            "close_date": close_date,
            "benchmark": benchmark,
        },
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/backtest/test_reflection.py -v
```

Expected: 2 passing.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/backtest/reflection.py tests/backtest/test_reflection.py
git commit -m "feat(backtest): write_outcome_log_on_close — persona-aware reflection hook"
```

---

## Task 14: BacktestHarness skeleton + watchlist open phase

**Files:**
- Create: `tradingagents/backtest/harness.py`
- Test: `tests/backtest/test_harness.py`

Watchlist mode in two phases:
1. **Open phase** (this task) — insert `backtests` row, invoke graph per (ticker × persona), insert `backtest_runs` rows with status=open.
2. **Maturation phase** (Task 15) — when `end_date <= today`, fetch close prices, compute metrics, transition to closed.

The graph invocation is wrapped behind a tiny `GraphRunner` protocol so tests can substitute a fast mock.

- [ ] **Step 1: Write the failing tests**

Create `tests/backtest/test_harness.py`:

```python
import json
import uuid
from datetime import date, datetime, timezone
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def conn(tmp_path):
    from tradingagents.persistence.db import connect
    return connect(str(tmp_path / "iic.db"))


@pytest.fixture
def data_dir(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    return str(d)


@pytest.fixture
def fake_graph_runner():
    """Mock graph runner: returns a fresh run_id and a deterministic decision
    per (ticker, persona)."""
    class FakeRunner:
        def __init__(self):
            self.invocations = []

        def run(self, *, ticker, trade_date, persona_id, conn):
            from tradingagents.persistence import store
            run_id = uuid.uuid4().hex
            now = datetime.now(timezone.utc).isoformat()
            store.insert_run(conn, run_id=run_id, ticker=ticker,
                             persona_id=persona_id, started_ts=now,
                             artifact_dir=f"runs/{run_id}")
            # Choose a decision deterministically from persona for test predictability
            decision = {"macro": "BUY", "value": "HOLD", "momentum": "SELL"}.get(
                persona_id, "HOLD"
            )
            store.finalize_run(conn, run_id=run_id, ended_ts=now,
                               status="complete", decision=decision)
            self.invocations.append((ticker, trade_date, persona_id))
            return run_id, decision
    return FakeRunner()


@pytest.fixture
def fake_price_chain():
    """Mock price chain: returns N-day daily Bars."""
    from tradingagents.backtest.prices import Bars, Resolution

    class FakeChain:
        def __init__(self):
            self.calls = []

        def get_bars(self, ticker, start, end, resolution):
            self.calls.append((ticker, start, end, resolution))
            days = (end - start).days + 1
            # synthetic prices: 100, 101, 102, ...
            from datetime import datetime as dt
            bars = [
                (dt.combine(start, dt.min.time()).replace(day=start.day + i)
                  if (start.day + i) <= 28 else dt(start.year, start.month, 28),
                 100.0 + i)
                for i in range(min(days, 5))
            ]
            return Bars(ticker=ticker, resolution=resolution, bars=bars,
                        source="fake")
    return FakeChain()


@pytest.mark.unit
def test_watchlist_open_inserts_backtests_and_backtest_runs(
    conn, data_dir, fake_graph_runner, fake_price_chain
):
    from tradingagents.backtest.harness import BacktestHarness
    h = BacktestHarness(conn=conn, data_dir=data_dir,
                         graph_runner=fake_graph_runner,
                         price_chain=fake_price_chain)
    backtest_id = h.run_watchlist(
        tickers=["AAPL", "MSFT"],
        personas=["macro", "value"],
        start_date=date(2030, 1, 1),  # future → don't auto-mature
        end_date=date(2030, 1, 31),
    )

    backtests = list(conn.execute("SELECT * FROM backtests WHERE backtest_id=?",
                                    (backtest_id,)))
    assert len(backtests) == 1
    assert backtests[0]["status"] == "open"
    assert json.loads(backtests[0]["universe"]) == ["AAPL", "MSFT"]

    runs = list(conn.execute("SELECT * FROM backtest_runs WHERE backtest_id=?",
                              (backtest_id,)))
    assert len(runs) == 4  # 2 tickers × 2 personas
    for r in runs:
        m = json.loads(r["metrics"])
        assert m["status"] == "open"
        assert m["decision"] in ("BUY", "HOLD", "SELL")
        assert m["entry_price"] == pytest.approx(100.0)
        assert m["entry_date"] == "2030-01-01"
        assert m["scheduled_close_date"] == "2030-01-31"
        assert m["resolution"] == "1d"
        assert m["price_source"] == "fake"


@pytest.mark.unit
def test_watchlist_open_calls_graph_runner_per_ticker_persona(
    conn, data_dir, fake_graph_runner, fake_price_chain
):
    from tradingagents.backtest.harness import BacktestHarness
    h = BacktestHarness(conn=conn, data_dir=data_dir,
                         graph_runner=fake_graph_runner,
                         price_chain=fake_price_chain)
    h.run_watchlist(tickers=["AAPL", "MSFT"],
                     personas=["macro", "value", "momentum"],
                     start_date=date(2030, 1, 1),
                     end_date=date(2030, 1, 31))
    assert len(fake_graph_runner.invocations) == 6  # 2 × 3
    # Every persona seen, every ticker seen
    personas_seen = {p for (_, _, p) in fake_graph_runner.invocations}
    tickers_seen = {t for (t, _, _) in fake_graph_runner.invocations}
    assert personas_seen == {"macro", "value", "momentum"}
    assert tickers_seen == {"AAPL", "MSFT"}


@pytest.mark.unit
def test_watchlist_open_does_not_mature_future_window(
    conn, data_dir, fake_graph_runner, fake_price_chain
):
    """When end_date > today, all backtest_runs stay status=open."""
    from tradingagents.backtest.harness import BacktestHarness
    h = BacktestHarness(conn=conn, data_dir=data_dir,
                         graph_runner=fake_graph_runner,
                         price_chain=fake_price_chain)
    backtest_id = h.run_watchlist(tickers=["AAPL"], personas=["macro"],
                                    start_date=date(2030, 1, 1),
                                    end_date=date(2030, 1, 31))
    runs = list(conn.execute("SELECT metrics FROM backtest_runs WHERE backtest_id=?",
                              (backtest_id,)))
    for r in runs:
        m = json.loads(r["metrics"])
        assert m["status"] == "open"
        assert "close_date" not in m
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/backtest/test_harness.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `harness.py` — open phase only**

Create `tradingagents/backtest/harness.py`:

```python
"""F2 BacktestHarness — orchestrator for the two invocation modes.

Watchlist mode: open + maturation (this file, Tasks 14-15).
Brief-scoped mode: open from persisted runs + maturation (Task 16).

The harness is decoupled from TradingAgentsGraph via the GraphRunner
Protocol so tests can substitute a fast mock. Same for prices via
PriceFallbackChain (or anything quacking get_bars(...) → Bars).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, List, Optional, Protocol, Tuple

from tradingagents.backtest.prices import Resolution
from tradingagents.backtest.simulator import position_from_decision


class GraphRunner(Protocol):
    """Anything that can invoke a per-persona graph and persist a runs row."""
    def run(self, *, ticker: str, trade_date: str, persona_id: str,
            conn: sqlite3.Connection) -> Tuple[str, str]:
        """Return ``(run_id, decision)``. The runs row must already be written."""
        ...


@dataclass
class BacktestHarness:
    conn: sqlite3.Connection
    data_dir: str
    graph_runner: GraphRunner
    price_chain: object   # any get_bars(...) → Bars producer
    resolution: Resolution = Resolution.DAILY
    benchmark: str = "SPY"

    def run_watchlist(
        self,
        *,
        tickers: List[str],
        personas: List[str],
        start_date: date,
        end_date: date,
    ) -> int:
        """Open one backtest covering tickers × personas. Auto-mature if
        ``end_date <= today``. Returns the new ``backtest_id``."""
        backtest_id = self._insert_backtests_row(
            triggered_by_brief_id=None,
            universe=tickers,
            start_date=start_date,
            end_date=end_date,
        )

        for ticker in tickers:
            for persona_id in personas:
                self._open_forward_test(
                    backtest_id=backtest_id,
                    ticker=ticker,
                    persona_id=persona_id,
                    start_date=start_date,
                    end_date=end_date,
                )

        if end_date <= date.today():
            self._mature_all_open(backtest_id=backtest_id, end_date=end_date)
            self._close_backtest(backtest_id)

        return backtest_id

    # ---------- internals ----------

    def _insert_backtests_row(
        self,
        *,
        triggered_by_brief_id: Optional[str],
        universe: List[str],
        start_date: date,
        end_date: date,
    ) -> int:
        cur = self.conn.execute(
            "INSERT INTO backtests "
            "(triggered_by_brief_id, universe, start_date, end_date, status, "
            " report_path, created_ts) VALUES (?, ?, ?, ?, 'open', NULL, ?)",
            (
                triggered_by_brief_id,
                json.dumps(universe),
                start_date.isoformat(),
                end_date.isoformat(),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    def _open_forward_test(
        self,
        *,
        backtest_id: int,
        ticker: str,
        persona_id: str,
        start_date: date,
        end_date: date,
    ) -> None:
        # 1. Invoke the graph at start_date — produces runs row + decision.
        run_id, decision = self.graph_runner.run(
            ticker=ticker,
            trade_date=start_date.isoformat(),
            persona_id=persona_id,
            conn=self.conn,
        )

        # 2. Fetch entry price (single-bar window @ start_date).
        bars = self.price_chain.get_bars(
            ticker, start_date, start_date, self.resolution,
        )
        if not bars.bars:
            self._insert_backtest_run_errored(
                backtest_id=backtest_id, ticker=ticker, persona_id=persona_id,
                run_id=run_id, error=f"no bars for entry {start_date}",
            )
            return
        entry_price = bars.bars[0][1]
        price_source = bars.source

        # 3. Fetch entry benchmark price too (best-effort).
        try:
            bench_bars = self.price_chain.get_bars(
                self.benchmark, start_date, start_date, self.resolution,
            )
            benchmark_entry_price = bench_bars.bars[0][1] if bench_bars.bars else None
        except Exception:
            benchmark_entry_price = None

        # 4. Translate decision → position.
        try:
            position = position_from_decision(decision)
        except ValueError:
            position = 0  # unknown → flat (HOLD-ish)

        metrics = {
            "status": "open",
            "run_id": run_id,
            "decision": decision,
            "position": position,
            "entry_date": start_date.isoformat(),
            "entry_price": entry_price,
            "benchmark": self.benchmark,
            "benchmark_entry_price": benchmark_entry_price,
            "scheduled_close_date": end_date.isoformat(),
            "resolution": str(self.resolution.value),
            "price_source": price_source,
        }
        self.conn.execute(
            "INSERT INTO backtest_runs (backtest_id, persona_id, ticker, metrics)"
            " VALUES (?, ?, ?, ?)",
            (backtest_id, persona_id, ticker, json.dumps(metrics)),
        )
        self.conn.commit()

    def _insert_backtest_run_errored(
        self,
        *,
        backtest_id: int,
        ticker: str,
        persona_id: str,
        run_id: Optional[str],
        error: str,
    ) -> None:
        metrics = {
            "status": "errored",
            "run_id": run_id,
            "error": error,
            "errored_sources": [],
        }
        self.conn.execute(
            "INSERT INTO backtest_runs (backtest_id, persona_id, ticker, metrics)"
            " VALUES (?, ?, ?, ?)",
            (backtest_id, persona_id, ticker, json.dumps(metrics)),
        )
        self.conn.commit()

    # Maturation lives in Task 15.
    def _mature_all_open(self, *, backtest_id: int, end_date: date) -> None:
        raise NotImplementedError("Maturation lands in Task 15.")

    def _close_backtest(self, backtest_id: int) -> None:
        self.conn.execute(
            "UPDATE backtests SET status='closed' WHERE backtest_id=?",
            (backtest_id,),
        )
        self.conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/backtest/test_harness.py -v
```

Expected: 3 passing (open-phase tests).

- [ ] **Step 5: Commit**

```bash
git add tradingagents/backtest/harness.py tests/backtest/test_harness.py
git commit -m "feat(backtest): BacktestHarness skeleton + watchlist open phase"
```

---

## Task 15: BacktestHarness — inline maturation phase

**Files:**
- Modify: `tradingagents/backtest/harness.py` (implement `_mature_all_open`)
- Modify: `tests/backtest/test_harness.py` (add maturation tests)

When `end_date <= today`, the harness matures every open `backtest_runs` row in the same call: fetch the full price window, compute the full metrics, transition to closed, write the outcome_log row.

- [ ] **Step 1: Append the failing tests**

Append to `tests/backtest/test_harness.py`:

```python
@pytest.fixture
def historical_price_chain():
    """Mock chain returning a deterministic 6-bar series for any ticker."""
    from tradingagents.backtest.prices import Bars, Resolution
    from datetime import datetime as dt

    class HistoricalChain:
        def __init__(self):
            # 30-day window of daily bars
            self.bars_for = {
                ("AAPL", "entry"):    [(dt(2026, 4, 26), 200.0)],
                ("AAPL", "full"):     [
                    (dt(2026, 4, 26), 200.0),
                    (dt(2026, 4, 30), 202.0),
                    (dt(2026, 5,  5), 198.0),
                    (dt(2026, 5, 12), 210.0),
                    (dt(2026, 5, 20), 215.0),
                    (dt(2026, 5, 26), 220.0),
                ],
                ("SPY",  "entry"):    [(dt(2026, 4, 26), 500.0)],
                ("SPY",  "full"):     [
                    (dt(2026, 4, 26), 500.0),
                    (dt(2026, 4, 30), 501.0),
                    (dt(2026, 5,  5), 499.0),
                    (dt(2026, 5, 12), 505.0),
                    (dt(2026, 5, 20), 507.0),
                    (dt(2026, 5, 26), 510.0),
                ],
            }

        def get_bars(self, ticker, start, end, resolution):
            # Single-day call → "entry" slice; multi-day → "full" slice.
            kind = "entry" if start == end else "full"
            bars = self.bars_for.get((ticker, kind), [])
            return Bars(ticker=ticker, resolution=resolution, bars=bars,
                        source="historical")

    return HistoricalChain()


@pytest.mark.unit
def test_watchlist_with_past_end_date_matures_inline(
    conn, data_dir, fake_graph_runner, historical_price_chain
):
    """When end_date <= today, all backtest_runs close inline."""
    from tradingagents.backtest.harness import BacktestHarness
    h = BacktestHarness(conn=conn, data_dir=data_dir,
                         graph_runner=fake_graph_runner,
                         price_chain=historical_price_chain)
    backtest_id = h.run_watchlist(
        tickers=["AAPL"], personas=["macro"],
        start_date=date(2026, 4, 26), end_date=date(2026, 5, 26),
    )

    backtests_row = conn.execute(
        "SELECT * FROM backtests WHERE backtest_id=?", (backtest_id,)
    ).fetchone()
    assert backtests_row["status"] == "closed"

    runs = list(conn.execute(
        "SELECT metrics FROM backtest_runs WHERE backtest_id=?", (backtest_id,)
    ))
    assert len(runs) == 1
    m = json.loads(runs[0]["metrics"])
    assert m["status"] == "closed"
    assert m["close_date"] == "2026-05-26"
    assert m["exit_price"] == pytest.approx(220.0)
    # macro persona ⇒ BUY ⇒ position=+1 ⇒ total_return = (220-200)/200 = +0.10
    assert m["total_return"] == pytest.approx(0.10, rel=1e-6)
    assert m["benchmark_return"] == pytest.approx((510 - 500) / 500, rel=1e-6)
    assert m["alpha"] == pytest.approx(0.10 - 0.02, rel=1e-6)
    assert isinstance(m["returns"], list) and len(m["returns"]) >= 1
    assert "sharpe" in m and "max_drawdown" in m and "win_rate" in m
    assert m["holding_days_elapsed"] == 30


@pytest.mark.unit
def test_maturation_writes_outcome_log_row(
    conn, data_dir, fake_graph_runner, historical_price_chain
):
    from tradingagents.backtest.harness import BacktestHarness
    h = BacktestHarness(conn=conn, data_dir=data_dir,
                         graph_runner=fake_graph_runner,
                         price_chain=historical_price_chain)
    h.run_watchlist(tickers=["AAPL"], personas=["macro"],
                     start_date=date(2026, 4, 26), end_date=date(2026, 5, 26))
    rows = list(conn.execute("SELECT * FROM outcome_log"))
    assert len(rows) == 1
    assert rows[0]["ticker"] == "AAPL"
    tags = json.loads(rows[0]["tags"])
    assert tags["persona_id"] == "macro"
    assert tags["source"] == "forward_test"


@pytest.mark.unit
def test_maturation_handles_missing_exit_price_as_errored(
    conn, data_dir, fake_graph_runner
):
    """If the price chain raises for the exit fetch, the row is errored,
    not silently zero-returns."""
    from tradingagents.backtest.harness import BacktestHarness

    class FlakyChain:
        def get_bars(self, ticker, start, end, resolution):
            from tradingagents.backtest.prices import Bars, Resolution
            from datetime import datetime as dt
            if start == end:  # entry fetch
                return Bars(ticker=ticker, resolution=resolution,
                            bars=[(dt(2026, 4, 26), 100.0)], source="x")
            raise RuntimeError("exit fetch failed")

    h = BacktestHarness(conn=conn, data_dir=data_dir,
                         graph_runner=fake_graph_runner,
                         price_chain=FlakyChain())
    backtest_id = h.run_watchlist(
        tickers=["AAPL"], personas=["macro"],
        start_date=date(2026, 4, 26), end_date=date(2026, 5, 26),
    )
    runs = list(conn.execute("SELECT metrics FROM backtest_runs WHERE backtest_id=?",
                              (backtest_id,)))
    m = json.loads(runs[0]["metrics"])
    assert m["status"] == "errored"
    assert "exit" in m["error"].lower() or "fetch" in m["error"].lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/backtest/test_harness.py -v
```

Expected: 3 new FAILs (NotImplementedError from `_mature_all_open`).

- [ ] **Step 3: Implement `_mature_all_open`**

In `tradingagents/backtest/harness.py`, replace the placeholder `_mature_all_open` with the real implementation. Add a top-level import:

```python
from tradingagents.backtest.simulator import (
    compute_returns, max_drawdown, sharpe_ratio, total_return, win_rate,
)
from tradingagents.backtest.reflection import write_outcome_log_on_close
```

Then the method:

```python
    def _mature_all_open(self, *, backtest_id: int, end_date: date) -> None:
        """Walk every open backtest_runs row for this backtest and close it."""
        rows = list(self.conn.execute(
            "SELECT btr_id, persona_id, ticker, metrics "
            "FROM backtest_runs WHERE backtest_id = ?",
            (backtest_id,),
        ))
        for row in rows:
            metrics = json.loads(row["metrics"])
            if metrics.get("status") != "open":
                continue
            self._mature_one(
                btr_id=row["btr_id"],
                persona_id=row["persona_id"],
                ticker=row["ticker"],
                metrics=metrics,
                end_date=end_date,
            )

    def _mature_one(
        self,
        *,
        btr_id: int,
        persona_id: str,
        ticker: str,
        metrics: dict,
        end_date: date,
    ) -> None:
        entry_date = date.fromisoformat(metrics["entry_date"])
        entry_price = metrics["entry_price"]
        position = metrics["position"]
        resolution = Resolution(metrics["resolution"])

        # Fetch the full window. Failures mark the row errored.
        try:
            bars = self.price_chain.get_bars(
                ticker, entry_date, end_date, resolution,
            )
        except Exception as e:
            metrics["status"] = "errored"
            metrics["error"] = f"price fetch failed during maturation: {e!r}"
            self._update_metrics(btr_id, metrics)
            return

        if not bars.bars:
            metrics["status"] = "errored"
            metrics["error"] = f"empty bars for maturation window"
            self._update_metrics(btr_id, metrics)
            return

        exit_price = bars.bars[-1][1]
        returns = compute_returns(bars, position=position)

        # Benchmark — best-effort; if it fails, alpha defaults to total_return.
        try:
            bench_bars = self.price_chain.get_bars(
                self.benchmark, entry_date, end_date, resolution,
            )
            bench_entry = bench_bars.bars[0][1] if bench_bars.bars else None
            bench_exit  = bench_bars.bars[-1][1] if bench_bars.bars else None
            if bench_entry and bench_entry > 0:
                bench_return = (bench_exit - bench_entry) / bench_entry
            else:
                bench_return = 0.0
        except Exception:
            bench_entry, bench_exit, bench_return = None, None, 0.0

        tr = total_return(entry=entry_price, exit=exit_price, position=position)
        metrics.update({
            "status": "closed",
            "close_date": end_date.isoformat(),
            "exit_price": exit_price,
            "benchmark_exit_price": bench_exit,
            "total_return": tr,
            "benchmark_return": bench_return,
            "alpha": tr - bench_return,
            "returns": returns,
            "sharpe": sharpe_ratio(returns, resolution=resolution),
            "max_drawdown": max_drawdown(returns),
            "win_rate": win_rate(returns),
            "holding_days_elapsed": (end_date - entry_date).days,
        })
        self._update_metrics(btr_id, metrics)

        write_outcome_log_on_close(
            self.conn,
            run_id=metrics["run_id"],
            ticker=ticker,
            persona_id=persona_id,
            decision=metrics["decision"],
            alpha=metrics["alpha"],
            total_return=metrics["total_return"],
            backtest_id=self._backtest_id_for(btr_id),
            close_date=metrics["close_date"],
            benchmark=self.benchmark,
        )

    def _update_metrics(self, btr_id: int, metrics: dict) -> None:
        self.conn.execute(
            "UPDATE backtest_runs SET metrics = ? WHERE btr_id = ?",
            (json.dumps(metrics), btr_id),
        )
        self.conn.commit()

    def _backtest_id_for(self, btr_id: int) -> int:
        row = self.conn.execute(
            "SELECT backtest_id FROM backtest_runs WHERE btr_id = ?", (btr_id,),
        ).fetchone()
        return row["backtest_id"]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/backtest/test_harness.py -v
```

Expected: 6 passing (3 from Task 14 + 3 new).

- [ ] **Step 5: Commit**

```bash
git add tradingagents/backtest/harness.py tests/backtest/test_harness.py
git commit -m "feat(backtest): inline maturation phase + outcome_log writes on close"
```

---

## Task 16: BacktestHarness — brief-scoped mode

**Files:**
- Modify: `tradingagents/backtest/harness.py` (add `run_brief_scoped`)
- Modify: `tests/backtest/test_harness.py` (brief-scoped tests)

Brief-scoped mode is for F5. It reads `briefs.run_ids`, pulls existing decisions out of `runs`, and opens forward tests using those decisions. **No fresh graph invocation.**

- [ ] **Step 1: Append the failing tests**

Append to `tests/backtest/test_harness.py`:

```python
@pytest.fixture
def seeded_brief(conn, fake_graph_runner):
    """Insert a brief with three runs (one per persona) for AAPL."""
    from tradingagents.persistence import store
    run_ids = []
    for persona_id in ("macro", "value", "momentum"):
        rid, _ = fake_graph_runner.run(
            ticker="AAPL", trade_date="2026-04-26",
            persona_id=persona_id, conn=conn,
        )
        run_ids.append(rid)

    brief_id = uuid.uuid4().hex
    store.insert_brief(conn,
        brief_id=brief_id, mode="deep_dive", scope="AAPL",
        generated_ts="2026-04-26T12:00:00+00:00",
        content_path=f"briefs/{brief_id}.md",
        run_ids=run_ids,
    )
    return brief_id, run_ids


@pytest.mark.unit
def test_brief_scoped_opens_one_run_per_brief_run_id(
    conn, data_dir, fake_graph_runner, historical_price_chain, seeded_brief
):
    brief_id, expected_run_ids = seeded_brief
    fake_graph_runner.invocations.clear()  # ensure brief-scoped doesn't re-invoke

    from tradingagents.backtest.harness import BacktestHarness
    h = BacktestHarness(conn=conn, data_dir=data_dir,
                         graph_runner=fake_graph_runner,
                         price_chain=historical_price_chain)
    backtest_id = h.run_brief_scoped(brief_id=brief_id)

    # No fresh graph runs.
    assert fake_graph_runner.invocations == []

    bt_row = conn.execute("SELECT * FROM backtests WHERE backtest_id=?",
                           (backtest_id,)).fetchone()
    assert bt_row["triggered_by_brief_id"] == brief_id
    assert json.loads(bt_row["universe"]) == ["AAPL"]

    runs = list(conn.execute("SELECT * FROM backtest_runs WHERE backtest_id=?",
                              (backtest_id,)))
    assert len(runs) == 3
    seen_run_ids = {json.loads(r["metrics"])["run_id"] for r in runs}
    assert seen_run_ids == set(expected_run_ids)


@pytest.mark.unit
def test_brief_scoped_entry_date_matches_brief_generated_ts(
    conn, data_dir, fake_graph_runner, historical_price_chain, seeded_brief
):
    brief_id, _ = seeded_brief
    from tradingagents.backtest.harness import BacktestHarness
    h = BacktestHarness(conn=conn, data_dir=data_dir,
                         graph_runner=fake_graph_runner,
                         price_chain=historical_price_chain)
    backtest_id = h.run_brief_scoped(brief_id=brief_id)
    runs = list(conn.execute("SELECT metrics FROM backtest_runs WHERE backtest_id=?",
                              (backtest_id,)))
    for r in runs:
        m = json.loads(r["metrics"])
        assert m["entry_date"] == "2026-04-26"
        # window is 30 calendar days from the brief
        assert m["scheduled_close_date"] == "2026-05-26"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/backtest/test_harness.py -v
```

Expected: 2 new FAILs (AttributeError `run_brief_scoped`).

- [ ] **Step 3: Implement `run_brief_scoped`**

In `tradingagents/backtest/harness.py`, add the method on `BacktestHarness`:

```python
    def run_brief_scoped(
        self,
        *,
        brief_id: str,
        window_days: int = 30,
    ) -> int:
        """Open forward tests for every run_id in the brief.

        Reads the brief, resolves each run_id → (ticker, persona_id, decision,
        started_ts), opens a backtest_runs row using those decisions WITHOUT
        re-invoking the graph. Auto-matures if scheduled_close_date <= today.
        """
        # 1. Resolve brief → run_ids and entry_date.
        brief_row = self.conn.execute(
            "SELECT generated_ts, run_ids FROM briefs WHERE brief_id = ?",
            (brief_id,),
        ).fetchone()
        if brief_row is None:
            raise ValueError(f"brief_id {brief_id!r} not found")
        generated_ts = brief_row["generated_ts"]
        run_ids = json.loads(brief_row["run_ids"])

        # entry_date = brief.generated_ts::date
        entry_date = date.fromisoformat(generated_ts.split("T")[0])
        end_date = entry_date + timedelta(days=window_days)

        # 2. Pull each run's ticker/persona/decision.
        seed_rows: List[Tuple[str, str, str, str]] = []
        for run_id in run_ids:
            r = self.conn.execute(
                "SELECT ticker, persona_id, decision FROM runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if r is None:
                raise ValueError(f"run_id {run_id!r} referenced by brief but missing")
            seed_rows.append((run_id, r["ticker"], r["persona_id"] or "", r["decision"] or "HOLD"))

        # 3. Insert backtests row tagged with brief.
        universe = sorted({t for (_, t, _, _) in seed_rows})
        backtest_id = self._insert_backtests_row(
            triggered_by_brief_id=brief_id,
            universe=universe,
            start_date=entry_date,
            end_date=end_date,
        )

        # 4. Insert one backtest_runs row per (persona, ticker), reusing the
        #    persisted decision — no graph_runner.run() call.
        for run_id, ticker, persona_id, decision in seed_rows:
            try:
                position = position_from_decision(decision)
            except ValueError:
                position = 0

            try:
                bars = self.price_chain.get_bars(
                    ticker, entry_date, entry_date, self.resolution,
                )
                entry_price = bars.bars[0][1] if bars.bars else None
                price_source = bars.source
            except Exception as e:
                self._insert_backtest_run_errored(
                    backtest_id=backtest_id, ticker=ticker,
                    persona_id=persona_id, run_id=run_id,
                    error=f"entry price fetch failed: {e!r}",
                )
                continue
            if entry_price is None:
                self._insert_backtest_run_errored(
                    backtest_id=backtest_id, ticker=ticker,
                    persona_id=persona_id, run_id=run_id,
                    error=f"no entry bar for {entry_date}",
                )
                continue

            try:
                bench_bars = self.price_chain.get_bars(
                    self.benchmark, entry_date, entry_date, self.resolution,
                )
                benchmark_entry_price = bench_bars.bars[0][1] if bench_bars.bars else None
            except Exception:
                benchmark_entry_price = None

            metrics = {
                "status": "open",
                "run_id": run_id,
                "decision": decision,
                "position": position,
                "entry_date": entry_date.isoformat(),
                "entry_price": entry_price,
                "benchmark": self.benchmark,
                "benchmark_entry_price": benchmark_entry_price,
                "scheduled_close_date": end_date.isoformat(),
                "resolution": str(self.resolution.value),
                "price_source": price_source,
            }
            self.conn.execute(
                "INSERT INTO backtest_runs (backtest_id, persona_id, ticker, metrics)"
                " VALUES (?, ?, ?, ?)",
                (backtest_id, persona_id, ticker, json.dumps(metrics)),
            )
            self.conn.commit()

        # 5. Auto-mature if window already in the past.
        if end_date <= date.today():
            self._mature_all_open(backtest_id=backtest_id, end_date=end_date)
            self._close_backtest(backtest_id)

        return backtest_id
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/backtest/test_harness.py -v
```

Expected: all passing.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/backtest/harness.py tests/backtest/test_harness.py
git commit -m "feat(backtest): brief-scoped mode reads briefs.run_ids without re-invoking graph"
```

---

## Task 17: backtest.leaderboard — read-only aggregations with lazy MTM

**Files:**
- Create: `tradingagents/backtest/leaderboard.py`
- Test: `tests/backtest/test_leaderboard.py`

Read-only over `backtest_runs`. Lazy MTM for open rows (fetch latest price via the chain; never write back); closed rows read final metrics directly. Output: list of dicts (per-persona summary; per-row details).

- [ ] **Step 1: Write the failing tests**

Create `tests/backtest/test_leaderboard.py`:

```python
import json
import uuid
from datetime import datetime, timezone

import pytest


@pytest.fixture
def conn(tmp_path):
    from tradingagents.persistence.db import connect
    return connect(str(tmp_path / "iic.db"))


def _seed_run(conn, ticker, persona_id):
    from tradingagents.persistence import store
    run_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    store.insert_run(conn, run_id=run_id, ticker=ticker, persona_id=persona_id,
                     started_ts=now, artifact_dir=f"runs/{run_id}")
    return run_id


def _insert_backtest(conn, universe, start_date="2026-04-26", end_date="2026-05-26",
                      status="open"):
    cur = conn.execute(
        "INSERT INTO backtests (universe, start_date, end_date, status, created_ts)"
        " VALUES (?, ?, ?, ?, ?)",
        (json.dumps(universe), start_date, end_date, status,
         datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    return cur.lastrowid


def _insert_btr(conn, backtest_id, ticker, persona_id, metrics):
    conn.execute(
        "INSERT INTO backtest_runs (backtest_id, persona_id, ticker, metrics)"
        " VALUES (?, ?, ?, ?)",
        (backtest_id, persona_id, ticker, json.dumps(metrics)),
    )
    conn.commit()


@pytest.mark.unit
def test_leaderboard_closed_rows_show_final_alpha(conn):
    from tradingagents.backtest.leaderboard import build_leaderboard

    bt = _insert_backtest(conn, ["AAPL"], status="closed")
    rid = _seed_run(conn, "AAPL", "macro")
    _insert_btr(conn, bt, "AAPL", "macro", {
        "status": "closed", "run_id": rid, "decision": "BUY", "position": 1,
        "entry_date": "2026-04-26", "entry_price": 200.0,
        "close_date": "2026-05-26", "exit_price": 220.0,
        "total_return": 0.10, "benchmark_return": 0.02, "alpha": 0.08,
        "sharpe": 1.4, "max_drawdown": -0.02, "win_rate": 0.6,
    })

    rows = build_leaderboard(conn, price_chain=None)
    assert len(rows) == 1
    assert rows[0]["persona_id"] == "macro"
    assert rows[0]["ticker"] == "AAPL"
    assert rows[0]["status"] == "closed"
    assert rows[0]["alpha"] == pytest.approx(0.08)


@pytest.mark.unit
def test_leaderboard_open_rows_use_lazy_mtm(conn):
    from tradingagents.backtest.leaderboard import build_leaderboard
    from tradingagents.backtest.prices import Bars, Resolution
    from datetime import datetime as dt

    bt = _insert_backtest(conn, ["AAPL"], status="open")
    rid = _seed_run(conn, "AAPL", "macro")
    _insert_btr(conn, bt, "AAPL", "macro", {
        "status": "open", "run_id": rid, "decision": "BUY", "position": 1,
        "entry_date": "2026-04-26", "entry_price": 200.0,
        "benchmark": "SPY", "benchmark_entry_price": 500.0,
        "scheduled_close_date": "2026-05-26",
        "resolution": "1d", "price_source": "fake",
    })

    class FakeChain:
        def get_bars(self, ticker, start, end, resolution):
            price = 220.0 if ticker == "AAPL" else 510.0
            return Bars(ticker=ticker, resolution=resolution,
                        bars=[(dt(2026, 5, 1), price)], source="fake")

    rows = build_leaderboard(conn, price_chain=FakeChain())
    assert len(rows) == 1
    r = rows[0]
    assert r["status"] == "open"
    assert r["current_price"] == pytest.approx(220.0)
    assert r["mtm_return"] == pytest.approx(0.10)
    assert r["mtm_alpha"] == pytest.approx(0.10 - 0.02)


@pytest.mark.unit
def test_leaderboard_open_rows_without_chain_skip_mtm(conn):
    from tradingagents.backtest.leaderboard import build_leaderboard

    bt = _insert_backtest(conn, ["AAPL"], status="open")
    rid = _seed_run(conn, "AAPL", "macro")
    _insert_btr(conn, bt, "AAPL", "macro", {
        "status": "open", "run_id": rid, "decision": "BUY", "position": 1,
        "entry_date": "2026-04-26", "entry_price": 200.0,
        "scheduled_close_date": "2026-05-26",
        "resolution": "1d", "price_source": "fake",
    })

    rows = build_leaderboard(conn, price_chain=None)
    assert rows[0]["status"] == "open"
    assert rows[0]["mtm_return"] is None


@pytest.mark.unit
def test_leaderboard_filter_by_persona(conn):
    from tradingagents.backtest.leaderboard import build_leaderboard

    bt = _insert_backtest(conn, ["AAPL", "MSFT"], status="closed")
    for ticker, persona in [("AAPL", "macro"), ("MSFT", "value")]:
        rid = _seed_run(conn, ticker, persona)
        _insert_btr(conn, bt, ticker, persona, {
            "status": "closed", "run_id": rid, "decision": "BUY", "position": 1,
            "entry_date": "2026-04-26", "entry_price": 100.0,
            "close_date": "2026-05-26", "exit_price": 110.0,
            "total_return": 0.10, "benchmark_return": 0.0, "alpha": 0.10,
            "sharpe": 0.0, "max_drawdown": 0.0, "win_rate": 1.0,
        })

    rows = build_leaderboard(conn, price_chain=None, persona="macro")
    assert {r["persona_id"] for r in rows} == {"macro"}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/backtest/test_leaderboard.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `leaderboard.py`**

Create `tradingagents/backtest/leaderboard.py`:

```python
"""Read-only leaderboard over backtest_runs.

Open rows: lazy MTM (fetch latest price via price_chain — never written back).
Closed rows: serve metrics straight from the frozen JSON.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from typing import List, Optional

from tradingagents.backtest.prices import Resolution


def build_leaderboard(
    conn: sqlite3.Connection,
    *,
    price_chain: Optional[object] = None,
    persona: Optional[str] = None,
    status_filter: Optional[str] = None,   # "open" | "closed" | None=all
) -> List[dict]:
    """Return per-row leaderboard entries grouped by status.

    Args:
        conn: open SQLite connection.
        price_chain: optional ``get_bars()`` producer for live MTM on open rows.
            When None, open rows report ``mtm_return=None``.
        persona: optional filter by persona_id.
        status_filter: optional restriction by metrics.status.
    """
    sql = "SELECT btr_id, backtest_id, persona_id, ticker, metrics FROM backtest_runs"
    args: list = []
    where: list = []
    if persona is not None:
        where.append("persona_id = ?")
        args.append(persona)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY btr_id ASC"

    rows: List[dict] = []
    for db_row in conn.execute(sql, args):
        m = json.loads(db_row["metrics"])
        status = m.get("status", "unknown")
        if status_filter and status != status_filter:
            continue
        entry = {
            "btr_id": db_row["btr_id"],
            "backtest_id": db_row["backtest_id"],
            "persona_id": db_row["persona_id"],
            "ticker": db_row["ticker"],
            "status": status,
            "decision": m.get("decision"),
            "position": m.get("position"),
            "entry_date": m.get("entry_date"),
            "entry_price": m.get("entry_price"),
            "scheduled_close_date": m.get("scheduled_close_date"),
        }
        if status == "closed":
            entry.update({
                "close_date": m.get("close_date"),
                "exit_price": m.get("exit_price"),
                "total_return": m.get("total_return"),
                "alpha": m.get("alpha"),
                "sharpe": m.get("sharpe"),
                "max_drawdown": m.get("max_drawdown"),
                "win_rate": m.get("win_rate"),
            })
        elif status == "open":
            if price_chain is not None and m.get("entry_price"):
                entry.update(_lazy_mtm(price_chain, db_row["ticker"], m))
            else:
                entry["current_price"] = None
                entry["mtm_return"] = None
                entry["mtm_alpha"] = None
        else:   # errored or unknown
            entry["error"] = m.get("error")
        rows.append(entry)
    return rows


def _lazy_mtm(price_chain, ticker: str, m: dict) -> dict:
    """Best-effort live MTM for one open row. Errors → all-None values."""
    try:
        bars = price_chain.get_bars(
            ticker, date.today(), date.today(),
            Resolution(m.get("resolution", "1d")),
        )
        current_price = bars.bars[-1][1] if bars.bars else None
    except Exception:
        current_price = None
    if current_price is None or m["entry_price"] <= 0:
        return {"current_price": None, "mtm_return": None, "mtm_alpha": None}

    position = m.get("position", 0)
    mtm_return = position * (current_price - m["entry_price"]) / m["entry_price"]

    mtm_alpha = None
    bench_entry = m.get("benchmark_entry_price")
    if bench_entry:
        try:
            bench_bars = price_chain.get_bars(
                m.get("benchmark", "SPY"), date.today(), date.today(),
                Resolution(m.get("resolution", "1d")),
            )
            bench_now = bench_bars.bars[-1][1] if bench_bars.bars else None
        except Exception:
            bench_now = None
        if bench_now and bench_entry > 0:
            mtm_alpha = mtm_return - (bench_now - bench_entry) / bench_entry

    return {
        "current_price": current_price,
        "mtm_return": mtm_return,
        "mtm_alpha": mtm_alpha,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/backtest/test_leaderboard.py -v
```

Expected: 4 passing.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/backtest/leaderboard.py tests/backtest/test_leaderboard.py
git commit -m "feat(backtest): leaderboard with lazy MTM for open rows; never writes back"
```

---

## Task 18: backtest.report — deterministic Markdown renderer

**Files:**
- Create: `tradingagents/backtest/report.py`
- Test: `tests/backtest/test_report.py`

Aggregates closed `backtest_runs` into a deterministic Markdown report. Byte-equal on rerun except for one `generated_ts` header line.

- [ ] **Step 1: Write the failing tests**

Create `tests/backtest/test_report.py`:

```python
import json
import re
import uuid
from datetime import datetime, timezone

import pytest


@pytest.fixture
def conn(tmp_path):
    from tradingagents.persistence.db import connect
    return connect(str(tmp_path / "iic.db"))


def _seed(conn):
    """Seed a closed backtest with 3 personas × 1 ticker (AAPL)."""
    from tradingagents.persistence import store

    cur = conn.execute(
        "INSERT INTO backtests (universe, start_date, end_date, status, "
        "report_path, created_ts) VALUES (?, ?, ?, 'closed', NULL, ?)",
        (json.dumps(["AAPL"]), "2026-04-26", "2026-05-26",
         datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    backtest_id = cur.lastrowid

    samples = [
        ("macro",    0.10, 0.08, 1.4,  -0.02, 0.60),
        ("value",    0.03, 0.01, 0.4,  -0.03, 0.55),
        ("momentum", -0.05, -0.07, -0.6, -0.12, 0.35),
    ]
    for persona_id, tr, alpha, sharpe, mdd, wr in samples:
        run_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        store.insert_run(conn, run_id=run_id, ticker="AAPL",
                         persona_id=persona_id, started_ts=now,
                         artifact_dir=f"runs/{run_id}")
        metrics = {
            "status": "closed", "run_id": run_id,
            "decision": "BUY" if tr > 0 else "SELL",
            "position": 1 if tr > 0 else -1,
            "entry_date": "2026-04-26", "entry_price": 200.0,
            "close_date": "2026-05-26", "exit_price": 220.0 if tr > 0 else 190.0,
            "benchmark": "SPY",
            "total_return": tr, "benchmark_return": tr - alpha,
            "alpha": alpha, "sharpe": sharpe, "max_drawdown": mdd, "win_rate": wr,
            "returns": [0.01] * 22, "holding_days_elapsed": 30,
            "price_source": "yfinance", "resolution": "1d",
        }
        conn.execute(
            "INSERT INTO backtest_runs (backtest_id, persona_id, ticker, metrics)"
            " VALUES (?, ?, ?, ?)",
            (backtest_id, persona_id, "AAPL", json.dumps(metrics)),
        )
    conn.commit()
    return backtest_id


@pytest.mark.unit
def test_report_contains_three_persona_rows(conn):
    from tradingagents.backtest.report import render_report
    bt = _seed(conn)
    md = render_report(conn, backtest_id=bt)
    for persona in ("macro", "value", "momentum"):
        assert persona in md
    # Required metric columns
    for col in ("Sharpe", "Total Return", "Alpha", "Win Rate"):
        assert col in md


@pytest.mark.unit
def test_report_includes_buy_and_hold_baseline(conn):
    from tradingagents.backtest.report import render_report
    bt = _seed(conn)
    md = render_report(conn, backtest_id=bt)
    assert "Buy-and-hold" in md or "buy-and-hold" in md.lower()


@pytest.mark.unit
def test_report_is_byte_equal_modulo_generated_ts(conn):
    from tradingagents.backtest.report import render_report
    bt = _seed(conn)
    a = render_report(conn, backtest_id=bt)
    b = render_report(conn, backtest_id=bt)
    # Strip the generated_ts line from both and compare.
    rx = re.compile(r"^generated_ts:.*$", re.MULTILINE)
    a_norm = rx.sub("", a)
    b_norm = rx.sub("", b)
    assert a_norm == b_norm
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/backtest/test_report.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `report.py`**

Create `tradingagents/backtest/report.py`:

```python
"""Deterministic Markdown report for a closed backtest.

Reads ``backtest_runs.metrics`` (frozen JSON) and aggregates per-persona.
Buy-and-hold baseline is approximated from the benchmark stored alongside
each backtest_runs row.

Reproducibility property: same backtest_id → same Markdown output
*except* a single ``generated_ts:`` header line.
"""

from __future__ import annotations

import json
import sqlite3
import statistics
from datetime import datetime, timezone
from typing import Dict, List


def render_report(conn: sqlite3.Connection, *, backtest_id: int) -> str:
    bt = conn.execute(
        "SELECT * FROM backtests WHERE backtest_id = ?", (backtest_id,)
    ).fetchone()
    if bt is None:
        raise ValueError(f"backtest_id {backtest_id} not found")
    universe = json.loads(bt["universe"])

    rows = list(conn.execute(
        "SELECT persona_id, ticker, metrics FROM backtest_runs "
        "WHERE backtest_id = ? ORDER BY persona_id, ticker",
        (backtest_id,),
    ))

    by_persona: Dict[str, List[dict]] = {}
    errored: List[dict] = []
    for r in rows:
        m = json.loads(r["metrics"])
        m["_persona_id"] = r["persona_id"]
        m["_ticker"] = r["ticker"]
        if m.get("status") == "errored":
            errored.append(m)
        elif m.get("status") == "closed":
            by_persona.setdefault(r["persona_id"], []).append(m)

    lines: List[str] = []
    lines.append(f"# F2 Backtest Report #{backtest_id}")
    lines.append("")
    lines.append(f"generated_ts: {datetime.now(timezone.utc).isoformat()}")
    lines.append("")
    lines.append(f"- **Universe:** {', '.join(universe)}")
    lines.append(f"- **Start date:** {bt['start_date']}")
    lines.append(f"- **End date:**   {bt['end_date']}")
    lines.append(f"- **Status:**     {bt['status']}")
    if bt["triggered_by_brief_id"]:
        lines.append(f"- **Triggered by brief:** `{bt['triggered_by_brief_id']}`")
    lines.append("")

    # Per-persona aggregate
    lines.append("## Per-persona aggregate")
    lines.append("")
    lines.append("| Persona | Sharpe | Total Return | Alpha | Win Rate | N |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for persona_id in sorted(by_persona):
        items = by_persona[persona_id]
        sharpe = _mean([m["sharpe"] for m in items])
        total = _mean([m["total_return"] for m in items])
        alpha = _mean([m["alpha"] for m in items])
        winrt = _mean([m["win_rate"] for m in items])
        lines.append(
            f"| {persona_id} | {sharpe:+.3f} | {total:+.4f} | {alpha:+.4f} | "
            f"{winrt:.3f} | {len(items)} |"
        )
    lines.append("")

    # Buy-and-hold baseline (from benchmark_return — same window).
    lines.append("## Buy-and-hold baseline")
    lines.append("")
    bench_rets = [m["benchmark_return"]
                   for items in by_persona.values()
                   for m in items
                   if m.get("benchmark_return") is not None]
    if bench_rets:
        avg_bench = _mean(bench_rets)
        lines.append(f"- Average benchmark return over window: {avg_bench:+.4f}")
    else:
        lines.append("- Benchmark return unavailable for all rows.")
    lines.append("")

    # Per-ticker detail
    lines.append("## Per-(persona, ticker) detail")
    lines.append("")
    lines.append("| Persona | Ticker | Decision | Entry | Exit | Total Return | Alpha | Sharpe |")
    lines.append("|---|---|---|---:|---:|---:|---:|---:|")
    for persona_id in sorted(by_persona):
        for m in by_persona[persona_id]:
            lines.append(
                f"| {persona_id} | {m['_ticker']} | {m['decision']} | "
                f"{m['entry_price']:.2f} | {m['exit_price']:.2f} | "
                f"{m['total_return']:+.4f} | {m['alpha']:+.4f} | {m['sharpe']:+.3f} |"
            )
    lines.append("")

    if errored:
        lines.append("## Errored rows")
        lines.append("")
        for m in errored:
            lines.append(
                f"- {m['_persona_id']} × {m['_ticker']}: {m.get('error', '(no message)')}"
            )
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("*Generated by `tradingagents.backtest.report`.*")
    return "\n".join(lines)


def _mean(xs):
    return statistics.fmean(xs) if xs else 0.0
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/backtest/test_report.py -v
```

Expected: 3 passing (including the byte-equality check).

- [ ] **Step 5: Commit**

```bash
git add tradingagents/backtest/report.py tests/backtest/test_report.py
git commit -m "feat(backtest): deterministic Markdown report renderer"
```

---

## Task 19: backtest.sweep — stateless maturation pass

**Files:**
- Create: `tradingagents/backtest/sweep.py`
- Test: `tests/backtest/test_sweep.py`

Shared logic for `forge backtest sweep` (one-shot) and `forge backtest watch` (looped). Queries `backtest_runs` with `metrics.status='open'` AND `scheduled_close_date <= today`, matures each, returns counts.

- [ ] **Step 1: Write the failing tests**

Create `tests/backtest/test_sweep.py`:

```python
import json
import uuid
from datetime import date, datetime, timezone

import pytest


@pytest.fixture
def conn(tmp_path):
    from tradingagents.persistence.db import connect
    return connect(str(tmp_path / "iic.db"))


def _seed_open_run(conn, ticker, persona_id, scheduled_close_date):
    """Seed a single open backtest_runs row + its parent backtests + runs."""
    from tradingagents.persistence import store

    cur = conn.execute(
        "INSERT INTO backtests (universe, start_date, end_date, status, created_ts)"
        " VALUES (?, ?, ?, 'open', ?)",
        (json.dumps([ticker]), "2026-04-26", scheduled_close_date,
         datetime.now(timezone.utc).isoformat()),
    )
    backtest_id = cur.lastrowid

    run_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    store.insert_run(conn, run_id=run_id, ticker=ticker, persona_id=persona_id,
                     started_ts=now, artifact_dir=f"runs/{run_id}")

    metrics = {
        "status": "open", "run_id": run_id, "decision": "BUY", "position": 1,
        "entry_date": "2026-04-26", "entry_price": 100.0,
        "benchmark": "SPY", "benchmark_entry_price": 500.0,
        "scheduled_close_date": scheduled_close_date,
        "resolution": "1d", "price_source": "fake",
    }
    conn.execute(
        "INSERT INTO backtest_runs (backtest_id, persona_id, ticker, metrics)"
        " VALUES (?, ?, ?, ?)",
        (backtest_id, persona_id, ticker, json.dumps(metrics)),
    )
    conn.commit()
    return backtest_id


@pytest.fixture
def fake_chain():
    from tradingagents.backtest.prices import Bars, Resolution
    from datetime import datetime as dt

    class FakeChain:
        def get_bars(self, ticker, start, end, resolution):
            # entry single-day fetch → one bar; multi-day → 3 bars
            if start == end:
                return Bars(ticker=ticker, resolution=resolution,
                            bars=[(dt.combine(start, dt.min.time()), 100.0)],
                            source="fake")
            return Bars(ticker=ticker, resolution=resolution,
                        bars=[(dt.combine(start, dt.min.time()), 100.0),
                              (dt.combine(end,   dt.min.time()), 110.0)],
                        source="fake")
    return FakeChain()


@pytest.mark.unit
def test_sweep_matures_only_past_due_rows(conn, fake_chain):
    from tradingagents.backtest.sweep import run_maturation_pass

    past_due_bt = _seed_open_run(conn, "AAPL", "macro", "2020-01-01")
    future_bt = _seed_open_run(conn, "MSFT", "value",
                                 "2099-01-01")  # never matures

    result = run_maturation_pass(conn, price_chain=fake_chain)
    assert result["closed"] == 1
    assert result["skipped"] == 1

    rows = list(conn.execute(
        "SELECT backtest_id, metrics FROM backtest_runs"
    ))
    for r in rows:
        m = json.loads(r["metrics"])
        if r["backtest_id"] == past_due_bt:
            assert m["status"] == "closed"
        else:
            assert m["status"] == "open"


@pytest.mark.unit
def test_sweep_returns_zero_when_nothing_due(conn, fake_chain):
    from tradingagents.backtest.sweep import run_maturation_pass
    result = run_maturation_pass(conn, price_chain=fake_chain)
    assert result == {"closed": 0, "skipped": 0, "errored": 0}


@pytest.mark.unit
def test_sweep_does_not_retry_errored_rows_by_default(conn, fake_chain):
    """Errored rows stay errored to avoid retry storms (per design §11)."""
    from tradingagents.backtest.sweep import run_maturation_pass
    from tradingagents.persistence import store

    cur = conn.execute(
        "INSERT INTO backtests (universe, start_date, end_date, status, created_ts)"
        " VALUES (?, '2020-01-01', '2020-02-01', 'open', ?)",
        (json.dumps(["AAPL"]), datetime.now(timezone.utc).isoformat()),
    )
    backtest_id = cur.lastrowid
    run_id = uuid.uuid4().hex
    store.insert_run(conn, run_id=run_id, ticker="AAPL", persona_id="macro",
                     started_ts=datetime.now(timezone.utc).isoformat(),
                     artifact_dir=f"runs/{run_id}")
    conn.execute(
        "INSERT INTO backtest_runs (backtest_id, persona_id, ticker, metrics)"
        " VALUES (?, ?, ?, ?)",
        (backtest_id, "macro", "AAPL",
         json.dumps({"status": "errored", "run_id": run_id,
                      "error": "old", "scheduled_close_date": "2020-02-01"})),
    )
    conn.commit()

    result = run_maturation_pass(conn, price_chain=fake_chain)
    assert result["closed"] == 0
    # Row still errored, untouched.
    m = json.loads(conn.execute(
        "SELECT metrics FROM backtest_runs WHERE backtest_id = ?", (backtest_id,)
    ).fetchone()["metrics"])
    assert m["status"] == "errored"
    assert m["error"] == "old"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/backtest/test_sweep.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `sweep.py`**

Create `tradingagents/backtest/sweep.py`:

```python
"""Stateless maturation pass — the engine behind ``forge backtest sweep``
and ``forge backtest watch``.

Queries open backtest_runs whose scheduled_close_date <= today, runs the
maturation logic inline using the BacktestHarness for each backtest_id,
returns counts. Errored rows are left alone by default to avoid retry
storms.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from typing import Dict

from tradingagents.backtest.harness import BacktestHarness


def run_maturation_pass(
    conn: sqlite3.Connection,
    *,
    price_chain: object,
    data_dir: str = "",
    today: date | None = None,
) -> Dict[str, int]:
    """Mature every open backtest_runs row whose scheduled_close_date <= today.

    Returns a counter dict with keys ``closed``, ``skipped``, ``errored``.
    """
    if today is None:
        today = date.today()

    closed = 0
    skipped = 0
    errored = 0

    # Group by backtest_id so we can reuse one harness per backtest.
    bt_ids = [
        row["backtest_id"] for row in conn.execute(
            "SELECT DISTINCT backtest_id FROM backtest_runs ORDER BY backtest_id"
        )
    ]

    for backtest_id in bt_ids:
        rows = list(conn.execute(
            "SELECT btr_id, persona_id, ticker, metrics FROM backtest_runs "
            "WHERE backtest_id = ?",
            (backtest_id,),
        ))
        per_bt_due: list = []
        for r in rows:
            m = json.loads(r["metrics"])
            status = m.get("status")
            if status == "errored":
                continue  # don't retry by default
            if status != "open":
                continue
            sched = m.get("scheduled_close_date")
            if not sched or date.fromisoformat(sched) > today:
                skipped += 1
                continue
            per_bt_due.append((r, m))

        if not per_bt_due:
            continue

        # Build a harness against this conn/chain; reuse for all rows in this backtest.
        # graph_runner is unused during maturation (no fresh graph calls).
        harness = BacktestHarness(
            conn=conn, data_dir=data_dir,
            graph_runner=_NullGraphRunner(),
            price_chain=price_chain,
        )
        end_date = max(
            date.fromisoformat(m["scheduled_close_date"]) for (_, m) in per_bt_due
        )
        try:
            harness._mature_all_open(backtest_id=backtest_id, end_date=end_date)
        except Exception:
            errored += len(per_bt_due)
            continue
        # Re-read to count closed vs errored after the pass
        rows_after = list(conn.execute(
            "SELECT metrics FROM backtest_runs WHERE backtest_id = ?",
            (backtest_id,),
        ))
        for r in rows_after:
            m = json.loads(r["metrics"])
            # Only count rows that were due in this pass
            sched = m.get("scheduled_close_date")
            if not sched or date.fromisoformat(sched) > today:
                continue
            if m.get("status") == "closed":
                closed += 1
            elif m.get("status") == "errored" and m.get("close_date") is None:
                errored += 1

        # If the whole backtest's runs are now closed, update parent status.
        any_open = any(
            json.loads(r["metrics"]).get("status") == "open"
            for r in rows_after
        )
        if not any_open:
            conn.execute(
                "UPDATE backtests SET status='closed' WHERE backtest_id=?",
                (backtest_id,),
            )
            conn.commit()

    return {"closed": closed, "skipped": skipped, "errored": errored}


class _NullGraphRunner:
    """A graph runner that must never be invoked (maturation doesn't run the graph)."""
    def run(self, **kwargs):
        raise RuntimeError(
            "_NullGraphRunner.run() called — maturation must not invoke the graph"
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/backtest/test_sweep.py -v
```

Expected: 3 passing.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/backtest/sweep.py tests/backtest/test_sweep.py
git commit -m "feat(backtest): sweep — maturation pass for cron + watch"
```

---

## Task 20: cli/forge.py — `backtest start` command

**Files:**
- Create: `cli/forge.py`
- Test: `tests/cli/test_forge.py`

`forge` is a Typer sub-app. `backtest start` is the first command. The other backtest commands land in Task 21–22.

We also introduce a small `TradingAgentsGraphRunner` adapter that wraps `TradingAgentsGraph` to satisfy the `GraphRunner` protocol. Lives in `cli/forge.py` next to the command (it's a CLI-side concern — keeps `tradingagents/backtest/` decoupled from the heavy graph module).

- [ ] **Step 1: Write the failing test**

Create `tests/cli/test_forge.py`:

```python
import pytest
from typer.testing import CliRunner


@pytest.mark.unit
def test_forge_command_exists():
    from cli.forge import forge_app
    runner = CliRunner()
    result = runner.invoke(forge_app, ["--help"])
    assert result.exit_code == 0
    assert "backtest" in result.stdout


@pytest.mark.unit
def test_backtest_start_help_lists_required_flags():
    from cli.forge import forge_app
    runner = CliRunner()
    result = runner.invoke(forge_app, ["backtest", "start", "--help"])
    assert result.exit_code == 0
    out = result.stdout
    assert "--watchlist" in out
    assert "--brief-id" in out
    assert "--start-date" in out
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/cli/test_forge.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `cli/forge.py` with `backtest start`**

Create `cli/forge.py`:

```python
"""IIC-FORGE F2 CLI: ``forge backtest ...`` commands."""

from __future__ import annotations

import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import typer

from tradingagents.backtest.harness import BacktestHarness
from tradingagents.backtest.prices import (
    PriceFallbackChain, Resolution,
)
from tradingagents.backtest.strict_historical import StrictHistoricalChain
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.persistence.db import connect as iic_connect

forge_app = typer.Typer(help="IIC-FORGE backtest commands")
backtest_app = typer.Typer(help="Forward-test harness and leaderboard")
forge_app.add_typer(backtest_app, name="backtest")


# --------------------------------------------------------------------
# Helpers: build a PriceFallbackChain from a list of source names.
# --------------------------------------------------------------------

_SOURCE_FACTORIES = {
    "yfinance":      "tradingagents.backtest.sources.yfinance_source:YFinanceSource",
    "polygon":       "tradingagents.backtest.sources.polygon_source:PolygonSource",
    "alpha_vantage": "tradingagents.backtest.sources.alpha_vantage_source:AlphaVantageSource",
    "futu":          "tradingagents.backtest.sources.futu_source:FutuSource",
}


def _build_price_chain(source_names: list[str]) -> PriceFallbackChain:
    sources = []
    for name in source_names:
        spec = _SOURCE_FACTORIES.get(name)
        if not spec:
            typer.echo(f"warning: unknown price source {name!r}; skipping", err=True)
            continue
        mod_name, class_name = spec.split(":")
        import importlib
        cls = getattr(importlib.import_module(mod_name), class_name)
        sources.append(cls())
    return PriceFallbackChain(sources)


# --------------------------------------------------------------------
# Graph runner adapter — wraps TradingAgentsGraph.
# --------------------------------------------------------------------

class TradingAgentsGraphRunner:
    """Adapter implementing the GraphRunner Protocol against the real graph."""

    def __init__(self, config: dict):
        self.config = config

    def run(self, *, ticker, trade_date, persona_id, conn: sqlite3.Connection):
        # Import lazily to keep CLI startup fast.
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        from tradingagents.personas.loader import load_persona_from_file

        overlay = dict(self.config)
        overlay["persona_id"] = persona_id

        # Apply per-persona LLM overrides (matches cli/deepdive.py pattern).
        personas_dir = Path(__file__).resolve().parent.parent / "tradingagents" / "personas"
        persona_file = personas_dir / f"{persona_id}.yaml"
        if persona_file.exists():
            p = load_persona_from_file(str(persona_file))
            overlay["deep_think_llm"]  = p.llm.deep_think_llm
            overlay["quick_think_llm"] = p.llm.quick_think_llm
            if p.llm.deepseek_reasoning_effort is not None:
                overlay["deepseek_reasoning_effort"] = p.llm.deepseek_reasoning_effort
            selected = list(p.analysts.include)
        else:
            selected = ["market", "news", "fundamentals"]

        graph = TradingAgentsGraph(config=overlay, selected_analysts=selected)
        graph.propagate(ticker, trade_date)
        # Pull the decision back from the runs table the Run Recorder just wrote.
        row = conn.execute(
            "SELECT decision FROM runs WHERE run_id = ?", (graph.run_id,),
        ).fetchone()
        decision = (row["decision"] if row and row["decision"] else "HOLD")
        return graph.run_id, decision


# --------------------------------------------------------------------
# `forge backtest start`
# --------------------------------------------------------------------

@backtest_app.command("start")
def backtest_start(
    watchlist: Optional[str] = typer.Option(
        None, "--watchlist", help="Comma-separated tickers (watchlist mode)"
    ),
    brief_id: Optional[str] = typer.Option(
        None, "--brief-id", help="Brief ID (brief-scoped mode); mutually exclusive with --watchlist"
    ),
    start_date_s: Optional[str] = typer.Option(
        None, "--start-date", help="YYYY-MM-DD (defaults to today)"
    ),
    end_date_s: Optional[str] = typer.Option(
        None, "--end-date", help="YYYY-MM-DD (defaults to start+30 days)"
    ),
    resolution_s: str = typer.Option(
        None, "--resolution", help="1d | 1m  (1m raises until a 1m source is registered)"
    ),
    sources_s: Optional[str] = typer.Option(
        None, "--sources", help="Comma-separated source priority order; default from config"
    ),
    personas_s: Optional[str] = typer.Option(
        None, "--personas", help="Comma-separated persona ids; default = all loaded"
    ),
):
    """Start a forward-test batch. Exactly one of --watchlist or --brief-id must be set."""
    if bool(watchlist) == bool(brief_id):
        typer.echo("error: provide exactly one of --watchlist or --brief-id", err=True)
        raise typer.Exit(code=2)

    config = dict(DEFAULT_CONFIG)
    resolution = Resolution(resolution_s or config["backtest_resolution_default"])
    source_names = (
        sources_s.split(",") if sources_s else config["backtest_price_sources"]
    )

    conn = iic_connect(config["iic_db_path"])
    chain = _build_price_chain(source_names)

    if brief_id:
        # No graph runner needed — brief-scoped reuses persisted decisions.
        harness = BacktestHarness(
            conn=conn, data_dir=config["iic_data_dir"],
            graph_runner=_NullGraphRunner(),
            price_chain=chain,
            resolution=resolution,
        )
        backtest_id = harness.run_brief_scoped(brief_id=brief_id)
    else:
        # Watchlist mode — parse inputs + maybe enable strict_historical.
        tickers = [t.strip().upper() for t in watchlist.split(",") if t.strip()]
        start_date = (
            date.fromisoformat(start_date_s) if start_date_s else date.today()
        )
        end_date = (
            date.fromisoformat(end_date_s) if end_date_s
            else start_date + timedelta(days=30)
        )

        # Auto-on strict historical when start_date < today (unless config forces).
        strict_cfg = config["backtest_strict_historical"]
        strict_on = (start_date < date.today()) if strict_cfg is None else bool(strict_cfg)
        effective_chain = (
            StrictHistoricalChain(chain, cutoff=end_date) if strict_on else chain
        )

        personas = (
            personas_s.split(",") if personas_s
            else _all_persona_ids()
        )

        harness = BacktestHarness(
            conn=conn, data_dir=config["iic_data_dir"],
            graph_runner=TradingAgentsGraphRunner(config),
            price_chain=effective_chain,
            resolution=resolution,
        )
        backtest_id = harness.run_watchlist(
            tickers=tickers, personas=personas,
            start_date=start_date, end_date=end_date,
        )

    typer.echo(f"backtest_id: {backtest_id}")
    return backtest_id


def _all_persona_ids() -> list[str]:
    from tradingagents.personas.loader import load_all_personas
    personas_dir = Path(__file__).resolve().parent.parent / "tradingagents" / "personas"
    return [p.id for p in load_all_personas(str(personas_dir))]


class _NullGraphRunner:
    def run(self, **kw):
        raise RuntimeError("brief-scoped mode must not invoke the graph")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/cli/test_forge.py -v
```

Expected: 2 passing.

- [ ] **Step 5: Commit**

```bash
git add cli/forge.py tests/cli/test_forge.py
git commit -m "feat(cli): forge backtest start (watchlist + brief-scoped modes)"
```

---

## Task 21: `forge backtest leaderboard`, `report`, `close` commands

**Files:**
- Modify: `cli/forge.py`
- Modify: `tests/cli/test_forge.py`

- [ ] **Step 1: Append the failing tests**

Append to `tests/cli/test_forge.py`:

```python
@pytest.mark.unit
def test_backtest_leaderboard_help():
    from cli.forge import forge_app
    runner = CliRunner()
    result = runner.invoke(forge_app, ["backtest", "leaderboard", "--help"])
    assert result.exit_code == 0
    assert "--persona" in result.stdout


@pytest.mark.unit
def test_backtest_report_help():
    from cli.forge import forge_app
    runner = CliRunner()
    result = runner.invoke(forge_app, ["backtest", "report", "--help"])
    assert result.exit_code == 0


@pytest.mark.unit
def test_backtest_close_help():
    from cli.forge import forge_app
    runner = CliRunner()
    result = runner.invoke(forge_app, ["backtest", "close", "--help"])
    assert result.exit_code == 0


@pytest.mark.unit
def test_backtest_report_writes_file(tmp_path, monkeypatch):
    """End-to-end: seed a closed backtest, run `report`, verify file."""
    import json, uuid
    from datetime import datetime, timezone

    iic_db = tmp_path / "iic.db"
    iic_data = tmp_path / "data"
    monkeypatch.setenv("TRADINGAGENTS_IIC_DB_PATH", str(iic_db))
    monkeypatch.setenv("TRADINGAGENTS_IIC_DATA_DIR", str(iic_data))

    # Force DEFAULT_CONFIG reload so env-var overrides apply.
    import importlib
    import tradingagents.default_config as dc
    importlib.reload(dc)
    import cli.forge as forge_mod
    importlib.reload(forge_mod)

    from tradingagents.persistence.db import connect
    from tradingagents.persistence import store
    conn = connect(str(iic_db))

    cur = conn.execute(
        "INSERT INTO backtests (universe, start_date, end_date, status, created_ts)"
        " VALUES (?, '2026-04-26', '2026-05-26', 'closed', ?)",
        (json.dumps(["AAPL"]), datetime.now(timezone.utc).isoformat()),
    )
    backtest_id = cur.lastrowid
    run_id = uuid.uuid4().hex
    store.insert_run(conn, run_id=run_id, ticker="AAPL", persona_id="macro",
                     started_ts=datetime.now(timezone.utc).isoformat(),
                     artifact_dir=f"runs/{run_id}")
    conn.execute(
        "INSERT INTO backtest_runs (backtest_id, persona_id, ticker, metrics)"
        " VALUES (?, ?, ?, ?)",
        (backtest_id, "macro", "AAPL", json.dumps({
            "status": "closed", "run_id": run_id, "decision": "BUY",
            "position": 1, "entry_date": "2026-04-26", "entry_price": 200.0,
            "close_date": "2026-05-26", "exit_price": 220.0,
            "total_return": 0.10, "benchmark_return": 0.02, "alpha": 0.08,
            "sharpe": 1.4, "max_drawdown": -0.02, "win_rate": 0.6,
            "returns": [], "holding_days_elapsed": 30,
        })),
    )
    conn.commit()
    conn.close()

    runner = CliRunner()
    result = runner.invoke(forge_mod.forge_app,
                            ["backtest", "report", str(backtest_id)])
    assert result.exit_code == 0, result.output
    report_path = iic_data / "backtests" / str(backtest_id) / "report.md"
    assert report_path.exists()
    content = report_path.read_text(encoding="utf-8")
    assert "macro" in content
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/cli/test_forge.py -v
```

Expected: 4 new FAILs (commands don't exist yet).

- [ ] **Step 3: Append the new commands to `cli/forge.py`**

```python
# --------------------------------------------------------------------
# `forge backtest leaderboard`
# --------------------------------------------------------------------

@backtest_app.command("leaderboard")
def backtest_leaderboard(
    persona: Optional[str] = typer.Option(None, "--persona"),
    status: Optional[str] = typer.Option(
        None, "--status", help="open | closed (default: all)"
    ),
    no_mtm: bool = typer.Option(
        False, "--no-mtm", help="Skip live mark-to-market for open rows (faster)"
    ),
):
    from tradingagents.backtest.leaderboard import build_leaderboard

    config = dict(DEFAULT_CONFIG)
    conn = iic_connect(config["iic_db_path"])
    chain = None if no_mtm else _build_price_chain(config["backtest_price_sources"])

    rows = build_leaderboard(conn, price_chain=chain, persona=persona,
                              status_filter=status)
    if not rows:
        typer.echo("(no rows)")
        return

    # Compact table for terminal.
    typer.echo(
        f"{'btr':>4}  {'persona':<10} {'ticker':<6} {'status':<8} "
        f"{'decision':<5} {'TR':>8} {'alpha':>8}"
    )
    for r in rows:
        tr = r.get("total_return") if r["status"] == "closed" else r.get("mtm_return")
        al = r.get("alpha") if r["status"] == "closed" else r.get("mtm_alpha")
        tr_s = f"{tr:+.4f}" if tr is not None else " - "
        al_s = f"{al:+.4f}" if al is not None else " - "
        typer.echo(
            f"{r['btr_id']:>4}  {r['persona_id'] or '-':<10} {r['ticker']:<6} "
            f"{r['status']:<8} {(r.get('decision') or '-'):<5} "
            f"{tr_s:>8} {al_s:>8}"
        )


# --------------------------------------------------------------------
# `forge backtest report`
# --------------------------------------------------------------------

@backtest_app.command("report")
def backtest_report(
    backtest_id: int = typer.Argument(..., help="backtest_id from `backtest start`"),
):
    from tradingagents.backtest.report import render_report

    config = dict(DEFAULT_CONFIG)
    conn = iic_connect(config["iic_db_path"])
    md = render_report(conn, backtest_id=backtest_id)

    out_dir = Path(config["iic_data_dir"]) / "backtests" / str(backtest_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "report.md"
    report_path.write_text(md, encoding="utf-8")

    # Also update the backtests.report_path so the row points at the file.
    conn.execute(
        "UPDATE backtests SET report_path = ? WHERE backtest_id = ?",
        (str(report_path.relative_to(config["iic_data_dir"])), backtest_id),
    )
    conn.commit()
    typer.echo(f"wrote {report_path}")


# --------------------------------------------------------------------
# `forge backtest close` — manual single-row maturation
# --------------------------------------------------------------------

@backtest_app.command("close")
def backtest_close(
    btr_id: int = typer.Argument(..., help="backtest_runs.btr_id"),
):
    import json
    from tradingagents.backtest.harness import BacktestHarness

    config = dict(DEFAULT_CONFIG)
    conn = iic_connect(config["iic_db_path"])
    row = conn.execute(
        "SELECT backtest_id, persona_id, ticker, metrics FROM backtest_runs WHERE btr_id = ?",
        (btr_id,),
    ).fetchone()
    if not row:
        typer.echo(f"btr_id {btr_id} not found", err=True)
        raise typer.Exit(code=1)
    m = json.loads(row["metrics"])
    if m.get("status") != "open":
        typer.echo(f"btr_id {btr_id} has status {m.get('status')!r}; nothing to close")
        return

    chain = _build_price_chain(config["backtest_price_sources"])
    harness = BacktestHarness(
        conn=conn, data_dir=config["iic_data_dir"],
        graph_runner=_NullGraphRunner(), price_chain=chain,
    )
    harness._mature_one(
        btr_id=btr_id,
        persona_id=row["persona_id"],
        ticker=row["ticker"],
        metrics=m,
        end_date=date.fromisoformat(m["scheduled_close_date"]),
    )
    typer.echo(f"closed btr_id {btr_id}")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/cli/test_forge.py -v
```

Expected: all passing.

- [ ] **Step 5: Commit**

```bash
git add cli/forge.py tests/cli/test_forge.py
git commit -m "feat(cli): forge backtest leaderboard / report / close"
```

---

## Task 22: `forge backtest sweep`, `watch` commands + register `forge` in cli/main.py

**Files:**
- Modify: `cli/forge.py` (add `sweep` and `watch`)
- Modify: `cli/main.py` (register the `forge` sub-app)
- Modify: `tests/cli/test_forge.py` (sweep/watch help + sweep behaviour)

- [ ] **Step 1: Append the failing tests**

Append to `tests/cli/test_forge.py`:

```python
@pytest.mark.unit
def test_backtest_sweep_help():
    from cli.forge import forge_app
    runner = CliRunner()
    result = runner.invoke(forge_app, ["backtest", "sweep", "--help"])
    assert result.exit_code == 0


@pytest.mark.unit
def test_backtest_watch_help():
    from cli.forge import forge_app
    runner = CliRunner()
    result = runner.invoke(forge_app, ["backtest", "watch", "--help"])
    assert result.exit_code == 0
    assert "--interval" in result.stdout


@pytest.mark.unit
def test_backtest_sweep_prints_counts(tmp_path, monkeypatch):
    """End-to-end: empty DB → sweep prints zero counts."""
    iic_db = tmp_path / "iic.db"
    iic_data = tmp_path / "data"
    monkeypatch.setenv("TRADINGAGENTS_IIC_DB_PATH", str(iic_db))
    monkeypatch.setenv("TRADINGAGENTS_IIC_DATA_DIR", str(iic_data))

    import importlib
    import tradingagents.default_config as dc; importlib.reload(dc)
    import cli.forge as forge_mod; importlib.reload(forge_mod)

    # touch DB so schema lands
    from tradingagents.persistence.db import connect
    connect(str(iic_db)).close()

    runner = CliRunner()
    result = runner.invoke(forge_mod.forge_app, ["backtest", "sweep"])
    assert result.exit_code == 0
    assert "closed=0" in result.output
    assert "skipped=0" in result.output


@pytest.mark.unit
def test_cli_main_registers_forge():
    """cli.main must register the forge sub-app under `forge`."""
    from cli.main import app
    runner = CliRunner()
    result = runner.invoke(app, ["forge", "--help"])
    assert result.exit_code == 0
    assert "backtest" in result.stdout
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/cli/test_forge.py -v
```

Expected: 4 new FAILs.

- [ ] **Step 3: Add `sweep` and `watch` to `cli/forge.py`**

Append:

```python
# --------------------------------------------------------------------
# `forge backtest sweep` — one-shot
# --------------------------------------------------------------------

@backtest_app.command("sweep")
def backtest_sweep():
    """Mature any open backtest_runs whose scheduled_close_date <= today."""
    from tradingagents.backtest.sweep import run_maturation_pass

    config = dict(DEFAULT_CONFIG)
    conn = iic_connect(config["iic_db_path"])
    chain = _build_price_chain(config["backtest_price_sources"])
    result = run_maturation_pass(
        conn, price_chain=chain, data_dir=config["iic_data_dir"],
    )
    typer.echo(
        f"sweep: closed={result['closed']} "
        f"skipped={result['skipped']} errored={result['errored']}"
    )


# --------------------------------------------------------------------
# `forge backtest watch` — long-running daemon
# --------------------------------------------------------------------

@backtest_app.command("watch")
def backtest_watch(
    interval: int = typer.Option(
        None, "--interval", help="Loop interval seconds; default from config"
    ),
):
    """Loop `sweep` every N seconds. Ctrl-C to exit."""
    import time
    from tradingagents.backtest.sweep import run_maturation_pass

    config = dict(DEFAULT_CONFIG)
    poll = interval if interval is not None else config["sweep_interval_seconds"]
    chain = _build_price_chain(config["backtest_price_sources"])
    typer.echo(f"watch: polling every {poll}s; Ctrl-C to exit")
    try:
        while True:
            conn = iic_connect(config["iic_db_path"])
            r = run_maturation_pass(
                conn, price_chain=chain, data_dir=config["iic_data_dir"],
            )
            ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
            typer.echo(
                f"{ts}  closed={r['closed']} "
                f"skipped={r['skipped']} errored={r['errored']}"
            )
            conn.close()
            time.sleep(poll)
    except KeyboardInterrupt:
        typer.echo("watch: stopped")
```

- [ ] **Step 4: Register the `forge` sub-app in `cli/main.py`**

Open `cli/main.py`. Find where `deepdive` is registered (it's a single `app.command(...)` or `app.add_typer(...)` somewhere). Add:

```python
from cli.forge import forge_app

app.add_typer(forge_app, name="forge")
```

Place the import + add_typer near the existing CLI registrations to keep the file orderly.

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/cli/test_forge.py -v
```

Expected: all passing.

- [ ] **Step 6: Run the full unit suite to confirm no regressions**

```bash
pytest -m "not integration" --tb=short -q
```

Expected: previously-passing tests still pass.

- [ ] **Step 7: Commit**

```bash
git add cli/forge.py cli/main.py tests/cli/test_forge.py
git commit -m "feat(cli): forge backtest sweep + watch; register forge sub-app"
```

---

## Task 23: F2 exit-gate smoke test (mocked LLM)

**Files:**
- Create: `tests/smoke/test_f2_exit_gate.py`

This is the boundary smoke test that runs entirely against an in-process mock LLM — fast, no API cost. The REAL exit-gate run (Task 24) spends LLM tokens and validates the whole flow end-to-end.

This task asserts: a back-dated watchlist with 5 tickers × 3 personas produces 15 closed `backtest_runs` rows, 15 `outcome_log` rows, a non-empty report, and byte-equal re-render of the report.

- [ ] **Step 1: Write the test**

Create `tests/smoke/test_f2_exit_gate.py`:

```python
"""F2 exit-gate boundary smoke test (no real LLM).

This is the structural / boundary check — it asserts the harness writes
the expected rows and the report is byte-equal on re-render. The actual
exit-gate run that spends LLM tokens lives in the runbook / Task 24.
"""

import json
import re
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest


F2_EXIT_TICKERS = ["AAPL", "MSFT", "GOOG", "NVDA", "TSLA"]
F2_EXIT_PERSONAS = ["macro", "value", "momentum"]


@pytest.mark.smoke
def test_f2_exit_gate_structural_checks(tmp_path, monkeypatch):
    """Structural check — runs the harness with a mock graph runner and
    a deterministic price chain. Asserts:
      * `backtests` row inserted, status=closed at the end.
      * 15 `backtest_runs` rows, all status=closed (no errored).
      * 15 `outcome_log` rows with `tags.source='forward_test'`.
      * Report exists at `data/backtests/<id>/report.md`.
      * Re-rendering the report produces byte-equal content modulo `generated_ts`.
    """
    iic_db = tmp_path / "iic.db"
    iic_data = tmp_path / "data"
    monkeypatch.setenv("TRADINGAGENTS_IIC_DB_PATH", str(iic_db))
    monkeypatch.setenv("TRADINGAGENTS_IIC_DATA_DIR", str(iic_data))

    import importlib
    import tradingagents.default_config as dc; importlib.reload(dc)

    from tradingagents.backtest.harness import BacktestHarness
    from tradingagents.backtest.prices import Bars, Resolution
    from tradingagents.persistence.db import connect
    from tradingagents.persistence import store

    # Deterministic price chain — same prices for every ticker so the
    # comparison is purely about persona / signal divergence.
    from datetime import datetime as dt

    class DeterministicChain:
        def get_bars(self, ticker, start, end, resolution):
            if start == end:
                return Bars(ticker=ticker, resolution=resolution,
                            bars=[(dt.combine(start, dt.min.time()), 100.0)],
                            source="det")
            # 5-bar synthetic series: 100 → 105 → 102 → 108 → 110
            from datetime import timedelta
            bars = []
            prices = [100.0, 105.0, 102.0, 108.0, 110.0]
            for i, p in enumerate(prices):
                step = start + timedelta(days=int(i * (end - start).days / max(1, len(prices) - 1)))
                bars.append((dt.combine(step, dt.min.time()), p))
            return Bars(ticker=ticker, resolution=resolution, bars=bars,
                        source="det")

    # Fake graph runner — deterministic decision per persona.
    class FakeRunner:
        DECISION_BY_PERSONA = {"macro": "BUY", "value": "HOLD", "momentum": "SELL"}
        def run(self, *, ticker, trade_date, persona_id, conn):
            run_id = uuid.uuid4().hex
            now = datetime.now(timezone.utc).isoformat()
            store.insert_run(conn, run_id=run_id, ticker=ticker,
                             persona_id=persona_id, started_ts=now,
                             artifact_dir=f"runs/{run_id}")
            store.finalize_run(conn, run_id=run_id, ended_ts=now,
                               status="complete",
                               decision=self.DECISION_BY_PERSONA[persona_id])
            return run_id, self.DECISION_BY_PERSONA[persona_id]

    conn = connect(str(iic_db))
    harness = BacktestHarness(
        conn=conn, data_dir=str(iic_data),
        graph_runner=FakeRunner(), price_chain=DeterministicChain(),
    )

    # Back-dated 30 days from today
    end_date = date.today()
    from datetime import timedelta
    start_date = end_date - timedelta(days=30)

    backtest_id = harness.run_watchlist(
        tickers=F2_EXIT_TICKERS,
        personas=F2_EXIT_PERSONAS,
        start_date=start_date,
        end_date=end_date,
    )

    # --- structural assertions ---
    bt = conn.execute("SELECT * FROM backtests WHERE backtest_id = ?",
                       (backtest_id,)).fetchone()
    assert bt["status"] == "closed"

    runs = list(conn.execute(
        "SELECT metrics FROM backtest_runs WHERE backtest_id = ?",
        (backtest_id,)))
    assert len(runs) == 15, f"expected 15 rows, got {len(runs)}"
    statuses = [json.loads(r["metrics"])["status"] for r in runs]
    assert statuses.count("closed") == 15, f"non-closed rows: {statuses}"

    outcome_rows = list(conn.execute("SELECT * FROM outcome_log"))
    assert len(outcome_rows) == 15
    for r in outcome_rows:
        tags = json.loads(r["tags"])
        assert tags["source"] == "forward_test"
        assert tags["persona_id"] in F2_EXIT_PERSONAS
        assert tags["backtest_id"] == backtest_id

    # --- report byte-equality ---
    from tradingagents.backtest.report import render_report
    md1 = render_report(conn, backtest_id=backtest_id)
    md2 = render_report(conn, backtest_id=backtest_id)
    rx = re.compile(r"^generated_ts:.*$", re.MULTILINE)
    assert rx.sub("", md1) == rx.sub("", md2), "report not byte-equal on rerun"
    for persona in F2_EXIT_PERSONAS:
        assert persona in md1
    for ticker in F2_EXIT_TICKERS:
        assert ticker in md1
```

- [ ] **Step 2: Run the smoke test**

```bash
pytest tests/smoke/test_f2_exit_gate.py -v
```

Expected: PASS. (This validates the structural plumbing without spending LLM budget. Task 24 is the real LLM-spending end-to-end run.)

- [ ] **Step 3: Commit**

```bash
git add tests/smoke/test_f2_exit_gate.py
git commit -m "test(smoke): F2 exit-gate structural check (mocked LLM + deterministic prices)"
```

---

## Task 24: Run the real F2 exit gate (LLM-spending) and capture the report

**Files:**
- Modify: `tests/smoke/test_f2_exit_gate.py` (add an opt-in `integration` test)
- Note: this task spends real LLM tokens. Estimated cost: $1–$10 at DeepSeek pricing for 15 graph runs.

This is the real-data validation. Run the harness end-to-end on AAPL, MSFT, GOOG, NVDA, TSLA back-dated 30 days from today (i.e., today’s actual date — currently 2026-05-26 — so `start_date=2026-04-26`). The 30-day window is already elapsed, so maturation runs inline. Strict-historical assertion is auto-on (`start_date < today`).

- [ ] **Step 1: Append the integration test (opt-in)**

Append to `tests/smoke/test_f2_exit_gate.py`:

```python
@pytest.mark.smoke
@pytest.mark.integration
def test_f2_exit_gate_real_run(tmp_path, monkeypatch):
    """Real LLM, real yfinance — back-dated 30-day window.

    Runs only when explicitly selected (``pytest -m integration`` or
    ``pytest tests/smoke/test_f2_exit_gate.py::test_f2_exit_gate_real_run``).
    Spends real LLM tokens; expected runtime ~15 minutes.
    """
    import os
    if not os.getenv("F2_RUN_REAL_EXIT_GATE"):
        pytest.skip("set F2_RUN_REAL_EXIT_GATE=1 to spend LLM budget")

    from datetime import date, timedelta
    iic_db = tmp_path / "iic.db"
    iic_data = tmp_path / "data"
    monkeypatch.setenv("TRADINGAGENTS_IIC_DB_PATH", str(iic_db))
    monkeypatch.setenv("TRADINGAGENTS_IIC_DATA_DIR", str(iic_data))

    import importlib
    import tradingagents.default_config as dc; importlib.reload(dc)
    import cli.forge as forge_mod; importlib.reload(forge_mod)

    from typer.testing import CliRunner
    runner = CliRunner()
    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    result = runner.invoke(
        forge_mod.forge_app,
        ["backtest", "start",
         "--watchlist", "AAPL,MSFT,GOOG,NVDA,TSLA",
         "--start-date", start_date.isoformat()],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    # Extract backtest_id from output.
    import re as _re
    m = _re.search(r"backtest_id:\s*(\d+)", result.output)
    assert m, f"no backtest_id in: {result.output}"
    backtest_id = int(m.group(1))

    # Render the report file.
    result = runner.invoke(forge_mod.forge_app,
                            ["backtest", "report", str(backtest_id)])
    assert result.exit_code == 0
    report_path = iic_data / "backtests" / str(backtest_id) / "report.md"
    assert report_path.exists()
    content = report_path.read_text(encoding="utf-8")
    # Sanity: 3 personas appear in the table.
    for persona in ("macro", "value", "momentum"):
        assert persona in content
    # Sanity: at least one ticker appears.
    assert "AAPL" in content
```

- [ ] **Step 2: Commit the test (the gate itself runs in Step 3)**

```bash
git add tests/smoke/test_f2_exit_gate.py
git commit -m "test(smoke): opt-in real F2 exit-gate (LLM-spending, ~15min)"
```

- [ ] **Step 3: Run the real exit gate**

```bash
F2_RUN_REAL_EXIT_GATE=1 pytest tests/smoke/test_f2_exit_gate.py::test_f2_exit_gate_real_run -v --tb=short
```

Expected: PASS in ~15 minutes. The test runs the `forge backtest start` CLI command end-to-end, then `forge backtest report`. On success:

- `data/backtests/<backtest_id>/report.md` exists and contains all three personas + all five tickers.
- `outcome_log` has 15 new rows tagged `source: forward_test`.
- Manual review of the report shows per-persona Sharpe / total return / win rate / alpha numbers vs. SPY.

If the LLM call rates trigger errors or particular `backtest_runs` rows mark `errored`, inspect the JSON metrics and decide whether to re-run after the API recovers, or to accept a partial exit-gate (errored rows are documented per R-F2-3).

- [ ] **Step 4: Save the report artifact for future reference**

```bash
# Copy the generated report into the repo for the record.
mkdir -p docs/superpowers/artifacts
cp $(python -c "from tradingagents.default_config import DEFAULT_CONFIG; print(DEFAULT_CONFIG['iic_data_dir'])")/backtests/*/report.md \
   docs/superpowers/artifacts/2026-05-26-f2-exit-gate-report.md
git add docs/superpowers/artifacts/2026-05-26-f2-exit-gate-report.md
git commit -m "docs(artifacts): F2 exit-gate report (real run, $(date +%Y-%m-%d))"
```

- [ ] **Step 5: Verify the persona spread (R-F2-2)**

Open the report. Compute the per-persona Sharpe spread:

```
spread = max(persona_sharpe) - min(persona_sharpe)
```

- If `spread >= 0.1`: the persona wiring is producing real behavioral divergence. Document the result; the gate is passed.
- If `spread < 0.1`: the wiring is "loaded but cosmetic" (R-F2-2). The gate is still procedurally passed (rows produced, byte-equal report), but flag this in the IIC-FORGE-05 follow-ups: revisit prompt structure, LLM choice, or the persona model itself.

Either way, F2 is shipped — the harness works. The persona-spread signal is feedback on the persona design, not the F2 harness design.

- [ ] **Step 6: Final commit + branch handoff**

```bash
# Final tidy commit with the exit-gate note.
git status
# If anything dangling — stage + commit
git push -u origin feat/iic-forge-05-f2
```

Then open a PR titled `IIC-FORGE F2 — forward-test harness + leaderboard` and link it to:
- The design spec at `docs/superpowers/specs/2026-05-26-iic-forge-05-f2-backtest-benchmark-design.md`
- The exit-gate artifact at `docs/superpowers/artifacts/2026-05-26-f2-exit-gate-report.md`

---

## Final test sweep

After all 24 tasks ship, run the unit + smoke suites one more time:

```bash
pytest -m "unit or smoke" --tb=short -q
```

Expected: all green. Integration tests (real LLM, real network) remain opt-in via `-m integration` or env var triggers.
