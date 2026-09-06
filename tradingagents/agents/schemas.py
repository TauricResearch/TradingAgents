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
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# LLMs sometimes write a placeholder string ("None", "N/A", ...) into an optional
# numeric field instead of omitting it. Coerce those to None so the structured
# call validates instead of erroring (#1058). Pydantic still parses real numeric
# strings ("189.5") to float.
_NULLISH_FLOAT = {"", "none", "n/a", "na", "null", "nil", "-", "tbd", "unknown"}


def _coerce_optional_float(value):
    if isinstance(value, str) and value.strip().lower() in _NULLISH_FLOAT:
        return None
    return value


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


class HoldingRecommendation(str, Enum):
    """Overnight-vs-intraday holding-duration call made by the Portfolio Manager.

    Distinct from ``rating`` (direction) and ``time_horizon`` (a coarse,
    optional multi-week/month band): this is the specific overnight decision
    that matters most for options positions, where the position itself may
    not even exist past today's close (theta decay), and a name-specific gap
    can swing the position more than a full session of intraday movement.

    Downstream (Hermes' paper-trade exit monitor), only HOLD_OVERNIGHT changes
    behavior — it extends the exit deadline to a bounded window the next
    trading day (09:15-10:15 IST) to actually capture the close->open gap.
    SQUARE_OFF_INTRADAY and DATA_DEPENDENT are both treated as same-day exit by
    15:15 IST, so DATA_DEPENDENT is not a live "wait and see" — it's a
    conservative default with the exact same effect as SQUARE_OFF_INTRADAY.
    Given the whole point of this pipeline is catching the overnight gap, a
    model that reflexively avoids HOLD_OVERNIGHT is quietly opting the
    position out of the trade's actual edge every time.
    """

    HOLD_OVERNIGHT = "Hold Overnight"
    SQUARE_OFF_INTRADAY = "Square Off Intraday"
    DATA_DEPENDENT = "Data-Dependent"


# ---------------------------------------------------------------------------
# Factor Extractor (structured decision_mode -- trading-workspace TradingAgents#19)
# ---------------------------------------------------------------------------


