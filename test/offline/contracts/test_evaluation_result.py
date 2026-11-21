"""Offline tests: EvaluationResult §5.1 completeness (D item 2).

``incomplete`` is a STATUS, never an exception. INCOMPLETE must carry an
``incomplete_reason``; COMPLETE must have ``None``. Typed ``metrics`` /
``quality_labels`` / ``failures``; explicit ``winner``/``baseline_win``/
``enhanced_win``. RED on the spec branch.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from egta.contracts.evaluation import (
    CompletionStatus,
    EvaluationResult,
    IncompleteReason,
)

pytestmark = pytest.mark.spec

MANIFEST_HASH = "a" * 64


def _result(**overrides):
    base = {
        "run_pair_id": "p1", "case_id": "c1", "variant": "B0",
        "manifest_hash": MANIFEST_HASH,
        "completion_status": CompletionStatus.COMPLETE,
    }
    base.update(overrides)
    return EvaluationResult(**base)


def test_completion_status_members():
    assert {s.name for s in CompletionStatus} == {
        "COMPLETE", "INCOMPLETE", "BLOCKED", "REVIEW", "FAILED"
    }


def test_incomplete_reason_members():
    names = {r.name for r in IncompleteReason}
    assert {"MANIFEST_MISMATCH", "SNAPSHOT_MISMATCH", "MODEL_MISMATCH",
            "PROMPT_MISMATCH", "CODE_MISMATCH", "POLICY_MISMATCH",
            "MISSING_RESULT", "MISSING_USAGE", "MISSING_METRIC"} <= names


def test_missing_metric_enum_member():
    assert IncompleteReason.MISSING_METRIC is not None
    r = _result(completion_status=CompletionStatus.INCOMPLETE,
                incomplete_reason=IncompleteReason.MISSING_METRIC)
    assert r.incomplete_reason is IncompleteReason.MISSING_METRIC


def test_missing_usage_enum_member():
    assert IncompleteReason.MISSING_USAGE is not None
    r = _result(completion_status=CompletionStatus.INCOMPLETE,
                incomplete_reason=IncompleteReason.MISSING_USAGE)
    assert r.incomplete_reason is IncompleteReason.MISSING_USAGE


def test_manifest_hash_required():
    with pytest.raises(ValidationError):
        EvaluationResult(run_pair_id="p1", case_id="c1", variant="B0",
                         completion_status=CompletionStatus.COMPLETE)


def test_typed_defaults():
    r = _result()
    assert r.metrics == {}
    assert r.quality_labels == []
    assert r.failures == []


def test_typed_fields_reject_wrong_types():
    with pytest.raises(ValidationError):
        _result(metrics=["not", "a", "mapping"])
    with pytest.raises(ValidationError):
        _result(quality_labels="not-a-list")
    with pytest.raises(ValidationError):
        _result(failures={"a": 1})


def test_incomplete_result_does_not_raise_and_has_reason():
    r = _result(completion_status=CompletionStatus.INCOMPLETE,
                incomplete_reason=IncompleteReason.SNAPSHOT_MISMATCH)
    assert r.completion_status is CompletionStatus.INCOMPLETE
    assert r.incomplete_reason is IncompleteReason.SNAPSHOT_MISMATCH
    assert r.winner is None
    assert r.baseline_win is False and r.enhanced_win is False


def test_incomplete_without_reason_rejected():
    with pytest.raises(ValidationError):
        _result(completion_status=CompletionStatus.INCOMPLETE)


def test_complete_with_reason_rejected():
    with pytest.raises(ValidationError):
        _result(completion_status=CompletionStatus.COMPLETE,
                incomplete_reason=IncompleteReason.SNAPSHOT_MISMATCH)


def test_complete_result_reason_is_none():
    r = _result(completion_status=CompletionStatus.COMPLETE)
    assert r.incomplete_reason is None


def test_winner_fields_typed():
    r = _result(completion_status=CompletionStatus.COMPLETE,
                winner="B1", baseline_win=False, enhanced_win=True)
    assert r.winner == "B1"
    assert r.enhanced_win is True


def test_hold_is_not_a_completion_status():
    """HOLD is an AdvisoryProposal.action, NOT a RunStatus/CompletionStatus."""
    names = {s.name for s in CompletionStatus}
    assert "HOLD" not in names


def test_hold_outcome_can_be_expressed_as_complete_result():
    """A HOLD recommendation is a normal COMPLETE outcome, not a system failure."""
    r = _result(completion_status=CompletionStatus.COMPLETE)
    assert r.completion_status is CompletionStatus.COMPLETE
    assert r.incomplete_reason is None
