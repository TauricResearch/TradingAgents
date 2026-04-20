"""Quantitative strategy signals for TradingAgents analysts.

Each strategy module implements compute() returning a StrategySignal dict
that gets injected into the relevant analyst's system prompt.

Reference:
    Zura Kakushadze and Juan Andrés Serur,
    "151 Trading Strategies",
    Palgrave Macmillan, 2018.
    SSRN: https://ssrn.com/abstract=3247865
    DOI: 10.1007/978-3-030-02792-6
"""

from tradingagents.strategies.base import StrategySignal, BaseStrategy
from tradingagents.strategies.registry import (
    compute_signals,
    signals_by_analyst,
    format_signals_for_prompt,
    format_signals_for_role,
    get_strategies,
)

__all__ = [
    "StrategySignal",
    "BaseStrategy",
    "compute_signals",
    "signals_by_analyst",
    "format_signals_for_prompt",
    "format_signals_for_role",
    "get_strategies",
]
