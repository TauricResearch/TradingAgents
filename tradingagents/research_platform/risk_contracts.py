"""Deterministic risk review contracts for validated trade signals."""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from .agent_contracts import TradeDirection, TradeSignal


class RiskDecision(str, Enum):
    APPROVE = "approve"
    REDUCE = "reduce"
    REJECT = "reject"
    WATCH = "watch"


class RiskSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    BLOCKER = "blocker"


class RiskPolicy(BaseModel):
    """Personal portfolio-level risk policy."""

    model_config = ConfigDict(frozen=True)

    max_single_position_pct: float = Field(default=0.10, gt=0.0, le=1.0)
    default_position_pct: float = Field(default=0.03, ge=0.0, le=1.0)
    min_signal_confidence: float = Field(default=0.55, ge=0.0, le=1.0)
    max_portfolio_drawdown_pct: float = Field(default=0.15, ge=0.0, le=1.0)
    max_realized_volatility_pct: float | None = Field(default=None, gt=0.0)
    max_gross_exposure_pct: float = Field(default=1.0, gt=0.0, le=1.0)
    min_cash_pct: float = Field(default=0.0, ge=0.0, le=1.0)


class RiskRuleResult(BaseModel):
    """Evaluation result for one deterministic risk rule."""

    model_config = ConfigDict(frozen=True)

    rule: str = Field(min_length=1)
    passed: bool
    observed: float | str
    limit: float | str
    severity: RiskSeverity = RiskSeverity.INFO
    message: str = Field(min_length=1)
    recommended_action: str | None = None


class RiskLimitBreach(BaseModel):
    """One breached risk rule."""

    model_config = ConfigDict(frozen=True)

    rule: str = Field(min_length=1)
    observed: float | str
    limit: float | str
    message: str = Field(min_length=1)
    severity: RiskSeverity = RiskSeverity.WARNING
    recommended_action: str | None = None


