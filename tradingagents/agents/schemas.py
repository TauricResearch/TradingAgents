"""Pydantic schemas used by agents that produce structured output.

The framework's primary artifact is still prose: each agent's natural-language
reasoning is what users read in the saved markdown reports and what the
downstream agents read as context.  Structured output is layered onto the
three decision-making agents (Research Manager, Trader, Portfolio Manager)
so that:

- Their outputs follow consistent section headers across runs and providers
- Each provider's native structured-output mode is used (json_schema for
  OpenAI/xAI, response_schema for Gemini, tool-use for Anthropic)
- Schema field descriptions become the model's output instructions, freeing
  the prompt body to focus on context and the rating-scale guidance
- A render helper turns the parsed Pydantic instance back into the same
  markdown shape the rest of the system already consumes, so display,
  memory log, and saved reports keep working unchanged

Phase-2 (Kalshi pivot) adds ``MarketDecision`` for the Portfolio Manager —
the canonical shape for prediction-market bets (probability + edge +
Kelly stake). The legacy ``PortfolioDecision`` / ``ResearchPlan`` /
``TraderProposal`` schemas remain available for the non-PM agents and
for tests that still reference them.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, confloat


# ---------------------------------------------------------------------------
# Shared rating types
# ---------------------------------------------------------------------------


class PortfolioRating(str, Enum):
    """5-tier rating used by the Research Manager and Portfolio Manager."""

    BUY = "Buy"
    OVERWEIGHT = "Overweight"
    HOLD = "Hold"
    UNDERWEIGHT = "Underweight"
    SELL = "Sell"


class TraderAction(str, Enum):
    """3-tier transaction direction used by the Trader.

    The Trader's job is to translate the Research Manager's investment plan
    into a concrete transaction proposal: should the desk execute a Buy, a
    Sell, or sit on Hold this round.  Position sizing and the nuanced
    Overweight / Underweight calls happen later at the Portfolio Manager.
    """

    BUY = "Buy"
    HOLD = "Hold"
    SELL = "Sell"


# ---------------------------------------------------------------------------
# Research Manager
# ---------------------------------------------------------------------------


class ResearchPlan(BaseModel):
    """Structured investment plan produced by the Research Manager.

    Hand-off to the Trader: the recommendation pins the directional view,
    the rationale captures which side of the bull/bear debate carried the
    argument, and the strategic actions translate that into concrete
    instructions the trader can execute against.
    """

    recommendation: PortfolioRating = Field(
        description=(
            "The investment recommendation. Exactly one of Buy / Overweight / "
            "Hold / Underweight / Sell. Reserve Hold for situations where the "
            "evidence on both sides is genuinely balanced; otherwise commit to "
            "the side with the stronger arguments."
        ),
    )
    rationale: str = Field(
        description=(
            "Conversational summary of the key points from both sides of the "
            "debate, ending with which arguments led to the recommendation. "
            "Speak naturally, as if to a teammate."
        ),
    )
    strategic_actions: str = Field(
        description=(
            "Concrete steps for the trader to implement the recommendation, "
            "including position sizing guidance consistent with the rating."
        ),
    )


def render_research_plan(plan: ResearchPlan) -> str:
    """Render a ResearchPlan to markdown for storage and the trader's prompt context."""
    return "\n".join([
        f"**Recommendation**: {plan.recommendation.value}",
        "",
        f"**Rationale**: {plan.rationale}",
        "",
        f"**Strategic Actions**: {plan.strategic_actions}",
    ])


# ---------------------------------------------------------------------------
# Trader
# ---------------------------------------------------------------------------


class TraderProposal(BaseModel):
    """Structured transaction proposal produced by the Trader.

    The trader reads the Research Manager's investment plan and the analyst
    reports, then turns them into a concrete transaction: what action to
    take, the reasoning that justifies it, and the practical levels for
    entry, stop-loss, and sizing.
    """

    action: TraderAction = Field(
        description="The transaction direction. Exactly one of Buy / Hold / Sell.",
    )
    reasoning: str = Field(
        description=(
            "The case for this action, anchored in the analysts' reports and "
            "the research plan. Two to four sentences."
        ),
    )
    entry_price: Optional[float] = Field(
        default=None,
        description="Optional entry price target in the instrument's quote currency.",
    )
    stop_loss: Optional[float] = Field(
        default=None,
        description="Optional stop-loss price in the instrument's quote currency.",
    )
    position_sizing: Optional[str] = Field(
        default=None,
        description="Optional sizing guidance, e.g. '5% of portfolio'.",
    )


