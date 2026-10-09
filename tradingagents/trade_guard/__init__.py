"""Fail-closed, paper-only validation of explicit trade intents.

This package is intentionally not attached to live exchange execution.
The existing Research Manager, Trader and Portfolio Manager remain unchanged.
"""

from .risk import (
    MarketSnapshot,
    PortfolioSnapshot,
    RiskLimits,
    TradeIntent,
    TradeVerdict,
    validate_intent,
)

__all__ = [
    "MarketSnapshot",
    "PortfolioSnapshot",
    "RiskLimits",
    "TradeIntent",
    "TradeVerdict",
    "validate_intent",
]
