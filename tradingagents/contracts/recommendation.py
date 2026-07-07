"""TradeRecommendation: the artifact the full debate pipeline produces.

Nothing reaches execution without one (Constraint 4), and its geometry is
validated per side: for a BUY the stop sits below entry and the take-profit
ladder ascends above it; for a SELL the mirror holds; a HOLD carries no
levels at all. ``risk_reward`` is always recomputed here from the levels,
and a supplied value that contradicts them is rejected — an LLM cannot
assert a ratio its own levels don't support (Constraint 2)."""

from __future__ import annotations

import math
import uuid
from datetime import datetime

from pydantic import Field, model_validator

from tradingagents.contracts.base import SCHEMA_VERSION, ContractModel, utc_now
from tradingagents.contracts.enums import AssetClass, MarketRegime, TradeAction
from tradingagents.contracts.evidence import AgentEvidence

_FRACTION_TOLERANCE = 1e-9


class TakeProfitLevel(ContractModel):
    """One rung of the take-profit ladder."""

    price: float = Field(gt=0)
    size_fraction: float = Field(
        gt=0, le=1, description="Fraction of the position closed at this level."
    )


class PositionSize(ContractModel):
    quantity: float = Field(ge=0, description="Units of the instrument (0 for HOLD).")
    notional: float | None = Field(default=None, ge=0, description="Quote-currency value.")
    pct_of_equity: float | None = Field(default=None, ge=0, le=100)


class AgentVote(ContractModel):
    agent_id: str = Field(min_length=1)
    vote: TradeAction
    confidence: int = Field(ge=0, le=100)


class VoteBreakdown(ContractModel):
    votes: list[AgentVote] = Field(min_length=1)

    def tally(self) -> dict[TradeAction, int]:
        counts = dict.fromkeys(TradeAction, 0)
        for v in self.votes:
            counts[v.vote] += 1
        return counts


class HistoricalAnalog(ContractModel):
    """A past episode retrieved from memory that resembles current conditions."""

    description: str = Field(min_length=1)
    period_start: datetime
    period_end: datetime
    similarity: float = Field(ge=0, le=1)
    outcome: str = Field(min_length=1, description="What happened and how it resolved.")
    memory_ref: str | None = Field(default=None, description="Key into the memory store.")

    @model_validator(mode="after")
    def _period_ordered(self) -> HistoricalAnalog:
        if self.period_end < self.period_start:
            raise ValueError("period_end precedes period_start")
        return self


class TradeRecommendation(ContractModel):
    schema_version: str = SCHEMA_VERSION
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str = Field(min_length=1)
    asset: AssetClass
    action: TradeAction
    confidence: int = Field(ge=0, le=100)
    entry_price: float | None = Field(default=None, gt=0)
    stop_loss: float | None = Field(default=None, gt=0)
    take_profits: list[TakeProfitLevel] = Field(default_factory=list)
    position_size: PositionSize
    market_regime: MarketRegime
    evidence: list[AgentEvidence] = Field(min_length=1)
    counterarguments: list[AgentEvidence] = Field(
        default_factory=list,
        description="The losing side of the debate, preserved for explainability.",
    )
    vote_breakdown: VoteBreakdown
    historical_analogs: list[HistoricalAnalog] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    risk_reward: float | None = Field(
        default=None,
        description=(
            "Size-weighted reward/risk ratio, computed from entry, stop, and the "
            "take-profit ladder. Do not supply: any provided value is checked "
            "against the recomputation and rejected on mismatch."
        ),
    )

    @model_validator(mode="after")
    def _validate_geometry(self) -> TradeRecommendation:
        if self.action is TradeAction.HOLD:
            if self.entry_price is not None or self.stop_loss is not None or self.take_profits:
                raise ValueError("HOLD must not carry entry, stop, or take-profit levels")
            if self.position_size.quantity != 0:
                raise ValueError("HOLD requires position_size.quantity == 0")
            return self._set_risk_reward()

        if self.entry_price is None or self.stop_loss is None or not self.take_profits:
            raise ValueError(f"{self.action.value} requires entry, stop, and >=1 take-profit")

        prices = [tp.price for tp in self.take_profits]
        if self.action is TradeAction.BUY:
            if not self.stop_loss < self.entry_price:
                raise ValueError("BUY requires stop_loss < entry_price")
            if not all(p > self.entry_price for p in prices):
                raise ValueError("BUY take-profits must sit above entry_price")
            if prices != sorted(prices) or len(set(prices)) != len(prices):
                raise ValueError("BUY take-profit ladder must be strictly ascending")
        else:  # SELL
            if not self.stop_loss > self.entry_price:
                raise ValueError("SELL requires stop_loss > entry_price")
            if not all(p < self.entry_price for p in prices):
                raise ValueError("SELL take-profits must sit below entry_price")
            if prices != sorted(prices, reverse=True) or len(set(prices)) != len(prices):
                raise ValueError("SELL take-profit ladder must be strictly descending")

        total = math.fsum(tp.size_fraction for tp in self.take_profits)
        if total > 1 + _FRACTION_TOLERANCE:
            raise ValueError(f"take-profit size fractions sum to {total:.4f} (> 1)")
        return self._set_risk_reward()

    def _compute_risk_reward(self) -> float | None:
        """Size-weighted reward distance over risk distance; None for HOLD.

        Ladder fractions are normalized so a partial ladder (e.g. two rungs
        closing 50% + 25%) still yields the R:R of the capital actually
        deployed to targets.
        """
        if self.action is TradeAction.HOLD:
            return None
        assert self.entry_price is not None and self.stop_loss is not None
        risk = abs(self.entry_price - self.stop_loss)
        total_fraction = math.fsum(tp.size_fraction for tp in self.take_profits)
        reward = math.fsum(
            abs(tp.price - self.entry_price) * (tp.size_fraction / total_fraction)
            for tp in self.take_profits
        )
        return round(reward / risk, 4)

    def _set_risk_reward(self) -> TradeRecommendation:
        computed = self._compute_risk_reward()
        if self.risk_reward is not None and (
            computed is None or abs(self.risk_reward - computed) > 1e-3
        ):
            raise ValueError(
                f"supplied risk_reward={self.risk_reward} contradicts the levels "
                f"(computed {computed}); omit the field — it is derived, not asserted"
            )
        object.__setattr__(self, "risk_reward", computed)
        return self