def render_trader_proposal(proposal: TraderProposal) -> str:
    """Render a TraderProposal to markdown.

    The trailing ``FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**`` line is
    preserved for backward compatibility with the analyst stop-signal text
    and any external code that greps for it.
    """
    parts = [
        f"**Action**: {proposal.action.value}",
        "",
        f"**Reasoning**: {proposal.reasoning}",
    ]
    if proposal.entry_price is not None:
        parts.extend(["", f"**Entry Price**: {proposal.entry_price}"])
    if proposal.stop_loss is not None:
        parts.extend(["", f"**Stop Loss**: {proposal.stop_loss}"])
    if proposal.position_sizing:
        parts.extend(["", f"**Position Sizing**: {proposal.position_sizing}"])
    parts.extend([
        "",
        f"FINAL TRANSACTION PROPOSAL: **{proposal.action.value.upper()}**",
    ])
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Portfolio Manager
# ---------------------------------------------------------------------------


class PortfolioDecision(BaseModel):
    """Structured output produced by the Portfolio Manager.

    The model fills every field as part of its primary LLM call; no separate
    extraction pass is required. Field descriptions double as the model's
    output instructions, so the prompt body only needs to convey context and
    the rating-scale guidance.
    """

    rating: PortfolioRating = Field(
        description=(
            "The final position rating. Exactly one of Buy / Overweight / Hold / "
            "Underweight / Sell, picked based on the analysts' debate."
        ),
    )
    executive_summary: str = Field(
        description=(
            "A concise action plan covering entry strategy, position sizing, "
            "key risk levels, and time horizon. Two to four sentences."
        ),
    )
    investment_thesis: str = Field(
        description=(
            "Detailed reasoning anchored in specific evidence from the analysts' "
            "debate. If prior lessons are referenced in the prompt context, "
            "incorporate them; otherwise rely solely on the current analysis."
        ),
    )
    price_target: Optional[float] = Field(
        default=None,
        description="Optional target price in the instrument's quote currency.",
    )
    time_horizon: Optional[str] = Field(
        default=None,
        description="Optional recommended holding period, e.g. '3-6 months'.",
    )


def render_pm_decision(decision: PortfolioDecision) -> str:
    """Render a PortfolioDecision back to the markdown shape the rest of the system expects.

    Memory log, CLI display, and saved report files all read this markdown,
    so the rendered output preserves the exact section headers (``**Rating**``,
    ``**Executive Summary**``, ``**Investment Thesis**``) that downstream
    parsers and the report writers already handle.
    """
    parts = [
        f"**Rating**: {decision.rating.value}",
        "",
        f"**Executive Summary**: {decision.executive_summary}",
        "",
        f"**Investment Thesis**: {decision.investment_thesis}",
    ]
    if decision.price_target is not None:
        parts.extend(["", f"**Price Target**: {decision.price_target}"])
    if decision.time_horizon:
        parts.extend(["", f"**Time Horizon**: {decision.time_horizon}"])
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Portfolio Manager — Kalshi prediction-market decision
# ---------------------------------------------------------------------------


class MarketSide(str, Enum):
    """Which side of a binary Kalshi contract to take."""

    YES = "YES"
    NO = "NO"
    PASS = "PASS"


class Confidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class MarketDecision(BaseModel):
    """Portfolio Manager's final call on a Kalshi prediction-market contract.

    The decision pins (a) the agent committee's probability estimate for YES,
    (b) the venue's currently-implied probability, (c) the edge between them
    in basis points, (d) which side to take (or PASS), (e) confidence band,
    and (f) the recommended Kelly fraction of bankroll for the stake.
    Prose fields capture the institutional-grade reasoning that the
    Sophistication-arbitrage thesis depends on.
    """

    p_yes: confloat(ge=0.0, le=1.0) = Field(
        description=(
            "Agent committee's probability estimate that the YES side resolves true. "
            "Range [0, 1]. Anchor in the analysts' debate; do not round to a "
            "comfortable round number — explicit probabilities sharpen edge "
            "estimation and Kelly sizing."
        ),
    )
    market_p_yes: confloat(ge=0.0, le=1.0) = Field(
        description=(
            "Kalshi-implied probability for YES at decision time, sourced from "
            "the get_kalshi_market tool (typically the YES bid/ask midpoint)."
        ),
    )
    edge_bps: float = Field(
        description=(
            "Signed edge against the market in basis points: "
            "(p_yes - market_p_yes) * 10000. Positive favors YES, negative favors NO."
        ),
    )
    recommended_side: MarketSide = Field(
        description=(
            "Which side to take. Use PASS when the |edge| is too small to justify "
            "the risk given confidence — explicit no-trade is a valid output."
        ),
    )
    confidence: Confidence = Field(
        description=(
            "Confidence band on the p_yes estimate. Reserve 'high' for cases where "
            "the analyst committee converged tightly with multiple corroborating "
            "signals; default to 'medium' on contested debates."
        ),
    )
    kelly_fraction: confloat(ge=0.0, le=1.0) = Field(
        description=(
            "Fractional Kelly stake size as a share of bankroll, in [0, 1]. "
            "Use a fractional-Kelly multiplier (typically 0.25x full Kelly) so "
            "stake variance stays manageable. PASS decisions emit 0.0."
        ),
    )
    executive_summary: str = Field(
        description=(
            "Two- to four-sentence punch-line: the call, the edge, the "
            "stake size, and the single biggest reason this is right."
        ),
    )
    investment_thesis: str = Field(
        description=(
            "Detailed reasoning anchored in specific evidence from the "
            "analyst committee. Cite the technical, news, sentiment, and "
            "on-chain reports by name where they support the conclusion. "
            "If past-context lessons are present in the prompt, weave them in."
        ),
    )
    key_risks: str = Field(
        description=(
            "What would invalidate this thesis: the specific event, level, "
            "or signal that, if it materializes, should make us close the "
            "position or wish we hadn't taken it."
        ),
    )


def render_market_decision(decision: MarketDecision) -> str:
    """Render a MarketDecision to the markdown shape the rest of the system consumes.

    The PM previously produced ``**Rating**: ...`` lines that signal_processor
    and the memory log parsed; this rendering preserves that contract while
    surfacing the prediction-market-specific fields (p_yes, edge, side,
    Kelly stake) prominently. The leading "Rating" line maps the binary
    side into the existing 5-tier rating vocabulary so downstream parsers
    keep working without modification:

    - ``YES`` with confidence high      -> Buy
    - ``YES`` with confidence medium    -> Overweight
    - ``NO``  with confidence high      -> Sell
    - ``NO``  with confidence medium    -> Underweight
    - ``PASS`` or low confidence         -> Hold
    """
    side = decision.recommended_side
    conf = decision.confidence

    if side == MarketSide.PASS or conf == Confidence.LOW:
        rating_label = "Hold"
    elif side == MarketSide.YES:
        rating_label = "Buy" if conf == Confidence.HIGH else "Overweight"
    else:
        rating_label = "Sell" if conf == Confidence.HIGH else "Underweight"

    parts = [
        f"**Rating**: {rating_label}",
        "",
        f"**Recommended Side**: {side.value}",
        f"**Confidence**: {conf.value}",
        f"**p_yes (committee)**: {decision.p_yes:.4f}",
        f"**market_p_yes (Kalshi)**: {decision.market_p_yes:.4f}",
        f"**edge_bps**: {decision.edge_bps:+.1f}",
        f"**Kelly fraction**: {decision.kelly_fraction:.4f}",
        "",
        f"**Executive Summary**: {decision.executive_summary}",
        "",
        f"**Investment Thesis**: {decision.investment_thesis}",
        "",
        f"**Key Risks**: {decision.key_risks}",
    ]
    return "\n".join(parts)
