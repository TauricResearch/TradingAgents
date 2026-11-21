"""Offline tests: compare_runs typed inputs + incompatibility (D item 5).

- typed inputs (reject bare dict); rubric passed and used.
- mismatch (snapshot/model/prompt/code/policy) -> INCOMPLETE + specific reason,
  winner=None, both wins False (no getattr escape).
- matching -> COMPLETE.
- MISSING_RESULT -> INCOMPLETE, not a win.
- manifest_hash mismatch -> INCOMPLETE/MANIFEST_MISMATCH.

Definitions: docs/req/contracts-summary.md §2. RED on the spec branch.
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
)

pytestmark = pytest.mark.spec

H = "a" * 64
H2 = "b" * 64


def _summary(**over):
    base = {
        "variant": "B0", "run_id": "run0",
        "target_snapshot_id": "snap1",
        "model_config_hash": H, "prompt_hash": H,
        "code_hash": H, "policy_hash": H,
        "manifest_hash": H,
        "has_result": True,
    }
    base.update(over)
    return RunSummary(**base)


def _rubric():
    return {
        "token_cost": MetricDef(
            metric="token_cost", operator="lte", threshold=2.0,
            verification="pytest", source="budget", aggregation="median",
            unit="USD",
        )
    }


def _manifest(**over):
    base = {
        "manifest_id": "m1",
        "created_at": datetime(2026, 1, 2, tzinfo=UTC),
        "target_snapshot_id": "snap1",
        "model_config_hash": H, "prompt_hash": H,
        "code_hash": H, "policy_hash": H, "manifest_hash": H,
        "variants": {"B0": {"m": 1}, "B1": {"m": 2}, "B2": {"m": 3}, "B3": {"m": 4}},
        "metrics_rubric": {"token_cost": _rubric()["token_cost"]},
        "quality_rubric": QualityRubric(
            levels=["gold", "silver", "bronze"], double_blind=True,
            third_party_adjudication=True, llm_judge_assist=False),
    }
    base.update(over)
    return ExperimentManifest(**base)


def test_compare_rejects_bare_dict():
    with pytest.raises((TypeError, ValueError)):
        compare_runs({"variant": "B0"}, {"variant": "B1"}, _rubric())


@pytest.mark.parametrize(
    "field, reason",
    [
        ("target_snapshot_id", IncompleteReason.SNAPSHOT_MISMATCH),
        ("model_config_hash", IncompleteReason.MODEL_MISMATCH),
        ("prompt_hash", IncompleteReason.PROMPT_MISMATCH),
        ("code_hash", IncompleteReason.CODE_MISMATCH),
        ("policy_hash", IncompleteReason.POLICY_MISMATCH),
    ],
)
def test_mismatch_yields_incomplete_not_win(field, reason):
    baseline = _summary(variant="B0")
    enhanced = _summary(variant="B1", **{field: H2})
    result = compare_runs(baseline, enhanced, _rubric())
    assert result.completion_status is CompletionStatus.INCOMPLETE
    assert result.incomplete_reason is reason
    assert result.winner is None
    assert result.baseline_win is False and result.enhanced_win is False


def test_manifest_hash_mismatch():
    baseline = _summary(variant="B0")
    enhanced = _summary(variant="B1", manifest_hash=H2)
    result = compare_runs(baseline, enhanced, _rubric())
    assert result.completion_status is CompletionStatus.INCOMPLETE
    assert result.incomplete_reason is IncompleteReason.MANIFEST_MISMATCH
    assert result.winner is None


def test_missing_result_is_incomplete_not_win():
    baseline = _summary(variant="B0")
    enhanced = _summary(variant="B1", has_result=False)
    result = compare_runs(baseline, enhanced, _rubric())
    assert result.completion_status is CompletionStatus.INCOMPLETE
    assert result.incomplete_reason is IncompleteReason.MISSING_RESULT
    assert result.winner is None
    assert result.baseline_win is False and result.enhanced_win is False


def test_matching_inputs_complete_and_rubric_used():
    """Observed metrics present -> COMPLETE, and operator/threshold actually apply."""
    baseline = _summary(variant="B0", metrics={"token_cost": 1.0})
    enhanced = _summary(variant="B1", metrics={"token_cost": 1.5})
    rubric = _rubric()  # token_cost lte 2.0
    result = compare_runs(baseline, enhanced, rubric)
    assert result.completion_status is CompletionStatus.COMPLETE
    assert result.incomplete_reason is None
    # rubric must influence the result: its metric appears in scored metrics
    assert "token_cost" in result.metrics
    # NOT threshold-as-metric: the scored value is the observed value (1.0/1.5),
    # not the threshold (2.0). This proves the observed values are used.
    assert result.metrics["token_cost"] in (1.0, 1.5)
    assert result.metrics["token_cost"] != rubric["token_cost"].threshold
    assert isinstance(result, EvaluationResult)


def test_missing_metric_observation_is_missing_metric():
    """No observation for a rubric metric -> INCOMPLETE/MISSING_METRIC, no win."""
    baseline = _summary(variant="B0")  # metrics = {} (no observation)
    enhanced = _summary(variant="B1")
    result = compare_runs(baseline, enhanced, _rubric())
    assert result.completion_status is CompletionStatus.INCOMPLETE
    assert result.incomplete_reason is IncompleteReason.MISSING_METRIC
    assert result.winner is None
    assert result.baseline_win is False and result.enhanced_win is False


# --- RunSummary typed contract (D item 1) -----------------------------------


def test_run_summary_positive():
    s = RunSummary(
        run_id="r0", variant="B0", target_snapshot_id="snap1",
        model_config_hash=H, prompt_hash=H, code_hash="c" * 40, policy_hash=H,
        manifest_hash=H,
    )
    assert s.has_result is True
    assert s.metrics == {}
    assert s.quality_labels == []


def test_run_summary_rejects_bare_construction_as_dict():
    """RunSummary itself rejects unknown/extra keys (extra=forbid)."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        RunSummary(
            run_id="r0", variant="B0", target_snapshot_id="s",
            model_config_hash=H, prompt_hash=H, code_hash="c" * 40,
            policy_hash=H, manifest_hash=H, bogus=1,
        )


