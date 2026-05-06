"""Stake sizing for Kalshi binary contracts.

Inputs come from the Portfolio Manager's ``MarketDecision``:
- ``p_yes``       — agent committee's probability for YES.
- ``market_p_yes`` — Kalshi-implied probability at decision time.
- ``recommended_side`` (YES / NO / PASS).
- ``confidence`` (low / medium / high).
- ``kelly_fraction`` — the PM's own preferred Kelly multiplier.

The sizing pipeline:

1. Compute *full* Kelly for the chosen side.
2. Apply a fractional-Kelly multiplier (the PM's ``kelly_fraction`` field
   acts as our explicit override; otherwise default to 0.25× full Kelly).
3. Discount further by confidence (high=1.0, medium=0.6, low=0.0).
4. Cap by ``max_stake_usd`` from the Kalshi config block.
5. Convert dollars-of-edge into integer contract count given the entry
   price (each YES contract pays $1 if YES resolves; cost = entry price).

Returns a stake plan that the runner hands to the Kalshi client.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from tradingagents.agents.schemas import (
    Confidence,
    MarketDecision,
    MarketSide,
)

logger = logging.getLogger(__name__)


_CONFIDENCE_DISCOUNT = {
    Confidence.HIGH: 1.0,
    Confidence.MEDIUM: 0.6,
    Confidence.LOW: 0.0,
}

# Default fractional-Kelly multiplier. Mirrors kalshi-trader's NEARLOCK_KELLY_FRACTION.
_DEFAULT_KELLY_MULTIPLIER = 0.25

# Minimum stake worth executing — below this, prefer PASS.
_MIN_STAKE_USD = 1.0


@dataclass
class StakePlan:
    """The runner reads this to decide whether and how to place an order."""

    side: MarketSide
    contract_count: int
    price_cents: int
    stake_usd: float
    full_kelly_fraction: float
    discounted_fraction: float
    notes: str

    @property
    def should_execute(self) -> bool:
        return self.side != MarketSide.PASS and self.contract_count > 0


def compute_full_kelly(p_true: float, p_market: float) -> float:
    """Full Kelly fraction for a binary contract priced at ``p_market``.

    Buying YES at price ``p_market`` pays out 1 (gross) on YES, 0 on NO.
    Net-of-stake: payout = 1 - p_market on YES, -p_market on NO.

    Kelly = (b * p - q) / b, where:
        b = (1 - p_market) / p_market   # net-odds on success
        p = p_true                       # probability of success
        q = 1 - p_true                   # probability of failure
    Reduces to: (p_true - p_market) / (1 - p_market) for YES.
    """
    if p_market <= 0 or p_market >= 1:
        return 0.0
    edge = p_true - p_market
    if edge <= 0:
        return 0.0
    return edge / (1 - p_market)


def _yes_kelly(p_yes: float, market_p_yes: float) -> float:
    return compute_full_kelly(p_yes, market_p_yes)


def _no_kelly(p_yes: float, market_p_yes: float) -> float:
    """Buying NO at ``1 - market_p_yes``, with success probability ``1 - p_yes``."""
    return compute_full_kelly(1 - p_yes, 1 - market_p_yes)


def plan_stake(
    decision: MarketDecision,
    *,
    bankroll_usd: float,
    max_stake_usd: float,
    kelly_multiplier: Optional[float] = None,
) -> StakePlan:
    """Translate a ``MarketDecision`` into a concrete order plan."""
    side = decision.recommended_side

    if side == MarketSide.PASS:
        return StakePlan(
            side=MarketSide.PASS,
            contract_count=0,
            price_cents=0,
            stake_usd=0.0,
            full_kelly_fraction=0.0,
            discounted_fraction=0.0,
            notes="PM recommended PASS; no order to place.",
        )

    p_yes = float(decision.p_yes)
    market_p_yes = float(decision.market_p_yes)

    if side == MarketSide.YES:
        full_kelly = _yes_kelly(p_yes, market_p_yes)
        entry_price = market_p_yes
    else:  # NO
        full_kelly = _no_kelly(p_yes, market_p_yes)
        entry_price = 1 - market_p_yes

    if full_kelly <= 0:
        return StakePlan(
            side=MarketSide.PASS,
            contract_count=0,
            price_cents=0,
            stake_usd=0.0,
            full_kelly_fraction=full_kelly,
            discounted_fraction=0.0,
            notes=(
                f"Edge is non-positive for the chosen side "
                f"(side={side.value}, p_yes={p_yes:.3f}, market_p_yes={market_p_yes:.3f}); "
                "downgrading to PASS."
            ),
        )

    # The PM's ``kelly_fraction`` is treated as an explicit multiplier on
    # full Kelly. Caller can override with ``kelly_multiplier`` (e.g. for
    # backtest sweeps). Fall back to a conservative default.
    multiplier = kelly_multiplier
    if multiplier is None:
        multiplier = float(decision.kelly_fraction) if decision.kelly_fraction > 0 else _DEFAULT_KELLY_MULTIPLIER

    confidence_discount = _CONFIDENCE_DISCOUNT[decision.confidence]
    discounted_fraction = full_kelly * multiplier * confidence_discount

    stake_usd = min(bankroll_usd * discounted_fraction, max_stake_usd)
    if stake_usd < _MIN_STAKE_USD:
        return StakePlan(
            side=MarketSide.PASS,
            contract_count=0,
            price_cents=0,
            stake_usd=0.0,
            full_kelly_fraction=full_kelly,
            discounted_fraction=discounted_fraction,
            notes=(
                f"Discounted stake ${stake_usd:.2f} is below the minimum "
                f"(${_MIN_STAKE_USD:.2f}); downgrading to PASS."
            ),
        )

    # Each contract pays $1 if it resolves; cost is ``entry_price`` dollars.
    # Round the contract count down so we never overshoot the stake cap.
    contract_count = int(stake_usd // entry_price)
    if contract_count <= 0:
        return StakePlan(
            side=MarketSide.PASS,
            contract_count=0,
            price_cents=0,
            stake_usd=0.0,
            full_kelly_fraction=full_kelly,
            discounted_fraction=discounted_fraction,
            notes=(
                f"Computed stake covers fewer than 1 contract at entry "
                f"price ${entry_price:.2f}; downgrading to PASS."
            ),
        )

    price_cents = max(1, min(99, int(round(entry_price * 100))))
    actual_stake = contract_count * entry_price

    return StakePlan(
        side=side,
        contract_count=contract_count,
        price_cents=price_cents,
        stake_usd=actual_stake,
        full_kelly_fraction=full_kelly,
        discounted_fraction=discounted_fraction,
        notes=(
            f"Full Kelly = {full_kelly:.4f}; multiplier = {multiplier:.2f}; "
            f"confidence discount = {confidence_discount:.2f}; "
            f"discounted = {discounted_fraction:.4f}; "
            f"stake = ${actual_stake:.2f} ({contract_count} contracts at "
            f"{price_cents}c entry)."
        ),
    )
