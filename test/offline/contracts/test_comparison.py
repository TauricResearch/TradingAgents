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


# ===========================================================================
# Follow-up spec (spec/FR-05-compare-fixes): D#1/#2/#4 hardening.
# These assertions must FAIL on the current #10 implementation (false-green) and
# PASS on a corrected implementation.
# ===========================================================================


# --- A. Single-sided missing metric -> INCOMPLETE/MISSING_METRIC -----------


def test_single_sided_missing_baseline_only_is_missing_metric():
    """Baseline observes token_cost, enhanced does NOT -> INCOMPLETE/MISSING_METRIC."""
    b = _summary(variant="B0", metrics={"token_cost": 1.0})
    e = _summary(variant="B1")  # no observation
    r = compare_runs(b, e, _rubric())
    assert r.completion_status is CompletionStatus.INCOMPLETE
    assert r.incomplete_reason is IncompleteReason.MISSING_METRIC
    assert r.winner is None and r.baseline_win is False and r.enhanced_win is False


def test_single_sided_missing_enhanced_only_is_missing_metric():
    """Enhanced observes token_cost, baseline does NOT -> INCOMPLETE/MISSING_METRIC."""
    b = _summary(variant="B0")  # no observation
    e = _summary(variant="B1", metrics={"token_cost": 1.5})
    r = compare_runs(b, e, _rubric())
    assert r.completion_status is CompletionStatus.INCOMPLETE
    assert r.incomplete_reason is IncompleteReason.MISSING_METRIC
    assert r.winner is None


def test_both_sides_present_is_complete():
    """Both sides observe the metric -> COMPLETE (positive retained)."""
    b = _summary(variant="B0", metrics={"token_cost": 1.0})
    e = _summary(variant="B1", metrics={"token_cost": 1.5})
    r = compare_runs(b, e, _rubric())
    assert r.completion_status is CompletionStatus.COMPLETE


# --- B. Typed rubric validation (illegal rubric rejected) ------------------


def test_illegal_rubric_flat_dict_rejected():
    """A rubric entry that is not a MetricDef (flat dict) must be rejected."""
    from pydantic import ValidationError

    bad = {"token_cost": {"operator": "lte", "threshold": 2.0}}  # missing fields
    b = _summary(variant="B0", metrics={"token_cost": 1.0})
    e = _summary(variant="B1", metrics={"token_cost": 1.5})
    with pytest.raises(ValidationError):
        compare_runs(b, e, bad)


def test_illegal_rubric_non_metricdef_object_rejected():
    """A non-MetricDef value (arbitrary object) must be rejected, not COMPLETE."""
    from pydantic import ValidationError

    b = _summary(variant="B0", metrics={"token_cost": 1.0})
    e = _summary(variant="B1", metrics={"token_cost": 1.5})
    with pytest.raises(ValidationError):
        compare_runs(b, e, {"token_cost": object()})


# --- B. Observed value, not threshold ---------------------------------------


def test_compare_runs_scores_observed_value_not_threshold():
    """The scored value reflects observed data (not the rubric threshold)."""
    b = _summary(variant="B0", metrics={"token_cost": 0.5})
    e = _summary(variant="B1", metrics={"token_cost": 1.25})
    r = compare_runs(b, e, _rubric())  # threshold 2.0
    assert r.completion_status is CompletionStatus.COMPLETE
    assert r.metrics["token_cost"] == 1.25
    assert r.metrics["token_cost"] != _rubric()["token_cost"].threshold


# --- C. Strong field assertions (failures / quality_labels / ids) ----------


def test_run_pair_and_case_ids_are_really_propagated():
    b = _summary(variant="B0", metrics={"token_cost": 1.0})
    e = _summary(variant="B1", metrics={"token_cost": 1.5})
    r = compare_runs(b, e, _rubric(), run_pair_id="PAIR-XYZ", case_id="CASE-42")
    assert r.run_pair_id == "PAIR-XYZ"
    assert r.case_id == "CASE-42"
    assert r.run_pair_id != "pair" and r.case_id != "case"  # not hardcoded


def test_quality_labels_propagated_strong():
    """quality_labels source = ENHANCED (result.variant=enhanced / observed metrics); baseline differs to prove source."""
    baseline_labels = ["gold", "silver"]
    enhanced_labels = ["bronze", "platinum"]
    b = _summary(variant="B0", metrics={"token_cost": 1.0}, quality_labels=baseline_labels)
    e = _summary(variant="B1", metrics={"token_cost": 1.5}, quality_labels=enhanced_labels)
    r = compare_runs(b, e, _rubric())
    assert r.variant == "B1"
    assert r.quality_labels == enhanced_labels          # from ENHANCED (option A)
    assert r.quality_labels != baseline_labels          # not baseline; source proven


def test_failures_field_present_and_list():
    b = _summary(variant="B0", metrics={"token_cost": 1.0})
    e = _summary(variant="B1", metrics={"token_cost": 1.5})
    r = compare_runs(b, e, _rubric())
    assert isinstance(r.failures, list)


# --- D contract: threshold handling (Option Y, D-decided) -------------------
#   both present & WITHIN threshold      -> COMPLETE, failures=[], winner=None
#   ONE side exceeds                     -> REVIEW, failures has 1 violation
#   BOTH sides exceed                    -> REVIEW, failures >= 2 (one per side)
#   one side lacks metric                -> INCOMPLETE/MISSING_METRIC
#   illegal rubric                       -> ValidationError
#   failure format (one per violating side):
#     THRESHOLD_VIOLATION:<metric>:<side>:observed=<v>:operator=<op>:threshold=<t>
#   THRESHOLD_VIOLATION is NOT an IncompleteReason.

