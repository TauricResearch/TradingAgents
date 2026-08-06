"""Pure insertion-governance contracts for formal artifacts and labels."""

from __future__ import annotations

import math
import statistics
from copy import deepcopy

import pytest

from tradingagents.formal_governance import (
    FORMAL_ARTIFACT_SCHEMAS,
    FORMAL_LABEL_SCHEMAS,
    FormalGovernanceError,
    validate_formal_artifact_insert,
    validate_formal_label_insert,
)
from tradingagents.research_protocol import content_id

RUN_ID = "formal-governance-primary"
PROTOCOL_ID = "protocol-formal-governance"


def _artifact_id(artifact_type: str, content: dict) -> str:
    if artifact_type == "global_forecast_bundle":
        return content_id(content, prefix="artifact_")
    return content_id({"artifact_type": artifact_type, "content": content}, prefix="artifact_")


def _validate_artifact(
    artifact_type: str,
    content: dict,
    *,
    artifact_id: str | None = None,
    primary_run_id: str | None = RUN_ID,
    completed_intervals: int = 0,
    activity_exists: bool = True,
) -> None:
    validate_formal_artifact_insert(
        artifact_id=artifact_id or _artifact_id(artifact_type, content),
        artifact_type=artifact_type,
        content=content,
        primary_run_id=primary_run_id,
        protocol_id=PROTOCOL_ID,
        completed_intervals=completed_intervals,
        activity_exists=activity_exists,
    )


def _invocation_identity(*, ordinal: int = 1) -> dict:
    return {
        "scope": "formal-global-v2",
        "run_id": RUN_ID,
        "decision_date": "2026-08-05",
        "ordinal": ordinal,
        "stage": "champion",
        "provider": "openai",
        "requested_model": "gpt-5",
        "input_bundle_id": "input_fixture",
    }


def _reservation() -> dict:
    identity = _invocation_identity()
    decision_key = f"llm:formal-global-v2:decision:{RUN_ID}:{identity['decision_date']}"
    daily_key = (
        f"llm:formal-global-v2:protocol:{PROTOCOL_ID}:utc-day:2026-08-06"
    )
    return {
        "schema_version": 2,
        "invocation_id": content_id(identity, prefix="invocation_"),
        **identity,
        "prompt_id": "prompt_fixture",
        "prompt_bytes": 10,
        "max_prompt_bytes": 100,
        "max_completion_tokens": 20,
        "max_calls_per_decision": 3,
        "max_calls_per_utc_day": 10,
        "decision_counter_key": decision_key,
        "daily_counter_key": daily_key,
        "utc_day": "2026-08-06",
        "reserved_utc": "2026-08-06T00:00:00+00:00",
        "reservation_counts": {decision_key: 1, daily_key: 1},
    }


def _successful_result(*, usage_metadata: dict | None = None) -> dict:
    identity = _invocation_identity()
    return {
        "schema_version": 2,
        "invocation_id": content_id(identity, prefix="invocation_"),
        **identity,
        "reservation_artifact_id": "artifact_" + "a" * 24,
        "status": "success",
        "returned_model": "gpt-5",
        "model_id": "model_fixture",
        "response_id": "response_fixture",
        "usage_metadata": usage_metadata or {"output_tokens": 10},
        "forecast_bundle_id": "bundle_fixture",
        "completed_utc": "2026-08-06T00:00:01+00:00",
        "elapsed_ms": 10,
    }


def _gate20_report() -> dict:
    base = {
        "schema_version": 1,
        "report_type": "global-event-v2-operations-only-interim",
        "protocol_id": PROTOCOL_ID,
        "run_id": RUN_ID,
        "registration_id": "registration_fixture",
        "review_gate": 20,
        "interim": True,
        "scope": "operations-only",
        "completed_intervals": 20,
        "interpretation": "operations-only; no efficacy outcomes were accessed",
        "outcomes_read": False,
        "assignment_completeness": {},
        "attempt_operations": {},
        "mark_completeness": {},
        "receipt_operations": {},
    }
    return {**base, "report_id": content_id(base, prefix="interim_report_")}


def _development_audit() -> dict:
    paths = {
        "candidate-a": [0.001 * ((index % 4) - 1) for index in range(20)],
        "candidate-b": [0.0008 * ((index % 5) - 2) for index in range(20)],
    }
    sharpes = {
        candidate: statistics.fmean(path) / statistics.stdev(path) * math.sqrt(252)
        for candidate, path in paths.items()
    }
    base = {
        "schema_version": 1,
        "audit_type": "complete-development-selection-universe",
        "protocol_id": PROTOCOL_ID,
        "development_sample_id": "development-sample-fixture",
        "selected_candidate_id": "candidate-a",
        "candidate_ids": sorted(paths),
        "candidate_sharpes": sharpes,
        "candidate_return_paths": paths,
        "observation_count": 20,
        "periods_per_year": 252,
        "completeness_attested": True,
    }
    return {**base, "audit_id": content_id(base, prefix="selection_audit_")}


