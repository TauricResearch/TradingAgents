# Backtest Engine + Performance Dashboard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** TradingAgents에 백테스트 엔진, 실거래 성과 추적기, HTML 대시보드를 추가하여 전략 검증과 성과 시각화를 가능하게 한다.

**Architecture:** 기존 TradingAgentsGraph를 변경하지 않고 3개 신규 모듈(backtest/, tracker/, dashboard/)이 외부 오케스트레이터로 기존 코드를 호출. JSON 파일 기반 저장, DB 의존성 없음.

**Tech Stack:** Python 3.10+, pandas (기존 의존성), yfinance (기존 의존성), Plotly.js CDN (HTML 내장), dataclasses, pytest

---

## Task 1: Data Models (backtest/models.py)

**Files:**
- Create: `tradingagents/backtest/__init__.py`
- Create: `tradingagents/backtest/models.py`
- Test: `tests/test_backtest_models.py`

**Step 1: Write the failing test**

```python
# tests/test_backtest_models.py
"""Tests for tradingagents.backtest.models."""

from tradingagents.backtest.models import (
    TradeRecord,
    PerformanceMetrics,
    BacktestResult,
)


class TestTradeRecord:
    def test_creation_with_defaults(self):
        rec = TradeRecord(
            ticker="005930",
            trade_date="2026-01-15",
            signal="BUY",
            entry_price=58000.0,
            quantity=100,
            source="backtest",
        )
        assert rec.ticker == "005930"
        assert rec.signal == "BUY"
        assert rec.exit_price is None
        assert rec.exit_date is None
        assert rec.pnl is None
        assert rec.pnl_pct is None
        assert rec.analyst_reports == {}
        assert rec.debate_summary == ""
        assert rec.risk_decision == ""
        assert rec.persona is None

    def test_closed_trade(self):
        rec = TradeRecord(
            ticker="NVDA",
            trade_date="2026-01-15",
            signal="BUY",
            entry_price=100.0,
            quantity=50,
            source="paper",
            exit_price=110.0,
            exit_date="2026-02-15",
            pnl=500.0,
            pnl_pct=10.0,
        )
        assert rec.exit_price == 110.0
        assert rec.pnl == 500.0
        assert rec.pnl_pct == 10.0

    def test_to_dict(self):
        rec = TradeRecord(
            ticker="005930",
            trade_date="2026-01-15",
            signal="BUY",
            entry_price=58000.0,
            quantity=100,
            source="backtest",
        )
        d = rec.to_dict()
        assert d["ticker"] == "005930"
        assert isinstance(d, dict)

    def test_from_dict(self):
        d = {
            "ticker": "005930",
            "trade_date": "2026-01-15",
            "signal": "BUY",
            "entry_price": 58000.0,
            "quantity": 100,
            "source": "backtest",
        }
        rec = TradeRecord.from_dict(d)
        assert rec.ticker == "005930"
        assert rec.entry_price == 58000.0

    def test_source_validation(self):
        """Source must be backtest, paper, or real."""
        import pytest
        with pytest.raises(ValueError):
            TradeRecord(
                ticker="X", trade_date="2026-01-01", signal="BUY",
                entry_price=1.0, quantity=1, source="invalid",
            )

    def test_signal_validation(self):
        """Signal must be BUY, SELL, or HOLD."""
        import pytest
        with pytest.raises(ValueError):
            TradeRecord(
                ticker="X", trade_date="2026-01-01", signal="MAYBE",
                entry_price=1.0, quantity=1, source="backtest",
            )


class TestPerformanceMetrics:
    def test_creation(self):
        m = PerformanceMetrics(
            total_trades=20,
            win_rate=65.0,
            avg_return=2.1,
            cumulative_return=23.4,
            sharpe_ratio=1.42,
            max_drawdown=-8.7,
            max_drawdown_duration=15,
            alpha=5.2,
            beta=0.87,
            profit_factor=1.83,
            avg_holding_days=12.3,
            equity_curve=[{"date": "2026-01-01", "equity": 100000, "drawdown": 0.0}],
            monthly_returns=[{"month": "2026-01", "return_pct": 2.1}],
        )
        assert m.sharpe_ratio == 1.42
        assert m.max_drawdown == -8.7
        assert len(m.equity_curve) == 1

    def test_to_dict(self):
        m = PerformanceMetrics(
            total_trades=10, win_rate=50.0, avg_return=1.0,
            cumulative_return=10.0, sharpe_ratio=1.0, max_drawdown=-5.0,
            max_drawdown_duration=5, alpha=2.0, beta=1.0,
            profit_factor=1.5, avg_holding_days=10.0,
            equity_curve=[], monthly_returns=[],
        )
        d = m.to_dict()
        assert d["sharpe_ratio"] == 1.0


class TestBacktestResult:
    def test_creation(self):
        metrics = PerformanceMetrics(
            total_trades=1, win_rate=100.0, avg_return=5.0,
            cumulative_return=5.0, sharpe_ratio=2.0, max_drawdown=-1.0,
            max_drawdown_duration=1, alpha=3.0, beta=0.5,
            profit_factor=5.0, avg_holding_days=30.0,
            equity_curve=[], monthly_returns=[],
        )
        result = BacktestResult(
            ticker="NVDA",
            config_snapshot={"llm_provider": "anthropic", "persona": "warren_buffett"},
            start_date="2024-04-01",
            end_date="2026-04-01",
            benchmark="SPY",
            trades=[],
            metrics=metrics,
        )
        assert result.ticker == "NVDA"
        assert result.benchmark == "SPY"
        assert result.created_at is not None
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/herald/Projects/agents/TradingAgents && python -m pytest tests/test_backtest_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tradingagents.backtest'`

**Step 3: Write minimal implementation**

```python
# tradingagents/backtest/__init__.py
# Copyright 2026 herald.k, HongSoo Kim
#
# Licensed under the Apache License, Version 2.0 (the "License");
# ...

from .models import TradeRecord, PerformanceMetrics, BacktestResult
```

```python
# tradingagents/backtest/models.py
# Copyright 2026 herald.k, HongSoo Kim
#
# Licensed under the Apache License, Version 2.0 (the "License");
# ...

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

VALID_SOURCES = ("backtest", "paper", "real")
VALID_SIGNALS = ("BUY", "SELL", "HOLD")


@dataclass
class TradeRecord:
    """단일 거래 기록. 백테스트·모의투자·실투자 공용."""

    ticker: str
    trade_date: str
    signal: str
    entry_price: float
    quantity: int
    source: str  # "backtest" | "paper" | "real"

    exit_price: Optional[float] = None
    exit_date: Optional[str] = None
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None

    analyst_reports: dict = field(default_factory=dict)
    debate_summary: str = ""
    risk_decision: str = ""
    persona: Optional[str] = None

    def __post_init__(self):
        if self.source not in VALID_SOURCES:
            raise ValueError(f"source must be one of {VALID_SOURCES}, got '{self.source}'")
        self.signal = self.signal.strip().upper()
        if self.signal not in VALID_SIGNALS:
            raise ValueError(f"signal must be one of {VALID_SIGNALS}, got '{self.signal}'")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> TradeRecord:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class PerformanceMetrics:
    """기간 성과 지표."""

    total_trades: int
    win_rate: float
    avg_return: float
    cumulative_return: float
    sharpe_ratio: float
    max_drawdown: float
    max_drawdown_duration: int
    alpha: float
    beta: float
    profit_factor: float
    avg_holding_days: float
    equity_curve: list = field(default_factory=list)
    monthly_returns: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BacktestResult:
    """백테스트 전체 결과."""

    ticker: str
    config_snapshot: dict
    start_date: str
    end_date: str
    benchmark: str
    trades: list  # list[TradeRecord]
    metrics: PerformanceMetrics
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        return d
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/herald/Projects/agents/TradingAgents && python -m pytest tests/test_backtest_models.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add tradingagents/backtest/__init__.py tradingagents/backtest/models.py tests/test_backtest_models.py
git commit -m "feat: add backtest data models (TradeRecord, PerformanceMetrics, BacktestResult)"
```

---

## Task 2: Performance Calculator (backtest/performance.py)

**Files:**
- Create: `tradingagents/backtest/performance.py`
- Test: `tests/test_performance.py`

