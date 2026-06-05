"""Deterministic execution layer.

The wiki decision is that the Trader is **not** an LLM: a Python function turns
an approved, complete investment thesis into a concrete order. This package
holds that translation plus the portfolio-injection helper (tool G), bridging
the domain model (``domain``) and the persistence layer (``storage``).
"""

from .trade import (
    OrderProposal,
    build_trade,
    can_trade,
    inject_portfolio_state,
    persist_trade,
    propose_and_record,
)
from .submit import execute_thesis, reconcile_open_trades, submit_trade
from .costs import CostAssessment, assess_costs, expected_reward, expected_risk

__all__ = [
    "OrderProposal",
    "build_trade",
    "can_trade",
    "inject_portfolio_state",
    "persist_trade",
    "propose_and_record",
    "execute_thesis",
    "reconcile_open_trades",
    "submit_trade",
    "CostAssessment",
    "assess_costs",
    "expected_reward",
    "expected_risk",
]
