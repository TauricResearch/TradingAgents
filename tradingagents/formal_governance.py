"""Frozen insertion-time governance for formal artifacts and run labels.

The PostgreSQL migration is the production enforcement boundary.  This module
holds the same explicit allowlist as testable Python data and provides a pure
validator for writers that want to fail before attempting an INSERT.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping
from typing import Any

from tradingagents.research_protocol import content_id


def _keys(*values: str) -> frozenset[str]:
    return frozenset(values)


_RUN_PROTOCOL = _keys("run_id", "protocol_id")
_INTERIM_COMMON = _keys(
    "schema_version",
    "report_type",
    "protocol_id",
    "run_id",
    "registration_id",
    "review_gate",
    "interim",
    "scope",
    "completed_intervals",
    "interpretation",
    "report_id",
)

FORMAL_ARTIFACT_SCHEMAS: dict[str, tuple[frozenset[str], ...]] = {
    "formal_development_selection_audit": (
        _keys(
            "schema_version",
            "audit_type",
            "protocol_id",
            "development_sample_id",
            "selected_candidate_id",
            "candidate_ids",
            "candidate_sharpes",
            "candidate_return_paths",
            "observation_count",
            "periods_per_year",
            "completeness_attested",
            "audit_id",
        ),
    ),
    "llm_invocation_reserved": (
        _keys(
            "schema_version",
            "invocation_id",
            "scope",
            "run_id",
            "decision_date",
            "ordinal",
            "stage",
            "provider",
            "requested_model",
            "input_bundle_id",
            "prompt_id",
            "prompt_bytes",
            "max_prompt_bytes",
            "max_completion_tokens",
            "max_calls_per_decision",
            "max_calls_per_utc_day",
            "decision_counter_key",
            "daily_counter_key",
            "utc_day",
            "reserved_utc",
            "reservation_counts",
        ),
    ),
    "llm_invocation_result": (
        _keys(
            "schema_version",
            "invocation_id",
            "scope",
            "run_id",
            "decision_date",
            "ordinal",
            "stage",
            "provider",
            "requested_model",
            "input_bundle_id",
            "reservation_artifact_id",
            "status",
            "error_type",
            "completed_utc",
            "elapsed_ms",
        ),
        _keys(
            "schema_version",
            "invocation_id",
            "scope",
            "run_id",
            "decision_date",
            "ordinal",
            "stage",
            "provider",
            "requested_model",
            "input_bundle_id",
            "reservation_artifact_id",
            "status",
            "returned_model",
            "model_id",
            "response_id",
            "usage_metadata",
            "forecast_bundle_id",
            "completed_utc",
            "elapsed_ms",
        ),
    ),
    "global_forecast_bundle": (
        _keys(
            "schema_version",
            "protocol_id",
            "build_id",
            "run_id",
            "decision_date",
            "attempt_ordinal",
            "universe",
            "decision_context",
            "coverage",
            "required_evidence_query_slots",
            "evidence_policy",
            "x_cycle_availability",
            "evidence_selection_manifest",
            "evidence_selection_coverage",
            "decision_semantics",
            "trial_registration_id",
            "llm_policy",
            "invocation_stage_order",
            "champion",
            "without_public_reaction",
            "public_reaction_only",
            "market_inputs",
            "stale_input_lineage",
            "strategy_inputs",
            "strategy_targets",
        ),
    ),
    "formal_outcome_access": (
        _keys(
            "schema_version",
            "run_id",
            "protocol_id",
            "review_gate",
            "access_kind",
            "accessed_utc",
            "outcomes_may_be_read_after_this_receipt",
        ),
        _keys(
            "schema_version",
            "run_id",
            "protocol_id",
            "review_gate",
            "access_kind",
            "accessed_utc",
            "report_id",
            "outcomes_may_be_read_after_this_receipt",
        ),
    ),
    "formal_interim_integrity_failure": (
        _keys("schema_version", "run_id", "protocol_id", "review_gate", "reason_code"),
        _keys(
            "schema_version",
            "run_id",
            "protocol_id",
            "review_gate",
            "reason_code",
            "access_artifact_id",
        ),
    ),
    "formal_interim_operations_report": (
        _INTERIM_COMMON
        | _keys(
            "outcomes_read",
            "assignment_completeness",
            "attempt_operations",
            "mark_completeness",
            "receipt_operations",
        ),
    ),
    "formal_interim_calibration_report": (
        _INTERIM_COMMON
        | _keys(
            "successful_decision_sets",
            "forecast_observations",
            "calibration",
            "forecast_integrity",
            "selected_evidence_occurrence_balance",
            "missingness",
        ),
    ),
    "formal_interim_operational_integrity_report": (
        _INTERIM_COMMON
        | _keys(
            "successful_decision_sets",
            "outcomes_read",
            "strategy_identities_withheld",
            "efficacy_statistics_withheld",
            "aggregate_integrity",
        ),
    ),
    "formal_final_verification_manifest": (
        _keys(
            "schema_version",
            "manifest_type",
            "protocol_id",
            "run_id",
            "coverage_rule",
            "successful_applied_decisions",
            "decision_dates",
            "verifications",
            "external_calls_total",
            "exact_coverage",
            "price_capture_manifest_id",
            "verification_manifest_id",
        ),
    ),
    "formal_review_integrity_failure": (
        _keys("schema_version", "run_id", "protocol_id", "review_gate", "reason_code"),
        _keys(
            "schema_version",
            "run_id",
            "protocol_id",
            "review_gate",
            "access_artifact_id",
            "reason_code",
        ),
    ),
    "formal_outcome_bundle": (
        _keys(
            "schema_version",
            "bundle_type",
            "protocol_id",
            "run_id",
            "registration_id",
            "holding_intervals",
            "successful_decision_sets",
            "synchronized_marks",
            "verification_manifest_id",
            "verification_manifest_artifact_id",
            "assignments",
            "strategy_returns",
            "benchmark_returns",
        ),
    ),
    "formal_confirmatory_report": (
        _keys(
            "schema_version",
            "report_type",
            "protocol_id",
            "run_id",
            "registration_id",
            "review_gate",
            "interim",
            "outcome_bundle_id",
            "verification_manifest_id",
            "verification_manifest_artifact_id",
            "readout",
            "report_id",
        ),
    ),
}

FORMAL_LABEL_SCHEMAS: dict[str, tuple[frozenset[str], ...]] = {
    "confirmatory-trial": (
        _keys(
            "schema_version",
            "registration_type",
            "run_id",
            "protocol_id",
            "analysis_id",
            "review_gates_id",
            "decision_semantics_id",
            "outcome_semantics_id",
            "configuration_binding",
            "registered_strategies",
            "confirmatory_family",
            "secondary_family",
            "trial_clock",
            "parent_run_id",
            "outcomes_accessed_before_registration",
            "registration_id",
        ),
    ),
    "formal-review-20-operations": (
        _keys(
            "schema_version",
            "protocol_id",
            "review_gate",
            "scope",
            "report_id",
            "report_artifact_id",
            "outcomes_withheld",
        ),
    ),
    "formal-review-60-calibration": (
        _keys(
            "schema_version",
            "protocol_id",
            "review_gate",
            "scope",
            "report_id",
            "report_artifact_id",
            "outcomes_withheld",
        ),
    ),
    "formal-review-126-descriptive": (
        _keys(
            "schema_version",
            "protocol_id",
            "review_gate",
            "scope",
            "report_id",
            "report_artifact_id",
            "outcomes_withheld",
        ),
    ),
    "formal-review-252-complete": (
        _keys(
            "schema_version",
            "protocol_id",
            "review_gate",
            "outcome_bundle_id",
            "outcome_bundle_artifact_id",
            "report_id",
            "report_artifact_id",
            "verification_manifest_id",
            "verification_manifest_artifact_id",
            "live_capital_approved",
        ),
    ),
}

_INTERIM_ARTIFACT_GATES = {
    "formal_interim_operations_report": 20,
    "formal_interim_calibration_report": 60,
    "formal_interim_operational_integrity_report": 126,
}
_INTERIM_LABELS = {
    "formal-review-20-operations": (20, "operations-only"),
    "formal-review-60-calibration": (60, "data-and-calibration-only"),
    "formal-review-126-descriptive": (126, "locked-descriptive-nonconclusive"),
}
_FINAL_ARTIFACTS = {
    "formal_final_verification_manifest",
    "formal_review_integrity_failure",
    "formal_outcome_bundle",
    "formal_confirmatory_report",
}
_ARTIFACT_SCHEMA_VERSIONS = {
    "formal_development_selection_audit": 1,
    "llm_invocation_reserved": 2,
    "llm_invocation_result": 2,
    "global_forecast_bundle": 3,
    "formal_outcome_access": 1,
    "formal_interim_integrity_failure": 1,
    "formal_interim_operations_report": 1,
    "formal_interim_calibration_report": 1,
    "formal_interim_operational_integrity_report": 1,
    "formal_final_verification_manifest": 1,
    "formal_review_integrity_failure": 1,
    "formal_outcome_bundle": 1,
    "formal_confirmatory_report": 1,
}
_INTERIM_REPORT_CONTRACTS = {
    "formal_interim_operations_report": (
        "global-event-v2-operations-only-interim",
        "operations-only",
    ),
    "formal_interim_calibration_report": (
        "global-event-v2-data-calibration-interim",
        "data-and-calibration-only",
    ),
    "formal_interim_operational_integrity_report": (
        "global-event-v2-blinded-operational-integrity-interim",
        "locked-descriptive-nonconclusive",
    ),
}
_PRE_FINAL_FORBIDDEN_KEYS = {
    "benchmark_returns",
    "benchmark_nav",
    "benchmark_period_return",
    "formal_readout",
    "machine_statistical_candidate",
    "nav",
    "period_return",
    "pnl",
    "portfolio_returns",
    "profit_and_loss",
    "promotion_decision",
    "realized_returns",
    "returns",
    "sharpe",
    "sharpe_ratio",
    "spy_descriptives",
    "strategy_descriptives",
    "strategy_performance",
    "strategy_returns",
}


class FormalGovernanceError(ValueError):
    """Raised when a formal artifact or label violates the frozen contract."""


def _require_exact_schema(kind: str, value: Mapping[str, Any], schemas) -> None:
    actual = frozenset(value)
    if actual not in schemas:
        raise FormalGovernanceError(f"{kind} schema differs from the frozen allowlist")


def _require_nonempty_strings(
    kind: str, value: Mapping[str, Any], fields: tuple[str, ...]
) -> None:
    if any(
        not isinstance(value.get(field), str) or not value[field].strip()
        for field in fields
    ):
        raise FormalGovernanceError(f"{kind} string fields are malformed")


def _require_integer_fields(
    kind: str,
    value: Mapping[str, Any],
    fields: tuple[str, ...],
    *,
    minimum: int = 0,
) -> None:
    if any(type(value.get(field)) is not int or value[field] < minimum for field in fields):
        raise FormalGovernanceError(f"{kind} integer fields are malformed")


def _require_container_fields(
    kind: str,
    value: Mapping[str, Any],
    *,
    objects: tuple[str, ...] = (),
    arrays: tuple[str, ...] = (),
) -> None:
    if any(not isinstance(value.get(field), Mapping) for field in objects) or any(
        not isinstance(value.get(field), list) for field in arrays
    ):
        raise FormalGovernanceError(f"{kind} container fields are malformed")


def _require_content_id(
    value: Any, prefix: str, label: str, *, digest_length: int = 24
) -> str:
    if (
        not isinstance(value, str)
        or len(value) != len(prefix) + digest_length
        or not value.startswith(prefix)
        or any(character not in "0123456789abcdef" for character in value[len(prefix) :])
    ):
        raise FormalGovernanceError(f"{label} is malformed")
    return value


def _nested_forbidden_key(value: Any) -> str | None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if isinstance(key, str) and key.lower() in _PRE_FINAL_FORBIDDEN_KEYS:
                return key
            nested = _nested_forbidden_key(child)
            if nested is not None:
                return nested
    elif isinstance(value, list):
        for child in value:
            nested = _nested_forbidden_key(child)
            if nested is not None:
                return nested
    return None


def _artifact_identity(artifact_type: str, content: Mapping[str, Any]) -> str:
    if artifact_type == "global_forecast_bundle":
        return content_id(content, prefix="artifact_")
    return content_id({"artifact_type": artifact_type, "content": content}, prefix="artifact_")


def _validate_invocation_identity(content: Mapping[str, Any]) -> None:
    identity_keys = (
        "scope",
        "run_id",
        "decision_date",
        "ordinal",
        "stage",
        "provider",
        "requested_model",
        "input_bundle_id",
    )
    identity = {key: content.get(key) for key in identity_keys}
    if content.get("scope") != "formal-global-v2" or content.get("invocation_id") != content_id(
        identity, prefix="invocation_"
    ):
        raise FormalGovernanceError("formal invocation identity is invalid")


def _validate_development_audit(content: Mapping[str, Any], *, protocol_id: str) -> None:
    if (
        content.get("schema_version") != 1
        or content.get("audit_type") != "complete-development-selection-universe"
        or content.get("protocol_id") != protocol_id
        or content.get("periods_per_year") != 252
        or content.get("completeness_attested") is not True
    ):
        raise FormalGovernanceError("development selection audit is malformed")
    candidate_ids = content.get("candidate_ids")
    paths = content.get("candidate_return_paths")
    sharpes = content.get("candidate_sharpes")
    observations = content.get("observation_count")
    if (
        not isinstance(candidate_ids, list)
        or len(candidate_ids) < 2
        or candidate_ids != sorted(candidate_ids)
        or len(candidate_ids) != len(set(candidate_ids))
        or any(not isinstance(candidate, str) or not candidate for candidate in candidate_ids)
        or content.get("selected_candidate_id") not in candidate_ids
        or not isinstance(content.get("development_sample_id"), str)
        or not content["development_sample_id"]
        or type(observations) is not int
        or observations < 4
        or not isinstance(paths, Mapping)
        or set(paths) != set(candidate_ids)
        or not isinstance(sharpes, Mapping)
        or set(sharpes) != set(candidate_ids)
    ):
        raise FormalGovernanceError("development selection audit is incomplete")
    for candidate in candidate_ids:
        values = paths[candidate]
        reported = sharpes[candidate]
        if (
            not isinstance(values, list)
            or len(values) != observations
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) <= -1.0
                for value in values
            )
            or isinstance(reported, bool)
            or not isinstance(reported, (int, float))
            or not math.isfinite(float(reported))
        ):
            raise FormalGovernanceError("development selection audit paths are invalid")
        numeric_values = [float(value) for value in values]
        mean = statistics.fmean(numeric_values)
        standard_deviation = statistics.stdev(numeric_values)
        if standard_deviation == 0:
            recomputed = math.copysign(math.inf, mean) if mean else 0.0
        else:
            recomputed = mean / standard_deviation * math.sqrt(252)
        if not math.isfinite(recomputed) or not math.isclose(
            recomputed, float(reported), rel_tol=1e-12, abs_tol=1e-12
        ):
            raise FormalGovernanceError("development selection audit Sharpe is invalid")
    base = {key: value for key, value in content.items() if key != "audit_id"}
    if content.get("audit_id") != content_id(base, prefix="selection_audit_"):
        raise FormalGovernanceError("development selection audit ID is invalid")


def validate_formal_artifact_insert(
    *,
    artifact_id: str,
    artifact_type: str,
    content: Mapping[str, Any],
    primary_run_id: str | None,
    protocol_id: str,
    completed_intervals: int,
    activity_exists: bool,
) -> None:
    """Validate one artifact against the frozen insertion-time contract."""
    if not isinstance(content, Mapping):
        raise FormalGovernanceError("formal artifact content must be an object")
    schemas = FORMAL_ARTIFACT_SCHEMAS.get(artifact_type)
    if schemas is None:
        raise FormalGovernanceError("formal artifact type is not allowlisted")
    _require_exact_schema("formal artifact", content, schemas)

    if artifact_type == "formal_development_selection_audit":
        if primary_run_id is not None or activity_exists or completed_intervals != 0:
            raise FormalGovernanceError(
                "development selection audit must precede registration and activity"
            )
        forbidden = _nested_forbidden_key(content)
        if forbidden is not None:
            raise FormalGovernanceError(
                f"development selection audit contains forbidden outcome key {forbidden!r}"
            )
        _validate_development_audit(content, protocol_id=protocol_id)
    else:
        if not isinstance(primary_run_id, str) or not primary_run_id:
            raise FormalGovernanceError("formal artifact requires a primary run")
        if content.get("run_id") != primary_run_id:
            raise FormalGovernanceError("formal artifact run ID is unscoped or wrong")
        if "protocol_id" in content and content.get("protocol_id") != protocol_id:
            raise FormalGovernanceError("formal artifact protocol ID is wrong")

    if content.get("schema_version") != _ARTIFACT_SCHEMA_VERSIONS[artifact_type]:
        raise FormalGovernanceError("formal artifact schema version is unsupported")
    _require_integer_fields("formal artifact", content, ("schema_version",), minimum=1)
    if _artifact_identity(artifact_type, content) != artifact_id:
        raise FormalGovernanceError("formal artifact content ID is invalid")

    if artifact_type in {"llm_invocation_reserved", "llm_invocation_result"}:
        _require_nonempty_strings(
            "formal invocation",
            content,
            (
                "invocation_id",
                "scope",
                "run_id",
                "decision_date",
                "stage",
                "provider",
                "requested_model",
                "input_bundle_id",
            ),
        )
        _require_integer_fields("formal invocation", content, ("ordinal",), minimum=1)
        _validate_invocation_identity(content)
    if artifact_type == "llm_invocation_reserved":
        _require_nonempty_strings(
            "formal invocation reservation",
            content,
            (
                "prompt_id",
                "decision_counter_key",
                "daily_counter_key",
                "utc_day",
                "reserved_utc",
            ),
        )
        _require_integer_fields(
            "formal invocation reservation",
            content,
            (
                "prompt_bytes",
                "max_prompt_bytes",
                "max_completion_tokens",
                "max_calls_per_decision",
                "max_calls_per_utc_day",
            ),
            minimum=1,
        )
        _require_container_fields(
            "formal invocation reservation", content, objects=("reservation_counts",)
        )
        decision_key = content.get("decision_counter_key")
        daily_key = content.get("daily_counter_key")
        counts = content.get("reservation_counts")
        if (
            not isinstance(decision_key, str)
            or not decision_key
            or not isinstance(daily_key, str)
            or not daily_key
            or decision_key == daily_key
            or not isinstance(counts, Mapping)
            or set(counts) != {decision_key, daily_key}
            or any(type(value) is not int or value < 1 for value in counts.values())
        ):
            raise FormalGovernanceError("formal invocation reservation counters are invalid")
    if artifact_type == "llm_invocation_result" and content.get("status") not in {
        "failed",
        "success",
    }:
        raise FormalGovernanceError("formal invocation result status is invalid")
    if artifact_type == "llm_invocation_result":
        _require_nonempty_strings(
            "formal invocation result",
            content,
            (
                "reservation_artifact_id",
                "status",
                "completed_utc",
            ),
        )
        _require_integer_fields(
            "formal invocation result", content, ("elapsed_ms",), minimum=0
        )
        _require_content_id(
            content["reservation_artifact_id"],
            "artifact_",
            "formal invocation reservation artifact ID",
        )
        if content["status"] == "failed":
            _require_nonempty_strings("formal invocation failure", content, ("error_type",))
        else:
            _require_nonempty_strings(
                "formal invocation success",
                content,
                (
                    "returned_model",
                    "model_id",
                    "response_id",
                    "forecast_bundle_id",
                ),
            )
            _require_container_fields(
                "formal invocation success", content, objects=("usage_metadata",)
            )
    if artifact_type == "global_forecast_bundle" and content.get("trial_registration_id") in {
        None,
        "",
    }:
        raise FormalGovernanceError("formal forecast registration identity is missing")
    if artifact_type == "global_forecast_bundle" and (
        type(content.get("attempt_ordinal")) is not int or content["attempt_ordinal"] < 1
    ):
        raise FormalGovernanceError("formal forecast attempt ordinal is invalid")
    if artifact_type == "global_forecast_bundle":
        _require_nonempty_strings(
            "formal forecast bundle",
            content,
            (
                "protocol_id",
                "build_id",
                "run_id",
                "decision_date",
                "trial_registration_id",
            ),
        )
        _require_container_fields(
            "formal forecast bundle",
            content,
            objects=(
                "decision_context",
                "coverage",
                "evidence_policy",
                "x_cycle_availability",
                "evidence_selection_manifest",
                "evidence_selection_coverage",
                "decision_semantics",
                "llm_policy",
                "champion",
                "without_public_reaction",
                "market_inputs",
                "stale_input_lineage",
                "strategy_inputs",
                "strategy_targets",
            ),
            arrays=("universe", "required_evidence_query_slots", "invocation_stage_order"),
        )
        public_only = content.get("public_reaction_only")
        if public_only is not None and not isinstance(public_only, Mapping):
            raise FormalGovernanceError(
                "formal forecast bundle public-reaction field is malformed"
            )

    gate = _INTERIM_ARTIFACT_GATES.get(artifact_type)
    if gate is not None:
        report_type, scope = _INTERIM_REPORT_CONTRACTS[artifact_type]
        if (
            completed_intervals != gate
            or content.get("review_gate") != gate
            or content.get("completed_intervals") != gate
            or content.get("interim") is not True
            or content.get("report_type") != report_type
            or content.get("scope") != scope
        ):
            raise FormalGovernanceError("formal interim artifact is outside its exact gate")
        report_base = {key: value for key, value in content.items() if key != "report_id"}
        if content.get("report_id") != content_id(report_base, prefix="interim_report_"):
            raise FormalGovernanceError("formal interim report ID is invalid")
        _require_nonempty_strings(
            "formal interim report",
            content,
            (
                "report_type",
                "protocol_id",
                "run_id",
                "registration_id",
                "scope",
                "interpretation",
                "report_id",
            ),
        )
        _require_integer_fields(
            "formal interim report",
            content,
            ("review_gate", "completed_intervals"),
            minimum=1,
        )
        _require_content_id(
            content["report_id"], "interim_report_", "formal interim report ID"
        )
        if artifact_type == "formal_interim_operations_report":
            _require_container_fields(
                "formal operations report",
                content,
                objects=(
                    "assignment_completeness",
                    "attempt_operations",
                    "mark_completeness",
                    "receipt_operations",
                ),
            )
            if content.get("outcomes_read") is not False:
                raise FormalGovernanceError("formal operations report read outcomes")
        elif artifact_type == "formal_interim_calibration_report":
            _require_integer_fields(
                "formal calibration report",
                content,
                ("successful_decision_sets", "forecast_observations"),
                minimum=0,
            )
            _require_container_fields(
                "formal calibration report",
                content,
                objects=(
                    "calibration",
                    "forecast_integrity",
                    "selected_evidence_occurrence_balance",
                    "missingness",
                ),
            )
        else:
            _require_integer_fields(
                "formal operational-integrity report",
                content,
                ("successful_decision_sets",),
                minimum=0,
            )
            _require_container_fields(
                "formal operational-integrity report",
                content,
                objects=("aggregate_integrity",),
            )
            if (
                content.get("outcomes_read") is not False
                or content.get("strategy_identities_withheld") is not True
                or content.get("efficacy_statistics_withheld") is not True
            ):
                raise FormalGovernanceError(
                    "formal operational-integrity report reveals efficacy"
                )
    elif artifact_type in _FINAL_ARTIFACTS:
        if completed_intervals != 252:
            raise FormalGovernanceError("formal final artifact requires exactly 252 intervals")
    elif (
        artifact_type != "formal_development_selection_audit"
        and artifact_type != "formal_outcome_access"
        and artifact_type != "formal_interim_integrity_failure"
        and completed_intervals >= 252
    ):
        raise FormalGovernanceError("formal decision artifact is beyond the trial horizon")

    if artifact_type == "formal_outcome_access":
        _require_nonempty_strings(
            "formal outcome access",
            content,
            ("run_id", "protocol_id", "access_kind"),
        )
        _require_integer_fields(
            "formal outcome access", content, ("review_gate",), minimum=1
        )
        if (
            isinstance(content.get("accessed_utc"), bool)
            or not isinstance(content.get("accessed_utc"), (int, float))
            or not math.isfinite(float(content["accessed_utc"]))
        ):
            raise FormalGovernanceError("formal outcome access timestamp is malformed")
        gate = content.get("review_gate")
        kind = content.get("access_kind")
        allowed = {
            (60, "automatic_interim_60_materialization", 60),
            (60, "explicit_interim_60_report_view", None),
            (252, "automatic_final_report_materialization", 252),
            (252, "explicit_final_report_view", None),
        }
        if (
            not any(
                gate == allowed_gate
                and kind == allowed_kind
                and (
                    exact is None
                    and completed_intervals >= allowed_gate
                    or exact is not None
                    and completed_intervals == exact
                )
                for allowed_gate, allowed_kind, exact in allowed
            )
            or content.get("outcomes_may_be_read_after_this_receipt") is not True
            or (kind.startswith("explicit_") if isinstance(kind, str) else False)
            is not ("report_id" in content)
        ):
            raise FormalGovernanceError("formal outcome access is outside its exact gate")
    if artifact_type == "formal_interim_integrity_failure":
        gate = content.get("review_gate")
        if (
            gate not in {20, 60, 126}
            or completed_intervals != gate
            or content.get("reason_code") != "integrity_validation_failed"
            or (gate == 60) is not ("access_artifact_id" in content)
        ):
            raise FormalGovernanceError("formal interim failure is outside its exact gate")
        _require_nonempty_strings(
            "formal interim failure",
            content,
            ("run_id", "protocol_id", "reason_code"),
        )
        _require_integer_fields(
            "formal interim failure", content, ("review_gate",), minimum=1
        )
        if "access_artifact_id" in content:
            _require_content_id(
                content["access_artifact_id"],
                "artifact_",
                "formal interim access artifact ID",
            )
    if artifact_type == "formal_final_verification_manifest":
        base = {key: value for key, value in content.items() if key != "verification_manifest_id"}
        if (
            content.get("manifest_type") != "global-event-v2-final-offline-verification"
            or content.get("coverage_rule") != "every-successful-applied-decision-exactly-once"
            or content.get("external_calls_total") != 0
            or content.get("exact_coverage") is not True
            or content.get("verification_manifest_id")
            != content_id(base, prefix="formal_verification_")
        ):
            raise FormalGovernanceError("formal verification manifest ID is invalid")
        _require_nonempty_strings(
            "formal verification manifest",
            content,
            (
                "manifest_type",
                "protocol_id",
                "run_id",
                "coverage_rule",
                "price_capture_manifest_id",
                "verification_manifest_id",
            ),
        )
        _require_integer_fields(
            "formal verification manifest",
            content,
            ("successful_applied_decisions", "external_calls_total"),
            minimum=0,
        )
        _require_container_fields(
            "formal verification manifest",
            content,
            arrays=("decision_dates", "verifications"),
        )
    if artifact_type == "formal_review_integrity_failure" and (
        content.get("review_gate") != 252
        or content.get("reason_code")
        not in {"offline_verification_failed", "integrity_validation_failed"}
        or (content.get("reason_code") == "integrity_validation_failed")
        is not ("access_artifact_id" in content)
    ):
        raise FormalGovernanceError("formal review failure reason is not allowlisted")
    if artifact_type == "formal_review_integrity_failure":
        _require_nonempty_strings(
            "formal review failure",
            content,
            ("run_id", "protocol_id", "reason_code"),
        )
        _require_integer_fields(
            "formal review failure", content, ("review_gate",), minimum=1
        )
        if "access_artifact_id" in content:
            _require_content_id(
                content["access_artifact_id"],
                "artifact_",
                "formal final access artifact ID",
            )
    if artifact_type == "formal_outcome_bundle" and (
        content.get("bundle_type") != "global-event-v2-final-outcomes"
        or content.get("holding_intervals") != 252
    ):
        raise FormalGovernanceError("formal outcome bundle contract is invalid")
    if artifact_type == "formal_outcome_bundle":
        _require_nonempty_strings(
            "formal outcome bundle",
            content,
            (
                "bundle_type",
                "protocol_id",
                "run_id",
                "registration_id",
                "verification_manifest_id",
                "verification_manifest_artifact_id",
            ),
        )
        _require_integer_fields(
            "formal outcome bundle",
            content,
            ("holding_intervals", "successful_decision_sets", "synchronized_marks"),
            minimum=0,
        )
        _require_container_fields(
            "formal outcome bundle",
            content,
            objects=("strategy_returns",),
            arrays=("assignments", "benchmark_returns"),
        )
        _require_content_id(
            content["verification_manifest_id"],
            "formal_verification_",
            "formal verification manifest ID",
        )
        _require_content_id(
            content["verification_manifest_artifact_id"],
            "artifact_",
            "formal verification manifest artifact ID",
        )
    if artifact_type == "formal_confirmatory_report":
        base = {key: value for key, value in content.items() if key != "report_id"}
        if (
            content.get("review_gate") != 252
            or content.get("interim") is not False
            or content.get("report_type") != "global-event-v2-sole-confirmatory-readout"
            or content.get("report_id") != content_id(base, prefix="formal_report_")
            or not isinstance(content.get("readout"), Mapping)
            or content["readout"].get("live_capital_approved") is not False
        ):
            raise FormalGovernanceError("formal confirmatory report contract is invalid")
        _require_nonempty_strings(
            "formal confirmatory report",
            content,
            (
                "report_type",
                "protocol_id",
                "run_id",
                "registration_id",
                "outcome_bundle_id",
                "verification_manifest_id",
                "verification_manifest_artifact_id",
                "report_id",
            ),
        )
        _require_content_id(
            content["outcome_bundle_id"], "outcome_bundle_", "formal outcome bundle ID"
        )
        _require_content_id(
            content["verification_manifest_id"],
            "formal_verification_",
            "formal verification manifest ID",
        )
        _require_content_id(
            content["verification_manifest_artifact_id"],
            "artifact_",
            "formal verification manifest artifact ID",
        )

    if artifact_type not in {
        "formal_development_selection_audit",
        "formal_outcome_bundle",
        "formal_confirmatory_report",
    }:
        forbidden = _nested_forbidden_key(content)
        if forbidden is not None:
            raise FormalGovernanceError(
                f"pre-final formal artifact contains forbidden outcome key {forbidden!r}"
            )


def validate_formal_label_insert(
    *,
    run_id: str,
    label: str,
    details: Mapping[str, Any],
    primary_run_id: str,
    protocol_id: str,
    completed_intervals: int,
    activity_exists: bool,
) -> None:
    """Validate one primary formal run label against its exact phase and schema."""
    if run_id != primary_run_id:
        raise FormalGovernanceError("formal label run ID is wrong")
    schemas = FORMAL_LABEL_SCHEMAS.get(label)
    if schemas is None:
        raise FormalGovernanceError("formal label is not allowlisted")
    if not isinstance(details, Mapping):
        raise FormalGovernanceError("formal label details must be an object")
    _require_exact_schema("formal label", details, schemas)
    forbidden = _nested_forbidden_key(details)
    if forbidden is not None:
        raise FormalGovernanceError(f"formal label contains forbidden outcome key {forbidden!r}")
    if details.get("protocol_id") != protocol_id:
        raise FormalGovernanceError("formal label protocol ID is wrong")
    _require_integer_fields("formal label", details, ("schema_version",), minimum=1)
    _require_nonempty_strings("formal label", details, ("protocol_id",))

    if label == "confirmatory-trial":
        base = {key: value for key, value in details.items() if key != "registration_id"}
        if (
            activity_exists
            or completed_intervals != 0
            or details.get("run_id") != run_id
            or details.get("schema_version") != 2
            or details.get("registration_type") != "confirmatory"
            or details.get("parent_run_id") is not None
            or details.get("outcomes_accessed_before_registration") is not False
            or details.get("registration_id") != content_id(base, prefix="registration_")
        ):
            raise FormalGovernanceError("confirmatory label is not pre-activity exact")
        _require_nonempty_strings(
            "confirmatory label",
            details,
            (
                "registration_type",
                "run_id",
                "analysis_id",
                "review_gates_id",
                "decision_semantics_id",
                "outcome_semantics_id",
                "registration_id",
            ),
        )
        for field, prefix in (
            ("analysis_id", "analysis_"),
            ("review_gates_id", "reviews_"),
            ("decision_semantics_id", "semantics_"),
            ("registration_id", "registration_"),
        ):
            _require_content_id(
                details[field], prefix, f"confirmatory {field}"
            )
        _require_content_id(
            details["outcome_semantics_id"],
            "outcome_semantics_",
            "confirmatory outcome semantics ID",
            digest_length=64,
        )
        _require_container_fields(
            "confirmatory label",
            details,
            objects=("trial_clock", "configuration_binding"),
            arrays=("registered_strategies", "confirmatory_family", "secondary_family"),
        )
        configuration = details["configuration_binding"]
        if set(configuration) != {
            "collector_configuration_id",
            "paper_decision_configuration_id",
            "paper_marker_configuration_id",
            "configuration_manifest_id",
        }:
            raise FormalGovernanceError(
                "confirmatory configuration binding schema is malformed"
            )
        for field in configuration:
            _require_content_id(
                configuration[field], "config_", f"confirmatory {field}"
            )
        return

    if label in _INTERIM_LABELS:
        gate, scope = _INTERIM_LABELS[label]
        if (
            completed_intervals != gate
            or details.get("schema_version") != 1
            or details.get("review_gate") != gate
            or details.get("scope") != scope
            or details.get("outcomes_withheld") is not True
        ):
            raise FormalGovernanceError("formal interim label is outside its exact gate")
        _require_nonempty_strings(
            "formal interim label",
            details,
            ("scope", "report_id", "report_artifact_id"),
        )
        _require_content_id(
            details["report_id"], "interim_report_", "formal interim report ID"
        )
        _require_content_id(
            details["report_artifact_id"],
            "artifact_",
            "formal interim report artifact ID",
        )
        return

    if (
        completed_intervals != 252
        or details.get("schema_version") != 2
        or details.get("review_gate") != 252
        or details.get("live_capital_approved") is not False
    ):
        raise FormalGovernanceError("formal final label requires exactly 252 intervals")
    _require_nonempty_strings(
        "formal final label",
        details,
        (
            "outcome_bundle_id",
            "outcome_bundle_artifact_id",
            "report_id",
            "report_artifact_id",
            "verification_manifest_id",
            "verification_manifest_artifact_id",
        ),
    )
    for field, prefix in (
        ("outcome_bundle_id", "outcome_bundle_"),
        ("outcome_bundle_artifact_id", "artifact_"),
        ("report_id", "formal_report_"),
        ("report_artifact_id", "artifact_"),
        ("verification_manifest_id", "formal_verification_"),
        ("verification_manifest_artifact_id", "artifact_"),
    ):
        _require_content_id(details[field], prefix, f"formal final {field}")


__all__ = [
    "FORMAL_ARTIFACT_SCHEMAS",
    "FORMAL_LABEL_SCHEMAS",
    "FormalGovernanceError",
    "validate_formal_artifact_insert",
    "validate_formal_label_insert",
]
