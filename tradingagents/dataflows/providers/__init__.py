"""
Multi-provider data layer for TradingAgents.

This package provides a unified interface for accessing market data
from multiple sources (Yahoo Finance, BYMA, WorldMonitor, etc.).
"""

from .base import DataProvider, MarketData
from .registry import (
    get_provider,
    get_all_providers,
    get_providers_for_market,
    register_provider,
    init_default_providers,
)

__all__ = [
    "DataProvider",
    "MarketData",
    "get_provider",
    "get_all_providers",
    "get_providers_for_market",
    "register_provider",
    "init_default_providers",
]