class RiskReview(BaseModel):
    """Final deterministic risk artifact for a signal."""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1)
    as_of_date: date
    decision: RiskDecision
    approved_position_pct: float = Field(ge=0.0, le=1.0)
    breaches: list[RiskLimitBreach] = Field(default_factory=list)
    rule_results: list[RiskRuleResult] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def evaluate_basic_risk(
    signal: TradeSignal,
    policy: RiskPolicy,
    *,
    current_position_pct: float = 0.0,
    portfolio_drawdown_pct: float = 0.0,
    realized_volatility_pct: float | None = None,
    portfolio_gross_exposure_pct: float = 0.0,
    cash_pct: float = 1.0,
) -> RiskReview:
    """Apply a small deterministic risk policy to a validated signal."""

    breaches: list[RiskLimitBreach] = []
    rule_results: list[RiskRuleResult] = []
    notes: list[str] = []

    proposed = signal.proposed_position_pct
    if proposed is None:
        proposed = 0.0 if signal.direction == TradeDirection.HOLD else policy.default_position_pct

    approved = min(proposed, policy.max_single_position_pct)
    decision = RiskDecision.APPROVE

    if signal.direction == TradeDirection.HOLD:
        rule_results.append(
            RiskRuleResult(
                rule="hold_signal",
                passed=True,
                observed=signal.direction.value,
                limit="no_new_risk",
                severity=RiskSeverity.INFO,
                message="Hold signal does not add portfolio risk.",
                recommended_action="watch",
            )
        )
        return RiskReview(
            symbol=signal.symbol,
            as_of_date=signal.as_of_date,
            decision=RiskDecision.WATCH,
            approved_position_pct=current_position_pct,
            rule_results=rule_results,
            notes=["Hold signal does not add portfolio risk."],
        )

    if signal.confidence < policy.min_signal_confidence:
        _record_rule(
            breaches,
            rule_results,
            rule="min_signal_confidence",
            passed=False,
            observed=signal.confidence,
            limit=policy.min_signal_confidence,
            severity=RiskSeverity.BLOCKER,
            message="Signal confidence is below the risk policy floor.",
            recommended_action="reject",
        )
        decision = RiskDecision.REJECT
        approved = 0.0
    else:
        _record_rule(
            breaches,
            rule_results,
            rule="min_signal_confidence",
            passed=True,
            observed=signal.confidence,
            limit=policy.min_signal_confidence,
            severity=RiskSeverity.INFO,
            message="Signal confidence satisfies the policy floor.",
        )

    if portfolio_drawdown_pct > policy.max_portfolio_drawdown_pct:
        _record_rule(
            breaches,
            rule_results,
            rule="max_portfolio_drawdown_pct",
            passed=False,
            observed=portfolio_drawdown_pct,
            limit=policy.max_portfolio_drawdown_pct,
            severity=RiskSeverity.BLOCKER,
            message="Portfolio drawdown limit is breached.",
            recommended_action="reject",
        )
        decision = RiskDecision.REJECT
        approved = 0.0
    else:
        _record_rule(
            breaches,
            rule_results,
            rule="max_portfolio_drawdown_pct",
            passed=True,
            observed=portfolio_drawdown_pct,
            limit=policy.max_portfolio_drawdown_pct,
            severity=RiskSeverity.INFO,
            message="Portfolio drawdown is inside the policy limit.",
        )

    if proposed > policy.max_single_position_pct and decision != RiskDecision.REJECT:
        _record_rule(
            breaches,
            rule_results,
            rule="max_single_position_pct",
            passed=False,
            observed=proposed,
            limit=policy.max_single_position_pct,
            severity=RiskSeverity.WARNING,
            message="Proposed position exceeds single-name cap.",
            recommended_action="reduce_to_limit",
        )
        decision = RiskDecision.REDUCE
        notes.append("Position capped at policy maximum.")
    elif decision != RiskDecision.REJECT:
        _record_rule(
            breaches,
            rule_results,
            rule="max_single_position_pct",
            passed=True,
            observed=proposed,
            limit=policy.max_single_position_pct,
            severity=RiskSeverity.INFO,
            message="Proposed position is inside the single-name cap.",
        )

    available_exposure = max(0.0, policy.max_gross_exposure_pct - portfolio_gross_exposure_pct)
    if approved > available_exposure and decision != RiskDecision.REJECT:
        _record_rule(
            breaches,
            rule_results,
            rule="max_gross_exposure_pct",
            passed=False,
            observed=portfolio_gross_exposure_pct + approved,
            limit=policy.max_gross_exposure_pct,
            severity=RiskSeverity.WARNING if available_exposure > 0 else RiskSeverity.BLOCKER,
            message="Portfolio gross exposure would exceed the policy limit.",
            recommended_action="reduce_to_available_exposure" if available_exposure > 0 else "reject",
        )
        approved = min(approved, available_exposure)
        decision = RiskDecision.REDUCE if approved > 0 else RiskDecision.REJECT
        notes.append("Position reduced to fit remaining gross exposure budget.")
    elif decision != RiskDecision.REJECT:
        _record_rule(
            breaches,
            rule_results,
            rule="max_gross_exposure_pct",
            passed=True,
            observed=portfolio_gross_exposure_pct + approved,
            limit=policy.max_gross_exposure_pct,
            severity=RiskSeverity.INFO,
            message="Portfolio gross exposure remains inside the policy limit.",
        )

    max_position_with_cash_floor = max(0.0, cash_pct - policy.min_cash_pct)
    if signal.direction == TradeDirection.BUY and approved > max_position_with_cash_floor and decision != RiskDecision.REJECT:
        _record_rule(
            breaches,
            rule_results,
            rule="min_cash_pct",
            passed=False,
            observed=cash_pct - approved,
            limit=policy.min_cash_pct,
            severity=RiskSeverity.WARNING if max_position_with_cash_floor > 0 else RiskSeverity.BLOCKER,
            message="Trade would leave cash below the policy floor.",
            recommended_action="reduce_to_cash_budget" if max_position_with_cash_floor > 0 else "reject",
        )
        approved = min(approved, max_position_with_cash_floor)
        decision = RiskDecision.REDUCE if approved > 0 else RiskDecision.REJECT
        notes.append("Position reduced to preserve the cash floor.")
    elif signal.direction == TradeDirection.BUY and decision != RiskDecision.REJECT:
        _record_rule(
            breaches,
            rule_results,
            rule="min_cash_pct",
            passed=True,
            observed=cash_pct - approved,
            limit=policy.min_cash_pct,
            severity=RiskSeverity.INFO,
            message="Cash floor remains satisfied after the approved trade.",
        )

    if (
        realized_volatility_pct is not None
        and policy.max_realized_volatility_pct is not None
        and realized_volatility_pct > policy.max_realized_volatility_pct
        and decision != RiskDecision.REJECT
    ):
        _record_rule(
            breaches,
            rule_results,
            rule="max_realized_volatility_pct",
            passed=False,
            observed=realized_volatility_pct,
            limit=policy.max_realized_volatility_pct,
            severity=RiskSeverity.WARNING,
            message="Realized volatility is above the policy limit.",
            recommended_action="reduce_to_default_size",
        )
        decision = RiskDecision.REDUCE
        approved = min(approved, policy.default_position_pct)
        notes.append("Volatility breach reduces position to the default size.")
    elif policy.max_realized_volatility_pct is not None and realized_volatility_pct is not None and decision != RiskDecision.REJECT:
        _record_rule(
            breaches,
            rule_results,
            rule="max_realized_volatility_pct",
            passed=True,
            observed=realized_volatility_pct,
            limit=policy.max_realized_volatility_pct,
            severity=RiskSeverity.INFO,
            message="Realized volatility is inside the policy limit.",
        )

    return RiskReview(
        symbol=signal.symbol,
        as_of_date=signal.as_of_date,
        decision=decision,
        approved_position_pct=approved,
        breaches=breaches,
        rule_results=rule_results,
        notes=notes,
    )


def _record_rule(
    breaches: list[RiskLimitBreach],
    rule_results: list[RiskRuleResult],
    *,
    rule: str,
    passed: bool,
    observed: float | str,
    limit: float | str,
    severity: RiskSeverity,
    message: str,
    recommended_action: str | None = None,
) -> None:
    rule_results.append(
        RiskRuleResult(
            rule=rule,
            passed=passed,
            observed=observed,
            limit=limit,
            severity=severity,
            message=message,
            recommended_action=recommended_action,
        )
    )
    if not passed:
        breaches.append(
            RiskLimitBreach(
                rule=rule,
                observed=observed,
                limit=limit,
                message=message,
                severity=severity,
                recommended_action=recommended_action,
            )
        )