def _registration_details() -> dict:
    base = {
        "schema_version": 2,
        "registration_type": "confirmatory",
        "run_id": RUN_ID,
        "protocol_id": PROTOCOL_ID,
        "analysis_id": "analysis_" + "1" * 24,
        "review_gates_id": "reviews_" + "2" * 24,
        "decision_semantics_id": "semantics_" + "3" * 24,
        "outcome_semantics_id": "outcome_semantics_" + "a" * 64,
        "configuration_binding": {
            "collector_configuration_id": "config_" + "b" * 24,
            "paper_decision_configuration_id": "config_" + "c" * 24,
            "paper_marker_configuration_id": "config_" + "d" * 24,
            "configuration_manifest_id": "config_" + "e" * 24,
        },
        "registered_strategies": ["champion"],
        "confirmatory_family": ["primary"],
        "secondary_family": [],
        "trial_clock": {"holding_intervals": 252},
        "parent_run_id": None,
        "outcomes_accessed_before_registration": False,
    }
    return {**base, "registration_id": content_id(base, prefix="registration_")}


@pytest.mark.unit
def test_frozen_artifact_and_label_allowlists_are_exact():
    assert set(FORMAL_ARTIFACT_SCHEMAS) == {
        "formal_development_selection_audit",
        "llm_invocation_reserved",
        "llm_invocation_result",
        "global_forecast_bundle",
        "formal_outcome_access",
        "formal_interim_integrity_failure",
        "formal_interim_operations_report",
        "formal_interim_calibration_report",
        "formal_interim_operational_integrity_report",
        "formal_final_verification_manifest",
        "formal_review_integrity_failure",
        "formal_outcome_bundle",
        "formal_confirmatory_report",
    }
    assert set(FORMAL_LABEL_SCHEMAS) == {
        "confirmatory-trial",
        "formal-review-20-operations",
        "formal-review-60-calibration",
        "formal-review-126-descriptive",
        "formal-review-252-complete",
    }


@pytest.mark.unit
def test_llm_receipt_accepts_exact_primary_scope_and_rejects_wrong_or_forged_id():
    reservation = _reservation()
    _validate_artifact("llm_invocation_reserved", reservation)

    wrong_run = {**reservation, "run_id": "wrong-run"}
    with pytest.raises(FormalGovernanceError, match="run ID"):
        _validate_artifact("llm_invocation_reserved", wrong_run)
    with pytest.raises(FormalGovernanceError, match="content ID"):
        _validate_artifact(
            "llm_invocation_reserved",
            reservation,
            artifact_id="artifact_" + "f" * 24,
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("content", "primary_run_id"),
    [
        ({"run_id": RUN_ID, "payload": {"strategy_returns": [0.1]}}, RUN_ID),
        ({"payload": {"run_id": RUN_ID, "strategy_returns": [0.1]}}, RUN_ID),
        ({"run_id": RUN_ID}, None),
    ],
)
def test_unknown_unscoped_and_nested_only_artifacts_fail(content, primary_run_id):
    with pytest.raises(FormalGovernanceError):
        _validate_artifact("research_note", content, primary_run_id=primary_run_id)


@pytest.mark.unit
@pytest.mark.parametrize(
    "forbidden_key",
    ["strategy_returns", "Strategy_Returns", "returns", "NAV", "pnl"],
)
def test_rehashed_allowed_artifact_cannot_smuggle_nested_outcomes(forbidden_key):
    result = _successful_result(
        usage_metadata={"provider_usage": {forbidden_key: [0.01, -0.02]}}
    )
    with pytest.raises(FormalGovernanceError, match="forbidden outcome key"):
        _validate_artifact("llm_invocation_result", result)


@pytest.mark.unit
def test_interim_and_final_artifacts_are_rejected_before_their_exact_gate():
    report = _gate20_report()
    _validate_artifact("formal_interim_operations_report", report, completed_intervals=20)
    with pytest.raises(FormalGovernanceError, match="exact gate"):
        _validate_artifact("formal_interim_operations_report", report, completed_intervals=19)

    final_bundle = {
        "schema_version": 1,
        "bundle_type": "global-event-v2-final-outcomes",
        "protocol_id": PROTOCOL_ID,
        "run_id": RUN_ID,
        "registration_id": "registration_fixture",
        "holding_intervals": 252,
        "successful_decision_sets": 60,
        "synchronized_marks": 60,
        "verification_manifest_id": "formal_verification_fixture",
        "verification_manifest_artifact_id": "artifact_fixture",
        "assignments": [],
        "strategy_returns": {},
        "benchmark_returns": [],
    }
    with pytest.raises(FormalGovernanceError, match="exactly 252"):
        _validate_artifact("formal_outcome_bundle", final_bundle, completed_intervals=60)