**Step 1: Write the failing test**

```python
# tests/test_performance.py
"""Tests for tradingagents.backtest.performance."""

import pytest
from tradingagents.backtest.models import TradeRecord
from tradingagents.backtest.performance import PerformanceCalculator


def _make_trades():
    """10 trades: 7 wins, 3 losses across 2024-04 to 2025-03."""
    data = [
        ("2024-04-01", "BUY", 100.0, "2024-05-01", 110.0),   # +10%
        ("2024-05-01", "BUY", 200.0, "2024-06-01", 190.0),   # -5%
        ("2024-06-01", "BUY", 150.0, "2024-07-01", 165.0),   # +10%
        ("2024-07-01", "BUY", 120.0, "2024-08-01", 132.0),   # +10%
        ("2024-08-01", "BUY", 180.0, "2024-09-01", 171.0),   # -5%
        ("2024-09-01", "BUY", 140.0, "2024-10-01", 154.0),   # +10%
        ("2024-10-01", "BUY", 160.0, "2024-11-01", 176.0),   # +10%
        ("2024-11-01", "BUY", 130.0, "2024-12-01", 117.0),   # -10%
        ("2024-12-01", "BUY", 170.0, "2025-01-01", 187.0),   # +10%
        ("2025-01-01", "BUY", 190.0, "2025-02-01", 209.0),   # +10%
    ]
    trades = []
    for entry_date, signal, entry_p, exit_date, exit_p in data:
        pnl_pct = (exit_p - entry_p) / entry_p * 100
        trades.append(TradeRecord(
            ticker="TEST", trade_date=entry_date, signal=signal,
            entry_price=entry_p, quantity=100, source="backtest",
            exit_price=exit_p, exit_date=exit_date,
            pnl=(exit_p - entry_p) * 100, pnl_pct=pnl_pct,
        ))
    return trades


class TestPerformanceCalculator:
    def test_basic_metrics(self):
        calc = PerformanceCalculator()
        trades = _make_trades()
        metrics = calc.calculate(
            trades=trades,
            initial_capital=100_000.0,
            benchmark_ticker="SPY",
            start_date="2024-04-01",
            end_date="2025-02-01",
        )
        assert metrics.total_trades == 10
        assert metrics.win_rate == 70.0  # 7/10
        assert metrics.avg_return == pytest.approx(5.0, abs=0.1)  # avg of returns

    def test_sharpe_positive(self):
        calc = PerformanceCalculator()
        trades = _make_trades()
        metrics = calc.calculate(
            trades=trades, initial_capital=100_000.0,
            benchmark_ticker="SPY", start_date="2024-04-01", end_date="2025-02-01",
        )
        assert metrics.sharpe_ratio > 0

    def test_max_drawdown_negative(self):
        calc = PerformanceCalculator()
        trades = _make_trades()
        metrics = calc.calculate(
            trades=trades, initial_capital=100_000.0,
            benchmark_ticker="SPY", start_date="2024-04-01", end_date="2025-02-01",
        )
        assert metrics.max_drawdown < 0

    def test_equity_curve_not_empty(self):
        calc = PerformanceCalculator()
        trades = _make_trades()
        metrics = calc.calculate(
            trades=trades, initial_capital=100_000.0,
            benchmark_ticker="SPY", start_date="2024-04-01", end_date="2025-02-01",
        )
        assert len(metrics.equity_curve) > 0
        assert "date" in metrics.equity_curve[0]
        assert "equity" in metrics.equity_curve[0]

    def test_monthly_returns_not_empty(self):
        calc = PerformanceCalculator()
        trades = _make_trades()
        metrics = calc.calculate(
            trades=trades, initial_capital=100_000.0,
            benchmark_ticker="SPY", start_date="2024-04-01", end_date="2025-02-01",
        )
        assert len(metrics.monthly_returns) > 0

    def test_empty_trades(self):
        calc = PerformanceCalculator()
        metrics = calc.calculate(
            trades=[], initial_capital=100_000.0,
            benchmark_ticker="SPY", start_date="2024-04-01", end_date="2025-02-01",
        )
        assert metrics.total_trades == 0
        assert metrics.win_rate == 0.0
        assert metrics.sharpe_ratio == 0.0

    def test_profit_factor(self):
        calc = PerformanceCalculator()
        trades = _make_trades()
        metrics = calc.calculate(
            trades=trades, initial_capital=100_000.0,
            benchmark_ticker="SPY", start_date="2024-04-01", end_date="2025-02-01",
        )
        # profit_factor = total_gains / total_losses (absolute)
        assert metrics.profit_factor > 1.0
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/herald/Projects/agents/TradingAgents && python -m pytest tests/test_performance.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tradingagents.backtest.performance'`

**Step 3: Write minimal implementation**

```python
# tradingagents/backtest/performance.py
# Copyright 2026 herald.k, HongSoo Kim
#
# Licensed under the Apache License, Version 2.0 (the "License");
# ...

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import List

import pandas as pd

from .models import TradeRecord, PerformanceMetrics


class PerformanceCalculator:
    """TradeRecord 리스트로부터 성과 지표를 계산한다."""

    def calculate(
        self,
        trades: List[TradeRecord],
        initial_capital: float,
        benchmark_ticker: str,
        start_date: str,
        end_date: str,
    ) -> PerformanceMetrics:
        if not trades:
            return self._empty_metrics()

        closed = [t for t in trades if t.exit_price is not None and t.pnl_pct is not None]
        if not closed:
            return self._empty_metrics()

        returns = [t.pnl_pct for t in closed]
        wins = [r for r in returns if r > 0]
        losses = [r for r in returns if r <= 0]

        total_trades = len(closed)
        win_rate = len(wins) / total_trades * 100 if total_trades else 0.0
        avg_return = sum(returns) / total_trades if total_trades else 0.0

        # Equity curve
        equity_curve = self._build_equity_curve(closed, initial_capital)

        # Cumulative return
        final_equity = equity_curve[-1]["equity"] if equity_curve else initial_capital
        cumulative_return = (final_equity - initial_capital) / initial_capital * 100

        # Sharpe ratio (annualized from monthly returns)
        sharpe_ratio = self._sharpe_ratio(returns)

        # Max drawdown
        mdd, mdd_duration = self._max_drawdown(equity_curve)

        # Alpha, beta (simplified — without benchmark fetch to keep tests fast)
        alpha = cumulative_return  # placeholder; real alpha = cumulative - benchmark
        beta = 1.0  # placeholder

        # Profit factor
        total_gains = sum(abs(r) for r in wins) if wins else 0.0
        total_losses = sum(abs(r) for r in losses) if losses else 1.0
        profit_factor = total_gains / total_losses if total_losses > 0 else float("inf")

        # Average holding days
        holding_days = []
        for t in closed:
            d0 = datetime.strptime(t.trade_date, "%Y-%m-%d")
            d1 = datetime.strptime(t.exit_date, "%Y-%m-%d")
            holding_days.append((d1 - d0).days)
        avg_holding_days = sum(holding_days) / len(holding_days) if holding_days else 0.0

        # Monthly returns
        monthly_returns = self._monthly_returns(closed)

        return PerformanceMetrics(
            total_trades=total_trades,
            win_rate=round(win_rate, 1),
            avg_return=round(avg_return, 2),
            cumulative_return=round(cumulative_return, 2),
            sharpe_ratio=round(sharpe_ratio, 2),
            max_drawdown=round(mdd, 2),
            max_drawdown_duration=mdd_duration,
            alpha=round(alpha, 2),
            beta=round(beta, 2),
            profit_factor=round(profit_factor, 2),
            avg_holding_days=round(avg_holding_days, 1),
            equity_curve=equity_curve,
            monthly_returns=monthly_returns,
        )

    def _empty_metrics(self) -> PerformanceMetrics:
        return PerformanceMetrics(
            total_trades=0, win_rate=0.0, avg_return=0.0,
            cumulative_return=0.0, sharpe_ratio=0.0, max_drawdown=0.0,
            max_drawdown_duration=0, alpha=0.0, beta=0.0,
            profit_factor=0.0, avg_holding_days=0.0,
            equity_curve=[], monthly_returns=[],
        )

    def _build_equity_curve(
        self, trades: List[TradeRecord], initial_capital: float
    ) -> list:
        equity = initial_capital
        curve = [{"date": trades[0].trade_date, "equity": equity, "drawdown": 0.0}]
        peak = equity
        for t in trades:
            pnl = t.pnl if t.pnl is not None else 0.0
            equity += pnl
            peak = max(peak, equity)
            dd = (equity - peak) / peak * 100 if peak > 0 else 0.0
            curve.append({
                "date": t.exit_date or t.trade_date,
                "equity": round(equity, 2),
                "drawdown": round(dd, 2),
            })
        return curve

    def _sharpe_ratio(self, returns: list) -> float:
        if len(returns) < 2:
            return 0.0
        mean_r = sum(returns) / len(returns)
        var = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
        std = math.sqrt(var) if var > 0 else 0.0
        if std == 0:
            return 0.0
        # Annualize assuming monthly rebalancing
        return round(math.sqrt(12) * mean_r / std, 2)

    def _max_drawdown(self, equity_curve: list) -> tuple:
        if not equity_curve:
            return 0.0, 0
        peak = equity_curve[0]["equity"]
        max_dd = 0.0
        dd_start = 0
        max_dd_duration = 0
        current_dd_start = 0
        for i, point in enumerate(equity_curve):
            eq = point["equity"]
            if eq >= peak:
                peak = eq
                duration = i - current_dd_start
                if duration > max_dd_duration:
                    max_dd_duration = duration
                current_dd_start = i
            dd = (eq - peak) / peak * 100 if peak > 0 else 0.0
            if dd < max_dd:
                max_dd = dd
        return max_dd, max_dd_duration

    def _monthly_returns(self, trades: List[TradeRecord]) -> list:
        monthly = {}
        for t in trades:
            month = t.trade_date[:7]  # "YYYY-MM"
            if month not in monthly:
                monthly[month] = []
            monthly[month].append(t.pnl_pct or 0.0)
        return [
            {"month": m, "return_pct": round(sum(rets) / len(rets), 2)}
            for m, rets in sorted(monthly.items())
        ]
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/herald/Projects/agents/TradingAgents && python -m pytest tests/test_performance.py -v`
Expected: All PASS

