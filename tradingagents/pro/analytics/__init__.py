"""Deterministic analytics (Phase 3): quant features and the risk engine.

Everything here is pure, typed Python — the numeric ground truth that
quant- and risk-team agents explain but never compute (Constraint 2).
"""

from tradingagents.pro.analytics.features import (
    classify_regime,
    close_zscore,
    realized_volatility,
    trend_slope,
)
from tradingagents.pro.analytics.risk import (
    atr_stop_loss,
    atr_take_profits,
    fixed_risk_position_size,
    historical_cvar,
    historical_var,
    kelly_fraction,
)

__all__ = [
    "classify_regime",
    "close_zscore",
    "realized_volatility",
    "trend_slope",
    "atr_stop_loss",
    "atr_take_profits",
    "fixed_risk_position_size",
    "historical_cvar",
    "historical_var",
    "kelly_fraction",
]