class FactorExtraction(BaseModel):
    """Structured factors pulled from the four analyst reports, produced by a
    single non-debating LLM call. This is the "structured" decision_mode's
    replacement for the Bull/Bear/Research-Manager debate: the LLM's only job
    is to extract/score named factors from prose it already has -- it does not
    see or influence the deterministic scoring that follows (decision_model.py).
    """

    dated_catalyst_present: bool = Field(
        description=(
            "Whether any analyst identified a specific, dated event/catalyst "
            "that could resolve within this decision's own short holding "
            "window (same session or next open) -- not a multi-week/quarter "
            "development."
        ),
    )
    catalyst_hours_to_resolution: float | None = Field(
        default=None,
        description=(
            "Estimated hours until the identified catalyst resolves, if "
            "dated_catalyst_present is true. Null if no catalyst or the "
            "timing is unclear."
        ),
    )
    technical_direction: float = Field(
        ge=-1.0, le=1.0,
        description="Net technical-report directional lean, -1 (strongly bearish) to +1 (strongly bullish).",
    )
    technical_confidence: float = Field(
        ge=0.0, le=1.0,
        description="How clear-cut the technical setup is (0=ambiguous/two-sided, 1=unambiguous).",
    )
    sentiment_direction: float = Field(
        ge=-1.0, le=1.0,
        description="Net news/sentiment-report directional lean, -1 (strongly bearish) to +1 (strongly bullish).",
    )
    sentiment_confidence: float = Field(
        ge=0.0, le=1.0,
        description="How reliable/fresh the sentiment signal is (0=stale or contested, 1=fresh and one-sided).",
    )
    risk_flags: list[str] = Field(
        default_factory=list,
        description=(
            "Short tags for anything that should suppress conviction regardless "
            "of the scores above, e.g. 'earnings in window', 'illiquid', "
            "'contested by analysts', 'macro overhang'."
        ),
    )

    @field_validator("catalyst_hours_to_resolution", mode="before")
    @classmethod
    def _coerce_catalyst_hours(cls, value):
        return _coerce_optional_float(value)


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
            "Hold / Underweight / Sell. Choose Hold when the evidence is "
            "balanced, materially conflicting, ambiguous, or insufficient to "
            "justify changing exposure; otherwise commit to the side with the "
            "clearly stronger arguments. Do not pick a direction merely to be "
            "decisive."
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
    entry_price: float | None = Field(
        default=None,
        description="Optional entry price target in the instrument's quote currency.",
    )
    stop_loss: float | None = Field(
        default=None,
        description="Optional stop-loss price in the instrument's quote currency.",
    )
    position_sizing: str | None = Field(
        default=None,
        description="Optional sizing guidance, e.g. '5% of portfolio'.",
    )

    @field_validator("entry_price", "stop_loss", mode="before")
    @classmethod
    def _nullish_float_to_none(cls, v):
        return _coerce_optional_float(v)


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
            "Underweight / Sell, picked based on the analysts' debate. Choose "
            "Hold when the case is balanced, materially conflicting, ambiguous, "
            "or insufficient to justify changing exposure, rather than forcing a "
            "direction to appear decisive."
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
    price_target: float | None = Field(
        default=None,
        description="Optional target price in the instrument's quote currency.",
    )
    time_horizon: str | None = Field(
        default=None,
        description=(
            "Optional note on how long the thesis needs to play out, e.g. "
            "'overnight' or 'by tomorrow's open' for the common case where "
            "today's event is the catalyst. A multi-week/quarter horizon (e.g. "
            "'next earnings, ~8 weeks') is only appropriate when that later "
            "event is itself expected to move the instrument in the next "
            "session — state that link explicitly if so, since the position "
            "is not held that long regardless."
        ),
    )
    holding_recommendation: HoldingRecommendation = Field(
        description=(
            "Whether to hold this position overnight or square it off before "
            "today's close — evaluated independently of the directional rating "
            "and the multi-week time_horizon above. Weigh overnight gap risk "
            "(a name-specific catalyst, or a broad market move while this "
            "market is closed) and, if the position is held via options, "
            "theta decay through the close, against whichever intraday move "
            "has already been captured. Use Hold Overnight only when the "
            "thesis specifically depends on something that resolves after "
            "today's close (an anticipated catalyst, a multi-day setup still "
            "developing). Use Square Off Intraday when the case is that "
            "today's move is what the thesis was for and there's no specific "
            "reason to carry overnight risk. Use Data-Dependent only when the "
            "call genuinely hinges on how the position performs into the "
            "close (e.g. only hold overnight if still profitable) — state "
            "that condition explicitly in holding_rationale, not just the tier."
        ),
    )
    holding_rationale: str = Field(
        description=(
            "One to two sentences justifying the holding_recommendation "
            "specifically — the overnight risk being weighed, not a restatement "
            "of the directional thesis already covered in investment_thesis."
        ),
    )
    external_signal_disagreement_reason: str | None = Field(
        default=None,
        description=(
            "Only when the prompt states an external signal with an explicit "
            "direction (TradingAgents#30): if your rating points the OPPOSITE "
            "way, or is Hold, name the specific evidence from the reports that "
            "overrides that signal. 'No company-specific catalyst found' is not "
            "sufficient on its own -- the signal is itself a dated sector-wide "
            "catalyst. Null when there is no external signal or you agree with it."
        ),
    )

    @field_validator("price_target", mode="before")
    @classmethod
    def _nullish_float_to_none(cls, v):
        return _coerce_optional_float(v)

    @field_validator("external_signal_disagreement_reason", mode="before")
    @classmethod
    def _nullish_reason_to_none(cls, v):
        if isinstance(v, str) and v.strip().lower() in _NULLISH_FLOAT:
            return None
        return v


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
        "",
        f"**Holding Recommendation**: {decision.holding_recommendation.value}",
        "",
        f"**Holding Rationale**: {decision.holding_rationale}",
    ]
    if decision.price_target is not None:
        parts.extend(["", f"**Price Target**: {decision.price_target}"])
    if decision.time_horizon:
        parts.extend(["", f"**Time Horizon**: {decision.time_horizon}"])
    if decision.external_signal_disagreement_reason:
        parts.extend(["", f"**External Signal Disagreement**: {decision.external_signal_disagreement_reason}"])
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Sentiment Analyst
# ---------------------------------------------------------------------------