@pytest.mark.parametrize("missing", ["run_id", "variant", "target_snapshot_id",
                                     "model_config_hash", "prompt_hash",
                                     "code_hash", "policy_hash", "manifest_hash"])
def test_run_summary_missing_required_field_rejected(missing):
    from pydantic import ValidationError

    fields = {
        "run_id": "r0", "variant": "B0", "target_snapshot_id": "s",
        "model_config_hash": H, "prompt_hash": H, "code_hash": "c" * 40,
        "policy_hash": H, "manifest_hash": H,
    }
    fields.pop(missing)
    with pytest.raises(ValidationError):
        RunSummary(**fields)


@pytest.mark.parametrize("field", ["model_config_hash", "prompt_hash",
                                   "policy_hash", "manifest_hash"])
@pytest.mark.parametrize("bad", ["XYZ", "A" * 64, "a" * 63, ""])
def test_run_summary_bad_64_hex_rejected(field, bad):
    from pydantic import ValidationError

    base = {
        "run_id": "r0", "variant": "B0", "target_snapshot_id": "s",
        "model_config_hash": H, "prompt_hash": H, "code_hash": "c" * 40,
        "policy_hash": H, "manifest_hash": H,
    }
    base[field] = bad
    with pytest.raises(ValidationError):
        RunSummary(**base)


@pytest.mark.parametrize("bad", ["XYZ", "c" * 39, ""])
def test_run_summary_bad_code_hash_rejected(bad):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        RunSummary(
            run_id="r0", variant="B0", target_snapshot_id="s",
            model_config_hash=H, prompt_hash=H, code_hash=bad,
            policy_hash=H, manifest_hash=H,
        )


# --- variant propagation (D item 5d) ----------------------------------------


def test_variant_propagated_to_result():
    baseline = _summary(variant="B0")
    enhanced = _summary(variant="B1")
    result = compare_runs(baseline, enhanced, _rubric())
    assert result.variant == "B1"


# --- MISSING_USAGE (D item 5a) ----------------------------------------------