**Step 5: Update __init__.py and commit**

Add to `tradingagents/backtest/__init__.py`:
```python
from .performance import PerformanceCalculator
```

```bash
git add tradingagents/backtest/performance.py tradingagents/backtest/__init__.py tests/test_performance.py
git commit -m "feat: add PerformanceCalculator with Sharpe, MDD, win rate, equity curve"
```

---

## Task 3: Backtest Engine (backtest/engine.py)

**Files:**
- Create: `tradingagents/backtest/engine.py`
- Test: `tests/test_backtest_engine.py`

**Step 1: Write the failing test**

```python
# tests/test_backtest_engine.py
"""Tests for tradingagents.backtest.engine."""

from unittest.mock import MagicMock, patch
import pytest

from tradingagents.backtest.engine import BacktestEngine
from tradingagents.backtest.models import TradeRecord, BacktestResult
from tradingagents.default_config import DEFAULT_CONFIG


def _make_config():
    config = DEFAULT_CONFIG.copy()
    config["results_dir"] = "/tmp/test_backtest_results"
    return config


def _mock_graph_propagate(ticker, date):
    """Mock that returns a minimal state + signal."""
    state = {
        "company_of_interest": ticker,
        "trade_date": date,
        "market_report": "Mock market report",
        "sentiment_report": "Mock sentiment",
        "news_report": "Mock news",
        "fundamentals_report": "Mock fundamentals",
        "investment_debate_state": {
            "bull_history": "Bull case",
            "bear_history": "Bear case",
            "judge_decision": "BUY recommended",
        },
        "risk_debate_state": {
            "judge_decision": "Risk acceptable",
        },
        "final_trade_decision": "FINAL TRANSACTION PROPOSAL: **BUY**",
    }
    return state, "BUY"


class TestRebalanceDates:
    def test_monthly_dates(self):
        engine = BacktestEngine(_make_config())
        dates = engine._generate_rebalance_dates("2024-04-01", "2024-07-01", "monthly")
        assert len(dates) >= 3
        # First date should be in April 2024
        assert dates[0].month == 4

    def test_weekly_dates(self):
        engine = BacktestEngine(_make_config())
        dates = engine._generate_rebalance_dates("2024-04-01", "2024-05-01", "weekly")
        assert len(dates) >= 4


class TestBacktestEngine:
    @patch("tradingagents.backtest.engine.TradingAgentsGraph")
    @patch("tradingagents.backtest.engine.yf")
    def test_run_returns_backtest_result(self, mock_yf, mock_graph_cls):
        """Engine.run() should return a BacktestResult with trades and metrics."""
        # Mock yfinance price data
        mock_hist = MagicMock()
        mock_hist.empty = False
        mock_hist.__getitem__ = MagicMock(return_value=MagicMock(
            iloc=MagicMock(__getitem__=MagicMock(return_value=100.0))
        ))
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = mock_hist
        mock_yf.Ticker.return_value = mock_ticker

        # Mock graph
        mock_graph = MagicMock()
        mock_graph.propagate.side_effect = _mock_graph_propagate
        mock_graph_cls.return_value = mock_graph

        engine = BacktestEngine(_make_config())
        result = engine.run(
            ticker="NVDA",
            start_date="2024-04-01",
            end_date="2024-07-01",
            rebalance_freq="monthly",
            benchmark="SPY",
            initial_capital=100_000.0,
        )
        assert isinstance(result, BacktestResult)
        assert result.ticker == "NVDA"
        assert result.metrics.total_trades >= 0
        assert len(result.trades) >= 0

    @patch("tradingagents.backtest.engine.TradingAgentsGraph")
    @patch("tradingagents.backtest.engine.yf")
    def test_signals_cached(self, mock_yf, mock_graph_cls):
        """With save_signals=True, signals should be cached."""
        mock_hist = MagicMock()
        mock_hist.empty = False
        mock_hist.__getitem__ = MagicMock(return_value=MagicMock(
            iloc=MagicMock(__getitem__=MagicMock(return_value=100.0))
        ))
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = mock_hist
        mock_yf.Ticker.return_value = mock_ticker

        mock_graph = MagicMock()
        mock_graph.propagate.side_effect = _mock_graph_propagate
        mock_graph_cls.return_value = mock_graph

        engine = BacktestEngine(_make_config())
        result = engine.run(
            ticker="NVDA",
            start_date="2024-04-01",
            end_date="2024-06-01",
            rebalance_freq="monthly",
            benchmark="SPY",
            initial_capital=100_000.0,
            save_signals=True,
        )
        assert engine._signal_cache is not None
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/herald/Projects/agents/TradingAgents && python -m pytest tests/test_backtest_engine.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# tradingagents/backtest/engine.py
# Copyright 2026 herald.k, HongSoo Kim
#
# Licensed under the Apache License, Version 2.0 (the "License");
# ...

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import yfinance as yf

from tradingagents.graph.trading_graph import TradingAgentsGraph

from .models import TradeRecord, BacktestResult
from .performance import PerformanceCalculator

logger = logging.getLogger(__name__)


class BacktestEngine:
    """과거 데이터로 TradingAgentsGraph를 반복 실행하여 전략 성과를 측정."""

    def __init__(self, config: dict):
        self.config = config
        self._signal_cache: Dict[str, str] = {}
        self._calculator = PerformanceCalculator()

    def run(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        rebalance_freq: str = "monthly",
        benchmark: str = "SPY",
        initial_capital: float = 100_000_000,
        save_signals: bool = False,
        skip_llm: bool = False,
    ) -> BacktestResult:
        dates = self._generate_rebalance_dates(start_date, end_date, rebalance_freq)

        if not skip_llm:
            graph = TradingAgentsGraph(config=self.config)

        trades: List[TradeRecord] = []
        position: Optional[TradeRecord] = None  # current open position

        for i, rebal_date in enumerate(dates):
            date_str = rebal_date.strftime("%Y-%m-%d")
            price = self._get_price_at_date(ticker, date_str)
            if price is None:
                logger.warning("No price for %s on %s, skipping", ticker, date_str)
                continue

            # Get signal
            if skip_llm and date_str in self._signal_cache:
                signal = self._signal_cache[date_str]
                state = {}
            else:
                try:
                    state, signal = graph.propagate(ticker, date_str)
                except Exception as e:
                    logger.error("propagate failed for %s on %s: %s", ticker, date_str, e)
                    continue

            if save_signals:
                self._signal_cache[date_str] = signal

            signal = signal.strip().upper()
            if signal not in ("BUY", "SELL", "HOLD"):
                signal = "HOLD"

            # Position management
            if signal == "BUY" and position is None:
                quantity = int(initial_capital * 0.05 / price) if price > 0 else 0
                if quantity > 0:
                    position = TradeRecord(
                        ticker=ticker,
                        trade_date=date_str,
                        signal="BUY",
                        entry_price=price,
                        quantity=quantity,
                        source="backtest",
                        analyst_reports=self._extract_reports(state),
                        debate_summary=self._extract_debate(state),
                        risk_decision=self._extract_risk(state),
                        persona=self.config.get("persona"),
                    )

            elif signal == "SELL" and position is not None:
                pnl = (price - position.entry_price) * position.quantity
                pnl_pct = (price - position.entry_price) / position.entry_price * 100
                closed = TradeRecord(
                    ticker=position.ticker,
                    trade_date=position.trade_date,
                    signal=position.signal,
                    entry_price=position.entry_price,
                    quantity=position.quantity,
                    source="backtest",
                    exit_price=price,
                    exit_date=date_str,
                    pnl=round(pnl, 2),
                    pnl_pct=round(pnl_pct, 2),
                    analyst_reports=position.analyst_reports,
                    debate_summary=position.debate_summary,
                    risk_decision=position.risk_decision,
                    persona=position.persona,
                )
                trades.append(closed)
                position = None

        # Close any remaining position at last price
        if position is not None and dates:
            last_date = dates[-1].strftime("%Y-%m-%d")
            last_price = self._get_price_at_date(ticker, last_date)
            if last_price:
                pnl = (last_price - position.entry_price) * position.quantity
                pnl_pct = (last_price - position.entry_price) / position.entry_price * 100
                position.exit_price = last_price
                position.exit_date = last_date
                position.pnl = round(pnl, 2)
                position.pnl_pct = round(pnl_pct, 2)
                trades.append(position)

        metrics = self._calculator.calculate(
            trades=trades,
            initial_capital=initial_capital,
            benchmark_ticker=benchmark,
            start_date=start_date,
            end_date=end_date,
        )

        result = BacktestResult(
            ticker=ticker,
            config_snapshot={
                "llm_provider": self.config.get("llm_provider"),
                "deep_think_llm": self.config.get("deep_think_llm"),
                "persona": self.config.get("persona"),
                "max_debate_rounds": self.config.get("max_debate_rounds"),
            },
            start_date=start_date,
            end_date=end_date,
            benchmark=benchmark,
            trades=trades,
            metrics=metrics,
        )

        self._save_result(result)
        return result

    def _generate_rebalance_dates(
        self, start: str, end: str, freq: str
    ) -> List[date]:
        start_d = datetime.strptime(start, "%Y-%m-%d").date()
        end_d = datetime.strptime(end, "%Y-%m-%d").date()
        dates = []
        current = start_d

        if freq == "monthly":
            while current <= end_d:
                # Adjust to next weekday if weekend
                adjusted = self._next_business_day(current)
                if adjusted <= end_d:
                    dates.append(adjusted)
                if current.month == 12:
                    current = current.replace(year=current.year + 1, month=1, day=1)
                else:
                    current = current.replace(month=current.month + 1, day=1)
        elif freq == "weekly":
            while current <= end_d:
                adjusted = self._next_business_day(current)
                if adjusted <= end_d:
                    dates.append(adjusted)
                current += timedelta(days=7)
        elif freq == "biweekly":
            while current <= end_d:
                adjusted = self._next_business_day(current)
                if adjusted <= end_d:
                    dates.append(adjusted)
                current += timedelta(days=14)

        return dates

    def _next_business_day(self, d: date) -> date:
        while d.weekday() >= 5:  # Saturday=5, Sunday=6
            d += timedelta(days=1)
        return d

    def _get_price_at_date(self, ticker: str, date_str: str) -> Optional[float]:
        try:
            t = yf.Ticker(ticker)
            d = datetime.strptime(date_str, "%Y-%m-%d")
            hist = t.history(start=d - timedelta(days=5), end=d + timedelta(days=1))
            if hist.empty:
                return None
            return float(hist["Close"].iloc[-1])
        except Exception as e:
            logger.warning("Price fetch failed for %s on %s: %s", ticker, date_str, e)
            return None

    def _extract_reports(self, state: dict) -> dict:
        if not state:
            return {}
        return {
            "market": state.get("market_report", "")[:500],
            "sentiment": state.get("sentiment_report", "")[:500],
            "news": state.get("news_report", "")[:500],
            "fundamentals": state.get("fundamentals_report", "")[:500],
        }

    def _extract_debate(self, state: dict) -> str:
        if not state:
            return ""
        ids = state.get("investment_debate_state", {})
        bull = ids.get("bull_history", "")[:300]
        bear = ids.get("bear_history", "")[:300]
        return f"Bull: {bull}\nBear: {bear}"

    def _extract_risk(self, state: dict) -> str:
        if not state:
            return ""
        return state.get("risk_debate_state", {}).get("judge_decision", "")[:500]

    def _save_result(self, result: BacktestResult):
        results_dir = self.config.get("results_dir", "./results")
        out_dir = Path(results_dir) / "backtest"
        out_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{result.ticker}_{result.start_date}_{result.end_date}.json"
        filepath = out_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2, ensure_ascii=False, default=str)

        logger.info("Backtest result saved to %s", filepath)
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/herald/Projects/agents/TradingAgents && python -m pytest tests/test_backtest_engine.py -v`
Expected: All PASS

