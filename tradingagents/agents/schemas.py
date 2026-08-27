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

from pydantic import BaseModel, Field, field_validator, model_validator

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

    The Trader translates the Research Manager's investment plan into a
    research-only transaction scenario: Buy, Sell, or Hold. Position sizing
    and nuanced Overweight / Underweight views remain unexecuted research
    suggestions for the Portfolio Manager and a human reviewer.
    """

    BUY = "Buy"
    HOLD = "Hold"
    SELL = "Sell"


class DecisionStatus(str, Enum):
    """Research disposition kept separate from the backwards-compatible rating.

    A rating expresses the directional research view. The status says whether
    the evidence is complete enough for a human to consider acting on it.
    """

    RESEARCH_COMPLETE = "Research Complete"
    NO_TRADE = "No Trade"
    DATA_INSUFFICIENT = "Data Insufficient"
    HUMAN_REVIEW_REQUIRED = "Human Review Required"


class DataQuality(str, Enum):
    """Coarse quality assessment for the evidence used in a decision."""

    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    UNAVAILABLE = "Unavailable"
    UNKNOWN = "Unknown"


class EvidenceKind(str, Enum):
    """Distinguish sourced observations from interpretation and missing data."""

    SOURCED_FACT = "Sourced Fact"
    MODEL_INFERENCE = "Model Inference"
    DATA_UNAVAILABLE = "Data Unavailable"


class EvidenceStrength(str, Enum):
    """Evidence strength used by the lightweight provenance contract."""

    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class EvidenceItem(BaseModel):
    """One auditable claim supporting or limiting a portfolio decision."""

    claim: str = Field(description="Concise claim, number, or conclusion being relied upon.")
    kind: EvidenceKind = Field(
        description=(
            "Exactly one of Sourced Fact / Model Inference / Data Unavailable. "
            "Do not label an interpretation as a sourced fact."
        ),
    )
    source: str | None = Field(
        default=None,
        description="Provider, report, filing, article, or series identifier; null if unavailable.",
    )
    as_of: str | None = Field(
        default=None,
        description="Observation/publication time or analysis cutoff; null if unknown.",
    )
    strength: EvidenceStrength = Field(
        default=EvidenceStrength.LOW,
        description="High / Medium / Low based on source quality, timeliness, and corroboration.",
    )


class _UncertaintyFields(BaseModel):
    """Shared, optional forecast fields layered onto existing agent schemas."""

    decision_status: DecisionStatus = Field(
        default=DecisionStatus.RESEARCH_COMPLETE,
        description=(
            "Research disposition separate from direction. Use No Trade when a complete forecast "
            "cannot be formed, Data Insufficient when required inputs are unavailable, and Human "
            "Review Required for material unresolved evidence conflicts."
        ),
    )
    time_horizon: str | None = Field(
        default=None,
        description="Forecast and suggested holding horizon, e.g. '20 trading days' or '3-6 months'.",
    )
    expected_return_low: float | None = Field(
        default=None,
        description="Lower bound of expected total return as a decimal (for example -0.05 = -5%).",
    )
    expected_return_high: float | None = Field(
        default=None,
        description="Upper bound of expected total return as a decimal (for example 0.12 = 12%).",
    )
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Calibrated confidence from 0 to 1, reduced for missing or weak evidence.",
    )
    invalidation_conditions: list[str] = Field(
        default_factory=list,
        description="Observable conditions that would invalidate the thesis or require reassessment.",
    )

    @field_validator("expected_return_low", "expected_return_high", mode="before")
    @classmethod
    def _nullish_return_to_none(cls, v):
        return _coerce_optional_float(v)

    @model_validator(mode="after")
    def _return_bounds_are_ordered(self):
        if (
            self.expected_return_low is not None
            and self.expected_return_high is not None
            and self.expected_return_low > self.expected_return_high
        ):
            raise ValueError("expected_return_low must be <= expected_return_high")
        return self


def _format_percent(value: float) -> str:
    return f"{value:+.1%}"


def _append_uncertainty_fields(parts: list[str], value: _UncertaintyFields) -> None:
    """Append optional uncertainty fields using stable, parser-friendly labels."""
    parts.extend(["", f"**Decision Status**: {value.decision_status.value}"])
    if value.time_horizon:
        parts.extend(["", f"**Time Horizon**: {value.time_horizon}"])
    if value.expected_return_low is not None and value.expected_return_high is not None:
        parts.extend([
            "",
            "**Expected Return Range**: "
            f"{_format_percent(value.expected_return_low)} to "
            f"{_format_percent(value.expected_return_high)}",
        ])
    if value.confidence is not None:
        parts.extend(["", f"**Confidence**: {value.confidence:.1%}"])
    if value.invalidation_conditions:
        parts.extend(["", "**Invalidation Conditions**:"])
        parts.extend(f"- {condition}" for condition in value.invalidation_conditions)


# ---------------------------------------------------------------------------
# Research Manager
# ---------------------------------------------------------------------------


class ResearchPlan(_UncertaintyFields):
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
            "including research-only sizing guidance consistent with the rating. "
            "Do not describe an approved or executable order."
        ),
    )


def render_research_plan(plan: ResearchPlan) -> str:
    """Render a ResearchPlan to markdown for storage and the trader's prompt context."""
    parts = [
        f"**Recommendation**: {plan.recommendation.value}",
        "",
        "**Research Use Only**: Yes",
        "",
        f"**Rationale**: {plan.rationale}",
        "",
        f"**Strategic Actions**: {plan.strategic_actions}",
    ]
    _append_uncertainty_fields(parts, plan)
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Trader
# ---------------------------------------------------------------------------


