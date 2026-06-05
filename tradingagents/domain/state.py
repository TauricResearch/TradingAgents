"""The research_state / investment_state contract (Pydantic).

Mirrors ``state-schemas.md``: a single object with two maturity states. At
runtime it works flat (nodes mutate fields); at sealing ``seal()`` produces the
nested document persisted as JSON (Opzione C). The deterministic Trade function
reads the sealed proposal to build the order.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from pydantic import BaseModel, Field

from .enums import Direction, RiskVerdict


class AgentOpinion(BaseModel):
    """One desk agent's proposal. The PM aggregates these into the final call."""

    agent: str
    suggested_direction: Direction
    suggested_conviction: Direction
    rationale: str = ""


class Levels(BaseModel):
    """Entry/stop/take-profit expressed first in ATR units, then as prices.

    The LLM reasons in ATR coefficients (``k_*``); the deterministic risk engine
    fills the concrete prices from ``current_price`` and ATR.
    """

    k_entry: float
    k_stop: float
    k_tp: float
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

    @property
    def has_prices(self) -> bool:
        return None not in (self.entry_price, self.stop_loss, self.take_profit)


class RiskGate(BaseModel):
    """Risk Analyst verdict + the deterministic guardrail results."""

    verdict: Optional[RiskVerdict] = None
    rationale: str = ""
    guardrail_checks: dict[str, Any] = Field(default_factory=dict)
    risk_score: Optional[float] = None


class ResearchState(BaseModel):
    """The full investment thesis for one ticker."""

    # A — identity & context
    ticker: str
    as_of: Optional[date] = None
    current_price: Optional[float] = None
    portfolio_context: dict[str, Any] = Field(default_factory=dict)
    past_context: str = ""

    # B — analysis (the two desks)
    market_view: str = ""
    sentiment_view: str = ""
    fundamental_view: str = ""
    technical_view: str = ""
    key_factors: list[dict[str, Any]] = Field(default_factory=list)
    agent_opinions: list[AgentOpinion] = Field(default_factory=list)

    # C — proposal (aggregated by the PM)
    direction: Optional[Direction] = None
    conviction_level: Optional[Direction] = None
    levels: Optional[Levels] = None
    position_sizing_pct: Optional[float] = None
    pro: list[str] = Field(default_factory=list)
    contro: list[str] = Field(default_factory=list)
    next_check_date: Optional[date] = None

    # D — risk gate
    risk: RiskGate = Field(default_factory=RiskGate)

    # meta
    version: str = "alpha"
    status: str = "draft"  # draft / complete / approved / declined

    # ------------------------------------------------------------------
    def is_complete(self) -> bool:
        """Completeness gate: every obligatory field filled before sealing.

        A HOLD thesis is complete without price levels (there is nothing to
        execute); an actionable thesis needs direction, concrete levels and a
        sizing figure.
        """
        if not all([self.market_view, self.sentiment_view,
                    self.fundamental_view, self.technical_view]):
            return False
        if self.direction is None or self.conviction_level is None:
            return False
        if not self.direction.is_actionable:
            return True
        return (
            self.levels is not None
            and self.levels.has_prices
            and self.position_sizing_pct is not None
        )

    @property
    def is_approved(self) -> bool:
        return self.risk.verdict is RiskVerdict.APPROVED

    def seal(self) -> dict[str, Any]:
        """Produce the nested document persisted as JSON (Opzione C sealing)."""
        return {
            "identity": {
                "ticker": self.ticker,
                "as_of": self.as_of.isoformat() if self.as_of else None,
                "current_price": self.current_price,
                "portfolio_context": self.portfolio_context,
                "past_context": self.past_context,
            },
            "analysis": {
                "market_view": self.market_view,
                "sentiment_view": self.sentiment_view,
                "fundamental_view": self.fundamental_view,
                "technical_view": self.technical_view,
                "key_factors": self.key_factors,
                "agent_opinions": [o.model_dump(mode="json") for o in self.agent_opinions],
            },
            "proposal": {
                "direction": self.direction.value if self.direction else None,
                "conviction_level": self.conviction_level.value if self.conviction_level else None,
                "levels": self.levels.model_dump(mode="json") if self.levels else None,
                "position_sizing_pct": self.position_sizing_pct,
                "pro": self.pro,
                "contro": self.contro,
                "next_check_date": self.next_check_date.isoformat() if self.next_check_date else None,
            },
            "risk_gate": self.risk.model_dump(mode="json"),
            "meta": {"version": self.version, "status": self.status},
        }