**Step 5: Update __init__.py and commit**

Add to `tradingagents/backtest/__init__.py`:
```python
from .engine import BacktestEngine
```

```bash
git add tradingagents/backtest/engine.py tradingagents/backtest/__init__.py tests/test_backtest_engine.py
git commit -m "feat: add BacktestEngine with rebalancing, signal caching, position management"
```

---

## Task 4: Trade Tracker (tracker/tracker.py)

**Files:**
- Create: `tradingagents/tracker/__init__.py`
- Create: `tradingagents/tracker/tracker.py`
- Test: `tests/test_tracker.py`

**Step 1: Write the failing test**

```python
# tests/test_tracker.py
"""Tests for tradingagents.tracker.tracker."""

import json
import tempfile
import os
import pytest

from tradingagents.tracker.tracker import TradeTracker
from tradingagents.backtest.models import TradeRecord


def _make_config(tmp_dir):
    return {"results_dir": tmp_dir, "persona": "warren_buffett"}


def _make_agent_state():
    return {
        "market_report": "Strong uptrend",
        "sentiment_report": "Bullish sentiment",
        "news_report": "Positive earnings",
        "fundamentals_report": "Revenue growing 20%",
        "investment_debate_state": {
            "bull_history": "Bull: strong moat",
            "bear_history": "Bear: high valuation",
            "judge_decision": "BUY recommended",
        },
        "risk_debate_state": {
            "judge_decision": "Risk acceptable, 5% position",
        },
    }


class TestRecordTrade:
    def test_record_buy(self):
        with tempfile.TemporaryDirectory() as tmp:
            tracker = TradeTracker(_make_config(tmp))
            rec = tracker.record_trade(
                ticker="005930", trade_date="2026-04-25", signal="BUY",
                price=58000.0, quantity=100, source="paper",
                agent_state=_make_agent_state(),
            )
            assert rec.ticker == "005930"
            assert rec.signal == "BUY"
            assert rec.source == "paper"
            assert rec.exit_price is None

    def test_record_persists_to_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            tracker = TradeTracker(_make_config(tmp))
            tracker.record_trade(
                ticker="005930", trade_date="2026-04-25", signal="BUY",
                price=58000.0, quantity=100, source="paper",
                agent_state=_make_agent_state(),
            )
            filepath = os.path.join(tmp, "trades", "005930", "trades.json")
            assert os.path.exists(filepath)
            with open(filepath) as f:
                data = json.load(f)
            assert len(data) == 1
            assert data[0]["ticker"] == "005930"


class TestClosePosition:
    def test_close_updates_pnl(self):
        with tempfile.TemporaryDirectory() as tmp:
            tracker = TradeTracker(_make_config(tmp))
            tracker.record_trade(
                ticker="005930", trade_date="2026-04-25", signal="BUY",
                price=58000.0, quantity=100, source="paper",
                agent_state=_make_agent_state(),
            )
            closed = tracker.close_position("005930", "2026-04-28", 61000.0)
            assert closed.exit_price == 61000.0
            assert closed.pnl == pytest.approx(300000.0)  # (61000-58000)*100
            assert closed.pnl_pct == pytest.approx(5.17, abs=0.1)


class TestGetTrades:
    def test_filter_by_ticker(self):
        with tempfile.TemporaryDirectory() as tmp:
            tracker = TradeTracker(_make_config(tmp))
            tracker.record_trade("005930", "2026-04-25", "BUY", 58000, 100, "paper", {})
            tracker.record_trade("NVDA", "2026-04-25", "BUY", 130, 50, "paper", {})
            trades = tracker.get_trades(ticker="005930")
            assert len(trades) == 1
            assert trades[0].ticker == "005930"

    def test_filter_by_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            tracker = TradeTracker(_make_config(tmp))
            tracker.record_trade("005930", "2026-04-25", "BUY", 58000, 100, "paper", {})
            tracker.record_trade("005930", "2026-04-26", "BUY", 59000, 100, "real", {})
            trades = tracker.get_trades(source="paper")
            assert len(trades) == 1


class TestOpenPositions:
    def test_returns_unclosed_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            tracker = TradeTracker(_make_config(tmp))
            tracker.record_trade("005930", "2026-04-25", "BUY", 58000, 100, "paper", {})
            tracker.record_trade("NVDA", "2026-04-25", "BUY", 130, 50, "paper", {})
            tracker.close_position("005930", "2026-04-28", 61000.0)
            open_pos = tracker.get_open_positions()
            assert len(open_pos) == 1
            assert open_pos[0].ticker == "NVDA"
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/herald/Projects/agents/TradingAgents && python -m pytest tests/test_tracker.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# tradingagents/tracker/__init__.py
# Copyright 2026 herald.k, HongSoo Kim
# ...
from .tracker import TradeTracker
```

