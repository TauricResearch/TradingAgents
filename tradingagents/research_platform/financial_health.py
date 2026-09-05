"""Transparent financial-health checks over disclosed quality metrics."""

from __future__ import annotations

from enum import Enum
from math import isfinite

from pydantic import BaseModel, ConfigDict, Field

from .data_contracts import FundamentalSnapshot


class FinancialHealthStatus(str, Enum):
    HEALTHY = "healthy"
    WATCH = "watch"
    CAUTION = "caution"
    UNKNOWN = "unknown"


class FinancialHealthCheck(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    status: FinancialHealthStatus
    observed: float | None = None
    threshold: float
    message: str


class FinancialHealthAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: FinancialHealthStatus
    score: int = Field(ge=0, le=4)
    checks: list[FinancialHealthCheck]


def assess_financial_health(snapshot: FundamentalSnapshot | None) -> FinancialHealthAssessment:
    """Assess only disclosed metrics; missing values remain explicit unknowns."""

    metrics = snapshot.metrics if snapshot is not None else {}
    checks = [
        _minimum_check(
            "cash_conversion",
            _number(metrics.get("operating_cashflow_to_net_income_ratio")),
            0.8,
            "Operating cash flow relative to net income",
        ),
        _maximum_check(
            "leverage",
            _number(metrics.get("debt_to_assets_pct")),
            60.0,
            "Debt-to-assets percentage",
        ),
        _minimum_check(
            "liquidity",
            _number(metrics.get("current_ratio")),
            1.0,
            "Current ratio",
        ),
        _minimum_check(
            "return_on_equity",
            _number(metrics.get("return_on_equity_pct")),
            10.0,
            "Return on equity percentage",
        ),
    ]
    score = sum(check.status == FinancialHealthStatus.HEALTHY for check in checks)
    known = [check for check in checks if check.status != FinancialHealthStatus.UNKNOWN]
    status = (
        FinancialHealthStatus.UNKNOWN
        if not known
        else FinancialHealthStatus.CAUTION
        if any(check.status == FinancialHealthStatus.CAUTION for check in known)
        else FinancialHealthStatus.HEALTHY
        if score == len(checks)
        else FinancialHealthStatus.WATCH
    )
    return FinancialHealthAssessment(status=status, score=score, checks=checks)


def _minimum_check(
    name: str, observed: float | None, threshold: float, label: str
) -> FinancialHealthCheck:
    if observed is None:
        return FinancialHealthCheck(
            name=name,
            status=FinancialHealthStatus.UNKNOWN,
            threshold=threshold,
            message=f"{label} is unavailable.",
        )
    status = FinancialHealthStatus.HEALTHY if observed >= threshold else FinancialHealthStatus.WATCH
    return FinancialHealthCheck(
        name=name,
        status=status,
        observed=observed,
        threshold=threshold,
        message=f"{label} is {'inside' if status == FinancialHealthStatus.HEALTHY else 'below'} the reference threshold.",
    )


def _maximum_check(
    name: str, observed: float | None, threshold: float, label: str
) -> FinancialHealthCheck:
    if observed is None:
        return FinancialHealthCheck(
            name=name,
            status=FinancialHealthStatus.UNKNOWN,
            threshold=threshold,
            message=f"{label} is unavailable.",
        )
    status = (
        FinancialHealthStatus.HEALTHY if observed <= threshold else FinancialHealthStatus.CAUTION
    )
    return FinancialHealthCheck(
        name=name,
        status=status,
        observed=observed,
        threshold=threshold,
        message=f"{label} is {'inside' if status == FinancialHealthStatus.HEALTHY else 'above'} the reference threshold.",
    )


def _number(value: object) -> float | None:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return None
    number = float(value)
    return number if isfinite(number) else None
