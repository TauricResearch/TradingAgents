"""Backtest-only Portfolio State Manager.

State-first refactor of portfolio decision-making for backtest mode:
- The LLM only emits a latent MarketState (orthogonal regimes + evidence consistency).
- Deterministic Python policy converts MarketState into the existing
  PortfolioStrategy order schema using anchors and rule constraints.

Live mode continues to use create_portfolio_manager from portfolio_manager.py.
"""

import json
import logging
import re
import warnings
from pathlib import Path
from typing import Any, Literal, Optional

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator

from back_test.policy_config import (
    PortfolioStatePolicyConfig,
    coerce_portfolio_state_policy_config,
    _DEFAULT_VOLUME_MULTIPLIER,
)
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
)
from tradingagents.agents.utils.structure_patterns import (
    analyze_ohlcv_structure,
    format_structure_analysis_for_prompt,
)
from tradingagents.agents.managers.portfolio_manager import (
    PortfolioStrategy,
    PriceSizeBlock,
    StopLossBlock,
    _classify_volume_regime,
    _enforce_strategy_rules,
    _is_broad_index_instrument,
)
from tradingagents.dataflows.stockstats_utils import load_ohlcv

logger = logging.getLogger(__name__)

__all__ = [
    "PortfolioStatePolicyConfig",
    "MarketState",
    "create_portfolio_state_manager",
    "create_market_aware_portfolio_state_manager",
    "policy_from_market_state",
]


def _apply_order_size_multiplier(strategy: dict, multiplier: float) -> dict:
    """Scale deterministic order sizes without exposing the multiplier to the LLM."""
    if multiplier <= 0:
        raise ValueError(f"order_size_multiplier must be > 0, got {multiplier}")
    if multiplier == 1.0:
        return strategy

    for key in ("entry", "add_position", "take_profit", "reduce_stop"):
        block = strategy.get(key)
        if not isinstance(block, dict):
            continue
        size_pct = float(block.get("size_pct") or 0.0)
        if size_pct <= 0:
            continue
        block["size_pct"] = round(min(size_pct * multiplier, 100.0), 1)

    rationale = strategy.get("rationale_summary") or ""
    strategy["rationale_summary"] = (
        f"{rationale} | hardcoded_order_size_multiplier={multiplier:g}"
    )
    return strategy


class ConfidenceComponents(BaseModel):
    """Evidence-consistency inputs; not analyst rhetorical conviction."""

    model_config = ConfigDict(extra="forbid")

    anchor_agreement: float = Field(
        ge=0.0,
        le=1.0,
        description="Agreement among hard OHLCV/structure anchors.",
    )
    timeframe_consistency: float = Field(
        ge=0.0,
        le=1.0,
        description="Agreement across higher/trading/lower timeframe reads.",
    )
    volatility_stability: float = Field(
        ge=0.0,
        le=1.0,
        description="Lower when volatility is rapidly changing or shock-like.",
    )
    contradiction_absence: float = Field(
        ge=0.0,
        le=1.0,
        description="Lower when anchors materially conflict.",
    )
    event_certainty: float = Field(
        ge=0.0,
        le=1.0,
        description="Lower when scheduled or unscheduled events dominate state estimation.",
    )


class TimeframeHierarchy(BaseModel):
    """Separates persistent structure from lower-timeframe noise."""

    model_config = ConfigDict(extra="forbid")

    higher_timeframe_trend: Literal["ascending", "descending", "sideways", "transition", "unclear"]
    trading_timeframe_trend: Literal["ascending", "descending", "sideways", "transition", "unclear"]
    lower_timeframe_trend: Literal["ascending", "descending", "sideways", "transition", "unclear"]
    alignment: Literal[
        "aligned",
        "pullback_against_higher_timeframe",
        "countertrend_move",
        "higher_timeframe_transition",
        "lower_timeframe_noise",
        "conflicted",
        "unclear",
    ]
    short_term_override: Literal[
        "none",
        "confirmed_structure_break",
        "confirmed_structure_reclaim",
        "volatility_shock",
        "event_shock",
        "liquidity_dislocation",
    ] = "none"


class InvalidationCondition(BaseModel):
    """Machine-readable invalidation taxonomy."""

    model_config = ConfigDict(extra="forbid")

    invalidation_type: Literal[
        "structure_break",
        "volatility_expansion",
        "failed_breakout",
        "failed_breakdown",
        "momentum_divergence",
        "event_shock",
        "liquidity_shift",
        "timeframe_reclassification",
        "data_revision",
        "unclear",
    ]
    invalidation_detail: str
    reference_timeframe: Literal["lower", "trading", "higher", "multi_timeframe", "event"] = (
        "trading"
    )


class EvidenceAggregation(BaseModel):
    """Three-stage evidence stack used to suppress narrative contamination."""

    model_config = ConfigDict(extra="forbid")

    hard_anchors: list[str] = Field(
        default_factory=list,
        description="Price structure, EMA hierarchy, ATR/RV, S/R, volume structure.",
    )
    event_modifiers: list[str] = Field(
        default_factory=list,
        description="Earnings, macro, filings, policy, or other concrete event modifiers.",
    )
    narrative_residual: list[str] = Field(
        default_factory=list,
        description="Low-weight residual narrative after anchor and event evidence.",
    )
    contradictory_signals: list[str] = Field(default_factory=list)