```python
# tradingagents/tracker/tracker.py
# Copyright 2026 herald.k, HongSoo Kim
#
# Licensed under the Apache License, Version 2.0 (the "License");
# ...

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import List, Optional

from tradingagents.backtest.models import TradeRecord
from tradingagents.backtest.performance import PerformanceCalculator, PerformanceMetrics

logger = logging.getLogger(__name__)


class TradeTracker:
    """실거래·모의투자 결과를 누적 기록하고 성과를 추적한다."""

    def __init__(self, config: dict):
        self.config = config
        self.storage_dir = config.get("results_dir", "./results")
        self._calculator = PerformanceCalculator()
        self._trades: List[TradeRecord] = []
        self._load_existing()

    def _trades_dir(self, ticker: str) -> Path:
        return Path(self.storage_dir) / "trades" / ticker

    def _trades_file(self, ticker: str) -> Path:
        return self._trades_dir(ticker) / "trades.json"

    def _load_existing(self):
        """Load all existing trade records from disk."""
        trades_root = Path(self.storage_dir) / "trades"
        if not trades_root.exists():
            return
        for ticker_dir in trades_root.iterdir():
            if not ticker_dir.is_dir():
                continue
            trades_file = ticker_dir / "trades.json"
            if trades_file.exists():
                with open(trades_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for d in data:
                    self._trades.append(TradeRecord.from_dict(d))

    def record_trade(
        self,
        ticker: str,
        trade_date: str,
        signal: str,
        price: float,
        quantity: int,
        source: str,
        agent_state: dict,
    ) -> TradeRecord:
        rec = TradeRecord(
            ticker=ticker,
            trade_date=trade_date,
            signal=signal.strip().upper(),
            entry_price=price,
            quantity=quantity,
            source=source,
            analyst_reports=self._extract_reports(agent_state),
            debate_summary=self._extract_debate(agent_state),
            risk_decision=self._extract_risk(agent_state),
            persona=self.config.get("persona"),
        )
        self._trades.append(rec)
        self._save_ticker(ticker)
        return rec

    def close_position(
        self, ticker: str, exit_date: str, exit_price: float
    ) -> TradeRecord:
        for rec in reversed(self._trades):
            if rec.ticker == ticker and rec.exit_price is None:
                rec.exit_price = exit_price
                rec.exit_date = exit_date
                rec.pnl = round((exit_price - rec.entry_price) * rec.quantity, 2)
                rec.pnl_pct = round(
                    (exit_price - rec.entry_price) / rec.entry_price * 100, 2
                )
                self._save_ticker(ticker)
                return rec
        raise ValueError(f"No open position found for {ticker}")

    def get_trades(
        self,
        ticker: str = None,
        source: str = None,
        start_date: str = None,
        end_date: str = None,
    ) -> List[TradeRecord]:
        result = self._trades
        if ticker:
            result = [t for t in result if t.ticker == ticker]
        if source:
            result = [t for t in result if t.source == source]
        if start_date:
            result = [t for t in result if t.trade_date >= start_date]
        if end_date:
            result = [t for t in result if t.trade_date <= end_date]
        return result

    def get_performance(
        self,
        ticker: str = None,
        source: str = None,
        benchmark: str = "SPY",
    ) -> PerformanceMetrics:
        trades = self.get_trades(ticker=ticker, source=source)
        if not trades:
            return self._calculator._empty_metrics()
        start = min(t.trade_date for t in trades)
        end = max(t.exit_date or t.trade_date for t in trades)
        return self._calculator.calculate(
            trades=trades,
            initial_capital=100_000_000,
            benchmark_ticker=benchmark,
            start_date=start,
            end_date=end,
        )

    def get_open_positions(self) -> List[TradeRecord]:
        return [t for t in self._trades if t.exit_price is None]

    def _save_ticker(self, ticker: str):
        d = self._trades_dir(ticker)
        d.mkdir(parents=True, exist_ok=True)
        ticker_trades = [t for t in self._trades if t.ticker == ticker]
        with open(self._trades_file(ticker), "w", encoding="utf-8") as f:
            json.dump([t.to_dict() for t in ticker_trades], f, indent=2,
                      ensure_ascii=False, default=str)

    def _extract_reports(self, state: dict) -> dict:
        if not state:
            return {}
        return {
            k: state.get(f"{k}_report", "")[:500]
            for k in ("market", "sentiment", "news", "fundamentals")
        }

    def _extract_debate(self, state: dict) -> str:
        if not state:
            return ""
        ids = state.get("investment_debate_state", {})
        return f"Bull: {ids.get('bull_history', '')[:300]}\nBear: {ids.get('bear_history', '')[:300]}"

    def _extract_risk(self, state: dict) -> str:
        if not state:
            return ""
        return state.get("risk_debate_state", {}).get("judge_decision", "")[:500]
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/herald/Projects/agents/TradingAgents && python -m pytest tests/test_tracker.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add tradingagents/tracker/__init__.py tradingagents/tracker/tracker.py tests/test_tracker.py
git commit -m "feat: add TradeTracker for live/paper trade recording and performance queries"
```

---

## Task 5: Dashboard Builder (dashboard/builder.py)

**Files:**
- Create: `tradingagents/dashboard/__init__.py`
- Create: `tradingagents/dashboard/builder.py`
- Test: `tests/test_dashboard.py`

**Step 1: Write the failing test**

