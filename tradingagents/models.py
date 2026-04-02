"""Pydantic structured output models for the equity ranking engine.

All agents return one of these models. Deterministic scoring functions
compute master_score, confidence penalties, position roles, and hard vetoes
using only structured outputs — no prose drives downstream decisions.
"""

from __future__ import annotations

import json
import logging
from typing import List, Literal, Optional, Tuple

from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

RiskLevel = Literal["low", "medium", "high"]

PositionRole = Literal[
    "Core Position",
    "Strong Position",
    "Tactical / Satellite",
    "Watchlist",
    "Avoid",
]

Archetype = Literal[
    "Infrastructure Builder",
    "Bottleneck Supplier",
    "Platform Company",
    "Commodity Leverage",
    "Secular Growth Innovator",
    "Turnaround",
    "Defensive Compounder",
]


# ---------------------------------------------------------------------------
# Data quality flag
# ---------------------------------------------------------------------------

class DataFlag(BaseModel):
    """A data quality issue discovered during analysis."""
    field: str
    severity: Literal["minor", "moderate", "severe"]
    message: str


# ---------------------------------------------------------------------------
# Base output (inherited by most agents)
# ---------------------------------------------------------------------------

class AgentBaseOutput(BaseModel):
    """Common structured fields every analyst agent must return."""
    agent_name: str = ""
    score_0_to_10: float = Field(default=5.0, ge=0, le=10)
    confidence_0_to_1: float = Field(default=0.5, ge=0, le=1)
    key_positives: List[str] = Field(default_factory=list)
    key_negatives: List[str] = Field(default_factory=list)
    key_risks: List[str] = Field(default_factory=list)
    data_quality_flags: List[DataFlag] = Field(default_factory=list)
    veto: bool = False
    veto_reason: Optional[str] = None
    summary_1_sentence: str = ""


# ---------------------------------------------------------------------------
# Tier 1 outputs
# ---------------------------------------------------------------------------

class ValidationOutput(BaseModel):
    """Ticker validation and identity check."""
    agent_name: str = "Validation"
    ticker_valid: bool = True
    ticker_resolved: str = ""
    company_name: str = ""
    company_name_match: bool = True
    exchange: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    is_active: bool = True
    veto: bool = False
    veto_reason: Optional[str] = None
    data_quality_flags: List[DataFlag] = Field(default_factory=list)


class CompanyCard(BaseModel):
    """Cached company identity card."""
    company_name: str = ""
    ticker: str = ""
    sector: str = "Unknown"
    industry: str = "Unknown"
    description: str = ""
    market_cap: Optional[float] = None
    market_cap_formatted: Optional[str] = None
    market_cap_category: str = "unknown"
    current_price: Optional[float] = None
    revenue: Optional[float] = None
    profit_margins: Optional[float] = None
    employees: Optional[int] = None
    competitors: List[str] = Field(default_factory=list)


class MacroRegimeOutput(AgentBaseOutput):
    """Macro regime assessment."""
    agent_name: str = "Macro Regime"
    vix_level: Optional[float] = None
    vix_regime: str = "unknown"
    ten_year_yield: Optional[float] = None
    dollar_strength: str = "unknown"
    credit_spread_direction: str = "unknown"
    spy_1m_return: Optional[float] = None
    regime_label: str = "unknown"
    macro_alignment_0_to_10: float = Field(default=5.0, ge=0, le=10)
    # Regime awareness
    risk_appetite: str = "neutral"  # risk-on / risk-off / transitional
    liquidity_regime: str = "neutral"  # expansion / contraction / neutral
    regime_score_adjustment: float = Field(
        default=0.0, ge=-10, le=10,
        description="Adjustment applied to the 0-100 master score. "
                    "+10 = strong macro tailwind, -10 = severe macro headwind.",
    )


class LiquidityOutput(AgentBaseOutput):
    """Liquidity and market conditions."""
    agent_name: str = "Liquidity"
    fed_stance: str = "unknown"
    market_breadth: str = "unknown"
    volume_profile: str = "unknown"
    spy_trend: str = "unknown"


# ---------------------------------------------------------------------------
# Tier 2 outputs
# ---------------------------------------------------------------------------

class BusinessQualityOutput(AgentBaseOutput):
    """Business quality and competitive position."""
    agent_name: str = "Business Quality"
    revenue_growth: Optional[float] = None
    profit_margins: Optional[float] = None
    operating_margins: Optional[float] = None
    return_on_equity: Optional[float] = None
    return_on_assets: Optional[float] = None
    debt_to_equity: Optional[float] = None
    free_cashflow: Optional[float] = None
    competitive_moat: str = "unknown"
    management_quality: str = "unknown"


