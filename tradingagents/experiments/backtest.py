from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import backtrader as bt
import pandas as pd
import yfinance as yf


_TARGETS = {
    "Buy": 1.0,
    "Overweight": 0.75,
    "Hold": 0.5,
    "Underweight": 0.25,
    "Sell": 0.0,
}


def rating_to_target(rating: str) -> float:
    return _TARGETS.get(rating, 0.5)


def calculate_metrics(values: list[float]) -> dict[str, float]:
    series = pd.Series(values, dtype=float)
    returns = series.pct_change().dropna()
    drawdown = series / series.cummax() - 1.0
    sharpe = 0.0
    if len(returns) > 1 and returns.std() > 0:
        sharpe = math.sqrt(252) * float(returns.mean() / returns.std())
    return {
        "total_return": float(series.iloc[-1] / series.iloc[0] - 1.0),
        "sharpe_ratio": sharpe,
        "max_drawdown": float(drawdown.min()),
    }


@dataclass
class BacktestResult:
    ticker: str
    start_date: str
    end_date: str
    metrics: dict[str, float]
    actions: list[dict]


class _AgentStrategy(bt.Strategy):
    params = (("runner", None), ("ticker", ""), ("rebalance_days", 5))

    def __init__(self):
        self.actions = []
        self.values = []
        self._last_rebalance = None

    def next(self):
        self.values.append(float(self.broker.getvalue()))
        current = self.data.datetime.date(0)
        if self._last_rebalance and (current - self._last_rebalance).days < self.p.rebalance_days:
            return
        self._last_rebalance = current
        _, rating = self.p.runner.graph.propagate(self.p.ticker, current.isoformat())
        target = rating_to_target(rating)
        self.order_target_percent(target=target)
        self.actions.append({"date": current.isoformat(), "rating": rating, "target": target})


class AgentBacktestRunner:
    def __init__(self, graph: Any, initial_cash: float = 100_000.0, rebalance_days: int = 5):
        self.graph = graph
        self.initial_cash = initial_cash
        self.rebalance_days = rebalance_days

    def run(self, ticker: str, start_date: str, end_date: str) -> BacktestResult:
        data = yf.download(ticker, start=start_date, end=end_date, auto_adjust=True, progress=False)
        if data.empty:
            raise ValueError(f"No market data available for {ticker}")
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        cerebro = bt.Cerebro()
        cerebro.broker.setcash(self.initial_cash)
        cerebro.adddata(bt.feeds.PandasData(dataname=data))
        cerebro.addstrategy(
            _AgentStrategy, runner=self, ticker=ticker, rebalance_days=self.rebalance_days
        )
        strategy = cerebro.run()[0]
        values = [self.initial_cash, *strategy.values, float(cerebro.broker.getvalue())]
        return BacktestResult(ticker, start_date, end_date, calculate_metrics(values), strategy.actions)