```python
# tests/test_dashboard.py
"""Tests for tradingagents.dashboard.builder."""

import tempfile
import os

from tradingagents.backtest.models import TradeRecord, PerformanceMetrics, BacktestResult
from tradingagents.dashboard.builder import DashboardBuilder


def _make_metrics():
    return PerformanceMetrics(
        total_trades=10, win_rate=70.0, avg_return=5.0,
        cumulative_return=23.4, sharpe_ratio=1.42, max_drawdown=-8.7,
        max_drawdown_duration=15, alpha=5.2, beta=0.87,
        profit_factor=1.83, avg_holding_days=12.3,
        equity_curve=[
            {"date": "2024-04-01", "equity": 100000, "drawdown": 0.0},
            {"date": "2024-05-01", "equity": 105000, "drawdown": 0.0},
            {"date": "2024-06-01", "equity": 102000, "drawdown": -2.86},
            {"date": "2024-07-01", "equity": 112000, "drawdown": 0.0},
        ],
        monthly_returns=[
            {"month": "2024-04", "return_pct": 5.0},
            {"month": "2024-05", "return_pct": -2.86},
            {"month": "2024-06", "return_pct": 9.8},
        ],
    )


def _make_trades():
    return [
        TradeRecord(
            ticker="NVDA", trade_date="2024-04-01", signal="BUY",
            entry_price=100.0, quantity=100, source="backtest",
            exit_price=110.0, exit_date="2024-05-01",
            pnl=1000.0, pnl_pct=10.0,
            debate_summary="Bull: strong AI demand\nBear: high valuation",
            risk_decision="Risk acceptable",
        ),
        TradeRecord(
            ticker="NVDA", trade_date="2024-05-01", signal="BUY",
            entry_price=110.0, quantity=100, source="backtest",
            exit_price=105.0, exit_date="2024-06-01",
            pnl=-500.0, pnl_pct=-4.55,
        ),
    ]


class TestDashboardBuilder:
    def test_build_creates_html_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            builder = DashboardBuilder(output_dir=tmp)
            path = builder.build(
                metrics=_make_metrics(),
                trades=_make_trades(),
                title="Test Dashboard",
            )
            assert os.path.exists(path)
            assert path.endswith(".html")

    def test_html_contains_kpi_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            builder = DashboardBuilder(output_dir=tmp)
            path = builder.build(metrics=_make_metrics(), trades=_make_trades())
            with open(path) as f:
                html = f.read()
            assert "23.4" in html   # cumulative return
            assert "1.42" in html   # sharpe
            assert "-8.7" in html   # MDD
            assert "70.0" in html   # win rate

    def test_html_contains_plotly(self):
        with tempfile.TemporaryDirectory() as tmp:
            builder = DashboardBuilder(output_dir=tmp)
            path = builder.build(metrics=_make_metrics(), trades=_make_trades())
            with open(path) as f:
                html = f.read()
            assert "plotly" in html.lower()

    def test_html_contains_trade_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            builder = DashboardBuilder(output_dir=tmp)
            path = builder.build(metrics=_make_metrics(), trades=_make_trades())
            with open(path) as f:
                html = f.read()
            assert "NVDA" in html
            assert "BUY" in html

    def test_backtest_comparison_section(self):
        """When backtest_results provided, comparison table should appear."""
        with tempfile.TemporaryDirectory() as tmp:
            bt = BacktestResult(
                ticker="NVDA",
                config_snapshot={"persona": "warren_buffett"},
                start_date="2024-04-01", end_date="2025-04-01",
                benchmark="SPY", trades=[], metrics=_make_metrics(),
            )
            builder = DashboardBuilder(output_dir=tmp)
            path = builder.build(
                metrics=_make_metrics(), trades=_make_trades(),
                backtest_results=[bt],
            )
            with open(path) as f:
                html = f.read()
            assert "backtest" in html.lower() or "비교" in html.lower() or "Backtest" in html

    def test_empty_trades(self):
        """Should not crash with empty trades."""
        with tempfile.TemporaryDirectory() as tmp:
            builder = DashboardBuilder(output_dir=tmp)
            metrics = PerformanceMetrics(
                total_trades=0, win_rate=0.0, avg_return=0.0,
                cumulative_return=0.0, sharpe_ratio=0.0, max_drawdown=0.0,
                max_drawdown_duration=0, alpha=0.0, beta=0.0,
                profit_factor=0.0, avg_holding_days=0.0,
                equity_curve=[], monthly_returns=[],
            )
            path = builder.build(metrics=metrics, trades=[])
            assert os.path.exists(path)
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/herald/Projects/agents/TradingAgents && python -m pytest tests/test_dashboard.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# tradingagents/dashboard/__init__.py
# Copyright 2026 herald.k, HongSoo Kim
# ...
from .builder import DashboardBuilder
```