def test_missing_usage_is_incomplete_not_win():
    """Unknown usage (has_usage=False) -> INCOMPLETE/MISSING_USAGE, not a win."""
    result = compare_runs(
        _summary(variant="B0", has_usage=False),
        _summary(variant="B1", has_usage=False),
        _rubric(),
    )
    assert result.completion_status is CompletionStatus.INCOMPLETE
    assert result.incomplete_reason is IncompleteReason.MISSING_USAGE
    assert result.winner is None
    assert result.baseline_win is False and result.enhanced_win is False


# --- D#1 (contracts): compare_runs(manifest=...) direct ---------------------


def _manifest_obj(**over):
    from egta.contracts.manifest import compute_manifest_hash

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


def test_compare_runs_manifest_param_matches_complete():
    m = _manifest_obj()
    b = _summary(variant="B0", manifest_hash=m.manifest_hash, metrics={"token_cost": 1.0})
    e = _summary(variant="B1", manifest_hash=m.manifest_hash, metrics={"token_cost": 1.5})
    r = compare_runs(b, e, _rubric(), manifest=m)
    assert r.completion_status is CompletionStatus.COMPLETE


def test_compare_runs_manifest_param_mismatch_incomplete():
    m = _manifest_obj()
    forged = m.model_copy(update={"manifest_hash": H2})  # != compute
    b = _summary(variant="B0", manifest_hash=H2, metrics={"token_cost": 1.0})
    e = _summary(variant="B1", manifest_hash=H2, metrics={"token_cost": 1.5})
    r = compare_runs(b, e, _rubric(), manifest=forged)
    assert r.completion_status is CompletionStatus.INCOMPLETE
    assert r.incomplete_reason is IncompleteReason.MANIFEST_MISMATCH
    assert r.winner is None and r.baseline_win is False and r.enhanced_win is False


def test_compare_runs_manifest_param_side_inconsistent_incomplete():
    m = _manifest_obj()
    b = _summary(variant="B0", manifest_hash=m.manifest_hash, metrics={"token_cost": 1.0})
    e = _summary(variant="B1", manifest_hash=H2, metrics={"token_cost": 1.5})  # differs
    r = compare_runs(b, e, _rubric(), manifest=m)
    assert r.completion_status is CompletionStatus.INCOMPLETE
    assert r.incomplete_reason is IncompleteReason.MANIFEST_MISMATCH


def test_manifest_check_precedes_missing_metric():
    """Order: manifest → result/usage → rubric observation (D#1 counterexample)."""
    m = _manifest_obj()
    # sides disagree with manifest AND no metric observations; MANIFEST_MISMATCH wins
    b = _summary(variant="B0", manifest_hash=H2)
    e = _summary(variant="B1", manifest_hash=H2)
    r = compare_runs(b, e, _rubric(), manifest=m)
    assert r.incomplete_reason is IncompleteReason.MANIFEST_MISMATCH


# --- D#4: no hardcoded pair/case; quality_labels propagated -----------------


def test_run_pair_and_case_ids_explicit_not_hardcoded():
    """run_pair_id/case_id come from inputs, not hardcoded 'pair'/'case'."""
    b = _summary(variant="B0", run_id="runB0", metrics={"token_cost": 1.0})
    e = _summary(variant="B1", run_id="runB1", metrics={"token_cost": 1.5})
    r = compare_runs(b, e, _rubric(), run_pair_id="PAIR-42", case_id="CASE-7")
    assert r.run_pair_id == "PAIR-42"
    assert r.case_id == "CASE-7"


def test_quality_labels_propagated_without_forgery():
    """Observed quality_labels are propagated verbatim (no fabrication)."""
    labels = ["gold", "silver"]
    b = _summary(variant="B0", metrics={"token_cost": 1.0}, quality_labels=labels)
    e = _summary(variant="B1", metrics={"token_cost": 1.5}, quality_labels=["bronze"])
    r = compare_runs(b, e, _rubric())
    # result carries a quality_labels list consistent with inputs (not invented)
    assert isinstance(r.quality_labels, list)
    assert set(r.quality_labels) <= set(labels) | {"bronze"}
