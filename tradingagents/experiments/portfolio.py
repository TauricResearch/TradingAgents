from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import yfinance as yf


_RATING_TILTS = {
    "Buy": 1.5,
    "Overweight": 1.2,
    "Hold": 1.0,
    "Underweight": 0.6,
    "Sell": 0.2,
}


def allocate_risk_parity(
    returns: pd.DataFrame, ratings: dict[str, str]
) -> dict[str, float]:
    volatility = returns.std().replace(0, float("nan"))
    scores = {}
    for ticker in returns.columns:
        inverse_volatility = 1.0 / volatility.get(ticker, float("nan"))
        if pd.isna(inverse_volatility):
            inverse_volatility = 1.0
        scores[ticker] = inverse_volatility * _RATING_TILTS.get(ratings.get(ticker, "Hold"), 1.0)
    total = sum(scores.values())
    return {ticker: score / total for ticker, score in scores.items()} if total else {}


@dataclass
class PortfolioAnalysis:
    trade_date: str
    ratings: dict[str, str]
    weights: dict[str, float]
    correlations: dict[str, dict[str, float]]
    decisions: dict[str, str]


class PortfolioCoordinator:
    def __init__(self, graph: Any, lookback_days: int = 90):
        self.graph = graph
        self.lookback_days = lookback_days

    def analyze(self, tickers: list[str], trade_date: str) -> PortfolioAnalysis:
        end = pd.Timestamp(trade_date)
        start = end - pd.Timedelta(days=self.lookback_days)
        prices = yf.download(
            tickers, start=start.strftime("%Y-%m-%d"), end=trade_date,
            auto_adjust=True, progress=False,
        )["Close"]
        if isinstance(prices, pd.Series):
            prices = prices.to_frame(name=tickers[0])
        returns = prices.pct_change().dropna(how="all")
        ratings, decisions = {}, {}
        for ticker in tickers:
            state, rating = self.graph.propagate(ticker, trade_date)
            ratings[ticker] = rating
            decisions[ticker] = state["final_trade_decision"]
        return PortfolioAnalysis(
            trade_date=trade_date,
            ratings=ratings,
            weights=allocate_risk_parity(returns[tickers], ratings),
            correlations=returns[tickers].corr().fillna(0.0).to_dict(),
            decisions=decisions,
        )
