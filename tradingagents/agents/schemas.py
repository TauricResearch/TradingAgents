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

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
        description="Optional recommended holding period, e.g. '3-6 months'.",
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
# Portfolio Context (#1166)
# ---------------------------------------------------------------------------


class PositionSnapshot(BaseModel):
    """A single instrument holding inside a portfolio snapshot.

    Broker-neutral by design: no account identifiers, order ids, credentials,
    or broker-specific fields. Quantity is signed (negative for short) and in
    the instrument's native share/coin units.
    """

    model_config = ConfigDict(allow_inf_nan=False)

    symbol: str = Field(
        description="Instrument symbol exactly as the caller tracks it (e.g. 'NVDA').",
    )
    quantity: float = Field(
        description="Signed position size in native units (negative for short).",
    )
    market_value: float | None = Field(
        default=None,
        description="Optional current market value in the portfolio currency.",
    )
    average_entry_price: float | None = Field(
        default=None,
        description="Optional average entry price in the instrument's quote currency.",
    )

    @field_validator("symbol")
    @classmethod
    def _strip_symbol(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("symbol must be a non-empty string")
        return cleaned


class PortfolioContext(BaseModel):
    """Optional, broker-neutral snapshot of the portfolio being analysed.

    Threaded through the graph as plain JSON-safe data so it survives
    checkpointing. ``None`` at the graph entrypoint means the context was not
    provided; a ``PortfolioContext`` with empty ``positions`` means a known
    flat portfolio. The two states are deliberately distinct: agents must not
    present sizing guidance as portfolio-grounded when no context was given.
    """

    model_config = ConfigDict(allow_inf_nan=False)

    positions: list[PositionSnapshot] = Field(
        default_factory=list,
        description="Open positions. Empty means a known flat portfolio.",
    )
    cash: float | None = Field(
        default=None,
        description="Optional available cash in the portfolio currency.",
    )
    portfolio_value: float | None = Field(
        default=None,
        description="Optional total portfolio value in the portfolio currency.",
    )
    buying_power: float | None = Field(
        default=None,
        description="Optional buying power in the portfolio currency.",
    )
    as_of: str | None = Field(
        default=None,
        description="Optional snapshot timestamp (ISO-8601 expected, free-form accepted).",
    )
    source: str | None = Field(
        default=None,
        description="Optional snapshot origin label (e.g. 'paper-broker', 'manual').",
    )
    currency: str | None = Field(
        default=None,
        description=(
            "Optional portfolio reporting currency label (e.g. 'USD', 'JPY'). "
            "Display-only; TradingAgents performs no FX conversion."
        ),
    )

    @field_validator("currency")
    @classmethod
    def _normalize_currency(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = v.strip().upper()
        if not cleaned:
            raise ValueError("currency must be a non-empty label or omitted")
        return cleaned

    def position_for(self, symbol: str) -> PositionSnapshot | None:
        """Return the position matching ``symbol`` (case-insensitive), if any."""
        wanted = symbol.strip().upper()
        for position in self.positions:
            if position.symbol.upper() == wanted:
                return position
        return None


def _format_amount(value: float, currency: str | None = None) -> str:
    """Format an amount with an optional ISO-style currency label.

    No currency symbols are used: ``$`` is ambiguous across USD/CAD/AUD/HKD,
    and the framework is market-neutral (non-US equities, crypto). Amounts
    without a currency render as bare numbers.
    """
    text = f"{value:,.2f}"
    if currency:
        return f"{text} {currency.strip().upper()}"
    return text


def render_portfolio_context(context: PortfolioContext, symbol: str) -> str:
    """Render a deterministic portfolio block focused on ``symbol``.

    Only the current instrument's position is itemised; the remaining
    holdings are summarised by count so prompts stay small and stable.
    Never renders ``str(dict)``: every line is an explicit, labelled fact.

    Market-neutral: quantities use generic ``units`` (stocks, ETFs, crypto),
    and amounts carry the optional portfolio ``currency`` label only. The
    average entry price is quoted in the instrument's own quote currency,
    which may differ from the portfolio currency, so it never inherits the
    portfolio currency label.
    """
    lines = ["Portfolio Context:"]
    snapshot = context.as_of or "timestamp not recorded"
    origin = context.source or "unspecified"
    lines.append(f"- Snapshot: {snapshot} (source: {origin})")

    capital = []
    if context.portfolio_value is not None:
        capital.append(
            f"portfolio value {_format_amount(context.portfolio_value, context.currency)}"
        )
    if context.cash is not None:
        capital.append(f"cash {_format_amount(context.cash, context.currency)}")
    if context.buying_power is not None:
        capital.append(
            f"buying power {_format_amount(context.buying_power, context.currency)}"
        )
    lines.append(
        "- Capital: " + ("; ".join(capital) if capital else "no capital figures provided")
    )

    current = context.position_for(symbol)
    if current is not None:
        detail = f"- Current {current.symbol} position: {current.quantity:g} units"
        extras = []
        if current.market_value is not None:
            extras.append(
                f"market value {_format_amount(current.market_value, context.currency)}"
            )
        if current.average_entry_price is not None:
            extras.append(f"avg entry {_format_amount(current.average_entry_price)}")
        if extras:
            detail += f" ({'; '.join(extras)})"
        lines.append(detail + ".")
    elif not context.positions:
        lines.append("- Holdings: known flat portfolio, no open positions.")
    else:
        lines.append(
            f"- Holdings: no current {symbol.strip() or 'requested-instrument'} position; "
            f"{len(context.positions)} other position(s) held."
        )
    return "\n".join(lines)


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
