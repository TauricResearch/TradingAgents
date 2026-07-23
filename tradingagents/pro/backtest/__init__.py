"""Pro backtesting engine (Phase 7): same pipeline as live, replayed data."""

from tradingagents.pro.backtest.broker import ClosedTrade, PendingOrder, SimBroker
from tradingagents.pro.backtest.costs import CommissionModel, LiquidityModel, SlippageModel
from tradingagents.pro.backtest.data import BarReplay, HistoricalCorpus
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
from tradingagents.pro.backtest.optimize import (
    OptResult,
    Trial,
    engine_backtest_fn,
    objective_choices,
    run_optimization,
)
from tradingagents.pro.backtest.registry import (
    StrategyInfo,
    build_strategy,
    is_registered,
    list_strategies,
    register,
)

# import last: registers built-in strategies (rules_v1) via @register on import
from tradingagents.pro.backtest.strategies import PipelineStrategy  # noqa: E402
from tradingagents.pro.backtest.strategy import (
    AccountView,
    BracketIntent,
    Fill,
    OrderIntent,
    Param,
    ParamSpace,
    PositionView,
    RegimeView,
    Strategy,
    StrategyContext,
)
from tradingagents.pro.backtest.validation import (
    deflated_sharpe_ratio,
    probability_of_backtest_overfitting,
)
from tradingagents.pro.backtest.walkforward import (
    WalkForwardResult,
    Window,
    run_walk_forward,
    walk_forward_windows,
)

__all__ = [
    "ClosedTrade",
    "PendingOrder",
    "SimBroker",
    "CommissionModel",
    "LiquidityModel",
    "SlippageModel",
    "BarReplay",
    "HistoricalCorpus",
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
    "AccountView",
    "BracketIntent",
    "Fill",
    "OrderIntent",
    "Param",
    "ParamSpace",
    "PositionView",
    "RegimeView",
    "Strategy",
    "StrategyContext",
    "StrategyInfo",
    "PipelineStrategy",
    "OptResult",
    "Trial",
    "deflated_sharpe_ratio",
    "engine_backtest_fn",
    "objective_choices",
    "probability_of_backtest_overfitting",
    "run_optimization",
    "build_strategy",
    "is_registered",
    "list_strategies",
    "register",
    "WalkForwardResult",
    "Window",
    "run_walk_forward",
    "walk_forward_windows",
]
