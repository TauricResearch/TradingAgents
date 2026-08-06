"""Frozen least-privilege contract for formal paper-trial runtimes.

PostgreSQL migration 013 is the enforcement boundary.  This module keeps the
same role/table matrix as ordinary Python data so deployment checks can reject
the legacy combined credential before any provider call is made.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from tradingagents.research_protocol import content_id

DECISION_ROLE = "tradingagents-paper-decision"
MARKER_ROLE = "tradingagents-paper-marker"
LEGACY_PAPER_ROLE = "tradingagents-paper"
SCHEMA_ADMIN_ROLE = "schema_admin"
SCHEMA_ADMIN_LOGIN = "tradingagents-app-v2"

DECISION_ARTIFACT_TYPES = frozenset(
    {"llm_invocation_reserved", "llm_invocation_result", "global_forecast_bundle"}
)
RUNTIME_HEARTBEAT_EVENTS = frozenset({"success", "failure", "paused"})

# Exact held weights are point-in-time operational state, not an efficacy
# outcome.  They are needed to preserve the preregistered turnover and
# constraint arithmetic.  The projection still withholds every price, return,
# NAV, cost, review artifact, and aggregate efficacy field.
DECISION_HELD_WEIGHT_POLICY = {
    "classification": "point-in-time-operational-state",
    "purpose": "exact-preregistered-turnover-and-constraint-arithmetic",
    "allowed_fields": [
        "strategy_id",
        "weights_json",
        "source_kind",
        "source_session_date",
        "source_decision_date",
    ],
    "forbidden_field_classes": [
        "prices",
        "returns",
        "nav",
        "costs",
        "review-artifacts",
        "aggregate-efficacy",
    ],
}

DECISION_SELECT_TABLES = frozenset(
    {
        "paper_runs",
        "experiment_registry",
        "formal_trial_registry",
        "formal_release_receipts",
        "formal_trial_authorizations",
        "formal_role_split_decommissions",
        "paper_run_labels",
        "paper_artifacts",
        "paper_decisions",
        "paper_targets",
        "paper_decision_bundles",
        "paper_events",
        "paper_forecasts",
        "paper_strategy_targets",
        "paper_decision_attempt_events",
    }
)
DECISION_INSERT_TABLES = frozenset(
    {
        "paper_artifacts",
        "paper_decisions",
        "paper_targets",
        "paper_decision_bundles",
        "paper_events",
        "paper_forecasts",
        "paper_strategy_targets",
        "paper_decision_attempt_events",
    }
)

MARKER_SELECT_TABLES = frozenset(
    {
        "paper_runs",
        "experiment_registry",
        "formal_trial_registry",
        "formal_release_receipts",
        "formal_trial_authorizations",
        "formal_role_split_decommissions",
        "paper_run_labels",
        "paper_targets",
        "paper_decision_bundles",
        "paper_strategy_targets",
        "paper_marks",
        "paper_strategy_marks",
        "paper_price_capture_attempt_events",
        "paper_price_capture_batches",
        "paper_price_integrity_failures",
        "paper_price_receipts",
        "paper_interval_assignments",
    }
)
MARKER_INSERT_TABLES = frozenset(
    {
        "paper_marks",
        "paper_strategy_marks",
        "paper_price_capture_attempt_events",
        "paper_price_capture_batches",
        "paper_price_integrity_failures",
        "paper_price_receipts",
        "paper_interval_assignments",
    }
)

# Every row-bearing table that must remain empty until the sole formal release
# authorization exists. Artifacts and nonconfirmatory labels use content/label
# predicates and are checked separately by the clone inspector and SQL trigger.
PREAUTHORIZATION_ACTIVITY_TABLES = frozenset(
    (DECISION_INSERT_TABLES | MARKER_INSERT_TABLES) - {"paper_artifacts"}
)

OUTCOME_TABLES = frozenset(
    {
        "paper_marks",
        "paper_strategy_marks",
        "paper_price_capture_attempt_events",
        "paper_price_capture_batches",
        "paper_price_integrity_failures",
        "paper_price_receipts",
        "paper_interval_assignments",
    }
)

PROTECTED_TABLES = frozenset(
    {
        "formal_llm_budget_counters",
        "paper_runs",
        "paper_decisions",
        "paper_targets",
        "paper_marks",
        "experiment_registry",
        "formal_trial_registry",
        "paper_run_labels",
        "paper_artifacts",
        "paper_decision_bundles",
        "paper_events",
        "paper_forecasts",
        "paper_strategy_targets",
        "paper_strategy_marks",
        "paper_price_capture_attempt_events",
        "paper_price_capture_batches",
        "paper_price_integrity_failures",
        "paper_price_receipts",
        "paper_decision_attempt_events",
        "paper_interval_assignments",
        "formal_release_receipts",
        "formal_trial_authorizations",
        "formal_role_split_decommissions",
        "formal_role_policy_contracts",
        "formal_runtime_heartbeat_events",
    }
)

ROLE_SPLIT_CONTRACT = {
    "schema_version": 1,
    "roles": {
        "decision": DECISION_ROLE,
        "marker": MARKER_ROLE,
        "legacy": LEGACY_PAPER_ROLE,
    },
    "decision_artifact_types": sorted(DECISION_ARTIFACT_TYPES),
    "decision_select_tables": sorted(DECISION_SELECT_TABLES),
    "decision_insert_tables": sorted(DECISION_INSERT_TABLES),
    "marker_select_tables": sorted(MARKER_SELECT_TABLES),
    "marker_insert_tables": sorted(MARKER_INSERT_TABLES),
    "outcome_tables": sorted(OUTCOME_TABLES),
    "protected_tables": sorted(PROTECTED_TABLES),
    "decision_held_weight_policy": DECISION_HELD_WEIGHT_POLICY,
    "decision_slot_projection": "outcome-free-ledger-eligibility-only",
    "runtime_heartbeat_events": sorted(RUNTIME_HEARTBEAT_EVENTS),
    "collector_paper_table_access": "deny-all",
    "legacy_activation_policy": "must-be-append-only-decommissioned",
    "analyzer_policy": "offline-after-governed-outcome-access-only",
}
ROLE_SPLIT_CONTRACT_ID = content_id(ROLE_SPLIT_CONTRACT, prefix="role_contract_")

ROLE_PREFLIGHT_SQL = """
SELECT current_user AS current_role,
       session_user AS session_role,
       contract_id,
       ready,
       legacy_decommissioned,
       policy_contract_matches