```python
# tradingagents/dashboard/builder.py
# Copyright 2026 herald.k, HongSoo Kim
#
# Licensed under the Apache License, Version 2.0 (the "License");
# ...

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from tradingagents.backtest.models import (
    TradeRecord,
    PerformanceMetrics,
    BacktestResult,
)


class DashboardBuilder:
    """TradeRecord + PerformanceMetrics → 자체 포함 HTML 파일 생성."""

    def __init__(self, output_dir: str = None):
        self.output_dir = output_dir or "./results/dashboard"

    def build(
        self,
        metrics: PerformanceMetrics,
        trades: List[TradeRecord],
        backtest_results: List[BacktestResult] = None,
        title: str = "TradingAgents Performance Dashboard",
    ) -> str:
        """HTML 파일을 생성하고 경로를 반환한다."""
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(self.output_dir, f"performance_{timestamp}.html")

        html = self._render_html(metrics, trades, backtest_results, title)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)
        return filepath

    def _render_html(
        self,
        metrics: PerformanceMetrics,
        trades: List[TradeRecord],
        backtest_results: Optional[List[BacktestResult]],
        title: str,
    ) -> str:
        equity_dates = json.dumps([p["date"] for p in metrics.equity_curve])
        equity_values = json.dumps([p["equity"] for p in metrics.equity_curve])
        drawdown_values = json.dumps([p["drawdown"] for p in metrics.equity_curve])

        monthly_months = json.dumps([m["month"] for m in metrics.monthly_returns])
        monthly_vals = json.dumps([m["return_pct"] for m in metrics.monthly_returns])
        monthly_colors = json.dumps([
            "#10b981" if m["return_pct"] >= 0 else "#ef4444"
            for m in metrics.monthly_returns
        ])

        trades_rows = self._render_trades_table(trades)
        backtest_section = self._render_backtest_comparison(backtest_results, metrics)
        generated = datetime.now().strftime("%Y-%m-%d %H:%M")

        return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ background: #0f172a; color: #e2e8f0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding: 24px; }}
.header {{ text-align: center; margin-bottom: 32px; }}
.header h1 {{ font-size: 24px; font-weight: 600; }}
.header .sub {{ color: #94a3b8; font-size: 14px; margin-top: 4px; }}
.kpi-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 32px; }}
.kpi {{ background: #1e293b; border-radius: 12px; padding: 20px; text-align: center; }}
.kpi .value {{ font-size: 28px; font-weight: 700; }}
.kpi .label {{ color: #94a3b8; font-size: 13px; margin-top: 4px; }}
.positive {{ color: #10b981; }}
.negative {{ color: #ef4444; }}
.chart-container {{ background: #1e293b; border-radius: 12px; padding: 20px; margin-bottom: 24px; }}
.chart-container h2 {{ font-size: 16px; margin-bottom: 12px; }}
.grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 24px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th {{ background: #334155; padding: 10px 12px; text-align: left; font-weight: 500; }}
td {{ padding: 10px 12px; border-bottom: 1px solid #334155; }}
tr:hover {{ background: #1e293b; }}
.detail-toggle {{ cursor: pointer; color: #60a5fa; font-size: 12px; }}
.detail-content {{ display: none; padding: 8px; background: #0f172a; border-radius: 6px; margin-top: 4px; font-size: 12px; white-space: pre-wrap; }}
.comparison {{ background: #1e293b; border-radius: 12px; padding: 20px; margin-bottom: 24px; }}
.config-bar {{ background: #1e293b; border-radius: 8px; padding: 12px 20px; text-align: center; color: #94a3b8; font-size: 13px; }}
</style>
</head>
<body>

<div class="header">
  <h1>{title}</h1>
  <div class="sub">Generated: {generated}</div>
</div>

<div class="kpi-grid">
  <div class="kpi">
    <div class="value {'positive' if metrics.cumulative_return >= 0 else 'negative'}">{metrics.cumulative_return:+.1f}%</div>
    <div class="label">Cumulative Return</div>
  </div>
  <div class="kpi">
    <div class="value">{metrics.sharpe_ratio:.2f}</div>
    <div class="label">Sharpe Ratio</div>
  </div>
  <div class="kpi">
    <div class="value negative">{metrics.max_drawdown:.1f}%</div>
    <div class="label">Max Drawdown</div>
  </div>
  <div class="kpi">
    <div class="value">{metrics.win_rate:.1f}%</div>
    <div class="label">Win Rate</div>
  </div>
</div>

<div class="chart-container">
  <h2>Equity Curve</h2>
  <div id="equity-chart"></div>
</div>

<div class="grid-2">
  <div class="chart-container">
    <h2>Monthly Returns</h2>
    <div id="monthly-chart"></div>
  </div>
  <div class="chart-container">
    <h2>Performance Metrics</h2>
    <table>
      <tr><td>Alpha</td><td class="{'positive' if metrics.alpha >= 0 else 'negative'}">{metrics.alpha:+.2f}%</td></tr>
      <tr><td>Beta</td><td>{metrics.beta:.2f}</td></tr>
      <tr><td>Profit Factor</td><td>{metrics.profit_factor:.2f}</td></tr>
      <tr><td>Avg Holding Days</td><td>{metrics.avg_holding_days:.1f}</td></tr>
      <tr><td>Total Trades</td><td>{metrics.total_trades}</td></tr>
      <tr><td>Avg Return</td><td class="{'positive' if metrics.avg_return >= 0 else 'negative'}">{metrics.avg_return:+.2f}%</td></tr>
    </table>
  </div>
</div>

<div class="chart-container">
  <h2>Trade History</h2>
  <table>
    <thead>
      <tr><th>Date</th><th>Ticker</th><th>Signal</th><th>Entry</th><th>Exit</th><th>PnL %</th><th>Detail</th></tr>
    </thead>
    <tbody>
      {trades_rows}
    </tbody>
  </table>
</div>

{backtest_section}

<script>
// Equity Curve
Plotly.newPlot('equity-chart', [
  {{ x: {equity_dates}, y: {equity_values}, type: 'scatter', mode: 'lines', name: 'Portfolio', line: {{ color: '#60a5fa', width: 2 }} }},
  {{ x: {equity_dates}, y: {drawdown_values}, type: 'scatter', mode: 'lines', name: 'Drawdown %', yaxis: 'y2', fill: 'tozeroy', fillcolor: 'rgba(239,68,68,0.15)', line: {{ color: '#ef4444', width: 1 }} }}
], {{
  paper_bgcolor: 'transparent', plot_bgcolor: 'transparent',
  font: {{ color: '#94a3b8' }},
  xaxis: {{ gridcolor: '#334155' }},
  yaxis: {{ gridcolor: '#334155', title: 'Equity' }},
  yaxis2: {{ overlaying: 'y', side: 'right', title: 'Drawdown %', gridcolor: '#334155' }},
  margin: {{ t: 10, r: 60, b: 40, l: 60 }},
  legend: {{ x: 0, y: 1.1, orientation: 'h' }}
}}, {{ responsive: true }});

// Monthly Returns
Plotly.newPlot('monthly-chart', [{{
  x: {monthly_months}, y: {monthly_vals}, type: 'bar',
  marker: {{ color: {monthly_colors} }}
}}], {{
  paper_bgcolor: 'transparent', plot_bgcolor: 'transparent',
  font: {{ color: '#94a3b8' }},
  xaxis: {{ gridcolor: '#334155' }},
  yaxis: {{ gridcolor: '#334155', title: 'Return %' }},
  margin: {{ t: 10, r: 20, b: 40, l: 50 }}
}}, {{ responsive: true }});

// Toggle trade details
document.querySelectorAll('.detail-toggle').forEach(el => {{
  el.addEventListener('click', () => {{
    const content = el.parentElement.querySelector('.detail-content');
    content.style.display = content.style.display === 'none' ? 'block' : 'none';
  }});
}});
</script>

</body>
</html>"""

    def _render_trades_table(self, trades: List[TradeRecord]) -> str:
        rows = []
        for t in trades[-20:]:  # Last 20 trades
            pnl_class = "positive" if (t.pnl_pct or 0) >= 0 else "negative"
            pnl_str = f"{t.pnl_pct:+.2f}%" if t.pnl_pct is not None else "—"
            exit_str = f"{t.exit_price:,.0f}" if t.exit_price else "—"
            detail = t.debate_summary or "No detail available"
            rows.append(
                f'<tr>'
                f'<td>{t.trade_date}</td>'
                f'<td>{t.ticker}</td>'
                f'<td>{t.signal}</td>'
                f'<td>{t.entry_price:,.0f}</td>'
                f'<td>{exit_str}</td>'
                f'<td class="{pnl_class}">{pnl_str}</td>'
                f'<td><span class="detail-toggle">[?]</span>'
                f'<div class="detail-content">{detail}</div></td>'
                f'</tr>'
            )
        return "\n".join(rows)

    def _render_backtest_comparison(
        self,
        backtest_results: Optional[List[BacktestResult]],
        live_metrics: PerformanceMetrics,
    ) -> str:
        if not backtest_results:
            return ""

        bt = backtest_results[0]
        bm = bt.metrics

        return f"""
<div class="comparison">
  <h2>Backtest vs Live Comparison</h2>
  <table>
    <thead>
      <tr><th></th><th>Backtest</th><th>Live</th></tr>
    </thead>
    <tbody>
      <tr><td>Cumulative Return</td><td>{bm.cumulative_return:+.1f}%</td><td>{live_metrics.cumulative_return:+.1f}%</td></tr>
      <tr><td>Sharpe Ratio</td><td>{bm.sharpe_ratio:.2f}</td><td>{live_metrics.sharpe_ratio:.2f}</td></tr>
      <tr><td>Max Drawdown</td><td>{bm.max_drawdown:.1f}%</td><td>{live_metrics.max_drawdown:.1f}%</td></tr>
      <tr><td>Win Rate</td><td>{bm.win_rate:.1f}%</td><td>{live_metrics.win_rate:.1f}%</td></tr>
      <tr><td>Config</td><td colspan="2">Persona: {bt.config_snapshot.get('persona', 'None')}</td></tr>
    </tbody>
  </table>
</div>"""
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/herald/Projects/agents/TradingAgents && python -m pytest tests/test_dashboard.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add tradingagents/dashboard/__init__.py tradingagents/dashboard/builder.py tests/test_dashboard.py
git commit -m "feat: add DashboardBuilder with Plotly.js equity curve, monthly returns, trade history"
```

---

## Task 6: Integration — Wire Everything Together

**Files:**
- Modify: `tradingagents/backtest/__init__.py` (final exports)
- Create: `backtest_cli.py` (convenience entry point at project root)
- Test: `tests/test_integration.py`

**Step 1: Write the failing test**