class MarketState(BaseModel):
    """Latent market environment state, deliberately separated from trade intent."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["state_v2"] = "state_v2"
    ticker: str
    as_of_date: str

    trend_regime: Literal["ascending", "descending", "sideways", "transition", "unclear"]
    volatility_regime: Literal[
        "compressed", "normal", "expanding", "elevated", "shock", "unstable", "unavailable"
    ]
    momentum_regime: Literal[
        "positive", "negative", "neutral", "divergent", "mean_reverting", "unclear"
    ]
    liquidity_regime: Literal[
        "normal", "volume_expansion", "volume_contraction", "thin", "imbalanced", "unavailable"
    ]
    event_regime: Literal[
        "none",
        "scheduled_event",
        "earnings_dominant",
        "macro_dominant",
        "policy_dominant",
        "idiosyncratic_shock",
        "multi_event",
        "unclear",
    ]
    structure_quality: Literal[
        "coherent",
        "range_bound",
        "fragmented",
        "breakout_attempt",
        "breakdown_attempt",
        "damaged",
        "unclear",
    ]
    exhaustion_state: Literal[
        "none",
        "positive_extension",
        "negative_extension",
        "two_sided_chop",
        "late_trend_fatigue",
        "unclear",
    ] = "none"
    breadth_state: Literal[
        "broad_participation",
        "narrow_participation",
        "divergent",
        "neutral",
        "not_applicable",
        "unavailable",
    ] = "unavailable"

    trend_direction_score: float = Field(
        ge=-1.0,
        le=1.0,
        description="Signed directionality of the observed structure; not a trade signal.",
    )
    trend_strength: float = Field(
        ge=0.0,
        le=1.0,
        description="Persistence/clarity of trend structure independent of direction.",
    )
    momentum_score_value: float = Field(
        ge=-1.0,
        le=1.0,
        description="Signed recent impulse; exhaustion is represented separately.",
    )
    risk_pressure_score: float = Field(
        ge=0.0,
        le=1.0,
        description="State instability from structure, volatility, liquidity, and events.",
    )
    event_impact_score: float = Field(
        ge=-1.0,
        le=1.0,
        description="Signed event pressure on the observed state, not analyst opinion.",
    )
    confidence: float = Field(ge=0.0, le=1.0)
    confidence_components: ConfidenceComponents

    horizon_days: int = Field(ge=1, le=60)

    timeframe_hierarchy: TimeframeHierarchy
    invalidation: InvalidationCondition
    evidence: EvidenceAggregation
    state_summary: str
    key_risks: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_state_v1(cls, value: Any) -> Any:
        """Accept older saved/LLM v1 payloads, but normalize to state_v2."""
        if not isinstance(value, dict):
            return value
        if value.get("schema_version") != "state_v1" and "market_phase" not in value:
            return value

        regime = value.get("regime", "unclear")
        phase = value.get("market_phase", "unclear")
        trend_score = float(value.get("trend_score") or 0.0)
        momentum_score = float(value.get("momentum_score") or 0.0)
        risk_score = float(value.get("risk_score") or 0.5)
        event_score = float(value.get("event_score") or 0.0)
        confidence = float(value.get("confidence") or 0.5)

        if regime in {"strong_uptrend", "weak_uptrend"}:
            trend_regime = "ascending"
        elif regime in {"breakdown_risk", "downtrend"}:
            trend_regime = "descending"
        elif regime == "range":
            trend_regime = "sideways"
        elif regime == "event_driven":
            trend_regime = "transition"
        else:
            trend_regime = "unclear"

        if phase in {"range_compression"}:
            volatility_regime = "compressed"
        elif phase in {"high_volatility_range", "accelerating_bear"}:
            volatility_regime = "elevated"
        elif phase == "macro_event_regime":
            volatility_regime = "unstable"
        else:
            volatility_regime = "normal"

        if phase in {"accelerating_bull", "healthy_bull_trend"} or momentum_score > 0.15:
            momentum_regime = "positive"
        elif phase in {"accelerating_bear", "healthy_bear_trend"} or momentum_score < -0.15:
            momentum_regime = "negative"
        elif phase in {"bull_pullback", "bear_rally"}:
            momentum_regime = "mean_reverting"
        elif phase in {"late_bull_distribution"}:
            momentum_regime = "divergent"
        else:
            momentum_regime = "neutral"

        if phase in {"accelerating_bull", "accelerating_bear"}:
            liquidity_regime = "volume_expansion"
        elif phase in {"late_bull_distribution"}:
            liquidity_regime = "imbalanced"
        else:
            liquidity_regime = "normal"

        event_regime = "macro_dominant" if phase == "macro_event_regime" else "none"
        if phase in {"early_bear_reversal", "healthy_bear_trend", "accelerating_bear"}:
            structure_quality = "damaged" if regime == "downtrend" else "breakdown_attempt"
        elif phase in {"range_compression", "high_volatility_range"}:
            structure_quality = "range_bound"
        elif phase in {"early_bull_reversal", "accelerating_bull"}:
            structure_quality = "breakout_attempt"
        elif phase in {"unclear"}:
            structure_quality = "unclear"
        else:
            structure_quality = "coherent"

        if phase == "overextended_bull":
            exhaustion_state = "positive_extension"
        elif phase == "oversold_bear":
            exhaustion_state = "negative_extension"
        elif phase in {"late_bull_distribution", "late_bear_exhaustion"}:
            exhaustion_state = "late_trend_fatigue"
        elif phase == "high_volatility_range":
            exhaustion_state = "two_sided_chop"
        else:
            exhaustion_state = "none"

        return {
            "schema_version": "state_v2",
            "ticker": value.get("ticker"),
            "as_of_date": value.get("as_of_date"),
            "trend_regime": trend_regime,
            "volatility_regime": volatility_regime,
            "momentum_regime": momentum_regime,
            "liquidity_regime": liquidity_regime,
            "event_regime": event_regime,
            "structure_quality": structure_quality,
            "exhaustion_state": exhaustion_state,
            "breadth_state": "unavailable",
            "trend_direction_score": trend_score,
            "trend_strength": min(abs(trend_score) + 0.15, 1.0),
            "momentum_score_value": momentum_score,
            "risk_pressure_score": risk_score,
            "event_impact_score": event_score,
            "confidence": confidence,
            "confidence_components": {
                "anchor_agreement": confidence,
                "timeframe_consistency": confidence,
                "volatility_stability": max(0.0, 1.0 - risk_score * 0.5),
                "contradiction_absence": confidence,
                "event_certainty": max(0.0, 1.0 - abs(event_score) * 0.5),
            },
            "horizon_days": value.get("horizon_days", 5),
            "timeframe_hierarchy": {
                "higher_timeframe_trend": trend_regime,
                "trading_timeframe_trend": trend_regime,
                "lower_timeframe_trend": trend_regime,
                "alignment": "aligned" if trend_regime not in {"transition", "unclear"} else "unclear",
                "short_term_override": "none",
            },
            "invalidation": {
                "invalidation_type": "timeframe_reclassification",
                "invalidation_detail": value.get(
                    "invalidation_condition",
                    "Material anchor reclassification at the next review.",
                ),
                "reference_timeframe": "trading",
            },
            "evidence": {
                "hard_anchors": ["Migrated from legacy state_v1 payload."],
                "event_modifiers": [],
                "narrative_residual": [value.get("thesis", "")] if value.get("thesis") else [],
                "contradictory_signals": value.get("key_risks") or [],
            },
            "state_summary": value.get("thesis") or "Migrated legacy market state.",
            "key_risks": value.get("key_risks") or [],
        }

    @property
    def regime(self) -> str:
        """Compatibility adapter for the existing deterministic policy."""
        if self.event_regime != "none" and self.confidence_components.event_certainty < 0.45:
            return "event_driven"
        if self.trend_regime == "ascending":
            if self.trend_strength >= 0.60 and self.structure_quality in {
                "coherent",
                "breakout_attempt",
            }:
                return "strong_uptrend"
            return "weak_uptrend"
        if self.trend_regime == "descending":
            if self.trend_strength >= 0.70 and self.structure_quality == "damaged":
                return "downtrend"
            return "breakdown_risk"
        if self.trend_regime == "sideways":
            return "range"
        return "unclear"

    @property
    def market_phase(self) -> str:
        """Compatibility adapter; not part of the serialized state_v2 ontology."""
        if self.event_regime != "none" and self.confidence_components.event_certainty < 0.50:
            return "macro_event_regime"
        if self.trend_regime == "ascending":
            if self.exhaustion_state == "positive_extension":
                return "overextended_bull"
            if self.exhaustion_state == "late_trend_fatigue" or self.breadth_state in {
                "narrow_participation",
                "divergent",
            }:
                return "late_bull_distribution"
            if self.timeframe_hierarchy.alignment == "pullback_against_higher_timeframe":
                return "bull_pullback"
            if self.momentum_regime == "mean_reverting":
                return "bull_pullback"
            if self.momentum_regime == "positive" and self.liquidity_regime == "volume_expansion":
                return "accelerating_bull"
            if self.structure_quality == "coherent":
                return "healthy_bull_trend"
            return "early_bull_reversal"
        if self.trend_regime == "descending":
            if self.exhaustion_state == "negative_extension":
                return "oversold_bear"
            if self.exhaustion_state == "late_trend_fatigue":
                return "late_bear_exhaustion"
            if self.timeframe_hierarchy.alignment == "countertrend_move" or self.momentum_regime == "mean_reverting":
                return "bear_rally"
            if self.momentum_regime == "negative" and self.volatility_regime in {
                "elevated",
                "shock",
                "unstable",
            }:
                return "accelerating_bear"
            if self.structure_quality == "damaged":
                return "healthy_bear_trend"
            return "early_bear_reversal"
        if self.trend_regime == "sideways":
            if self.volatility_regime == "compressed":
                return "range_compression"
            if self.volatility_regime in {"elevated", "shock", "unstable"}:
                return "high_volatility_range"
            return "unclear"
        return "unclear"

    @property
    def trend_score(self) -> float:
        return self.trend_direction_score

    @property
    def risk_score(self) -> float:
        return self.risk_pressure_score

    @property
    def momentum_score(self) -> float:
        return self.momentum_score_value

    @property
    def event_score(self) -> float:
        return self.event_impact_score

    @property
    def thesis(self) -> str:
        return self.state_summary

    @property
    def invalidation_condition(self) -> str:
        return (
            f"{self.invalidation.invalidation_type}: "
            f"{self.invalidation.invalidation_detail}"
        )


def _find_market_state(value, seen: Optional[set[int]] = None) -> Optional[MarketState]:
    if value is None:
        return None
    if isinstance(value, MarketState):
        return value
    if seen is None:
        seen = set()
    obj_id = id(value)
    if obj_id in seen:
        return None
    seen.add(obj_id)

    if isinstance(value, dict):
        try:
            return MarketState.model_validate(value)
        except Exception:
            pass
        for nested in value.values():
            found = _find_market_state(nested, seen)
            if found is not None:
                return found
        return None

    for attr in ("parsed", "content", "output"):
        nested = getattr(value, attr, None)
        found = _find_market_state(nested, seen)
        if found is not None:
            return found

    if isinstance(value, (list, tuple)):
        for nested in value:
            found = _find_market_state(nested, seen)
            if found is not None:
                return found

    if isinstance(value, str):
        return _market_state_from_text(value)

    additional_kwargs = getattr(value, "additional_kwargs", None)
    if isinstance(additional_kwargs, dict):
        found = _find_market_state(additional_kwargs, seen)
        if found is not None:
            return found

    return None


def _market_state_from_text(text: str) -> Optional[MarketState]:
    """Parse a free-text JSON MarketState fallback response."""
    candidates = [text.strip()]
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        candidates.append(fenced.group(1).strip())

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])

    for candidate in candidates:
        if not candidate:
            continue
        try:
            return MarketState.model_validate_json(candidate)
        except Exception:
            try:
                return MarketState.model_validate(json.loads(candidate))
            except Exception:
                continue
    return None


def _market_state_response_to_model(response) -> MarketState:
    state = _find_market_state(response)
    if state is None:
        raise TypeError(
            f"Structured output did not contain MarketState: {type(response).__name__}"
        )
    return state


def _llm_disallows_structured_output(llm) -> bool:
    """Return True for known providers/modes that reject tool_choice."""
    model = (getattr(llm, "model_name", None) or getattr(llm, "model", "") or "").lower()
    if model.startswith("deepseek-") or model == "deepseek-chat":
        return True

    extra_body = getattr(llm, "extra_body", None) or {}
    thinking = extra_body.get("thinking") if isinstance(extra_body, dict) else None
    return isinstance(thinking, dict) and thinking.get("type") == "enabled"


def _compute_short_term_market_anchors(
    ticker: str,
    trade_date: str,
    lookback_days: int = 80,
) -> Optional[dict]:
    """Return short-horizon numeric anchors for 1-5 trading day decisions."""
    try:
        df = load_ohlcv(ticker, trade_date)
    except Exception:
        return None
    if df is None or df.empty:
        return None

    df = df.sort_values("Date").reset_index(drop=True)
    structure_analysis = analyze_ohlcv_structure(df, ticker, trade_date)
    df = df.tail(lookback_days).reset_index(drop=True)
    if len(df) < 2:
        return None

    last = df.iloc[-1]
    current_close = float(last["Close"])
    if current_close <= 0:
        return None

    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    close = df["Close"].astype(float)
    volume = pd.to_numeric(df.get("Volume"), errors="coerce") if "Volume" in df else None

    prev_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    def _sma(window: int) -> Optional[float]:
        if len(close) < window:
            return None
        return float(close.tail(window).mean())

    def _ema(window: int) -> Optional[float]:
        if len(close) < window:
            return None
        return float(close.ewm(span=window, adjust=False).mean().iloc[-1])

    def _nearest_resistance(window: int) -> Optional[float]:
        slice_ = high.tail(window)
        above = slice_[slice_ > current_close]
        return float(above.min()) if not above.empty else None

    def _nearest_support(window: int) -> Optional[float]:
        slice_ = low.tail(window)
        below = slice_[slice_ < current_close]
        return float(below.max()) if not below.empty else None

    atr5 = float(true_range.tail(5).mean()) if len(true_range) >= 5 else float(true_range.mean())
    atr14 = float(true_range.tail(14).mean()) if len(true_range) >= 14 else float(true_range.mean())

    resistance = _nearest_resistance(5) or _nearest_resistance(10) or _nearest_resistance(20)
    support = _nearest_support(5) or _nearest_support(10) or _nearest_support(20)
    latest_volume = float(volume.iloc[-1]) if volume is not None and pd.notna(volume.iloc[-1]) else None
    volume_20_sma = (
        float(volume.tail(20).mean())
        if volume is not None and len(volume.dropna()) >= 20
        else None
    )
    volume_ratio = (
        latest_volume / volume_20_sma
        if latest_volume is not None and volume_20_sma not in (None, 0)
        else None
    )
    volume_ratio_3d = None
    if volume is not None and volume_20_sma not in (None, 0) and len(volume.dropna()) >= 20:
        volume_20_series = volume.rolling(20).mean()
        ratio_series = volume / volume_20_series
        recent_ratios = ratio_series.tail(3).dropna()
        if len(recent_ratios) == 3:
            volume_ratio_3d = [round(float(v), 3) for v in recent_ratios.tolist()]

    return {
        "as_of_close_date": pd.to_datetime(last["Date"]).strftime("%Y-%m-%d"),
        "current_price": round(current_close, 4),
        "atr5": round(atr5, 4),
        "atr14": round(atr14, 4),
        "atr14_pct": round(atr14 / current_close * 100.0, 3),
        "ema5": round(_ema(5), 4) if _ema(5) is not None else None,
        "ema10": round(_ema(10), 4) if _ema(10) is not None else None,
        "ema20": round(_ema(20), 4) if _ema(20) is not None else None,
        "sma5": round(_sma(5), 4) if _sma(5) is not None else None,
        "sma10": round(_sma(10), 4) if _sma(10) is not None else None,
        "sma20": round(_sma(20), 4) if _sma(20) is not None else None,
        "sma50": round(_sma(50), 4) if _sma(50) is not None else None,
        "sma200": None,
        "recent_high_5d": round(float(high.tail(5).max()), 4),
        "recent_low_5d": round(float(low.tail(5).min()), 4),
        "recent_high_10d": round(float(high.tail(10).max()), 4),
        "recent_low_10d": round(float(low.tail(10).min()), 4),
        "recent_high_20d": round(float(high.tail(20).max()), 4),
        "recent_low_20d": round(float(low.tail(20).min()), 4),
        "nearest_resistance": round(resistance, 4) if resistance is not None else None,
        "nearest_support": round(support, 4) if support is not None else None,
        "latest_volume": round(latest_volume, 4) if latest_volume is not None else None,
        "volume_20_sma": round(volume_20_sma, 4) if volume_20_sma is not None else None,
        "volume_50_sma": round(volume_20_sma, 4) if volume_20_sma is not None else None,
        "volume_ratio": round(volume_ratio, 3) if volume_ratio is not None else None,
        "volume_ratio_3d": volume_ratio_3d,
        "structure_analysis": structure_analysis,
    }


def _format_short_term_market_anchors(anchors: dict) -> str:
    def _fmt(value):
        if value is None:
            return "n/a"
        if isinstance(value, list):
            return "[" + ", ".join(f"{item:g}" for item in value) + "]"
        return f"{value:g}"

    return (
        "**Short-term market anchors (precomputed from OHLCV through "
        f"{anchors['as_of_close_date']} — DO NOT recompute, USE these numbers verbatim):**\n"
        f"- current_price: {_fmt(anchors['current_price'])}\n"
        f"- ATR(5) / ATR(14): {_fmt(anchors['atr5'])} / {_fmt(anchors['atr14'])}  "
        f"(ATR14 ≈ {_fmt(anchors['atr14_pct'])}% of price)\n"
        f"- EMA5 / EMA10 / EMA20: {_fmt(anchors['ema5'])} / {_fmt(anchors['ema10'])} / {_fmt(anchors['ema20'])}\n"
        f"- SMA5 / SMA10 / SMA20 / SMA50: {_fmt(anchors['sma5'])} / {_fmt(anchors['sma10'])} / {_fmt(anchors['sma20'])} / {_fmt(anchors['sma50'])}\n"
        f"- 5-day range: high {_fmt(anchors['recent_high_5d'])}, low {_fmt(anchors['recent_low_5d'])}\n"
        f"- 10-day range: high {_fmt(anchors['recent_high_10d'])}, low {_fmt(anchors['recent_low_10d'])}\n"
        f"- nearest resistance above current: {_fmt(anchors['nearest_resistance'])}\n"
        f"- nearest support below current: {_fmt(anchors['nearest_support'])}\n"
        f"- latest_volume / volume_20_sma / volume_ratio: {_fmt(anchors.get('latest_volume'))} / "
        f"{_fmt(anchors.get('volume_20_sma'))} / {_fmt(anchors.get('volume_ratio'))}\n"
        f"- last 3 volume ratios vs 20-day average: {_fmt(anchors.get('volume_ratio_3d'))}\n"
        "- proximity rule: a price P is \"within X%\" iff |P - current_price| / current_price <= X/100. "
        "Use this for all distance-to-current checks; do not estimate from the report.\n"
        + format_structure_analysis_for_prompt(anchors.get("structure_analysis"))
    )


def _is_short_term_uptrend(anchors: dict) -> bool:
    current = anchors.get("current_price")
    ema5 = anchors.get("ema5") or anchors.get("sma20")
    ema10 = anchors.get("ema10") or anchors.get("sma50")
    ema20 = anchors.get("ema20") or anchors.get("sma200")
    if current is None or ema10 is None or ema20 is None:
        return False
    return (ema5 is not None and current > ema5 > ema10 > ema20) or current > ema10 > ema20


def _is_new_short_high_with_weak_volume(anchors: dict) -> bool:
    current = anchors.get("current_price")
    recent_high = anchors.get("recent_high_10d")
    ratios = anchors.get("volume_ratio_3d")
    if current is None or recent_high is None or not ratios:
        return False
    return current >= recent_high and all(ratio < 0.8 for ratio in ratios)


def _derive_short_term_rule_constraints(anchors: Optional[dict], holdings_info: dict, ticker: str) -> dict:
    if not anchors:
        return {
            "available": False,
            "allowed_actions": ["BUY", "HOLD", "SELL"],
            "entry_mode": "llm_discretion",
            "max_entry_size_pct": 30,
            "max_add_position_size_pct": 30,
            "volume_regime": "unavailable",
            "notes": ["Short-term anchors unavailable; cap new/add exposure at 30%."],
        }

    has_position = float(holdings_info.get("quantity") or 0.0) > 0
    volume_regime = _classify_volume_regime(anchors.get("volume_ratio"))
    short_uptrend = _is_short_term_uptrend(anchors)
    broad_index = _is_broad_index_instrument(ticker)
    bearish_volume_divergence = _is_new_short_high_with_weak_volume(anchors)

    allowed_actions = ["BUY", "HOLD", "SELL"]
    entry_mode = "short_term_normal"
    max_entry_size_pct = 60
    max_add_position_size_pct = 40
    notes = []

    if volume_regime == "unavailable":
        max_entry_size_pct = 30
        max_add_position_size_pct = 30
        notes.append("20-day volume ratio unavailable; cap short-term entries and adds at 30%.")
    elif volume_regime == "shrinking":
        max_entry_size_pct = 30
        max_add_position_size_pct = 20
        entry_mode = "pullback_or_small_only"
        notes.append("Shrinking 20-day volume confirmation limits short-term exposure.")
    elif volume_regime == "soft":
        max_entry_size_pct = 45
        max_add_position_size_pct = 30
        entry_mode = "pullback_or_reduced_size"
        notes.append("Sub-normal 20-day volume caps short-term entries at 45% and adds at 30%.")

    if broad_index and short_uptrend:
        allowed_actions = ["BUY", "HOLD"] if not has_position else ["BUY", "HOLD", "SELL"]
        if volume_regime in ("normal", "expanding"):
            max_entry_size_pct = max(max_entry_size_pct, 70)
        notes.append("Broad index short-term uptrend favors BUY/HOLD; SELL needs clear short-term damage.")

    if bearish_volume_divergence:
        max_entry_size_pct = 0
        max_add_position_size_pct = 0
        entry_mode = "no_new_or_add"
        notes.append("10-day high on weak 3-day volume ratio blocks new entries and adds.")

    return {
        "available": True,
        "allowed_actions": allowed_actions,
        "entry_mode": entry_mode,
        "max_entry_size_pct": max_entry_size_pct,
        "max_add_position_size_pct": max_add_position_size_pct,
        "volume_regime": volume_regime,
        "strong_uptrend": short_uptrend,
        "short_term_uptrend": short_uptrend,
        "broad_index": broad_index,
        "bearish_volume_divergence": bearish_volume_divergence,
        "notes": notes,
    }


def _format_short_term_rule_constraints(constraints: dict) -> str:
    notes = constraints.get("notes") or []
    notes_text = "\n".join(f"- {note}" for note in notes) if notes else "- none"
    return (
        "\n\n**Deterministic short-term rule constraints (hard limits; obey these over debate wording):**\n"
        f"- allowed_actions: {', '.join(constraints['allowed_actions'])}\n"
        f"- entry_mode: {constraints['entry_mode']}\n"
        f"- max_entry_size_pct: {constraints['max_entry_size_pct']:g}\n"
        f"- max_add_position_size_pct: {constraints['max_add_position_size_pct']:g}\n"
        f"- volume_regime: {constraints['volume_regime']}\n"
        f"- short_term_uptrend: {constraints.get('short_term_uptrend', 'n/a')}\n"
        f"- broad_index: {constraints.get('broad_index', 'n/a')}\n"
        f"- bearish_volume_divergence: {constraints.get('bearish_volume_divergence', 'n/a')}\n"
        f"- notes:\n{notes_text}\n"
    )


def _fallback_market_state(
    ticker: str,
    as_of_date: str,
    anchors: dict,
    volume_regime: str,
) -> MarketState:
    """Conservative deterministic MarketState when the LLM cannot emit valid JSON."""
    current = float(anchors["current_price"])
    atr = float(anchors.get("atr5") or anchors["atr14"])
    ema5 = anchors.get("ema5") or anchors.get("sma20")
    ema10 = anchors.get("ema10") or anchors.get("sma50")
    ema20 = anchors.get("ema20") or anchors.get("sma200")
    volume_ratio = anchors.get("volume_ratio")

    strong_uptrend = _is_short_term_uptrend(anchors)
    above_ema10 = ema10 is not None and current > float(ema10)
    above_ema20 = ema20 is not None and current > float(ema20)
    weak_uptrend = bool(above_ema10 and above_ema20)
    below_ema10 = ema10 is not None and current < float(ema10)

    atr_pct = float(anchors.get("atr14_pct") or 0.0)
    if atr_pct <= 0:
        volatility_regime = "unavailable"
    elif atr_pct < 1.0:
        volatility_regime = "compressed"
    elif atr_pct < 2.5:
        volatility_regime = "normal"
    elif atr_pct < 4.0:
        volatility_regime = "elevated"
    else:
        volatility_regime = "unstable"

    liquidity_regime = {
        "expanding": "volume_expansion",
        "normal": "normal",
        "soft": "volume_contraction",
        "shrinking": "volume_contraction",
        "unavailable": "unavailable",
    }.get(volume_regime, "unavailable")

    if strong_uptrend:
        trend_regime = "ascending"
        momentum_regime = "positive"
        structure_quality = "coherent"
        trend_score = 0.65
        momentum_score = 0.55
        risk_score = 0.30
        exhaustion_state = "none"
        if ema5 is not None and current > float(ema5) + 2.0 * atr:
            exhaustion_state = "positive_extension"
            risk_score = 0.45
        elif volume_ratio is not None and float(volume_ratio) >= 1.5:
            liquidity_regime = "volume_expansion"
            risk_score = 0.35
    elif weak_uptrend:
        trend_regime = "ascending"
        momentum_regime = "positive" if current > float(ema10) else "neutral"
        structure_quality = "breakout_attempt"
        trend_score = 0.35
        momentum_score = 0.25
        risk_score = 0.45
        exhaustion_state = "none"
    elif below_ema10:
        trend_regime = "descending"
        momentum_regime = "negative"
        structure_quality = "breakdown_attempt"
        trend_score = -0.35
        momentum_score = -0.25
        risk_score = 0.65
        exhaustion_state = "none"
    else:
        trend_regime = "sideways"
        momentum_regime = "neutral"
        structure_quality = "range_bound"
        if volume_regime in {"soft", "shrinking"}:
            volatility_regime = "compressed"
        trend_score = 0.0
        momentum_score = 0.0
        risk_score = 0.50
        exhaustion_state = "none"

    anchor_agreement = 0.70 if strong_uptrend or weak_uptrend or below_ema10 else 0.55
    timeframe_consistency = 0.70 if strong_uptrend else 0.55
    volatility_stability = 0.75 if volatility_regime in {"compressed", "normal"} else 0.45
    contradiction_absence = 0.65 if structure_quality != "range_bound" else 0.50
    event_certainty = 0.80
    confidence = round(
        (
            anchor_agreement
            + timeframe_consistency
            + volatility_stability
            + contradiction_absence
            + event_certainty
        )
        / 5.0,
        2,
    )

    return MarketState(
        ticker=ticker,
        as_of_date=as_of_date,
        trend_regime=trend_regime,
        volatility_regime=volatility_regime,
        momentum_regime=momentum_regime,
        liquidity_regime=liquidity_regime,
        event_regime="none",
        structure_quality=structure_quality,
        exhaustion_state=exhaustion_state,
        breadth_state="unavailable",
        trend_direction_score=trend_score,
        trend_strength=round(min(abs(trend_score) + 0.15, 1.0), 2),
        momentum_score_value=momentum_score,
        risk_pressure_score=risk_score,
        event_impact_score=0.0,
        confidence=confidence,
        confidence_components=ConfidenceComponents(
            anchor_agreement=anchor_agreement,
            timeframe_consistency=timeframe_consistency,
            volatility_stability=volatility_stability,
            contradiction_absence=contradiction_absence,
            event_certainty=event_certainty,
        ),
        horizon_days=5,
        timeframe_hierarchy=TimeframeHierarchy(
            higher_timeframe_trend=trend_regime,
            trading_timeframe_trend=trend_regime,
            lower_timeframe_trend=trend_regime,
            alignment="aligned" if trend_regime in {"ascending", "descending"} else "unclear",
            short_term_override="none",
        ),
        invalidation=InvalidationCondition(
            invalidation_type="timeframe_reclassification",
            invalidation_detail="Anchor structure changes materially at the next review.",
            reference_timeframe="trading",
        ),
        evidence=EvidenceAggregation(
            hard_anchors=[
                "Fallback state derived from price structure, moving averages, ATR, support/resistance, and volume anchors."
            ],
            event_modifiers=[],
            narrative_residual=[],
            contradictory_signals=[],
        ),
        state_summary=(
            "LLM MarketState JSON was unavailable; fallback latent-state classification "
            "was derived from hard OHLCV anchors."
        ),
        key_risks=[
            "Fallback state excludes qualitative news/fundamental nuance",
            "Single-date technical classification may be noisy",
        ],
    )


def _invoke_market_state(
    llm,
    state_prompt: str,
    ticker: str,
    as_of_date: str,
    anchors: dict,
    volume_regime: str,
) -> MarketState:
    """Invoke MarketState generation with structured output, JSON fallback, then anchors fallback."""
    structured_llm = None
    if _llm_disallows_structured_output(llm):
        logger.warning(
            "Portfolio State Manager: provider/mode does not support structured MarketState output; "
            "falling back to free-text JSON"
        )
    else:
        try:
            structured_llm = llm.with_structured_output(MarketState)
        except (NotImplementedError, AttributeError) as exc:
            logger.warning(
                "Portfolio State Manager: provider does not support structured MarketState output (%s); "
                "falling back to free-text JSON",
                exc,
            )

    if structured_llm is not None:
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message=r"Pydantic serializer warnings:.*",
                    category=UserWarning,
                )
                response = structured_llm.invoke(state_prompt)
            return _market_state_response_to_model(response)
        except Exception as exc:
            logger.warning(
                "Portfolio State Manager: structured MarketState invocation failed (%s); "
                "retrying once as free-text JSON",
                exc,
            )

    response = llm.invoke(state_prompt)
    try:
        return _market_state_response_to_model(response)
    except Exception as exc:
        content = getattr(response, "content", "")
        snippet = str(content).replace("\n", " ")[:300]
        logger.warning(
            "Portfolio State Manager: free-text MarketState JSON parse failed (%s); "
            "using deterministic anchor fallback. Response snippet: %s",
            exc,
            snippet,
        )
        return _fallback_market_state(ticker, as_of_date, anchors, volume_regime)


# Bull-phase claims that require short EMA hierarchy confirmation; if EMA disagrees,
# downgrade phase to "unclear" so the policy doesn't act on a fabricated trend.
_TRENDING_BULL_PHASES = {"healthy_bull_trend", "accelerating_bull", "bull_pullback"}

# Phases that get a high target_weight floor (>=0.50) and would commit a fresh
# 50-60%+ position on first activation. Bull hysteresis applies only to these.
_BULL_FLOOR_PHASES = {"healthy_bull_trend", "accelerating_bull", "bull_pullback"}

# Phases that force a full liquidation of an existing position. Bear hysteresis
# applies only to these — the symmetric risk to "commit 60% on noise" is
# "liquidate 100% on noise". The softer bear phases (oversold_bear, bear_rally,
# late_bear_exhaustion) already only block new entries, so they don't need it.
_BEAR_FORCE_SELL_PHASES = {
    "early_bear_reversal", "healthy_bear_trend", "accelerating_bear",
}

# Bull-side phase set for hysteresis checks.
_ANY_BULL_PHASE = {
    "early_bull_reversal", "healthy_bull_trend", "accelerating_bull",
    "overextended_bull", "bull_pullback", "late_bull_distribution",
}

# Bear-side phase set for hysteresis checks.
_ANY_BEAR_PHASE = {
    "early_bear_reversal", "healthy_bear_trend", "accelerating_bear",
    "oversold_bear", "bear_rally", "late_bear_exhaustion",
}


# Project-root-relative path to saved per-ticker strategy JSONs.
_STRATEGY_ROOT = Path(__file__).resolve().parents[3] / "back_test" / "strategy"

# Fallback regex when older strategy JSONs lack the market_state field but
# encode regime/phase in rationale_summary text.
_RATIONALE_PHASE_RE = re.compile(r"market_phase=([a-z_]+)")


def _load_recent_phases(ticker: str, trade_date: str, n: int = 2) -> list[str]:
    """Return the market_phase of the most recent N strategies before trade_date.

    Used by policy_from_market_state to apply regime-change hysteresis: when
    today's phase is "healthy_bull_trend" / "accelerating_bull" / "bull_pullback"
    (which trigger a >=50% sizing floor) but the most recent N strategies were
    not already in a bull-side phase, we treat today's claim as a single noisy flip rather than a
    confirmed regime, and downgrade to "early_bull_reversal".

    Falls back to parsing market_phase out of rationale_summary when an older
    strategy JSON lacks the structured `market_state` field.
    """
    strategy_dir = _STRATEGY_ROOT / ticker
    if not strategy_dir.exists():
        return []

    # Filenames are "{TICKER}_YYYY-MM-DD.json"; lex sort matches chronological.
    candidates = []
    prefix = f"{ticker}_"
    for path in strategy_dir.glob(f"{ticker}_*.json"):
        stem_date = path.stem[len(prefix):]
        if stem_date < trade_date:
            candidates.append((stem_date, path))
    candidates.sort()  # ascending by date
    candidates = candidates[-n:]

    phases: list[str] = []
    for _, path in candidates:
        try:
            with open(path) as fp:
                data = json.load(fp)
        except Exception:
            continue
        ms = data.get("market_state") or {}
        phase = ms.get("market_phase")
        if not phase and ms:
            try:
                phase = MarketState.model_validate(ms).market_phase
            except Exception:
                phase = None
        if not phase:
            rationale = data.get("rationale_summary") or ""
            match = _RATIONALE_PHASE_RE.search(rationale)
            if match:
                phase = match.group(1)
        if phase:
            phases.append(phase)
    return phases


def policy_from_market_state(
    state: MarketState,
    anchors: dict,
    holdings_info: dict,
    constraints: dict,
    volume_regime: str,
    recent_phases: Optional[list[str]] = None,
    policy_config: Optional[PortfolioStatePolicyConfig] = None,
    market_context_state: Optional[MarketState] = None,
    market_context_ticker: Optional[str] = None,
    trading_history_summary: Optional[dict] = None,
) -> PortfolioStrategy:
    """Deterministically convert MarketState → PortfolioStrategy.

    v1 weights are intentionally simple and pending calibration. Sizing/pricing
    logic lives here; volume regime and EMA structure are NOT re-judged from
    the LLM — they come from anchors via _classify_volume_regime and
    _is_short_term_uptrend.

    recent_phases: market_phase of the most recent prior strategies, oldest →
    newest. Used to apply hysteresis: a single LLM flip from bear/range to
    "core bull" gets downgraded to early_bull_reversal (probe size, no floor)
    until the new regime is confirmed by additional observations.
    """
    config = policy_config or PortfolioStatePolicyConfig()
    phase_modifiers = config.merged_phase_modifiers()

    current = float(anchors["current_price"])
    atr = float(anchors.get("atr5") or anchors["atr14"])
    support = anchors.get("nearest_support")
    resistance = anchors.get("nearest_resistance")
    support = float(support) if support is not None else None
    resistance = float(resistance) if resistance is not None else None

    has_position = float(holdings_info.get("quantity") or 0.0) > 0.0
    notes: list[str] = []
    market_context_blocks_add = False
    market_context_multiplier = 1.0
    if market_context_state is not None:
        context_name = market_context_ticker or market_context_state.ticker
        context_trend = max(-1.0, min(1.0, market_context_state.trend_direction_score))
        context_risk = max(0.0, min(1.0, market_context_state.risk_pressure_score))
        trend_component = max(-0.10, min(0.10, context_trend * 0.10))
        risk_component = -max(0.0, context_risk - 0.50) * 0.30
        market_context_multiplier = max(
            0.75,
            min(1.10, 1.0 + trend_component + risk_component),
        )
        market_context_blocks_add = context_risk >= 0.70 or (
            context_trend <= -0.40 and context_risk >= 0.55
        )
        notes.append(
            f"market_context={context_name}: continuous_multiplier={market_context_multiplier:.2f}, "
            f"trend_regime={market_context_state.trend_regime}, "
            f"volatility_regime={market_context_state.volatility_regime}, "
            f"momentum_regime={market_context_state.momentum_regime}, "
            f"trend_direction={context_trend:.2f}, "
            f"risk_pressure={context_risk:.2f}"
        )

    # A. Cross-check: if LLM claims uptrend but short EMA structure disagrees, downgrade.
    effective_regime = state.regime
    if state.regime in {"strong_uptrend", "weak_uptrend"} and not _is_short_term_uptrend(anchors):
        notes.append(
            f"LLM regime={state.regime} downgraded to range — EMA5/10/20 structure does not confirm short-term uptrend."
        )
        effective_regime = "range"

    # A'. Same cross-check for market_phase: trending bull phases require short EMA confirmation.
    effective_phase = state.market_phase
    if state.market_phase in _TRENDING_BULL_PHASES and not _is_short_term_uptrend(anchors):
        notes.append(
            f"LLM market_phase={state.market_phase} downgraded to unclear — EMA5/10/20 structure does not confirm trend."
        )
        effective_phase = "unclear"

    # A''. Objective check for overextended_bull. LLM tends to call "approaching
    # resistance" or "short-term momentum cooling" overextended; on broad bull
    # markets this is the norm, not a reason to exit. Require distance from
    # EMA5 to exceed 2 ATR before honoring the overextended call.
    ema5 = anchors.get("ema5")
    if state.market_phase == "overextended_bull" and ema5 is not None and atr > 0:
        distance_atr = (current - float(ema5)) / atr
        if distance_atr < config.overextended_sma20_atr_threshold:
            notes.append(
                f"LLM market_phase=overextended_bull downgraded to healthy_bull_trend — "
                f"distance from EMA5 is only {distance_atr:.2f} ATR "
                f"(< {config.overextended_sma20_atr_threshold:g} threshold)."
            )
            effective_phase = "healthy_bull_trend"

    # A'''. Bull-side hysteresis on regime change. The LLM can flip from
    # "breakdown_risk" to "healthy_bull_trend" in a single review (cf. AAPL
    # 2024-01-17 → 01-24). When that happens, an unconditional 50%+ floor
    # commits a fresh full-size position on a single noisy classification
    # right at a likely local top. Require at least one of the most recent
    # N phases to also have been bull-leaning before honoring core-bull
    # floors. Otherwise downgrade to early_bull_reversal: cap=0.40, no
    # floor, allow_add=False — i.e. probe.
    confirm_n = config.hysteresis_confirmation_count
    recent = recent_phases or []
    if (
        effective_phase in _BULL_FLOOR_PHASES
        and confirm_n > 0
        and len(recent) >= confirm_n
        and all(p not in _ANY_BULL_PHASE for p in recent[-confirm_n:])
    ):
        notes.append(
            f"hysteresis: phase={effective_phase} after recent_phases={recent[-confirm_n:]} "
            "(no prior bull confirmation); downgraded to early_bull_reversal — "
            "probe size only until trend is observed twice."
        )
        effective_phase = "early_bull_reversal"

    # A''''. Bear-side hysteresis (symmetric). The LLM can also flip from a
    # sustained bull/range into early_bear_reversal / healthy_bear_trend /
    # accelerating_bear in one review — and those phases force_sell_if_position,
    # liquidating 100% of the position on a single noisy bearish read. That
    # is the mirror of the bull-side over-commit: same noise, opposite sign.
    # When the prior 2 phases were not bear-leaning, downgrade to bear_rally —
    # block new entries, but DO NOT force_sell. Existing risk management
    # (stop_loss, take_profit) already protects the position; let it work
    # for one more cycle and only liquidate if bear is confirmed twice.
    if (
        effective_phase in _BEAR_FORCE_SELL_PHASES
        and confirm_n > 0
        and len(recent) >= confirm_n
        and all(p not in _ANY_BEAR_PHASE for p in recent[-confirm_n:])
    ):
        notes.append(
            f"hysteresis: phase={effective_phase} after recent_phases={recent[-confirm_n:]} "
            "(no prior bear confirmation); downgraded to bear_rally — "
            "block new entries but defer force_sell until bear is observed twice."
        )
        effective_phase = "bear_rally"

    # C. Broad-index uptrend override: when the ticker is a broad index ETF and
    # short EMA structure confirms uptrend, skip phase-driven block_new logic.
    # In long-running broad-market bulls, sitting out is the bigger risk than
    # adding too aggressively; defer sizing to short-term rule constraints which
    # already knows broad-index rules.
    broad_uptrend_override = (
        _is_broad_index_instrument(state.ticker) and _is_short_term_uptrend(anchors)
    )
    if broad_uptrend_override:
        notes.append("broad-index strong uptrend: phase block_new bypassed.")

    phase_mod = phase_modifiers.get(effective_phase, {})

    def _rationale(extra: Optional[list[str]] = None) -> str:
        all_notes = notes + (extra or [])
        parts = [
            state.state_summary,
            f"trend_regime={state.trend_regime}",
            f"volatility_regime={state.volatility_regime}",
            f"momentum_regime={state.momentum_regime}",
            f"liquidity_regime={state.liquidity_regime}",
            f"event_regime={state.event_regime}",
            f"structure_quality={state.structure_quality}",
            f"exhaustion_state={state.exhaustion_state}",
            f"policy_adapter_regime={effective_regime}",
            f"policy_adapter_phase={effective_phase}",
            f"trend_direction={state.trend_direction_score:.2f}",
            f"trend_strength={state.trend_strength:.2f}",
            f"momentum={state.momentum_score_value:.2f}",
            f"risk_pressure={state.risk_pressure_score:.2f}",
            f"event_impact={state.event_impact_score:.2f}",
            f"confidence={state.confidence:.2f}",
            f"volume_regime={volume_regime}",
            f"invalidation_type={state.invalidation.invalidation_type}",
            f"invalidation_detail={state.invalidation.invalidation_detail}",
            f"risks={'; '.join(state.key_risks) if state.key_risks else 'none'}",
        ]
        if all_notes:
            parts.append("notes=" + " | ".join(all_notes))
        return " | ".join(parts)

    # B. Hard regime overrides take priority over the linear formula.
    if effective_regime == "downtrend" and has_position:
        return PortfolioStrategy(
            ticker=state.ticker,
            as_of_date=state.as_of_date,
            action="SELL",
            entry=PriceSizeBlock(),
            add_position=PriceSizeBlock(),
            take_profit=PriceSizeBlock(),
            reduce_stop=PriceSizeBlock(),
            stop_loss=StopLossBlock(price=None),
            rationale_summary=_rationale(["regime=downtrend forces SELL on existing position."]),
        )

    if effective_regime == "breakdown_risk" and has_position:
        return PortfolioStrategy(
            ticker=state.ticker,
            as_of_date=state.as_of_date,
            action="SELL",
            entry=PriceSizeBlock(),
            add_position=PriceSizeBlock(),
            take_profit=PriceSizeBlock(),
            reduce_stop=PriceSizeBlock(),
            stop_loss=StopLossBlock(price=None),
            rationale_summary=_rationale(
                ["regime=breakdown_risk forces SELL on existing position."]
            ),
        )

    exhaustion_starter_phases = {"late_bear_exhaustion", "oversold_bear"}
    market_context_supportive = (
        market_context_state is not None
        and market_context_multiplier >= 1.0
        and not market_context_blocks_add
    )
    allow_exhaustion_starter = (
        effective_regime == "breakdown_risk"
        and effective_phase in exhaustion_starter_phases
        and not has_position
        and market_context_supportive
        and state.risk_pressure_score <= 0.75
    )
    if allow_exhaustion_starter:
        starter_size = 8.0 if state.risk_pressure_score <= 0.55 else 5.0
        stop_base = (
            support
            if support is not None
            else current - config.stop_loss_atr_multiple * atr
        )
        stop_price = round(min(stop_base, current - config.stop_loss_atr_multiple * atr), 2)
        take_profit_price = round(
            resistance
            if resistance is not None
            else current + config.default_take_profit_atr_multiple * atr,
            2,
        )
        return PortfolioStrategy(
            ticker=state.ticker,
            as_of_date=state.as_of_date,
            action="BUY",
            entry=PriceSizeBlock(price=None, size_pct=starter_size),
            add_position=PriceSizeBlock(),
            take_profit=PriceSizeBlock(
                price=take_profit_price,
                size_pct=config.default_take_profit_size_pct,
            ),
            reduce_stop=PriceSizeBlock(),
            stop_loss=StopLossBlock(price=stop_price),
            rationale_summary=_rationale(
                [
                    f"{effective_phase}: fixed {starter_size:g}% exhaustion starter because index context is supportive."
                ]
            ),
        )

    if effective_regime in {"breakdown_risk", "downtrend"} and not has_position:
        return PortfolioStrategy(
            ticker=state.ticker,
            as_of_date=state.as_of_date,
            action="HOLD",
            entry=PriceSizeBlock(),
            add_position=PriceSizeBlock(),
            take_profit=PriceSizeBlock(),
            reduce_stop=PriceSizeBlock(),
            stop_loss=StopLossBlock(price=None),
            rationale_summary=_rationale([f"regime={effective_regime} blocks new entries."]),
        )

    # B'. Phase-driven SELL on existing position (early/healthy/accelerating bear).
    if phase_mod.get("force_sell_if_position") and has_position:
        return PortfolioStrategy(
            ticker=state.ticker,
            as_of_date=state.as_of_date,
            action="SELL",
            entry=PriceSizeBlock(),
            add_position=PriceSizeBlock(),
            take_profit=PriceSizeBlock(),
            reduce_stop=PriceSizeBlock(),
            stop_loss=StopLossBlock(price=None),
            rationale_summary=_rationale(
                [f"market_phase={effective_phase} forces SELL on existing position."]
            ),
        )

    # B'½. Post-stop cooldown. After a stop_loss exit, prevent immediate re-entry
    # into the same name even if regime classification still looks bullish — the
    # typical whipsaw pattern is "stop → next-bar BUY at higher price → stop
    # again". Only triggers when we are currently flat (existing positions stay
    # managed by the usual trim/exit logic).
    if (
        config.post_stop_cooldown_days > 0
        and not has_position
        and trading_history_summary
    ):
        last_records = trading_history_summary.get("last_n_pnl") or []
        if last_records:
            last = last_records[-1]
            exit_date_str = last.get("exit_date")
            reason = (last.get("reason") or "").lower()
            if exit_date_str and "stop" in reason:
                try:
                    gap_days = (
                        pd.Timestamp(state.as_of_date) - pd.Timestamp(exit_date_str)
                    ).days
                except Exception:
                    gap_days = None
                if gap_days is not None and 0 <= gap_days <= config.post_stop_cooldown_days:
                    return PortfolioStrategy(
                        ticker=state.ticker,
                        as_of_date=state.as_of_date,
                        action="HOLD",
                        entry=PriceSizeBlock(),
                        add_position=PriceSizeBlock(),
                        take_profit=PriceSizeBlock(),
                        reduce_stop=PriceSizeBlock(),
                        stop_loss=StopLossBlock(price=None),
                        rationale_summary=_rationale([
                            f"post_stop_cooldown: {gap_days}d since {exit_date_str} "
                            f"{reason} exit (<= {config.post_stop_cooldown_days}d threshold) "
                            f"blocks new entry."
                        ]),
                    )

    # B''. Phase blocks new positions (bear phases, oversold_bear, bear_rally,
    # high_volatility_range, macro_event_regime). Without an existing position,
    # there is nothing to trim — return HOLD early. Skip when broad-index uptrend.
    if phase_mod.get("block_new_position") and not has_position and not broad_uptrend_override:
        return PortfolioStrategy(
            ticker=state.ticker,
            as_of_date=state.as_of_date,
            action="HOLD",
            entry=PriceSizeBlock(),
            add_position=PriceSizeBlock(),
            take_profit=PriceSizeBlock(),
            reduce_stop=PriceSizeBlock(),
            stop_loss=StopLossBlock(price=None),
            rationale_summary=_rationale(
                [f"market_phase={effective_phase} blocks new entries."]
            ),
        )

    transition_repair_structure = state.structure_quality in {
        "breakout_attempt",
        "coherent",
    } or (
        state.structure_quality == "fragmented"
        and state.risk_pressure_score <= 0.45
        and state.trend_direction_score >= 0.25
    )
    transition_repair_starter = (
        not has_position
        and effective_regime in {"unclear", "range"}
        and effective_phase in {"unclear", "early_bull_reversal"}
        and state.trend_regime == "transition"
        and state.momentum_regime == "positive"
        and transition_repair_structure
        and state.trend_direction_score >= 0.15
        and state.momentum_score_value >= 0.25
        and state.risk_pressure_score <= 0.58
        and state.confidence >= 0.70
        and volume_regime in {"soft", "normal", "expanding"}
        and not bool(constraints.get("bearish_volume_divergence"))
        and not market_context_blocks_add
    )
    if transition_repair_starter:
        starter_size = 3.0 if volume_regime == "soft" else 4.0
        if market_context_state is not None and market_context_multiplier < 1.0:
            starter_size = min(starter_size, 3.0)

        stop_floor = current - 1.2 * atr
        support_stop = support if support is not None and support < current else stop_floor
        stop_price = round(max(support_stop, stop_floor), 2)
        take_profit_price = round(
            resistance
            if resistance is not None and resistance > current
            else current + config.default_take_profit_atr_multiple * atr,
            2,
        )
        return PortfolioStrategy(
            ticker=state.ticker,
            as_of_date=state.as_of_date,
            action="BUY",
            entry=PriceSizeBlock(price=None, size_pct=starter_size),
            add_position=PriceSizeBlock(),
            take_profit=PriceSizeBlock(
                price=take_profit_price,
                size_pct=config.default_take_profit_size_pct,
            ),
            reduce_stop=PriceSizeBlock(),
            stop_loss=StopLossBlock(price=stop_price),
            rationale_summary=_rationale(
                [
                    "transition repair starter: fixed small entry for positive "
                    "breakout_attempt with controlled risk."
                ]
            ),
        )

    # C. Linear signal + regime ceilings/floors.
    # Directional score weights are intentionally modest:
    # the LLM tends to amplify directional advocacy from analyst reports
    # and risk-debate framing into score extremes, which then propagates into
    # target_weight. By halving these coefficients we keep the LLM's
    # qualitative judgment as a tilt, not a driver — regime/phase floors and
    # caps (set by SMA-anchored Python) carry the structural sizing decision.
    # risk_score weight is preserved so genuinely high-risk states still cut.
    raw_signal = (
        config.trend_score_weight * state.trend_score
        + config.momentum_score_weight * state.momentum_score
        + config.event_score_weight * state.event_score
        - config.risk_score_weight * state.risk_score
    )
    target_weight = max(0.0, raw_signal) * state.confidence

    if effective_regime == "strong_uptrend":
        target_weight = max(target_weight, config.strong_uptrend_floor)
        target_weight = min(target_weight, config.strong_uptrend_cap)
    elif effective_regime == "weak_uptrend":
        target_weight = max(target_weight, config.weak_uptrend_floor)
        target_weight = min(target_weight, config.weak_uptrend_cap)
    elif effective_regime in {"range", "unclear"}:
        target_weight = min(target_weight, config.range_cap)
    elif effective_regime == "event_driven":
        target_weight = min(target_weight, config.event_driven_cap)

    # D. Phase floor/cap. Floor implements 核心持仓 (e.g. healthy_bull_trend
    # holds >=0.50 even when raw_signal is weak); cap enforces phase-specific
    # ceilings (e.g. overextended_bull caps at 0.30). Volume is applied after
    # this so weak participation can still shrink an otherwise bullish floor.
    phase_floor = phase_mod.get("floor")
    phase_cap = phase_mod.get("cap")
    if phase_floor is not None:
        if effective_regime in {"strong_uptrend", "weak_uptrend"}:
            target_weight = max(target_weight, phase_floor)
        else:
            notes.append(
                f"phase floor ignored because effective_regime={effective_regime} "
                "is not an uptrend."
            )
    if phase_cap is not None:
        target_weight = min(target_weight, phase_cap)

    # D'. Volume regime multiplier (deterministic, anchored).
    multiplier = config.volume_multipliers.get(
        volume_regime,
        _DEFAULT_VOLUME_MULTIPLIER["unavailable"],
    )
    target_weight *= multiplier
    if volume_regime == "unavailable":
        target_weight = min(target_weight, config.unavailable_volume_cap)

    if market_context_state is not None:
        target_weight *= market_context_multiplier
        if market_context_blocks_add:
            notes.append("market_context risk is elevated: add_position blocked.")

    bearish_div = bool(constraints.get("bearish_volume_divergence"))
    if bearish_div:
        notes.append("bearish_volume_divergence: blocking new entries.")
        target_weight = 0.0
    
    target_weight = max(0.0, min(target_weight, config.max_target_weight))

    # Bearish divergence + has_position → defensive reduce_stop, not new orders.
    if bearish_div and has_position:
        stop_base = (
            support
            if support is not None
            else current - config.bearish_divergence_fallback_stop_atr * atr
        )
        stop_price = round(
            min(stop_base, current - config.bearish_divergence_stop_atr * atr), 2
        )
        reduce_price = round((stop_price + current) / 2.0, 2)
        return PortfolioStrategy(
            ticker=state.ticker,
            as_of_date=state.as_of_date,
            action="HOLD",
            entry=PriceSizeBlock(),
            add_position=PriceSizeBlock(),
            take_profit=PriceSizeBlock(),
            reduce_stop=PriceSizeBlock(
                price=reduce_price,
                size_pct=config.bearish_divergence_reduce_pct,
            ),
            stop_loss=StopLossBlock(price=stop_price),
            rationale_summary=_rationale(
                [
                    "bearish_volume_divergence: scaling out "
                    f"{config.bearish_divergence_reduce_pct:g}% via reduce_stop above hard stop."
                ]
            ),
        )

    # E. Action selection — SELL is regime-driven (handled above), not weight-driven.
    if target_weight <= config.min_trade_weight:
        return PortfolioStrategy(
            ticker=state.ticker,
            as_of_date=state.as_of_date,
            action="HOLD",
            entry=PriceSizeBlock(),
            add_position=PriceSizeBlock(),
            take_profit=PriceSizeBlock(),
            reduce_stop=PriceSizeBlock(),
            stop_loss=StopLossBlock(price=None),
            rationale_summary=_rationale(
                [f"target_weight={target_weight:.2f} below threshold; HOLD."]
            ),
        )

    # F. Build BUY orders. Phase decides entry mode and take-profit aggressiveness.
    trend_market_entry = (
        phase_mod.get("trend_market_entry") or effective_regime == "strong_uptrend"
    )
    pullback_buy = bool(phase_mod.get("pullback_buy"))
    block_new = bool(phase_mod.get("block_new_position")) and not broad_uptrend_override
    # broad_uptrend_override only relaxes the new-entry block. It must NOT force
    # allow_add=True, otherwise overextended_bull / late_bull_distribution lose
    # their explicit "no add" semantics and the policy adds against LLM warnings.
    allow_add = phase_mod.get("allow_add", True) and not market_context_blocks_add

    if block_new:
        # has_position branch — keep core, no new entry, no add. Stop and TP still set.
        entry_price = None
        entry_size = 0.0
        add_size = 0.0
    elif pullback_buy:
        # bull_pullback: we ARE in the pullback, fill at current rather than chase deeper.
        entry_price = round(current, 2)
        entry_size = round(target_weight * 100.0, 1) if not has_position else 0.0
        add_size = (
            round(
                min(
                    config.pullback_entry_add_max_pct,
                    target_weight * config.pullback_entry_add_weight_multiplier,
                ),
                1,
            )
            if has_position and allow_add
            else 0.0
        )
    elif trend_market_entry and volume_regime in {"normal", "expanding"} and not has_position:
        # 允许 trend following: market entry rather than wait for deep pullback.
        entry_price = None
        entry_size = round(target_weight * 100.0, 1)
        add_size = 0.0
    else:
        floor_price = support if support is not None else current * 0.98
        entry_price = round(max(current - 0.5 * atr, floor_price), 2)
        entry_size = round(target_weight * 100.0, 1) if not has_position else 0.0
        add_size = (
            round(
                min(
                    config.default_add_max_pct,
                    target_weight * config.default_add_weight_multiplier,
                ),
                1,
            )
            if has_position and allow_add
            else 0.0
        )

    if add_size > 0 and effective_regime == "weak_uptrend" and volume_regime == "soft":
        original_add_size = add_size
        add_size = min(add_size, config.weak_uptrend_soft_volume_add_max_pct)
        if add_size < original_add_size:
            notes.append(
                "weak uptrend with soft volume: cap add_position at "
                f"{config.weak_uptrend_soft_volume_add_max_pct:g}%."
            )

    # Stop loss: 2.5 ATR floor in trend regimes so normal volatility doesn't
    # whipsaw out. Use whichever (support or 2.5*ATR-below) is FURTHER, not closer.
    stop_base = support if support is not None else current - config.stop_loss_atr_multiple * atr
    stop_price = round(min(stop_base, current - config.stop_loss_atr_multiple * atr), 2)

    # Take-profit: for short-term trend phases, let winners clear the recent
    # 10-day high instead of taking profit too close to current price.
    recent_high_10d = anchors.get("recent_high_10d") or anchors.get("recent_high_20d")
    tp_far_phases = {"healthy_bull_trend", "accelerating_bull", "bull_pullback"}
    if effective_phase in tp_far_phases or effective_regime == "strong_uptrend":
        atr_target = current + config.trend_take_profit_atr_multiple * atr
        if recent_high_10d is not None:
            atr_target = max(
                atr_target,
                float(recent_high_10d) * config.trend_take_profit_recent_high_multiplier,
            )
        take_profit_price = round(atr_target, 2)
    else:
        take_profit_price = round(
            resistance
            if resistance is not None
            else current + config.default_take_profit_atr_multiple * atr,
            2,
        )

    phase_tp_size = phase_mod.get("tp_size")
    if phase_tp_size is not None:
        take_profit_size = phase_tp_size
    elif effective_regime == "strong_uptrend":
        take_profit_size = config.strong_uptrend_take_profit_size_pct
    else:
        take_profit_size = config.default_take_profit_size_pct

    # If phase blocks new positions but we have one, the resulting BUY-with-no-orders
    # is converted to HOLD by _enforce_strategy_rules downstream. We still emit
    # take_profit and stop_loss so risk management remains active.
    return PortfolioStrategy(
        ticker=state.ticker,
        as_of_date=state.as_of_date,
        action="BUY",
        entry=PriceSizeBlock(price=entry_price, size_pct=entry_size),
        add_position=PriceSizeBlock(price=None, size_pct=add_size),
        take_profit=PriceSizeBlock(price=take_profit_price, size_pct=take_profit_size),
        reduce_stop=PriceSizeBlock(),
        stop_loss=StopLossBlock(price=stop_price),
        rationale_summary=_rationale(
            [f"target_weight={target_weight:.2f}, phase_tp_size={take_profit_size:g}."]
        ),
    )


def _format_trading_history_section(summary: dict) -> str:
    if not summary or not summary.get("n_trades"):
        return ""
    window_days = summary.get("window_days")
    win_rate = summary.get("win_rate")
    win_rate_str = f"{win_rate:.0%}" if win_rate is not None else "n/a"
    avg_pnl = summary.get("avg_pnl")
    avg_pnl_str = f"{avg_pnl:.2f}" if avg_pnl is not None else "n/a"
    lines = [
        "- Recent realized PnL (read-only, do not chase or revenge-trade):",
        f"    window={window_days}d as_of={summary.get('as_of')}",
        f"    n_trades={summary['n_trades']}, win_rate={win_rate_str}, "
        f"total_pnl={summary.get('total_pnl', 0.0):.2f}, avg_pnl={avg_pnl_str}",
    ]
    recent = summary.get("last_n_pnl") or []
    if recent:
        compact = "; ".join(
            f"{r.get('exit_date', '?')}:{float(r.get('pnl', 0.0)):+.2f}"
            f"({r.get('reason', '?')})"
            for r in recent
        )
        lines.append(f"    recent: {compact}")
    return "\n".join(lines) + "\n"


def _format_prior_pending_orders_section(pending: list) -> str:
    if not pending:
        return ""
    lines = [
        "- Prior strategy's unfilled orders (from the immediately preceding "
        "review; left unfilled because price did not trigger). They will be "
        "cancelled when this strategy activates — treat as context, not as "
        "open exposure:",
    ]
    for o in pending:
        parts = [
            f"type={o.get('order_type')}",
            f"limit={o.get('limit_price')}",
            f"size_pct={o.get('size_pct')}",
        ]
        if o.get("stop_loss") is not None:
            parts.append(f"stop_loss={o.get('stop_loss')}")
        lines.append("    " + ", ".join(parts))
    return "\n".join(lines) + "\n"


def _format_holdings_section(holdings_info: dict) -> str:
    if not holdings_info:
        return ""
    quantity = float(holdings_info.get("quantity") or 0.0)
    cash = holdings_info.get("cash")
    avg_buy_price = holdings_info.get("avg_buy_price")
    mark_price = holdings_info.get("mark_price")
    equity = holdings_info.get("equity")
    stop_loss = holdings_info.get("stop_loss")
    if quantity > 0:
        return (
            "- Current simulated holdings: "
            f"{quantity:g} shares"
            + (f", average buy price {float(avg_buy_price):g}" if avg_buy_price is not None else "")
            + (f", mark price {float(mark_price):g}" if mark_price is not None else "")
            + (f", active stop {float(stop_loss):g}" if stop_loss is not None else "")
            + (f", cash {float(cash):g}" if cash is not None else "")
            + (f", equity {float(equity):g}" if equity is not None else "")
            + ". Manage this existing position; do not behave as if the portfolio is flat.\n"
        )
    return (
        "- Current simulated holdings: no open position"
        + (f", cash {float(cash):g}" if cash is not None else "")
        + (f", equity {float(equity):g}" if equity is not None else "")
        + ". Holdings context is provided only to preserve state awareness; do not infer a trade action from it.\n"
    )


def _passthrough_debate_state(risk_debate_state: dict, decision_text: str) -> dict:
    return {
        "judge_decision": decision_text,
        "history": risk_debate_state["history"],
        "aggressive_history": risk_debate_state["aggressive_history"],
        "conservative_history": risk_debate_state["conservative_history"],
        "neutral_history": risk_debate_state["neutral_history"],
        "latest_speaker": "Judge",
        "current_aggressive_response": risk_debate_state["current_aggressive_response"],
        "current_conservative_response": risk_debate_state["current_conservative_response"],
        "current_neutral_response": risk_debate_state["current_neutral_response"],
        "count": risk_debate_state["count"],
    }


def _compute_market_context_state(
    context_ticker: str,
    trade_date: str,
) -> tuple[Optional[MarketState], Optional[dict], str]:
    context_anchors = _compute_short_term_market_anchors(context_ticker, trade_date)
    if context_anchors is None:
        return None, None, "unavailable"
    context_volume_regime = _classify_volume_regime(context_anchors.get("volume_ratio"))
    context_state = _fallback_market_state(
        context_ticker,
        context_anchors["as_of_close_date"],
        context_anchors,
        context_volume_regime,
    )
    return context_state, context_anchors, context_volume_regime


def create_portfolio_state_manager(
    llm,
    memory,
    policy_config: Optional[dict[str, Any] | PortfolioStatePolicyConfig] = None,
):
    """Backtest-only Portfolio Manager that uses MarketState + deterministic policy.

    The LLM emits a qualitative MarketState; policy_from_market_state builds the
    PortfolioStrategy from anchors and rule constraints; _enforce_strategy_rules
    runs as the final gate.
    """

    resolved_policy_config = coerce_portfolio_state_policy_config(policy_config)

    def portfolio_state_manager_node(state) -> dict:
        instrument_context = build_instrument_context(state["company_of_interest"])
        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        research_plan = state["investment_plan"]
        trader_plan = state["trader_investment_plan"]
        holdings_info = state.get("holdings_info") or {}
        trading_history_summary = state.get("trading_history_summary") or {}
        prior_pending_orders = state.get("prior_pending_orders") or []
        ticker = state["company_of_interest"]
        trade_date = state["trade_date"]

        curr_situation = (
            f"{state['market_report']}\n\n{state['sentiment_report']}\n\n"
            f"{state['news_report']}\n\n{state['fundamentals_report']}"
        )
        past_memories = memory.get_memories(curr_situation, n_matches=2)
        past_memory_str = "".join(rec["recommendation"] + "\n\n" for rec in past_memories)
        lessons_section = (
            f"- Lessons from past decisions: **{past_memory_str}**\n" if past_memory_str else ""
        )

        anchors = _compute_short_term_market_anchors(ticker, trade_date)
        if anchors is not None:
            anchor_date = anchors.get("as_of_close_date")
            staleness = ""
            if anchor_date and anchor_date != trade_date:
                staleness = f" ⚠ STALE (Δ vs trade_date={trade_date})"
            print(
                f"[portfolio_state_manager] anchors {ticker} "
                f"trade_date={trade_date} as_of={anchor_date}{staleness} "
                f"current={anchors.get('current_price')} atr5/14={anchors.get('atr5')}/{anchors.get('atr14')} "
                f"support={anchors.get('nearest_support')} "
                f"resistance={anchors.get('nearest_resistance')} "
                f"recent_high_5d/10d={anchors.get('recent_high_5d')}/{anchors.get('recent_high_10d')} "
                f"ema5/10/20={anchors.get('ema5')}/{anchors.get('ema10')}/{anchors.get('ema20')} "
                f"vol_ratio={anchors.get('volume_ratio')}",
                flush=True,
            )
        if anchors is None:
            empty = PortfolioStrategy(
                ticker=ticker,
                as_of_date=trade_date,
                action="HOLD",
                entry=PriceSizeBlock(),
                add_position=PriceSizeBlock(),
                take_profit=PriceSizeBlock(),
                reduce_stop=PriceSizeBlock(),
                stop_loss=StopLossBlock(price=None),
                rationale_summary="No OHLCV anchors available; defaulting to HOLD.",
            ).model_dump()
            decision_text = (
                f"Decision: HOLD\n"
                f"MarketState: unavailable (no anchors)\n"
                f"Rationale: {empty['rationale_summary']}\n"
                f"Structured strategy schema_version={empty['schema_version']}"
            )
            return {
                "risk_debate_state": _passthrough_debate_state(risk_debate_state, decision_text),
                "final_trade_decision": decision_text,
                "market_state": None,
                "structure_analysis": None,
                "structured_strategy": empty,
            }

        constraints = _derive_short_term_rule_constraints(anchors, holdings_info, ticker)
        volume_regime = _classify_volume_regime(anchors.get("volume_ratio"))
        anchors_block = "\n\n" + _format_short_term_market_anchors(anchors)
        as_of_date = anchors["as_of_close_date"]
        holdings_section = _format_holdings_section(holdings_info)
        trading_history_section = _format_trading_history_section(trading_history_summary)
        prior_pending_section = _format_prior_pending_orders_section(prior_pending_orders)

        state_prompt = f"""You are the MarketState classifier for a multi-agent quantitative trading architecture. In backtest mode your job is NOT to create executable orders. You only classify the latent market environment.

        {instrument_context}

        You are NOT allowed to output:
        - entry / add / take-profit / reduce-stop / stop-loss prices
        - position sizes
        - BUY / SELL / HOLD trade orders
        - target prices or allocation percentages
        - labels whose meaning is equivalent to a trading instruction

        Your only job: answer "what statistical environment currently exists?" and compress the evidence into stable, testable state variables.

        Return only a MarketState object through the configured schema. If schema/tool
        output is unavailable, return only a raw JSON object with these exact fields.

        **Evidence priority architecture:**
        Phase 1 — hard anchors dominate:
        price structure, EMA hierarchy, ATR / realized-volatility behavior, support/resistance location, and volume structure.
        Phase 2 — event modifiers:
        earnings, macro prints, filings, policy decisions, and identifiable shocks may modify the anchor-derived state.
        Phase 3 — narrative residual:
        analyst rhetoric, debate tone, headlines, and confidence language are low-weight residuals. They must never dominate anchor-derived structure.

        **Anti-narrative contamination directive:**
        The inputs below contain three advocacy channels that you must NOT take at face value:
        (a) Bull / Bear researcher arguments embedded in the Research Manager's plan.
        (b) Aggressive / Conservative / Neutral analysts in the Risk Analysts Debate.
        (c) Subjective adjectives in news, sentiment, or fundamentals reports.
        These channels are RHETORIC, not evidence. They are designed to take a side. Do NOT let the volume, intensity, or polarity of bullish or bearish framing decide your scores.

        Equal advocacy on both sides means contradictory narrative residuals, not a reason to choose the louder side.

        **MarketState schema and ontology:**
        - schema_version: always "state_v2".
        - trend_regime: ascending / descending / sideways / transition / unclear.
          Describes price-structure direction across the trading horizon. It is not a trade instruction.
        - volatility_regime: compressed / normal / expanding / elevated / shock / unstable / unavailable.
          Describes dispersion and stability of realized movement.
        - momentum_regime: positive / negative / neutral / divergent / mean_reverting / unclear.
          Describes recent impulse; do not mix with exhaustion.
        - liquidity_regime: normal / volume_expansion / volume_contraction / thin / imbalanced / unavailable.
          Describes participation and volume behavior.
        - event_regime: none / scheduled_event / earnings_dominant / macro_dominant / policy_dominant / idiosyncratic_shock / multi_event / unclear.
          Describes whether concrete events dominate state estimation.
        - structure_quality: coherent / range_bound / fragmented / breakout_attempt / breakdown_attempt / damaged / unclear.
          Describes whether anchors form a stable interpretable structure.
        - exhaustion_state: none / positive_extension / negative_extension / two_sided_chop / late_trend_fatigue / unclear.
          Describes extension/fatigue, separate from trend and momentum.
        - breadth_state: broad_participation / narrow_participation / divergent / neutral / not_applicable / unavailable.
          Use not_applicable for single names when no market/sector breadth data is present; use unavailable when relevant breadth evidence is missing.
        - trend_direction_score [-1, 1]: signed directionality of observed structure.
        - trend_strength [0, 1]: persistence/clarity of trend structure independent of direction.
        - momentum_score_value [-1, 1]: signed recent impulse.
        - risk_pressure_score [0, 1]: state instability from structure, volatility, liquidity, and events.
        - event_impact_score [-1, 1]: signed event pressure on the observed state, not analyst opinion.
        - confidence [0, 1]: evidence consistency only.
        - confidence_components:
            anchor_agreement, timeframe_consistency, volatility_stability,
            contradiction_absence, event_certainty. The top-level confidence should be consistent with these components.
        - timeframe_hierarchy:
            higher_timeframe_trend, trading_timeframe_trend, lower_timeframe_trend,
            alignment, short_term_override.
        - invalidation:
            invalidation_type must be one of structure_break, volatility_expansion, failed_breakout,
            failed_breakdown, momentum_divergence, event_shock, liquidity_shift,
            timeframe_reclassification, data_revision, unclear.
            invalidation_detail must be specific and machine-readable enough for later study.
        - evidence:
            hard_anchors, event_modifiers, narrative_residual, contradictory_signals.
            Put analyst rhetoric in narrative_residual only after extracting anchor-grounded content.
        - state_summary: neutral description of the environment. Do not include trade recommendations.
        - key_risks: short state-instability phrases, not execution advice.

        **Timeframe hierarchy logic:**
        Higher timeframe structure has precedence over lower timeframe noise.
        A lower-timeframe move may override only when there is:
        - confirmed_structure_break
        - confirmed_structure_reclaim
        - volatility_shock
        - event_shock
        - liquidity_dislocation
        Distinguish pullback_against_higher_timeframe from countertrend_move:
        a pullback preserves higher-timeframe structure; a countertrend move conflicts with it but has not yet reclassified it.

        **Confidence calculation philosophy:**
        Confidence is high only when hard anchors agree, timeframe reads align, volatility is stable,
        contradictory signals are limited, and event uncertainty is low.
        Confidence is low when anchors conflict, lower timeframe noise contradicts higher timeframe structure,
        volatility is unstable, or concrete event risk dominates.
        Never increase confidence because language sounds certain.

        Use ticker exactly: {ticker}.
        Use as_of_date exactly: {as_of_date}.

        Anchors below are context for state classification. DO NOT echo numbers as orders.

        **Context:**
        - Research Manager's plan: {research_plan}
        - Trader's proposal: {trader_plan}
        {lessons_section}{holdings_section}{trading_history_section}{prior_pending_section}**Risk Analysts Debate:**
        {history}
        {anchors_block}

        Do not output trading orders, prices, sizes, markdown, or fenced code blocks.
        Do not output text outside the schema/JSON object.{get_language_instruction()}"""

        market_state = _invoke_market_state(
            llm,
            state_prompt,
            ticker,
            as_of_date,
            anchors,
            volume_regime,
        )

        market_context_state = None
        market_context_volume_regime = "unavailable"
        if resolved_policy_config.market_context_enabled:
            context_ticker = resolved_policy_config.market_context_ticker
            if context_ticker:
                market_context_state, context_anchors, market_context_volume_regime = (
                    _compute_market_context_state(context_ticker, trade_date)
                )
                if context_anchors is not None and market_context_state is not None:
                    print(
                        f"[portfolio_state_manager] market_context {context_ticker} "
                        f"trade_date={trade_date} "
                        f"as_of={context_anchors.get('as_of_close_date')} "
                        f"trend_regime={market_context_state.trend_regime} "
                        f"volatility_regime={market_context_state.volatility_regime} "
                        f"momentum_regime={market_context_state.momentum_regime} "
                        f"current={context_anchors.get('current_price')} "
                        f"ema5/10/20={context_anchors.get('ema5')}/"
                        f"{context_anchors.get('ema10')}/{context_anchors.get('ema20')} "
                        f"vol_ratio={context_anchors.get('volume_ratio')}",
                        flush=True,
                    )

        # Hysteresis input: load most recent N prior strategies' market_phase
        # so policy can detect single-flip regime changes (e.g. 3 weeks of
        # breakdown_risk → 1 week of healthy_bull_trend = probe, not commit).
        recent_phases = _load_recent_phases(
            ticker,
            trade_date,
            n=resolved_policy_config.recent_phase_lookback,
        )

        strategy_dict = policy_from_market_state(
            market_state, anchors, holdings_info, constraints, volume_regime,
            recent_phases=recent_phases,
            policy_config=resolved_policy_config,
            market_context_state=market_context_state,
            market_context_ticker=resolved_policy_config.market_context_ticker,
            trading_history_summary=trading_history_summary,
        ).model_dump()
        strategy_dict = _enforce_strategy_rules(
            strategy_dict, anchors, constraints, holdings_info
        )
        strategy_dict = _apply_order_size_multiplier(
            strategy_dict,
            resolved_policy_config.order_size_multiplier,
        )

        if market_context_state is not None:
            market_context_text = (
                f"MarketContext: ticker={resolved_policy_config.market_context_ticker}, "
                f"trend_regime={market_context_state.trend_regime}, "
                f"volatility_regime={market_context_state.volatility_regime}, "
                f"momentum_regime={market_context_state.momentum_regime}, "
                f"liquidity_regime={market_context_state.liquidity_regime}, "
                f"structure_quality={market_context_state.structure_quality}, "
                f"risk_pressure={market_context_state.risk_pressure_score:.2f}, "
                f"confidence={market_context_state.confidence:.2f}, "
                f"volume_regime={market_context_volume_regime}\n"
            )
        else:
            market_context_text = "MarketContext: unavailable\n"

        decision_text = (
            f"Decision: {strategy_dict['action']}\n"
            f"MarketState: trend_regime={market_state.trend_regime}, "
            f"volatility_regime={market_state.volatility_regime}, "
            f"momentum_regime={market_state.momentum_regime}, "
            f"liquidity_regime={market_state.liquidity_regime}, "
            f"event_regime={market_state.event_regime}, "
            f"structure_quality={market_state.structure_quality}, "
            f"exhaustion_state={market_state.exhaustion_state}, "
            f"trend_direction={market_state.trend_direction_score:.2f}, "
            f"trend_strength={market_state.trend_strength:.2f}, "
            f"momentum={market_state.momentum_score_value:.2f}, "
            f"risk_pressure={market_state.risk_pressure_score:.2f}, "
            f"event_impact={market_state.event_impact_score:.2f}, "
            f"confidence={market_state.confidence:.2f}, "
            f"volume_regime={volume_regime}\n"
            f"{market_context_text}"
            f"Rationale: {strategy_dict.get('rationale_summary', '')}\n"
            f"Structured strategy schema_version={strategy_dict['schema_version']}"
        )

        return {
            "risk_debate_state": _passthrough_debate_state(risk_debate_state, decision_text),
            "final_trade_decision": decision_text,
            "market_state": market_state.model_dump(),
            "structure_analysis": anchors.get("structure_analysis"),
            "market_context_state": (
                market_context_state.model_dump()
                if market_context_state is not None
                else None
            ),
            "structured_strategy": strategy_dict,
        }

    return portfolio_state_manager_node


def create_market_aware_portfolio_state_manager(
    llm,
    memory,
    policy_config: Optional[dict[str, Any] | PortfolioStatePolicyConfig] = None,
):
    """Backtest PortfolioState manager with continuous stock + index context."""
    return create_portfolio_state_manager(llm, memory, policy_config=policy_config)
