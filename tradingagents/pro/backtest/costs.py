"""Execution-cost models: slippage, commission, liquidity participation.

Deterministic and side-aware: buys fill above the reference price, sells
below. The participation cap is the liquidity constraint — an order may
not exceed a fraction of the bar's traded volume; the remainder is
dropped, never magically filled.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class SlippageModel:
    """Side-aware execution slippage against the trader. Total adverse move =
    a fixed ``bps`` + a half-spread (``spread_bps``) + a square-root MARKET
    IMPACT term ``impact_bps * sqrt(participation)`` (roadmap P4 / track T5 —
    the standard model: cost per share grows with order size relative to the
    bar's liquidity). ``spread_bps``/``impact_bps`` default 0, so a model with
    only ``bps`` is byte-identical to before."""

    bps: float = 2.0            # fixed basis points of the reference price
    spread_bps: float = 0.0     # half the quoted bid/ask spread, paid each side
    impact_bps: float = 0.0     # coefficient on sqrt(participation) impact

    def fill_price(self, reference: float, side: str) -> float:
        """Fixed-cost fill (no size impact) — the zero-participation case."""
        return self.fill_price_at(reference, side, 0.0)

    def fill_price_at(self, reference: float, side: str,
                      participation: float = 0.0) -> float:
        """Fill price including market impact for an order taking
        ``participation`` (order size / bar volume) of the bar's liquidity."""
        if reference <= 0:
            raise ValueError("reference price must be positive")
        adverse = (self.bps + self.spread_bps
                   + self.impact_bps * math.sqrt(max(0.0, participation)))
        if side == "BUY":
            return reference * (1 + adverse / 10_000)
        if side == "SELL":
            return reference * (1 - adverse / 10_000)
        raise ValueError(f"side must be BUY or SELL, got {side!r}")


@dataclass(frozen=True)
class CommissionModel:
    rate_bps: float = 1.0  # of traded notional, charged per fill
    minimum: float = 0.0

    def cost(self, quantity: float, price: float) -> float:
        if quantity < 0 or price <= 0:
            raise ValueError("quantity must be >= 0 and price > 0")
        return max(quantity * price * self.rate_bps / 10_000, self.minimum if quantity else 0.0)


@dataclass(frozen=True)
class LiquidityModel:
    max_participation: float = 0.1  # fraction of the fill bar's volume

    def cap_quantity(self, desired: float, bar_volume: float) -> float:
        if not 0 < self.max_participation <= 1:
            raise ValueError("max_participation must be in (0, 1]")
        if desired < 0:
            raise ValueError("desired quantity must be >= 0")
        return min(desired, self.max_participation * bar_volume)
