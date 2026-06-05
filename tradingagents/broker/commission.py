"""Commission models (cost-accounting, runtime).

A swappable estimator of the broker fee for an order, so the cost is read from
the broker's real schedule rather than hardcoded. Used pre-trade to fold the
commission into the net-EV guardrail (see ``execution/costs.py``).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class CommissionModel(Protocol):
    def estimate(self, symbol: str, quantity: float, price: float) -> float: ...


class ZeroCommission:
    """Commission-free equity (e.g. Alpaca). Spread is not modelled here."""

    def estimate(self, symbol: str, quantity: float, price: float) -> float:
        return 0.0


class PerTradeCommission:
    def __init__(self, fee: float):
        self.fee = fee

    def estimate(self, symbol: str, quantity: float, price: float) -> float:
        return self.fee if quantity else 0.0


class PerShareCommission:
    """IBKR-style: per-share fee with a per-order minimum."""

    def __init__(self, per_share: float, min_fee: float = 0.0):
        self.per_share = per_share
        self.min_fee = min_fee

    def estimate(self, symbol: str, quantity: float, price: float) -> float:
        if not quantity:
            return 0.0
        return max(self.min_fee, abs(quantity) * self.per_share)


class PercentCommission:
    def __init__(self, pct: float):
        self.pct = pct

    def estimate(self, symbol: str, quantity: float, price: float) -> float:
        return abs(quantity) * price * self.pct