@pytest.mark.unit
def test_development_audit_is_exact_content_addressed_and_pre_activity_only():
    audit = _development_audit()
    _validate_artifact(
        "formal_development_selection_audit",
        audit,
        primary_run_id=None,
        completed_intervals=0,
        activity_exists=False,
    )
    with pytest.raises(FormalGovernanceError, match="precede registration"):
        _validate_artifact(
            "formal_development_selection_audit",
            audit,
            primary_run_id=RUN_ID,
            completed_intervals=0,
            activity_exists=False,
        )
    forged = deepcopy(audit)
    forged["candidate_sharpes"]["candidate-a"] += 1.0
    forged["audit_id"] = content_id(
        {key: value for key, value in forged.items() if key != "audit_id"},
        prefix="selection_audit_",
    )
    with pytest.raises(FormalGovernanceError, match="Sharpe"):
        _validate_artifact(
            "formal_development_selection_audit",
            forged,
            primary_run_id=None,
            completed_intervals=0,
            activity_exists=False,
        )


@pytest.mark.unit
def test_formal_labels_reject_unknown_wrong_early_and_nested_smuggling():
    registration = _registration_details()
    validate_formal_label_insert(
        run_id=RUN_ID,
        label="confirmatory-trial",
        details=registration,
        primary_run_id=RUN_ID,
        protocol_id=PROTOCOL_ID,
        completed_intervals=0,
        activity_exists=False,
    )
    with pytest.raises(FormalGovernanceError, match="not allowlisted"):
        validate_formal_label_insert(
            run_id=RUN_ID,
            label="incident",
            details={},
            primary_run_id=RUN_ID,
            protocol_id=PROTOCOL_ID,
            completed_intervals=0,
            activity_exists=False,
        )
    with pytest.raises(FormalGovernanceError, match="run ID"):
        validate_formal_label_insert(
            run_id="wrong-run",
            label="confirmatory-trial",
            details=registration,
            primary_run_id=RUN_ID,
            protocol_id=PROTOCOL_ID,
            completed_intervals=0,
            activity_exists=False,
        )

    nested = deepcopy(registration)
    nested["trial_clock"]["strategy_returns"] = [0.1]
    nested["registration_id"] = content_id(
        {key: value for key, value in nested.items() if key != "registration_id"},
        prefix="registration_",
    )
    with pytest.raises(FormalGovernanceError, match="forbidden outcome key"):
        validate_formal_label_insert(
            run_id=RUN_ID,
            label="confirmatory-trial",
            details=nested,
            primary_run_id=RUN_ID,
            protocol_id=PROTOCOL_ID,
            completed_intervals=0,
            activity_exists=False,
        )

    interim_details = {
        "schema_version": 1,
        "protocol_id": PROTOCOL_ID,
        "review_gate": 20,
        "scope": "operations-only",
        "report_id": "interim_report_fixture",
        "report_artifact_id": "artifact_fixture",
        "outcomes_withheld": True,
    }
    with pytest.raises(FormalGovernanceError, match="exact gate"):
        validate_formal_label_insert(
            run_id=RUN_ID,
            label="formal-review-20-operations",
            details=interim_details,
            primary_run_id=RUN_ID,
            protocol_id=PROTOCOL_ID,
            completed_intervals=19,
            activity_exists=True,
        )


@pytest.mark.unit
def test_forecast_bundle_contract_includes_positive_attempt_ordinal():
    content = {key: {} for key in next(iter(FORMAL_ARTIFACT_SCHEMAS["global_forecast_bundle"]))}
    content.update(
        {
            "schema_version": 3,
            "protocol_id": PROTOCOL_ID,
            "build_id": "build_" + "1" * 24,
            "run_id": RUN_ID,
            "decision_date": "2026-08-05",
            "attempt_ordinal": 1,
            "trial_registration_id": "registration_fixture",
            "universe": [],
            "required_evidence_query_slots": [],
            "invocation_stage_order": [],
            "public_reaction_only": None,
        }
    )
    _validate_artifact("global_forecast_bundle", content)
    content["attempt_ordinal"] = 0
    with pytest.raises(FormalGovernanceError, match="attempt ordinal"):
        _validate_artifact("global_forecast_bundle", content)