class TraderProposal(_UncertaintyFields):
    """Structured transaction proposal produced by the Trader.

    The trader reads the Research Manager's investment plan and the analyst
    reports, then turns them into a research scenario: the directional action,
    reasoning, and hypothetical levels for entry, stop-loss, and sizing. It
    does not create an order or control a real position.
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
        "**Research Use Only**: Yes",
        "",
        f"**Reasoning**: {proposal.reasoning}",
    ]
    if proposal.entry_price is not None:
        parts.extend(["", f"**Entry Price**: {proposal.entry_price}"])
    if proposal.stop_loss is not None:
        parts.extend(["", f"**Stop Loss**: {proposal.stop_loss}"])
    if proposal.position_sizing:
        parts.extend(["", f"**Position Sizing**: {proposal.position_sizing}"])
    _append_uncertainty_fields(parts, proposal)
    parts.extend([
        "",
        f"FINAL TRANSACTION PROPOSAL: **{proposal.action.value.upper()}**",
    ])
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Portfolio Manager
# ---------------------------------------------------------------------------


class PortfolioDecision(_UncertaintyFields):
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
    price_target: float | None = Field(
        default=None,
        description="Optional target price in the instrument's quote currency.",
    )
    data_quality: DataQuality = Field(
        default=DataQuality.UNKNOWN,
        description=(
            "Overall quality of the provided evidence. Use Low or Unavailable when any required "
            "analyst input is missing, live-only in a historical analysis, or not point-in-time safe."
        ),
    )
    key_risks: list[str] = Field(
        default_factory=list,
        description="Material, decision-relevant risks stated as observable scenarios.",
    )
    evidence: list[EvidenceItem] = Field(
        default_factory=list,
        description=(
            "Compact evidence ledger for the most important claims. Include source and as-of time "
            "for sourced facts; explicitly mark model inference and unavailable data."
        ),
    )

    @field_validator("price_target", mode="before")
    @classmethod
    def _nullish_float_to_none(cls, v):
        return _coerce_optional_float(v)


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
        "**Research Use Only**: Yes",
        "",
        f"**Executive Summary**: {decision.executive_summary}",
        "",
        f"**Investment Thesis**: {decision.investment_thesis}",
    ]
    if decision.price_target is not None:
        parts.extend(["", f"**Price Target**: {decision.price_target}"])
    _append_uncertainty_fields(parts, decision)
    parts.extend(["", f"**Data Quality**: {decision.data_quality.value}"])
    if decision.key_risks:
        parts.extend(["", "**Key Risks**:"])
        parts.extend(f"- {risk}" for risk in decision.key_risks)
    if decision.evidence:
        parts.extend(["", "**Evidence Summary**:"])
        for item in decision.evidence:
            source = (item.source or "unavailable").replace("|", "/")
            as_of = (item.as_of or "unknown").replace("|", "/")
            parts.append(
                f"- [{item.kind.value} | {item.strength.value} | {source} | {as_of}] "
                f"{item.claim}"
            )
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
