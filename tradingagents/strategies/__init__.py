"""Quantitative strategy signals framework.

Based on:
    Zura Kakushadze and Juan Andrés Serur,
    "151 Trading Strategies",
    Palgrave Macmillan, 2018.
    SSRN: https://ssrn.com/abstract=3247865
    DOI: 10.1007/978-3-030-02792-6
"""

from .base import BaseStrategy, Role, StrategySignal
from .registry import compute_signals, format_signals_for_role, get_registry, reset_registry

__all__ = [
    "BaseStrategy",
    "Role",
    "StrategySignal",
    "compute_signals",
    "format_signals_for_role",
    "get_registry",
    "reset_registry",
]
