"""Pydantic structured output models for the equity ranking engine.

All agents return one of these models. Deterministic scoring functions
compute master_score, confidence penalties, position roles, and hard vetoes
using only structured outputs — no prose drives downstream decisions.
"""

from __future__ import annotations

import json
import logging
from typing import List, Literal, Optional, Tuple

from pydantic import BaseModel, Field

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
    return round(weighted * 10, 2)


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

def invoke_structured(llm, model_cls, prompt: str):
    """Call LLM with structured output, with JSON fallback."""
    try:
        structured = llm.with_structured_output(model_cls)
        return structured.invoke(prompt)
    except Exception as e:
        logger.warning("Structured output failed for %s: %s — using JSON fallback", model_cls.__name__, e)
        schema_str = json.dumps(model_cls.model_json_schema(), indent=2)
        json_prompt = (
            f"{prompt}\n\nReturn ONLY valid JSON matching this schema:\n{schema_str}"
        )
        response = llm.invoke(json_prompt)
        content = response.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        return model_cls.model_validate_json(content)