class InstitutionalFlowOutput(AgentBaseOutput):
    """Institutional ownership and flow signals."""
    agent_name: str = "Institutional Flow"
    institutional_ownership_pct: Optional[float] = None
    insider_ownership_pct: Optional[float] = None
    volume_ratio: Optional[float] = None
    short_interest_pct: Optional[float] = None
    short_ratio: Optional[float] = None
    float_turnover_pct: Optional[float] = None
    accumulation_signal: str = "unknown"
    # Smart-money tracking
    top_holders_change: str = "unknown"  # increasing / decreasing / stable
    fund_accumulation_pattern: str = "unknown"  # accumulating / distributing / holding
    short_interest_trend: str = "unknown"  # rising / falling / stable
    insider_transaction_signal: str = "unknown"  # buying / selling / none
    smart_money_signal: str = "unknown"  # bullish / bearish / neutral


class ValuationOutput(AgentBaseOutput):
    """Valuation metrics and verdict."""
    agent_name: str = "Valuation"
    trailing_pe: Optional[float] = None
    forward_pe: Optional[float] = None
    peg_ratio: Optional[float] = None
    price_to_book: Optional[float] = None
    ev_to_ebitda: Optional[float] = None
    price_to_sales: Optional[float] = None
    vs_52w_range_pct: Optional[float] = None
    valuation_verdict: str = "unknown"


class EntryTimingOutput(AgentBaseOutput):
    """Technical entry timing signals."""
    agent_name: str = "Entry Timing"
    current_price: Optional[float] = None
    fifty_day_avg: Optional[float] = None
    two_hundred_day_avg: Optional[float] = None
    fifty_day_vs_200_day: str = "unknown"
    vs_52w_range_pct: Optional[float] = None
    timing_verdict: str = "unknown"


class EarningsRevisionOutput(AgentBaseOutput):
    """Earnings revision and analyst consensus."""
    agent_name: str = "Earnings Revisions"
    trailing_eps: Optional[float] = None
    forward_eps: Optional[float] = None
    eps_revision_direction: str = "unknown"
    revenue_revision_direction: str = "unknown"
    analyst_consensus: str = "unknown"
    price_target_upside_pct: Optional[float] = None
    num_analysts: Optional[int] = None


class SectorRotationOutput(AgentBaseOutput):
    """Sector rotation and relative strength."""
    agent_name: str = "Sector Rotation"
    sector: str = "Unknown"
    sector_etf: Optional[str] = None
    sector_vs_spy_1m: Optional[float] = None
    sector_vs_spy_3m: Optional[float] = None
    sector_rank: Optional[int] = None
    total_sectors: int = 11
    rotation_direction: str = "unknown"


class BacklogOrderMomentumOutput(AgentBaseOutput):
    """Backlog and order momentum (where applicable)."""
    agent_name: str = "Backlog / Order Momentum"
    has_backlog_data: bool = False
    backlog_trend: str = "unknown"
    order_momentum: str = "unknown"


class NarrativeCrowdingOutput(AgentBaseOutput):
    """Narrative crowding and contrarian signals."""
    agent_name: str = "Narrative Crowding"
    narrative_saturation: str = "unknown"
    contrarian_opportunity: bool = False
    media_sentiment: str = "unknown"
    short_squeeze_potential: bool = False


class ArchetypeOutput(BaseModel):
    """Company archetype classification."""
    archetype: str = "Secular Growth Innovator"
    archetype_confidence: float = Field(default=0.5, ge=0, le=1)
    reasoning: str = ""


# ---------------------------------------------------------------------------
# Tier 3 outputs
# ---------------------------------------------------------------------------

class BullCaseOutput(BaseModel):
    """Structured bull case thesis."""
    thesis: str = ""
    catalysts: List[str] = Field(default_factory=list)
    upside_target: Optional[float] = None
    upside_pct: Optional[float] = None
    key_assumptions: List[str] = Field(default_factory=list)
    thesis_invalidation_triggers: List[str] = Field(default_factory=list)
    confidence_0_to_1: float = Field(default=0.5, ge=0, le=1)


class BearCaseOutput(BaseModel):
    """Structured bear case thesis."""
    thesis: str = ""
    risks: List[str] = Field(default_factory=list)
    downside_target: Optional[float] = None
    downside_pct: Optional[float] = None
    key_assumptions: List[str] = Field(default_factory=list)
    thesis_invalidation_triggers: List[str] = Field(default_factory=list)
    confidence_0_to_1: float = Field(default=0.5, ge=0, le=1)


