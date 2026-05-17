"""
Per-agent extraction schemas for TT-295.

One Pydantic model per TradingAgents agent. Each schema captures the
quantitative findings analysts typically cite in their reports so the
dashboard can render them as cards/gauges/charts.

All fields are Optional — extractors null fields the analyst didn't
mention rather than hallucinating. Stricter wins over completeness;
the dashboard's chart components no-op when a value is null.

SCHEMA_FOR_AGENT maps `agent_name` strings (as emitted by the
LangGraph callbacks — see callbacks.py `_normalize_agent_name`) to
their schema class.

To add a new agent's schema: define the class here, add the mapping
at the bottom, ship a follow-up PR with the dashboard chart component.
"""

from __future__ import annotations

from typing import Optional, Literal
from pydantic import BaseModel, Field


# ── Analysts (4) ────────────────────────────────────────────────────────

class MarketAnalystMetadata(BaseModel):
    """Technical indicators + price levels from the market_analyst."""
    rsi:                 Optional[float] = Field(None, description="Current RSI (0-100). 70+ overbought, 30- oversold.")
    macd_signal:         Optional[Literal["bullish", "bearish", "neutral"]] = None
    sma_50:              Optional[float] = Field(None, description="50-day simple moving average price")
    sma_200:             Optional[float] = Field(None, description="200-day simple moving average price")
    current_price:       Optional[float] = None
    support_level:       Optional[float] = None
    resistance_level:    Optional[float] = None
    trend:               Optional[Literal["uptrend", "downtrend", "sideways"]] = None
    volume_signal:       Optional[Literal["high", "average", "low"]] = None


class FundamentalsAnalystMetadata(BaseModel):
    """Valuation + financial-health metrics from fundamentals_analyst."""
    pe_ratio:            Optional[float] = None
    forward_pe_ratio:    Optional[float] = None
    peg_ratio:           Optional[float] = None
    pb_ratio:            Optional[float] = Field(None, description="Price-to-book")
    market_cap_usd:      Optional[float] = None
    revenue_growth_pct:  Optional[float] = Field(None, description="YoY revenue growth %")
    profit_margin_pct:   Optional[float] = None
    debt_to_equity:      Optional[float] = None
    free_cash_flow_usd:  Optional[float] = None
    rating:              Optional[Literal["overweight", "neutral", "underweight"]] = None


class NewsAnalystMetadata(BaseModel):
    """News flow + sentiment from news_analyst."""
    sentiment_score:     Optional[float] = Field(None, description="-1 (very bearish) to +1 (very bullish)")
    tone:                Optional[Literal["bullish", "bearish", "mixed", "neutral"]] = None
    news_volume:         Optional[Literal["high", "average", "low"]] = None
    key_events:          list[str] = Field(default_factory=list, description="Most material news items mentioned")
    catalysts:           list[str] = Field(default_factory=list, description="Upcoming catalysts / scheduled events")


class SocialMediaAnalystMetadata(BaseModel):
    """Social-media sentiment from social_media_analyst."""
    sentiment_score:     Optional[float] = Field(None, description="-1 to +1")
    mention_volume:      Optional[Literal["high", "average", "low"]] = None
    platform_breakdown:  dict[str, float] = Field(default_factory=dict, description='e.g. {"reddit": 0.4, "twitter": 0.6}')
    key_themes:          list[str] = Field(default_factory=list)
    retail_interest:     Optional[Literal["surging", "elevated", "normal", "low"]] = None


# ── Researchers (3) ─────────────────────────────────────────────────────

class BullResearcherMetadata(BaseModel):
    """Long-thesis points + conviction from bull_researcher."""
    conviction:          Optional[Literal["strong", "moderate", "weak"]] = None
    top_bullish_points:  list[str] = Field(default_factory=list)
    target_price:        Optional[float] = None
    upside_pct:          Optional[float] = Field(None, description="Implied upside to target")


class BearResearcherMetadata(BaseModel):
    """Short-thesis points + conviction from bear_researcher."""
    conviction:          Optional[Literal["strong", "moderate", "weak"]] = None
    top_bearish_points:  list[str] = Field(default_factory=list)
    target_price:        Optional[float] = None
    downside_pct:        Optional[float] = Field(None, description="Implied downside to target")


class ResearchManagerMetadata(BaseModel):
    """Synthesis + final research view from research_manager."""
    recommendation:      Optional[Literal["overweight", "neutral", "underweight"]] = None
    time_horizon_months: Optional[float] = None
    confidence:          Optional[Literal["high", "medium", "low"]] = None
    summary:             Optional[str] = Field(None, description="One-sentence thesis")


# ── Trader (1) ──────────────────────────────────────────────────────────

class TraderMetadata(BaseModel):
    """Concrete trade plan from trader."""
    action:              Optional[Literal["buy", "sell", "hold", "trim", "add"]] = None
    entry_price:         Optional[float] = None
    position_size_pct:   Optional[float] = Field(None, description="% of portfolio allocated")
    stop_loss_price:     Optional[float] = None
    take_profit_price:   Optional[float] = None
    risk_reward_ratio:   Optional[float] = None


# ── Risk debators (3) ───────────────────────────────────────────────────

class RiskDebatorMetadata(BaseModel):
    """Shared shape for risky_analyst, neutral_analyst, safe_analyst."""
    stance:              Optional[Literal["risky", "neutral", "safe"]] = None
    recommended_action:  Optional[Literal["aggressive_buy", "buy", "hold", "sell", "aggressive_sell"]] = None
    risk_tolerance:      Optional[Literal["high", "medium", "low"]] = None
    key_concerns:        list[str] = Field(default_factory=list)


# ── Risk manager (1) ────────────────────────────────────────────────────

class RiskManagerMetadata(BaseModel):
    """Final risk grade + sizing limits from risk_manager."""
    risk_grade:          Optional[Literal["A", "B", "C", "D", "F"]] = None
    max_position_pct:    Optional[float] = Field(None, description="Max recommended portfolio allocation")
    volatility_estimate: Optional[Literal["high", "medium", "low"]] = None
    final_action:        Optional[Literal["approve", "approve_with_limits", "reject"]] = None


# ── Agent name → schema mapping ─────────────────────────────────────────
#
# Keys match the `agent_name` strings emitted by callbacks.py's
# `_normalize_agent_name`. Agents not in this mapping skip extraction
# entirely (metadata stays null).

SCHEMA_FOR_AGENT: dict[str, type[BaseModel]] = {
    "market_analyst":        MarketAnalystMetadata,
    "fundamentals_analyst":  FundamentalsAnalystMetadata,
    "news_analyst":          NewsAnalystMetadata,
    "social_media_analyst":  SocialMediaAnalystMetadata,
    "bull_researcher":       BullResearcherMetadata,
    "bear_researcher":       BearResearcherMetadata,
    "research_manager":      ResearchManagerMetadata,
    "trader":                TraderMetadata,
    "risky_analyst":         RiskDebatorMetadata,
    "neutral_analyst":       RiskDebatorMetadata,
    "safe_analyst":          RiskDebatorMetadata,
    "risk_manager":          RiskManagerMetadata,
}
