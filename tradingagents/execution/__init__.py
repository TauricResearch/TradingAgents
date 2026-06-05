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

__all__ = [
    "OrderProposal",
    "build_trade",
    "can_trade",
    "inject_portfolio_state",
    "persist_trade",
    "propose_and_record",
]