class DebateRefereeOutput(BaseModel):
    """Debate referee decision."""
    winner: str = "bull"
    reasoning: str = ""
    bull_strength_0_to_10: float = Field(default=5.0, ge=0, le=10)
    bear_strength_0_to_10: float = Field(default=5.0, ge=0, le=10)
    key_unresolved_questions: List[str] = Field(default_factory=list)
    net_conviction_adjustment: float = Field(default=0.0, ge=-2, le=2)


class RiskInvalidationOutput(AgentBaseOutput):
    """Risk assessment and invalidation triggers."""
    agent_name: str = "Risk / Invalidation"
    overall_risk_level: str = "medium"
    max_position_size_pct: float = Field(default=5.0, ge=0, le=100)
    stop_loss_pct: Optional[float] = None
    invalidation_triggers: List[str] = Field(default_factory=list)


class FinalDecisionOutput(BaseModel):
    """Final synthesized decision with narrative."""
    ticker: str = ""
    company_name: str = ""
    master_score: float = 0.0
    adjusted_score: float = 0.0
    confidence: float = 0.0
    position_role: str = "Avoid"
    action: str = "AVOID"
    risk_level: str = "medium"
    thesis_summary: str = ""
    key_catalysts: List[str] = Field(default_factory=list)
    key_risks: List[str] = Field(default_factory=list)
    invalidation_triggers: List[str] = Field(default_factory=list)
    position_sizing_pct: float = 0.0
    narrative: str = ""


# ---------------------------------------------------------------------------
# Theme Substitution & Position Replacement outputs
# ---------------------------------------------------------------------------

class ThemeStock(BaseModel):
    """A stock ranked within a theme."""
    ticker: str
    company_name: str = ""
    master_score_estimate: float = Field(default=5.0, ge=0, le=10)
    key_advantage: str = ""
    key_weakness: str = ""


class ThemeSubstitutionOutput(BaseModel):
    """Identifies whether a stock is the best expression of its theme."""
    theme_name: str = ""
    theme_description: str = ""
    theme_stocks_ranked: List[ThemeStock] = Field(default_factory=list)
    best_expression_of_theme: bool = True
    best_expression_ticker: str = ""
    stronger_alternatives: List[str] = Field(default_factory=list)
    relative_score_gap: float = 0.0
    portfolio_overlap_warning: str = ""
    reasoning: str = ""


class PositionReplacementOutput(BaseModel):
    """Identifies when a new stock is a better use of capital."""
    replace_candidate: str = ""
    replace_with: str = ""
    score_difference: float = 0.0
    theme_overlap: str = ""
    replacement_reason: str = ""
    conviction_level: str = "low"  # low / medium / high
    stronger_on: List[str] = Field(
        default_factory=list,
        description="Dimensions where candidate beats replacement target",
    )
    weaker_on: List[str] = Field(default_factory=list)
    should_replace: bool = False


# ---------------------------------------------------------------------------
# Deterministic scoring functions
# ---------------------------------------------------------------------------

def compute_master_score(
    business_quality: float,
    macro_alignment: float,
    institutional_flow: float,
    valuation: float,
    entry_timing: float,
    earnings_revisions: float,
    backlog: float,
    crowding: float,
    regime_adjustment: float = 0.0,
) -> float:
    """Compute weighted master score (0-100).

    Weights:
        25% business_quality
        20% macro_alignment
        15% institutional_flow
        10% valuation
        10% entry_timing
        10% earnings_revisions
        5%  backlog
        5%  crowding

    regime_adjustment: -2 to +2, applied as direct offset to the 0-100 score.
    """
    weighted = (
        0.25 * business_quality
        + 0.20 * macro_alignment
        + 0.15 * institutional_flow
        + 0.10 * valuation
        + 0.10 * entry_timing
        + 0.10 * earnings_revisions
        + 0.05 * backlog
        + 0.05 * crowding
    )
    raw = weighted * 10
    adjusted = max(0.0, min(100.0, raw + regime_adjustment))
    return round(adjusted, 2)


def assign_position_role(score: float) -> str:
    """Map master score to a position role."""
    if score > 80:
        return "Core Position"
    if score > 70:
        return "Strong Position"
    if score > 60:
        return "Tactical / Satellite"
    if score > 50:
        return "Watchlist"
    return "Avoid"


def apply_confidence_penalty(
    base_score: float,
    flags: List[DataFlag],
    hard_veto: bool,
) -> float:
    """Reduce score based on data quality flags.

    Penalties: minor=-0.5, moderate=-1.0, severe=-2.0
    """
    if hard_veto:
        return 0.0
    penalty = 0.0
    for flag in flags:
        if flag.severity == "minor":
            penalty += 0.5
        elif flag.severity == "moderate":
            penalty += 1.0
        elif flag.severity == "severe":
            penalty += 2.0
    return max(0.0, base_score - penalty)


