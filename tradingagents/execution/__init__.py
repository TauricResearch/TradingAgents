"""CCXT crypto execution bridge (L1): signal -> sized plan -> gated execution."""

from tradingagents.execution.bridge import ExchangeBridge
from tradingagents.execution.sizing import PlannedOrder, SizingRules

__all__ = ["ExchangeBridge", "PlannedOrder", "SizingRules"]
