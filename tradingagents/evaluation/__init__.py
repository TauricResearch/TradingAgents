"""Evaluation tooling: reproducible backtesting for the TradingAgents graph."""

from .backtest import generate_dates, run_backtest, summarize

__all__ = ["generate_dates", "run_backtest", "summarize"]