FROM public.formal_role_split_preflight()
""".strip()

DECISION_WEIGHT_PROJECTION_SQL = """
SELECT strategy_id, weights_json, source_kind,
       source_session_date, source_decision_date
FROM public.formal_decision_weight_projection(:run_id)
ORDER BY strategy_id
""".strip()

DECISION_SLOT_PROJECTION_SQL = """
SELECT run_id, protocol_id, registration_id, authorization_id,
       paper_decision_build_id, paper_decision_configuration_id,
       requested_decision_date, requested_entry_date,
       decision_chain_valid, horizon_open, slot_is_next,
       terminal_price_integrity_failure, eligible_for_requested_slot
FROM public.formal_decision_slot_projection(
    :run_id, :decision_date, :entry_date
)
""".strip()

RUNTIME_HEARTBEAT_SQL = """
SELECT heartbeat_id, runtime_role, event_type, observed_utc
FROM public.record_formal_runtime_heartbeat(
    :run_id, :event_type, :runtime_build_id
)
""".strip()

RUNTIME_HEALTH_PROJECTION_SQL = """
SELECT runtime_component, event_type, observed_utc,
       latest_success_utc, latest_failure_utc, latest_paused_utc
FROM public.formal_runtime_latest_health_projection(
    :protocol_id, :collector_build_id
)
ORDER BY runtime_component
""".strip()


class FormalRoleContractError(RuntimeError):
    """The connected runtime is not the exact authorized split principal."""


def is_formal_schema_admin_identity(
    *,
    current_role: object,
    session_role: object,
    current_is_schema_admin: object,
    session_is_schema_admin: object,
) -> bool:
    """Accept a direct admin or Fly MPG's exact configured default role."""

    if current_is_schema_admin is not True or session_is_schema_admin is not True:
        return False
    if current_role == session_role:
        return isinstance(session_role, str) and bool(session_role)
    return current_role == SCHEMA_ADMIN_ROLE and session_role == SCHEMA_ADMIN_LOGIN


def build_legacy_role_decommission_receipt() -> dict[str, Any]:
    """Build the sole administrator document accepted by migration 013."""

    base = {
        "schema_version": 1,
        "contract_id": ROLE_SPLIT_CONTRACT_ID,
        "legacy_role": LEGACY_PAPER_ROLE,
        "decision_role": DECISION_ROLE,
        "marker_role": MARKER_ROLE,
    }
    return {**base, "decommission_id": content_id(base, prefix="decommission_")}


def runtime_role_decommission_release_payload() -> dict[str, Any]:
    """Build migration 012's release payload bound to the durable DB receipt."""

    receipt = build_legacy_role_decommission_receipt()
    return {
        "passed": True,
        "decommission_id": receipt["decommission_id"],
        "legacy_role": LEGACY_PAPER_ROLE,
        "decision_role": DECISION_ROLE,
        "marker_role": MARKER_ROLE,
    }


