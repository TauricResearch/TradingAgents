"""Pro backtesting engine (Phase 7): same pipeline as live, replayed data."""

from tradingagents.pro.backtest.broker import ClosedTrade, SimBroker
from tradingagents.pro.backtest.costs import CommissionModel, LiquidityModel, SlippageModel
from tradingagents.pro.backtest.data import BarReplay
from tradingagents.pro.backtest.engine import BacktestEngine, BacktestResult
from tradingagents.pro.backtest.llm_cache import CacheMiss, CachingLLM
from tradingagents.pro.backtest.metrics import (
    PerformanceReport,
    equity_returns,
    max_drawdown,
    performance_report,
    sharpe_ratio,
    sortino_ratio,
)
from tradingagents.pro.backtest.montecarlo import (
    MonteCarloSummary,
    bootstrap_paths,
    monte_carlo_summary,
)
from tradingagents.pro.backtest.walkforward import (
    WalkForwardResult,
    Window,
    run_walk_forward,
    walk_forward_windows,
)

__all__ = [
    "ClosedTrade",
    "SimBroker",
    "CommissionModel",
    "LiquidityModel",
    "SlippageModel",
    "BarReplay",
    "BacktestEngine",
    "BacktestResult",
    "CacheMiss",
    "CachingLLM",
    "PerformanceReport",
    "equity_returns",
    "max_drawdown",
    "performance_report",
    "sharpe_ratio",
    "sortino_ratio",
    "MonteCarloSummary",
    "bootstrap_paths",
    "monte_carlo_summary",
    "WalkForwardResult",
    "Window",
    "run_walk_forward",
    "walk_forward_windows",
]
