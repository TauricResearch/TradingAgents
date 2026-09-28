"""CCXT crypto execution bridge: signal -> sized plan -> risk check -> gated execution.

Modules: ``bridge`` (spot venue lifecycle, L1+L2), ``sizing`` (FR2 mapping),
``risk`` (FR-K limits over the audit log), ``derivatives`` (leveraged orders
behind the three-layer FR-D gate), ``daily`` (the once-a-day runner), and
``audit`` (the append-only JSONL trail).
"""

from tradingagents.execution.bridge import ExchangeBridge
from tradingagents.execution.daily import DailyResult, run_daily
from tradingagents.execution.derivatives import DerivativesExecutor
from tradingagents.execution.risk import RiskDecision, RiskGuard, RiskLimits
from tradingagents.execution.sizing import PlannedOrder, SizingRules

__all__ = [
    "DailyResult",
    "DerivativesExecutor",
    "ExchangeBridge",
    "PlannedOrder",
    "RiskDecision",
    "RiskGuard",
    "RiskLimits",
    "SizingRules",
    "run_daily",
]
