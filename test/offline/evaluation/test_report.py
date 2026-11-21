"""Offline spec: E2 paired report :mod:`egta.evaluation.report`.

Target: ``pair_report(baseline: RunSummary, enhanced: RunSummary, rubric,
*, manifest: ExperimentManifest | None = None) -> EvaluationResult`` — delegates
to ``egta.contracts.evaluation.compare_runs``; manifest_hash gate → INCOMPLETE/
MANIFEST_MISMATCH (never a win). D#1 option (a): optional ``manifest`` param;
when provided, ``compute_manifest_hash`` must equal BOTH sides' ``manifest_hash``.

Also covers D#4 (deferred rubric path): with no rubric observation metrics,
``compare_runs`` must NOT return a misleading COMPLETE (must be INCOMPLETE).

Red on this spec branch: ``egta.evaluation.report`` absent.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from egta.contracts.evaluation import (
    CompletionStatus,
    EvaluationResult,
    IncompleteReason,
    RunSummary,
    compare_runs,
)
from egta.contracts.manifest import (
    ExperimentManifest,
    MetricDef,
    QualityRubric,
    compute_manifest_hash,
)
from egta.evaluation.report import pair_report

pytestmark = pytest.mark.spec

H = "a" * 64
H2 = "b" * 64


def _summary(**over) -> RunSummary:
    base = {
        "variant": "B0", "run_id": "run0", "target_snapshot_id": "snap1",
        "model_config_hash": H, "prompt_hash": H, "code_hash": "c" * 40,
        "policy_hash": H, "manifest_hash": H,
    }
    base.update(over)
    return RunSummary(**base)


def _rubric():
    return {
        "token_cost": MetricDef(
            metric="token_cost", operator="lte", threshold=2.0,
            verification="pytest", source="budget", aggregation="median", unit="USD",
        )
    }


def _manifest(**over) -> ExperimentManifest:
    base = {
        "manifest_id": "m1", "created_at": datetime(2026, 1, 2, tzinfo=UTC),
        "target_snapshot_id": "snap1", "model_config_hash": H, "prompt_hash": H,
        "code_hash": "c" * 40, "policy_hash": H, "manifest_hash": H,
        "variants": {"B0": {"m": 1}, "B1": {"m": 2}, "B2": {"m": 3}, "B3": {"m": 4}},
        "metrics_rubric": {"token_cost": _rubric()["token_cost"]},
        "quality_rubric": QualityRubric(
            levels=["gold", "silver", "bronze"], double_blind=True,
            third_party_adjudication=True, llm_judge_assist=False),
    }
    base.update(over)
    m = ExperimentManifest(**base)
    return m.model_copy(update={"manifest_hash": compute_manifest_hash(m)})


# --- delegation & equality --------------------------------------------------


def test_equal_manifest_complete():
    # observed rubric metrics present (D#4: without them compare_runs is INCOMPLETE)
    r = pair_report(
        _summary(variant="B0", metrics={"token_cost": 1.0}),
        _summary(variant="B1", metrics={"token_cost": 1.5}),
        _rubric(),
    )
    assert isinstance(r, EvaluationResult)
    assert r.completion_status is CompletionStatus.COMPLETE


def test_delegates_to_compare_runs():
    # empty metrics -> both sides INCOMPLETE (MISSING_METRIC); pair must equal compare_runs
    b, e = _summary(variant="B0"), _summary(variant="B1")
    assert pair_report(b, e, _rubric()) == compare_runs(b, e, _rubric())


# --- D#1: manifest verification (option a) ----------------------------------


def test_manifest_param_hash_matches_compute_complete():
    m = _manifest()
    b = _summary(variant="B0", manifest_hash=m.manifest_hash, metrics={"token_cost": 1.0})
    e = _summary(variant="B1", manifest_hash=m.manifest_hash, metrics={"token_cost": 1.5})
    r = pair_report(b, e, _rubric(), manifest=m)
    assert r.completion_status is CompletionStatus.COMPLETE


def test_manifest_param_hash_not_equal_compute_incomplete():
    m = _manifest()
    # supplied manifest's own manifest_hash differs from its recomputed hash
    forged = m.model_copy(update={"manifest_hash": H2})
    b = _summary(variant="B0", manifest_hash=H2)
    e = _summary(variant="B1", manifest_hash=H2)
    r = pair_report(b, e, _rubric(), manifest=forged)
    assert r.completion_status is CompletionStatus.INCOMPLETE
    assert r.incomplete_reason is IncompleteReason.MANIFEST_MISMATCH
    assert r.winner is None and r.baseline_win is False and r.enhanced_win is False


def test_manifest_param_side_inconsistent_incomplete():
    # manifest computes to X, but the two summaries disagree with it
    m = _manifest()
    b = _summary(variant="B0", manifest_hash=m.manifest_hash)
    e = _summary(variant="B1", manifest_hash=H2)  # enhanced differs
    r = pair_report(b, e, _rubric(), manifest=m)
    assert r.completion_status is CompletionStatus.INCOMPLETE
    assert r.incomplete_reason is IncompleteReason.MANIFEST_MISMATCH
    assert r.winner is None


# --- D#4: deferred rubric — no misleading COMPLETE --------------------------


def test_no_rubric_observation_metrics_not_misleading_complete():
    """With no observed metric data, pair_report must be INCOMPLETE/MISSING_METRIC."""
    b = _summary(variant="B0")  # metrics={} (no observation)
    e = _summary(variant="B1")
    r = pair_report(b, e, _rubric())
    assert r.completion_status is CompletionStatus.INCOMPLETE
    assert r.incomplete_reason is IncompleteReason.MISSING_METRIC
    assert r.winner is None and r.baseline_win is False and r.enhanced_win is False
