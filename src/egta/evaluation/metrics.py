"""Deterministic metrics aggregation with failure-sample accounting (E2).

# Implements: FR-05, NFR-09

Aggregates ``EvaluationResult``s against a typed rubric (``dict[str, MetricDef]``,
validated via ``TypeAdapter`` — a raw/illegal rubric is rejected). Applies each
``MetricDef.operator``/``threshold`` to the observed per-result metric values.
Failure-sample accounting follows ``docs/code-governance/verification-constraints.md``:
the success denominator is ``|OK| + |HOLD|`` (``COMPLETE``); BLOCKED / INCOMPLETE /
REVIEW / FAILED are excluded from the denominator but **reported** (never deleted).
"""

from __future__ import annotations

from typing import Any

from pydantic import TypeAdapter

from egta.contracts.evaluation import CompletionStatus, EvaluationResult
from egta.contracts.manifest import MetricDef

_METRIC_OPERATORS = {
    "eq": lambda v, t: v == t,
    "lte": lambda v, t: v <= t,
    "gte": lambda v, t: v >= t,
    "lt": lambda v, t: v < t,
    "gt": lambda v, t: v > t,
}

_EXCLUDED = (
    CompletionStatus.BLOCKED,
    CompletionStatus.INCOMPLETE,
    CompletionStatus.REVIEW,
    CompletionStatus.FAILED,
)


def aggregate(
    results: list[EvaluationResult], rubric: dict[str, MetricDef]
) -> dict[str, Any]:
    """Deterministic aggregate of results under a typed rubric."""
    rubric = TypeAdapter(dict[str, MetricDef]).validate_python(rubric)

    counts: dict[str, int] = {status.value: 0 for status in CompletionStatus}
    for result in results:
        counts[result.completion_status.value] += 1

    denominator = counts[CompletionStatus.COMPLETE.value]
    excluded = sum(counts[status.value] for status in _EXCLUDED)

    per_metric: dict[str, dict[str, int]] = {}
    for name, definition in rubric.items():
        passed = failed = 0
        for result in results:
            if result.completion_status is not CompletionStatus.COMPLETE:
                continue
            if name not in result.metrics:
                continue
            ok = _METRIC_OPERATORS[definition.operator](
                result.metrics[name], definition.threshold
            )
            if ok:
                passed += 1
            else:
                failed += 1
        per_metric[name] = {"passed": passed, "failed": failed}

    return {
        "denominator": denominator,
        "excluded": excluded,
        "counts": counts,
        "per_metric": per_metric,
    }