def should_hard_veto(
    validation: Optional[ValidationOutput],
    risk: Optional[RiskInvalidationOutput] = None,
) -> Tuple[bool, Optional[str]]:
    """Check if analysis should be hard-vetoed."""
    if validation is not None:
        if validation.veto:
            return True, validation.veto_reason or "Validation veto"
        if not validation.company_name_match:
            return True, "Company name mismatch"
        if not validation.ticker_valid:
            return True, "Invalid ticker"
    if risk is not None and risk.veto:
        return True, risk.veto_reason or "Risk veto"
    return False, None


# ---------------------------------------------------------------------------
# LLM structured output helper
# ---------------------------------------------------------------------------

def _build_json_example(model_cls) -> str:
    """Build a minimal JSON example from a Pydantic model's fields."""
    examples = {}
    schema = model_cls.model_json_schema()
    props = schema.get("properties", {})
    for field_name, field_info in props.items():
        ftype = field_info.get("type", "string")
        if ftype == "number" or ftype == "integer":
            examples[field_name] = 5.0
        elif ftype == "boolean":
            examples[field_name] = True
        elif ftype == "array":
            examples[field_name] = ["example item"]
        else:
            examples[field_name] = "your analysis here"
    return json.dumps(examples, indent=2)


def _extract_json(text: str) -> str:
    """Extract JSON from LLM response that may contain markdown or prose."""
    text = text.strip()
    # Try direct parse first
    if text.startswith("{"):
        return text
    # Extract from ```json blocks
    if "```json" in text:
        return text.split("```json")[1].split("```")[0].strip()
    if "```" in text:
        parts = text.split("```")
        for part in parts[1::2]:  # odd indices are inside code blocks
            candidate = part.strip()
            if candidate.startswith("{"):
                return candidate
    # Find first { ... } block
    start = text.find("{")
    if start >= 0:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{": depth += 1
            elif text[i] == "}": depth -= 1
            if depth == 0:
                return text[start:i+1]
    return text


def invoke_structured(llm, model_cls, prompt: str, timeout: int = 60):
    """Call LLM with structured output, with aggressive JSON fallback.

    Strategy:
    1. Try langchain structured output (works with OpenAI, Anthropic)
    2. If that fails, use JSON-only system prompt with schema + example
    3. Extract JSON from any markdown/prose wrapper
    4. Fall back to defaults if all else fails
    """
    import concurrent.futures
    from langchain_core.messages import SystemMessage, HumanMessage

    def _call_structured():
        structured = llm.with_structured_output(model_cls)
        return structured.invoke(prompt)

    def _call_json_direct():
        """Force JSON output with aggressive system prompt and concrete example."""
        schema_str = json.dumps(model_cls.model_json_schema(), indent=2)
        example_str = _build_json_example(model_cls)
        messages = [
            SystemMessage(content=(
                "You are a JSON-only API. You MUST respond with a single valid JSON object. "
                "No markdown, no commentary, no explanation, no ```json blocks. "
                "Start your response with { and end with }. Nothing else."
            )),
            HumanMessage(content=(
                f"{prompt}\n\n"
                f"Respond with ONLY a JSON object matching this schema:\n{schema_str}\n\n"
                f"Example format (fill in real values):\n{example_str}"
            )),
        ]
        return llm.invoke(messages)

    # Try structured output with per-call timeout
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_call_structured)
            return future.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        logger.warning("Structured output timed out after %ds for %s", timeout, model_cls.__name__)
        raise TimeoutError(f"LLM call timed out after {timeout}s for {model_cls.__name__}")
    except Exception as e:
        logger.warning("Structured output failed for %s: %s — using JSON fallback", model_cls.__name__, e)

    # JSON-direct fallback with per-call timeout
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_call_json_direct)
            response = future.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        logger.warning("JSON fallback timed out after %ds for %s", timeout, model_cls.__name__)
        raise TimeoutError(f"LLM JSON fallback timed out after {timeout}s for {model_cls.__name__}")

    content = _extract_json(response.content)
    try:
        return model_cls.model_validate_json(content)
    except ValidationError as ve:
        logger.error(
            "JSON fallback validation failed for %s: %s — raw text: %.500s",
            model_cls.__name__, ve, content,
        )
        # Return minimal defaults so the pipeline keeps running
        defaults = {}
        if hasattr(model_cls, "model_fields"):
            if "score_0_to_10" in model_cls.model_fields:
                defaults["score_0_to_10"] = 5.0
            if "confidence_0_to_1" in model_cls.model_fields:
                defaults["confidence_0_to_1"] = 0.1
            if "summary_1_sentence" in model_cls.model_fields:
                defaults["summary_1_sentence"] = f"{model_cls.__name__} parsing failed — using fallback defaults"
        return model_cls(**defaults)
