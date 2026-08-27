"""Offline walk-forward evaluation primitives for research decisions.

Callers provide already time-aligned observations. This module performs no
network I/O, model calls, prompt updates, parameter search, or trade execution.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import fmean
from typing import Any

from tradingagents.agents.schemas import DecisionStatus


@dataclass(frozen=True)
class EvaluationCosts:
    """Total round-trip research assumptions, expressed in basis points."""

    transaction_cost_bps: float = 0.0
    slippage_bps: float = 0.0

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> EvaluationCosts:
        return cls(
            transaction_cost_bps=float(config.get("evaluation_transaction_cost_bps", 0.0)),
            slippage_bps=float(config.get("evaluation_slippage_bps", 0.0)),
        )

    def decimal(self) -> float:
        if self.transaction_cost_bps < 0 or self.slippage_bps < 0:
            raise ValueError("transaction cost and slippage assumptions must be non-negative")
        return (self.transaction_cost_bps + self.slippage_bps) / 10_000.0


@dataclass(frozen=True)
class ResearchPrediction:
    ticker: str
    analysis_date: str
    rating: str
    decision_status: str
    horizon_days: int
    expected_return_low: float | None = None
    expected_return_high: float | None = None
    confidence: float | None = None
    benchmark: str | None = None
    schema_version: str | None = None

    @classmethod
    def from_research_result(
        cls,
        research_result: dict[str, Any],
        *,
        horizon_days: int,
        benchmark: str | None = None,
    ) -> ResearchPrediction:
        return cls(
            ticker=str(research_result.get("ticker") or ""),
            analysis_date=str(research_result.get("analysis_date") or ""),
            rating=str(research_result.get("rating") or "Hold"),
            decision_status=str(
                research_result.get("decision_status")
                or DecisionStatus.HUMAN_REVIEW_REQUIRED.value
            ),
            horizon_days=horizon_days,
            expected_return_low=research_result.get("expected_return_low"),
            expected_return_high=research_result.get("expected_return_high"),
            confidence=research_result.get("confidence"),
            benchmark=benchmark,
            schema_version=research_result.get("schema_version"),
        )


@dataclass(frozen=True)
class EvaluationObservation:
    """Prices known only after the prediction cutoff."""

    entry_price: float
    exit_price: float
    path_prices: Sequence[float]
    benchmark_entry_price: float | None = None
    benchmark_exit_price: float | None = None
    observation_date: str | None = None


@dataclass(frozen=True)
class EvaluationResult:
    ticker: str
    analysis_date: str
    rating: str
    decision_status: str
    horizon_days: int
    observation_date: str | None
    eligible: bool
    entry_price: float
    exit_price: float
    benchmark: str | None
    benchmark_entry_price: float | None
    benchmark_exit_price: float | None
    expected_return_low: float | None
    expected_return_high: float | None
    actual_return: float
    benchmark_return: float | None
    benchmark_excess_return: float | None
    direction_adjusted_return: float | None
    net_direction_adjusted_return: float | None
    net_direction_adjusted_alpha: float | None
    hit: bool | None
    interval_hit: bool | None
    absolute_forecast_error: float | None
    max_adverse_excursion: float | None
    transaction_cost_bps: float
    slippage_bps: float
    confidence: float | None
    schema_version: str | None


_RATING_DIRECTION = {
    "buy": 1,
    "overweight": 1,
    "hold": 0,
    "underweight": -1,
    "sell": -1,
}


def _validate_price(value: float, name: str) -> float:
    value = float(value)
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def evaluate_prediction(
    prediction: ResearchPrediction,
    observation: EvaluationObservation,
    *,
    costs: EvaluationCosts | None = None,
    hold_band: float = 0.01,
) -> EvaluationResult:
    """Compare one prediction with an out-of-sample observed price path."""
    if prediction.horizon_days <= 0:
        raise ValueError("horizon_days must be positive")
    if hold_band < 0:
        raise ValueError("hold_band must be non-negative")
    entry = _validate_price(observation.entry_price, "entry_price")
    exit_price = _validate_price(observation.exit_price, "exit_price")
    rating_key = prediction.rating.strip().lower()
    if rating_key not in _RATING_DIRECTION:
        raise ValueError(f"unsupported rating: {prediction.rating!r}")
    path = [_validate_price(price, "path price") for price in observation.path_prices]
    if not path:
        path = [entry, exit_price]
    elif path[0] != entry:
        path.insert(0, entry)
    if path[-1] != exit_price:
        path.append(exit_price)

    actual_return = exit_price / entry - 1.0
    benchmark_return = None
    if observation.benchmark_entry_price is not None or observation.benchmark_exit_price is not None:
        if observation.benchmark_entry_price is None or observation.benchmark_exit_price is None:
            raise ValueError("both benchmark entry and exit prices are required")
        benchmark_entry = _validate_price(
            observation.benchmark_entry_price,
            "benchmark_entry_price",
        )
        benchmark_exit = _validate_price(
            observation.benchmark_exit_price,
            "benchmark_exit_price",
        )
        benchmark_return = benchmark_exit / benchmark_entry - 1.0

    direction = _RATING_DIRECTION[rating_key]
    eligible = prediction.decision_status == DecisionStatus.RESEARCH_COMPLETE.value
    cost_config = costs or EvaluationCosts()
    total_cost = cost_config.decimal()

    direction_adjusted = None
    net_direction_adjusted = None
    net_alpha = None
    hit = None
    max_adverse = None
    if eligible:
        if direction == 0:
            direction_adjusted = 0.0
            net_direction_adjusted = 0.0
            hit = abs(actual_return) <= hold_band
            max_adverse = -max(abs(price / entry - 1.0) for price in path)
        else:
            direction_adjusted = direction * actual_return
            net_direction_adjusted = direction_adjusted - total_cost
            hit = net_direction_adjusted > 0
            aligned_path = [direction * (price / entry - 1.0) for price in path]
            max_adverse = min(0.0, min(aligned_path))
        if benchmark_return is not None and direction != 0:
            net_alpha = direction * (actual_return - benchmark_return)
            net_alpha -= total_cost

    interval_hit = None
    absolute_error = None
    low = prediction.expected_return_low
    high = prediction.expected_return_high
    if low is not None and high is not None:
        if low > high:
            raise ValueError("expected return lower bound must be <= upper bound")
        interval_hit = low <= actual_return <= high
        absolute_error = abs(actual_return - (low + high) / 2.0)

    return EvaluationResult(
        ticker=prediction.ticker,
        analysis_date=prediction.analysis_date,
        rating=prediction.rating,
        decision_status=prediction.decision_status,
        horizon_days=prediction.horizon_days,
        observation_date=observation.observation_date,
        eligible=eligible,
        entry_price=entry,
        exit_price=exit_price,
        benchmark=prediction.benchmark,
        benchmark_entry_price=observation.benchmark_entry_price,
        benchmark_exit_price=observation.benchmark_exit_price,
        expected_return_low=prediction.expected_return_low,
        expected_return_high=prediction.expected_return_high,
        actual_return=actual_return,
        benchmark_return=benchmark_return,
        benchmark_excess_return=(
            actual_return - benchmark_return if benchmark_return is not None else None
        ),
        direction_adjusted_return=direction_adjusted,
        net_direction_adjusted_return=net_direction_adjusted,
        net_direction_adjusted_alpha=net_alpha,
        hit=hit,
        interval_hit=interval_hit,
        absolute_forecast_error=absolute_error,
        max_adverse_excursion=max_adverse,
        transaction_cost_bps=cost_config.transaction_cost_bps,
        slippage_bps=cost_config.slippage_bps,
        confidence=prediction.confidence,
        schema_version=prediction.schema_version,
    )


class WalkForwardEvaluator:
    """Collect and optionally append compact evaluation results to JSONL."""

    def __init__(self, record_path: str | Path | None = None):
        self.record_path = Path(record_path) if record_path else None
        self.results: list[EvaluationResult] = []
        if self.record_path:
            self.record_path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        prediction: ResearchPrediction,
        observation: EvaluationObservation,
        *,
        costs: EvaluationCosts | None = None,
        hold_band: float = 0.01,
    ) -> EvaluationResult:
        result = evaluate_prediction(
            prediction,
            observation,
            costs=costs,
            hold_band=hold_band,
        )
        self.results.append(result)
        if self.record_path:
            with open(self.record_path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(asdict(result), sort_keys=True) + "\n")
        return result

    def summarize(self, results: Iterable[EvaluationResult] | None = None) -> dict[str, Any]:
        rows = list(self.results if results is None else results)
        eligible = [row for row in rows if row.eligible]
        hits = [row.hit for row in eligible if row.hit is not None]
        interval_hits = [row.interval_hit for row in rows if row.interval_hit is not None]

        def mean(field: str, source: list[EvaluationResult]):
            values = [getattr(row, field) for row in source]
            values = [value for value in values if value is not None]
            return fmean(values) if values else None

        adverse = [
            row.max_adverse_excursion
            for row in eligible
            if row.max_adverse_excursion is not None
        ]
        return {
            "sample_count": len(rows),
            "eligible_count": len(eligible),
            "non_actionable_count": len(rows) - len(eligible),
            "hit_rate": sum(hits) / len(hits) if hits else None,
            "interval_coverage": (
                sum(interval_hits) / len(interval_hits) if interval_hits else None
            ),
            "mean_actual_return": mean("actual_return", rows),
            "mean_benchmark_excess_return": mean("benchmark_excess_return", rows),
            "mean_net_direction_adjusted_return": mean(
                "net_direction_adjusted_return",
                eligible,
            ),
            "mean_absolute_forecast_error": mean("absolute_forecast_error", rows),
            "worst_max_adverse_excursion": min(adverse) if adverse else None,
        }
