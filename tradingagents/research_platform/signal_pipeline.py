"""Small pipeline helpers that connect agent artifacts to risk review."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict

from .agent_artifacts import trade_signal_from_legacy_decision
from .agent_contracts import TradeHorizon, TradeSignal
from .risk_contracts import RiskPolicy, RiskReview, evaluate_basic_risk


class SignalRiskResult(BaseModel):
    """A validated trade signal paired with its deterministic risk review."""

    model_config = ConfigDict(frozen=True)

    signal: TradeSignal
    risk_review: RiskReview


def review_legacy_decision(
    *,
    symbol: str,
    as_of_date: date,
    decision_text: str,
    policy: RiskPolicy | None = None,
    confidence: float = 0.5,
    horizon: TradeHorizon = TradeHorizon.MEDIUM,
    current_position_pct: float = 0.0,
    portfolio_drawdown_pct: float = 0.0,
    realized_volatility_pct: float | None = None,
) -> SignalRiskResult:
    """Convert a legacy PM decision to TradeSignal, then run risk review."""

    active_policy = policy or RiskPolicy()
    signal = trade_signal_from_legacy_decision(
        symbol=symbol,
        as_of_date=as_of_date,
        decision_text=decision_text,
        confidence=confidence,
        horizon=horizon,
    )
    review = evaluate_basic_risk(
        signal,
        active_policy,
        current_position_pct=current_position_pct,
        portfolio_drawdown_pct=portfolio_drawdown_pct,
        realized_volatility_pct=realized_volatility_pct,
    )
    return SignalRiskResult(signal=signal, risk_review=review)