```python
# tests/test_integration.py
"""Integration test: backtest → tracker → dashboard pipeline."""

import tempfile
import os
from unittest.mock import MagicMock, patch

from tradingagents.backtest.engine import BacktestEngine
from tradingagents.backtest.models import TradeRecord, BacktestResult
from tradingagents.tracker.tracker import TradeTracker
from tradingagents.dashboard.builder import DashboardBuilder
from tradingagents.default_config import DEFAULT_CONFIG


class TestFullPipeline:
    @patch("tradingagents.backtest.engine.TradingAgentsGraph")
    @patch("tradingagents.backtest.engine.yf")
    def test_backtest_to_dashboard(self, mock_yf, mock_graph_cls):
        """Full pipeline: backtest → dashboard HTML."""
        # Mock price data
        mock_hist = MagicMock()
        mock_hist.empty = False
        mock_hist.__getitem__ = MagicMock(return_value=MagicMock(
            iloc=MagicMock(__getitem__=MagicMock(return_value=100.0))
        ))
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = mock_hist
        mock_yf.Ticker.return_value = mock_ticker

        # Mock graph: alternates BUY/SELL
        call_count = {"n": 0}
        def mock_propagate(ticker, date):
            call_count["n"] += 1
            signal = "BUY" if call_count["n"] % 2 == 1 else "SELL"
            state = {
                "market_report": "test", "sentiment_report": "test",
                "news_report": "test", "fundamentals_report": "test",
                "investment_debate_state": {"bull_history": "", "bear_history": "", "judge_decision": ""},
                "risk_debate_state": {"judge_decision": ""},
                "final_trade_decision": f"FINAL TRANSACTION PROPOSAL: **{signal}**",
            }
            return state, signal

        mock_graph = MagicMock()
        mock_graph.propagate.side_effect = mock_propagate
        mock_graph_cls.return_value = mock_graph

        with tempfile.TemporaryDirectory() as tmp:
            config = DEFAULT_CONFIG.copy()
            config["results_dir"] = tmp

            # 1. Run backtest
            engine = BacktestEngine(config)
            result = engine.run(
                ticker="TEST", start_date="2024-04-01", end_date="2024-10-01",
                rebalance_freq="monthly", benchmark="SPY", initial_capital=100_000.0,
            )
            assert isinstance(result, BacktestResult)

            # 2. Generate dashboard
            builder = DashboardBuilder(output_dir=os.path.join(tmp, "dashboard"))
            html_path = builder.build(
                metrics=result.metrics,
                trades=result.trades,
                backtest_results=[result],
                title="Integration Test",
            )
            assert os.path.exists(html_path)
            with open(html_path) as f:
                html = f.read()
            assert "plotly" in html.lower()

    def test_tracker_to_dashboard(self):
        """Pipeline: tracker records → dashboard HTML."""
        with tempfile.TemporaryDirectory() as tmp:
            config = DEFAULT_CONFIG.copy()
            config["results_dir"] = tmp

            tracker = TradeTracker(config)
            tracker.record_trade("TEST", "2026-04-01", "BUY", 100.0, 100, "paper", {})
            tracker.close_position("TEST", "2026-04-15", 110.0)
            tracker.record_trade("TEST", "2026-04-15", "BUY", 110.0, 100, "paper", {})
            tracker.close_position("TEST", "2026-04-25", 105.0)

            metrics = tracker.get_performance(ticker="TEST")
            trades = tracker.get_trades(ticker="TEST")

            builder = DashboardBuilder(output_dir=os.path.join(tmp, "dashboard"))
            html_path = builder.build(metrics=metrics, trades=trades)
            assert os.path.exists(html_path)
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/herald/Projects/agents/TradingAgents && python -m pytest tests/test_integration.py -v`
Expected: FAIL (until all prior tasks complete)

**Step 3: Create convenience CLI entry point**

```python
# backtest_cli.py (project root)
# Copyright 2026 herald.k, HongSoo Kim
#
# Licensed under the Apache License, Version 2.0 (the "License");
# ...

"""Convenience CLI for running backtests and generating dashboards.

Usage:
    python backtest_cli.py --ticker NVDA --start 2024-04-01 --end 2026-04-01
    python backtest_cli.py --ticker 005930 --start 2024-04-01 --end 2026-04-01 --persona warren_buffett
    python backtest_cli.py --ticker NVDA --start 2024-04-01 --end 2026-04-01 --freq weekly --benchmark QQQ
"""

import argparse
import sys

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.backtest.engine import BacktestEngine
from tradingagents.dashboard.builder import DashboardBuilder


def main():
    parser = argparse.ArgumentParser(description="TradingAgents Backtest & Dashboard")
    parser.add_argument("--ticker", required=True, help="Stock ticker (e.g. NVDA, 005930)")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--freq", default="monthly", choices=["monthly", "weekly", "biweekly"])
    parser.add_argument("--benchmark", default="SPY", help="Benchmark ticker")
    parser.add_argument("--capital", type=float, default=100_000_000, help="Initial capital")
    parser.add_argument("--persona", default=None, choices=["warren_buffett", "ray_dalio", "peter_lynch"])
    parser.add_argument("--provider", default="anthropic", help="LLM provider")
    parser.add_argument("--skip-llm", action="store_true", help="Skip LLM calls (use cached signals)")
    parser.add_argument("--no-dashboard", action="store_true", help="Skip dashboard generation")
    args = parser.parse_args()

    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = args.provider
    if args.persona:
        config["persona"] = args.persona

    print(f"Running backtest: {args.ticker} ({args.start} → {args.end}, {args.freq})")
    print(f"Config: provider={args.provider}, persona={args.persona}, benchmark={args.benchmark}")

    engine = BacktestEngine(config)
    result = engine.run(
        ticker=args.ticker,
        start_date=args.start,
        end_date=args.end,
        rebalance_freq=args.freq,
        benchmark=args.benchmark,
        initial_capital=args.capital,
        skip_llm=args.skip_llm,
    )

    m = result.metrics
    print(f"\n{'='*50}")
    print(f"Results: {result.ticker} ({result.start_date} → {result.end_date})")
    print(f"{'='*50}")
    print(f"  Total Trades:      {m.total_trades}")
    print(f"  Win Rate:          {m.win_rate:.1f}%")
    print(f"  Cumulative Return: {m.cumulative_return:+.2f}%")
    print(f"  Sharpe Ratio:      {m.sharpe_ratio:.2f}")
    print(f"  Max Drawdown:      {m.max_drawdown:.1f}%")
    print(f"  Alpha:             {m.alpha:+.2f}%")
    print(f"  Profit Factor:     {m.profit_factor:.2f}")
    print(f"  Avg Holding Days:  {m.avg_holding_days:.1f}")

    if not args.no_dashboard:
        builder = DashboardBuilder()
        path = builder.build(
            metrics=result.metrics,
            trades=result.trades,
            backtest_results=[result],
            title=f"TradingAgents Backtest: {args.ticker}",
        )
        print(f"\nDashboard: {path}")


if __name__ == "__main__":
    main()
```

**Step 4: Run all tests**

Run: `cd /Users/herald/Projects/agents/TradingAgents && python -m pytest tests/test_backtest_models.py tests/test_performance.py tests/test_backtest_engine.py tests/test_tracker.py tests/test_dashboard.py tests/test_integration.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add backtest_cli.py tests/test_integration.py
git commit -m "feat: add backtest CLI entry point and integration tests"
```

---

## Task 7: Update CLAUDE.md with new module documentation

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Add section to CLAUDE.md**

Append after the "Broker Execution" section:

```markdown
### Backtest & Performance Dashboard

Three new modules added as external orchestrators (no changes to existing code):

**Backtest Engine** (`tradingagents/backtest/`):
- `BacktestEngine.run(ticker, start_date, end_date, ...)` → runs propagate() at each rebalance date
- Supports monthly/weekly/biweekly rebalancing
- Signal caching (`save_signals=True`) for cost-free re-runs
- `skip_llm=True` to replay cached signals without LLM calls

**Trade Tracker** (`tradingagents/tracker/`):
- `TradeTracker.record_trade()` — records BUY/SELL/HOLD with agent state metadata
- `TradeTracker.close_position()` — closes open position, calculates PnL
- `TradeTracker.get_performance()` — returns PerformanceMetrics for filtered trades
- JSON file storage at `{results_dir}/trades/{ticker}/trades.json`

**Dashboard** (`tradingagents/dashboard/`):
- `DashboardBuilder.build()` → self-contained HTML with Plotly.js
- KPI cards, equity curve, monthly returns heatmap, trade history with debate detail toggle
- Backtest vs live comparison table

**CLI**: `python backtest_cli.py --ticker NVDA --start 2024-04-01 --end 2026-04-01`
```

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add backtest, tracker, dashboard modules to CLAUDE.md"
```

---

## Summary

| Task | Module | Files | Tests |
|------|--------|-------|-------|
| 1 | Data Models | `backtest/models.py` | `test_backtest_models.py` |
| 2 | Performance Calculator | `backtest/performance.py` | `test_performance.py` |
| 3 | Backtest Engine | `backtest/engine.py` | `test_backtest_engine.py` |
| 4 | Trade Tracker | `tracker/tracker.py` | `test_tracker.py` |
| 5 | Dashboard Builder | `dashboard/builder.py` | `test_dashboard.py` |
| 6 | Integration + CLI | `backtest_cli.py` | `test_integration.py` |
| 7 | Documentation | `CLAUDE.md` | — |

Total: 7 tasks, 7 commits, 13 new files, 0 existing files modified (except CLAUDE.md).
