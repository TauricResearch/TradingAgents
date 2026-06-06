"""Deterministic backtester (the continuous threshold validator).

Per the wiki, backtesting is a deterministic Python process over the internal
historical DB — *no LLM in the loop* — used to validate the thresholds the rest
of the system is tuned on (R:R, k_stop/k_tp, ATR period, sizing). It reuses our
own indicators + risk engine, so what it validates is exactly what runs live.
VectorBT can later replace the engine for speed; the contract stays.
"""

from .engine import BacktestResult, backtest, run_backtest

__all__ = ["BacktestResult", "backtest", "run_backtest"]