class SentimentBand(str, Enum):
    """Discrete sentiment direction produced by the Sentiment Analyst.

    Six tiers keep the signal granular enough to be actionable while remaining
    small enough for every provider to map reliably from its JSON output.
    """

    BULLISH = "Bullish"
    MILDLY_BULLISH = "Mildly Bullish"
    NEUTRAL = "Neutral"
    MIXED = "Mixed"
    MILDLY_BEARISH = "Mildly Bearish"
    BEARISH = "Bearish"


class SentimentReport(BaseModel):
    """Structured sentiment report produced by the Sentiment Analyst.

    Replaces the previous free-form prose output so downstream consumers
    (dashboards, audit logs, PDF renderers, other agents) can read
    ``overall_band`` and ``overall_score`` without maintaining fragile regex
    fallbacks that drift with every model release. ``narrative`` preserves the
    rich source-by-source analysis; ``render_sentiment_report`` prepends a
    deterministic header so the saved report stays human-readable.
    """

    overall_band: SentimentBand = Field(
        description=(
            "Overall sentiment direction. Exactly one of: "
            "Bullish / Mildly Bullish / Neutral / Mixed / Mildly Bearish / Bearish. "
            "Use Mixed when sources point in clearly different directions. "
            "Use Neutral only when all sources are genuinely silent or non-committal."
        ),
    )
    overall_score: float = Field(
        ge=0.0,
        le=10.0,
        description=(
            "Numeric sentiment intensity on a 0–10 scale. "
            "0 = maximally bearish, 5 = neutral, 10 = maximally bullish. "
            "Guideline for consistency with overall_band: "
            "Bullish ~6.5–10, Mildly Bullish ~5.5–6.4, Neutral/Mixed ~4.5–5.5, "
            "Mildly Bearish ~3.5–4.4, Bearish ~0–3.4. "
            "Only the 0–10 bounds are enforced."
        ),
    )
    confidence: Literal["low", "medium", "high"] = Field(
        description=(
            "Confidence in the assessment based on data quality and sample size. "
            "Use 'low' when one or more sources returned a placeholder or fewer "
            "than 5 data points; 'medium' when data is present but sparse; "
            "'high' when all three sources returned substantive data."
        ),
    )
    narrative: str = Field(
        description=(
            "Full sentiment report covering, in order: "
            "(1) source-by-source breakdown with specific evidence (cite message "
            "counts, ratios, notable posts); "
            "(2) cross-source divergences and alignments; "
            "(3) dominant narrative themes; "
            "(4) catalysts and risks surfaced by the data; "
            "(5) a markdown table summarising key sentiment signals, their "
            "direction, source, and supporting evidence. "
            "Keep it informative and substantive: develop each section thoroughly "
            "with concrete evidence so every point adds new signal for the trader."
        ),
    )


def render_sentiment_report(report: SentimentReport) -> str:
    """Render a SentimentReport to the markdown shape the rest of the system expects.

    The structured header (band + score + confidence) is prepended to the
    narrative so the saved report is both human-readable and machine-parseable
    without regex.
    """
    return "\n".join([
        f"**Overall Sentiment:** **{report.overall_band.value}** "
        f"(Score: {report.overall_score:.1f}/10)",
        f"**Confidence:** {report.confidence.capitalize()}",
        "",
        report.narrative,
    ])