def validate_runtime_role_preflight(
    row: Mapping[str, Any], *, expected_role: str
) -> dict[str, Any]:
    """Validate one row returned by :data:`ROLE_PREFLIGHT_SQL`.

    The caller must execute the probe on the same connection that will perform
    formal work.  In production ``current_role`` and ``session_role`` must both
    be the exact login role; inherited group roles and ``SET ROLE`` are refused.
    """

    if expected_role not in {DECISION_ROLE, MARKER_ROLE}:
        raise ValueError("expected formal runtime role is not allowlisted")
    required = {
        "current_role",
        "session_role",
        "contract_id",
        "ready",
        "legacy_decommissioned",
        "policy_contract_matches",
    }
    if set(row) != required:
        raise FormalRoleContractError("formal role preflight returned a wrong schema")
    if row["current_role"] != expected_role or row["session_role"] != expected_role:
        raise FormalRoleContractError("formal runtime is not using its exact login role")
    if row["contract_id"] != ROLE_SPLIT_CONTRACT_ID:
        raise FormalRoleContractError("formal database role contract is not pinned")
    if row["ready"] is not True:
        raise FormalRoleContractError("formal database role split is not ready")
    if row["legacy_decommissioned"] is not True:
        raise FormalRoleContractError("legacy combined paper role is still active")
    if row["policy_contract_matches"] is not True:
        raise FormalRoleContractError("formal row-security policy contract has drifted")
    return dict(row)


def validate_decision_slot_projection(
    row: Mapping[str, Any],
    *,
    expected_run_id: str,
    expected_decision_date: str,
    expected_entry_date: str,
) -> dict[str, Any]:
    """Reject any non-next, drifted, terminal, or exhausted decision slot."""

    required = {
        "run_id",
        "protocol_id",
        "registration_id",
        "authorization_id",
        "paper_decision_build_id",
        "paper_decision_configuration_id",
        "requested_decision_date",
        "requested_entry_date",
        "decision_chain_valid",
        "horizon_open",
        "slot_is_next",
        "terminal_price_integrity_failure",
        "eligible_for_requested_slot",
    }
    if set(row) != required:
        raise FormalRoleContractError(
            "formal decision-slot projection returned a wrong schema"
        )
    if (
        row["run_id"] != expected_run_id
        or row["requested_decision_date"] != expected_decision_date
        or row["requested_entry_date"] != expected_entry_date
    ):
        raise FormalRoleContractError(
            "formal decision-slot projection returned a wrong identity"
        )
    for identity_field in (
        "protocol_id",
        "registration_id",
        "authorization_id",
        "paper_decision_build_id",
        "paper_decision_configuration_id",
    ):
        if not isinstance(row[identity_field], str) or not row[identity_field]:
            raise FormalRoleContractError(
                "formal decision-slot projection lacks its frozen identity"
            )
    if row["terminal_price_integrity_failure"] is not False:
        raise FormalRoleContractError(
            "terminal price-integrity failure blocks formal decisions"
        )
    if row["decision_chain_valid"] is not True:
        raise FormalRoleContractError("formal decision target chain has drifted")
    if row["horizon_open"] is not True:
        raise FormalRoleContractError("formal decision horizon is complete")
    if row["slot_is_next"] is not True:
        raise FormalRoleContractError("formal decision is not the next frozen slot")
    if row["eligible_for_requested_slot"] is not True:
        raise FormalRoleContractError("formal decision slot is not eligible")
    return dict(row)


__all__ = [
    "DECISION_ARTIFACT_TYPES",
    "DECISION_HELD_WEIGHT_POLICY",
    "DECISION_INSERT_TABLES",
    "DECISION_ROLE",
    "DECISION_SELECT_TABLES",
    "DECISION_SLOT_PROJECTION_SQL",
    "DECISION_WEIGHT_PROJECTION_SQL",
    "FormalRoleContractError",
    "LEGACY_PAPER_ROLE",
    "MARKER_INSERT_TABLES",
    "MARKER_ROLE",
    "MARKER_SELECT_TABLES",
    "OUTCOME_TABLES",
    "PREAUTHORIZATION_ACTIVITY_TABLES",
    "PROTECTED_TABLES",
    "ROLE_PREFLIGHT_SQL",
    "RUNTIME_HEALTH_PROJECTION_SQL",
    "RUNTIME_HEARTBEAT_EVENTS",
    "RUNTIME_HEARTBEAT_SQL",
    "ROLE_SPLIT_CONTRACT",
    "ROLE_SPLIT_CONTRACT_ID",
    "SCHEMA_ADMIN_LOGIN",
    "SCHEMA_ADMIN_ROLE",
    "build_legacy_role_decommission_receipt",
    "is_formal_schema_admin_identity",
    "runtime_role_decommission_release_payload",
    "validate_decision_slot_projection",
    "validate_runtime_role_preflight",
]