_FMT = "THRESHOLD_VIOLATION:{metric}:{side}:observed={observed}:operator={op}:threshold={threshold}"


def test_both_within_threshold_is_complete_no_failures():
    b = _summary(variant="B0", metrics={"token_cost": 1.0})   # <= 2.0 (within)
    e = _summary(variant="B1", metrics={"token_cost": 1.5})   # <= 2.0 (within)
    r = compare_runs(b, e, _rubric())
    assert r.completion_status is CompletionStatus.COMPLETE
    assert r.incomplete_reason is None
    assert r.failures == []
    assert r.winner is None and r.baseline_win is False and r.enhanced_win is False


def test_one_side_exceeds_is_review_with_one_failure():
    b = _summary(variant="B0", metrics={"token_cost": 1.0})   # within
    e = _summary(variant="B1", metrics={"token_cost": 3.0})   # exceeds lte 2.0
    r = compare_runs(b, e, _rubric())
    assert r.completion_status is CompletionStatus.REVIEW
    assert r.incomplete_reason is None   # REVIEW != INCOMPLETE
    assert r.winner is None and r.baseline_win is False and r.enhanced_win is False
    expected = _FMT.format(metric="token_cost", side="enhanced", observed="3.0",
                           op="lte", threshold="2.0")
    assert expected in r.failures
    assert len(r.failures) == 1


def test_one_side_exceeds_baseline_is_review():
    b = _summary(variant="B0", metrics={"token_cost": 5.0})   # exceeds
    e = _summary(variant="B1", metrics={"token_cost": 1.0})   # within
    r = compare_runs(b, e, _rubric())
    assert r.completion_status is CompletionStatus.REVIEW
    expected = _FMT.format(metric="token_cost", side="baseline", observed="5.0",
                           op="lte", threshold="2.0")
    assert expected in r.failures
    assert len(r.failures) == 1


def test_both_sides_exceed_is_review_with_two_failures():
    b = _summary(variant="B0", metrics={"token_cost": 5.0})   # exceeds
    e = _summary(variant="B1", metrics={"token_cost": 9.0})   # exceeds
    r = compare_runs(b, e, _rubric())
    assert r.completion_status is CompletionStatus.REVIEW
    assert r.incomplete_reason is None
    assert r.winner is None and r.baseline_win is False and r.enhanced_win is False
    assert len(r.failures) >= 2
    assert _FMT.format(metric="token_cost", side="baseline", observed="5.0",
                       op="lte", threshold="2.0") in r.failures
    assert _FMT.format(metric="token_cost", side="enhanced", observed="9.0",
                       op="lte", threshold="2.0") in r.failures


def test_threshold_violation_not_in_incomplete_reason():
    """THRESHOLD_VIOLATION must NOT be an IncompleteReason member."""
    assert "THRESHOLD_VIOLATION" not in {r.name for r in IncompleteReason}


# --- A5: operator coverage + boundaries (D contract) ------------------------
# lte 2.0: obs==2.0 passes; lt 2.0: obs==2.0 fails; gte/gt equal-boundary mirror.
# Each failing side yields the exact THRESHOLD_VIOLATION format.

def _rubric_op(op: str, threshold: float):
    return {"token_cost": MetricDef(
        metric="token_cost", operator=op, threshold=threshold,
        verification="pytest", source="budget", aggregation="median", unit="USD")}


@pytest.mark.parametrize(
    "op,observed,expected_status",
    [
        ("eq", 2.0, "COMPLETE"),   # equal passes
        ("eq", 2.5, "REVIEW"),     # not equal fails
        ("lte", 2.0, "COMPLETE"),  # == boundary passes
        ("lte", 2.5, "REVIEW"),
        ("gte", 2.0, "COMPLETE"),  # == boundary passes
        ("gte", 1.5, "REVIEW"),
        ("lt", 2.0, "REVIEW"),     # == boundary FAILS (strict)
        ("lt", 1.5, "COMPLETE"),
        ("gt", 2.0, "REVIEW"),     # == boundary FAILS (strict)
        ("gt", 2.5, "COMPLETE"),
    ],
)
def test_operator_boundaries(op, observed, expected_status):
    rubric = _rubric_op(op, 2.0)
    # both sides same observed value -> both pass or both fail together
    b = _summary(variant="B0", metrics={"token_cost": observed})
    e = _summary(variant="B1", metrics={"token_cost": observed})
    r = compare_runs(b, e, rubric)
    if expected_status == "COMPLETE":
        assert r.completion_status is CompletionStatus.COMPLETE
        assert r.failures == []
    else:
        assert r.completion_status is CompletionStatus.REVIEW
        assert r.incomplete_reason is None
        assert r.winner is None and r.baseline_win is False and r.enhanced_win is False
        # both sides fail (same observed) -> exactly two violations, correct format
        assert len(r.failures) == 2
        for side in ("baseline", "enhanced"):
            assert (f"THRESHOLD_VIOLATION:token_cost:{side}:observed={observed}"
                    f":operator={op}:threshold=2.0") in r.failures
