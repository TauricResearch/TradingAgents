"""Descriptive historical context for cached daily valuation snapshots."""

from __future__ import annotations

from collections.abc import Iterable
from math import isfinite
from statistics import median

from pydantic import BaseModel, ConfigDict, Field

from .data_contracts import FundamentalSnapshot

_MINIMUM_OBSERVATIONS = 20
_MAXIMUM_OBSERVATIONS = 252
_METRICS = (
    ("pe_ratio_ttm", "P/E (TTM)"),
    ("price_to_book", "Price to Book"),
    ("price_to_sales_ttm", "Price to Sales (TTM)"),
    ("dividend_yield_pct", "Dividend Yield (%)"),
)


class ValuationMetricContext(BaseModel):
    """One valuation metric relative to the same instrument's cached history."""

    model_config = ConfigDict(frozen=True)

    key: str
    label: str
    latest: float | None = None
    observations: int = Field(ge=0)
    minimum_observations: int = Field(ge=1)
    available: bool
    percentile: float | None = Field(default=None, ge=0.0, le=100.0)
    low: float | None = None
    median: float | None = None
    high: float | None = None


class ValuationContext(BaseModel):
    """Point-in-time valuation context without a trade recommendation."""

    model_config = ConfigDict(frozen=True)

    as_of_date: str | None = None
    available: bool
    daily_snapshot_count: int = Field(ge=0)
    metrics: list[ValuationMetricContext]


def build_valuation_context(
    snapshots: Iterable[FundamentalSnapshot],
    *,
    minimum_observations: int = _MINIMUM_OBSERVATIONS,
    maximum_observations: int = _MAXIMUM_OBSERVATIONS,
) -> ValuationContext:
    """Compare current multiples only with the same symbol's cached history."""

    if minimum_observations < 1:
        raise ValueError("minimum_observations must be positive")
    if maximum_observations < minimum_observations:
        raise ValueError("maximum_observations must be at least minimum_observations")

    history = _daily_history(snapshots)[-maximum_observations:]
    latest = history[-1] if history else None
    metric_contexts = [
        _metric_context(
            key,
            label,
            history,
            minimum_observations=minimum_observations,
        )
        for key, label in _METRICS
    ]
    return ValuationContext(
        as_of_date=latest.period_end.isoformat() if latest is not None else None,
        available=any(item.available for item in metric_contexts),
        daily_snapshot_count=len(history),
        metrics=metric_contexts,
    )


def _daily_history(snapshots: Iterable[FundamentalSnapshot]) -> list[FundamentalSnapshot]:
    by_period: dict[object, FundamentalSnapshot] = {}
    for snapshot in snapshots:
        if snapshot.fiscal_period != "daily_snapshot":
            continue
        existing = by_period.get(snapshot.period_end)
        if existing is None or snapshot.provenance.as_of_date >= existing.provenance.as_of_date:
            by_period[snapshot.period_end] = snapshot
    return [item for _, item in sorted(by_period.items())]


def _metric_context(
    key: str,
    label: str,
    history: list[FundamentalSnapshot],
    *,
    minimum_observations: int,
) -> ValuationMetricContext:
    values = [
        value
        for snapshot in history
        if (value := _number(snapshot.metrics.get(key))) is not None
    ]
    latest = values[-1] if values else None
    if latest is None or len(values) < minimum_observations:
        return ValuationMetricContext(
            key=key,
            label=label,
            latest=latest,
            observations=len(values),
            minimum_observations=minimum_observations,
            available=False,
        )
    return ValuationMetricContext(
        key=key,
        label=label,
        latest=latest,
        observations=len(values),
        minimum_observations=minimum_observations,
        available=True,
        percentile=100.0 * sum(value <= latest for value in values) / len(values),
        low=min(values),
        median=median(values),
        high=max(values),
    )


def _number(value: object) -> float | None:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return None
    number = float(value)
    return number if isfinite(number) else None
