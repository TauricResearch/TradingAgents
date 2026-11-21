"""Offline spec: E2 metrics aggregation :mod:`egta.evaluation.metrics`.

Target: ``aggregate(results: list[EvaluationResult], rubric: dict[str, MetricDef]) -> dict``.
Deterministic; applies ``MetricDef.operator``/``threshold``; failure-sample
accounting per ``docs/code-governance/verification-constraints.md``:
success denominator = ``|OK| + |HOLD|``; BLOCKED/INCOMPLETE/REVIEW/FAILED are
excluded from the denominator but reported separately (never deleted).

Red on this spec branch: ``egta.evaluation.metrics`` absent.
"""

from __future__ import annotations

import pytest

from egta.contracts.evaluation import (
    CompletionStatus,
    EvaluationResult,
    IncompleteReason,
)
from egta.contracts.manifest import MetricDef
from egta.evaluation.metrics import aggregate

pytestmark = pytest.mark.spec

H = "a" * 64


def _result(status: CompletionStatus, **over) -> EvaluationResult:
    base = {
        "run_pair_id": "p", "case_id": "c", "variant": "B0",
        "manifest_hash": H, "completion_status": status,
    }
    if status is CompletionStatus.INCOMPLETE:
        base["incomplete_reason"] = over.pop("incomplete_reason",
                                             IncompleteReason.SNAPSHOT_MISMATCH)
    base.update(over)
    return EvaluationResult(**base)


def _rubric():
    return {
        "token_cost": MetricDef(
            metric="token_cost", operator="lte", threshold=2.0,
            verification="pytest", source="budget", aggregation="median", unit="USD",
        )
    }


def test_denominator_counts_ok_and_hold_only():
    results = [
        _result(CompletionStatus.COMPLETE, metrics={"token_cost": 1.0}),  # OK/HOLD
        _result(CompletionStatus.BLOCKED, metrics={}),
        _result(CompletionStatus.INCOMPLETE),
        _result(CompletionStatus.REVIEW),
        _result(CompletionStatus.FAILED),
    ]
    agg = aggregate(results, _rubric())
    # denominator excludes BLOCKED/INCOMPLETE/REVIEW/FAILED
    assert agg["denominator"] == 1
    assert agg["excluded"] == 4


def test_failure_samples_excluded_but_reported():
    results = [_result(CompletionStatus.BLOCKED), _result(CompletionStatus.FAILED)]
    agg = aggregate(results, _rubric())
    assert agg["denominator"] == 0
    assert agg["excluded"] == 2
    # reported per-state counts, not silently dropped
    assert agg["counts"]["BLOCKED"] == 1
    assert agg["counts"]["FAILED"] == 1


def test_rubric_used_operator_threshold():
    # token_cost lte 2.0: pass at 1.0, fail at 3.0
    results = [
        _result(CompletionStatus.COMPLETE, metrics={"token_cost": 1.0}),
        _result(CompletionStatus.COMPLETE, metrics={"token_cost": 3.0}),
    ]
    agg = aggregate(results, _rubric())
    assert agg["per_metric"]["token_cost"]["passed"] == 1
    assert agg["per_metric"]["token_cost"]["failed"] == 1


def test_missing_usage_incomplete_not_ok():
    results = [_result(CompletionStatus.INCOMPLETE,
                       incomplete_reason=IncompleteReason.MISSING_USAGE)]
    agg = aggregate(results, _rubric())
    assert agg["denominator"] == 0
    assert agg["counts"]["INCOMPLETE"] == 1


def test_invalid_rubric_rejected():
    """aggregate must reject an illegal rubric (not just MetricDef construction)."""
    from pydantic import ValidationError

    bad = {"token_cost": {"operator": "approximately", "threshold": "x"}}
    results = [_result(CompletionStatus.COMPLETE, metrics={"token_cost": 1.0})]
    with pytest.raises((ValueError, TypeError, ValidationError)):
        aggregate(results, bad)
