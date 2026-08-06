"""Immutable, explicitly labeled publication of the sole final formal readout."""

from __future__ import annotations

import json
import math
from typing import Any

from tradingagents.formal_readout import (
    _require_registered_outcome_semantics,
    build_formal_readout,
    materialize_final_verification_manifest,
    require_final_verification_manifest,
)
from tradingagents.research_protocol import (
    GLOBAL_EVENT_V2_PROTOCOL,
    GLOBAL_EVENT_V2_PROTOCOL_ID,
    content_id,
)

FINAL_REVIEW_LABEL = "formal-review-252-complete"
_FINAL_GATE = 252
_GATE_126_REPORT_TYPE = "formal_interim_operational_integrity_report"


def _timestamp(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(float(value)):
        raise ValueError("formal review timestamp must be finite")
    return float(value)


def _completion(store, run_id: str) -> dict | None:
    rows = store._rows(
        "SELECT details_json FROM paper_run_labels "
        "WHERE run_id=:run_id AND label=:label",
        {"run_id": run_id, "label": FINAL_REVIEW_LABEL},
    )
    if not rows:
        return None
    if len(rows) != 1:
        raise ValueError("formal run has multiple final-review labels")
    try:
        details = json.loads(rows[0]["details_json"])
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("formal final-review label is malformed") from exc
    required = {
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
    }
    if set(details) != required \
            or details.get("schema_version") != 2 \
            or details.get("protocol_id") != GLOBAL_EVENT_V2_PROTOCOL_ID \
            or details.get("review_gate") != _FINAL_GATE \
            or details.get("live_capital_approved") is not False:
        raise ValueError("formal final-review label differs from the frozen contract")
    for key in (
        "outcome_bundle_id", "outcome_bundle_artifact_id",
        "report_id", "report_artifact_id",
        "verification_manifest_id", "verification_manifest_artifact_id",
    ):
        if not isinstance(details.get(key), str) or not details[key]:
            raise ValueError("formal final-review label has a malformed identity")
    return details


def _require_final_clock(store, run_id: str) -> None:
    counts = store.formal_trial_counts(run_id)
    required = int(
        GLOBAL_EVENT_V2_PROTOCOL["analysis"]["trial_clock"]["holding_intervals"]
    )
    if not isinstance(counts, dict) \
            or counts.get("completed_intervals") != required \
            or counts.get("assignment_indices_contiguous") is not True \
            or counts.get("assignment_dates_contiguous") is not True:
        raise ValueError(
            f"formal review is unavailable before exactly {required} contiguous intervals"
        )
    manifest = store.price_capture_operational_manifest(run_id)
    if not isinstance(manifest, dict) \
            or manifest.get("terminal_failures") != []:
        raise ValueError("terminal or malformed price capture state blocks final review")


def _has_persisted_final_outcomes(store) -> bool:
    rows = store._rows(
        "SELECT artifact_type FROM paper_artifacts WHERE artifact_type IN "
        "('formal_outcome_bundle','formal_confirmatory_report') LIMIT 1",
        {},
    )
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("formal final artifact ledger is malformed")
    return any(
        row.get("artifact_type") in {
            "formal_outcome_bundle", "formal_confirmatory_report"
        }
        for row in rows
    )


def _decode_json_object(value: Any, label: str) -> dict:
    try:
        decoded = json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is malformed") from exc
    if not isinstance(decoded, dict):
        raise ValueError(f"{label} is malformed")
    return decoded


def _require_no_unauthorized_early_efficacy(store, run_id: str) -> None:
    """Reject evidence of an unregistered efficacy look before publication."""
    artifact_rows = store._rows(
        "SELECT artifact_id,artifact_type,content_json FROM paper_artifacts "
        "ORDER BY artifact_id",
        {},
    )
    if not isinstance(artifact_rows, list) or any(
        not isinstance(row, dict) for row in artifact_rows
    ):
        raise ValueError("formal governance artifact ledger is malformed")
    artifacts: dict[str, tuple[str, dict]] = {}
    governed_types = {
        "formal_outcome_access",
        "formal_interim_descriptive_report",
        _GATE_126_REPORT_TYPE,
        "formal_outcome_bundle",
        "formal_confirmatory_report",
    }
    strong_efficacy_fields = {
        "strategy_returns", "strategy_descriptives", "spy_descriptives",
        "machine_statistical_candidate", "formal_readout",
    }
    for row in artifact_rows:
        artifact_type = row.get("artifact_type")
        try:
            content = json.loads(row.get("content_json"))
        except (TypeError, json.JSONDecodeError) as exc:
            if artifact_type in governed_types:
                raise ValueError("formal governance artifact is malformed") from exc
            continue
        if not isinstance(content, dict) or content.get("run_id") != run_id:
            continue
        expected_id = (
            content_id(content, prefix="artifact_")
            if artifact_type == "global_forecast_bundle"
            else content_id(
                {"artifact_type": artifact_type, "content": content},
                prefix="artifact_",
            )
        )
        artifact_id = row.get("artifact_id")
        if artifact_id != expected_id:
            raise ValueError("formal governance artifact content identity is invalid")
        artifacts[artifact_id] = (artifact_type, content)

        if artifact_type == "formal_interim_descriptive_report":
            raise ValueError("unauthorized early efficacy artifact blocks final review")
        if artifact_type not in {
            "formal_outcome_bundle", "formal_confirmatory_report"
        } and strong_efficacy_fields.intersection(content):
            raise ValueError("unauthorized early efficacy artifact blocks final review")
        if isinstance(artifact_type, str) and (
            "efficacy" in artifact_type
            or "candidate_publication" in artifact_type
            or "strategy_performance" in artifact_type
        ):
            raise ValueError("unauthorized early efficacy artifact blocks final review")
        if artifact_type == "formal_outcome_access":
            gate = content.get("review_gate")
            kind = content.get("access_kind")
            allowed = {
                (60, "automatic_interim_60_materialization"),
                (60, "explicit_interim_60_report_view"),
                (252, "automatic_final_report_materialization"),
                (252, "explicit_final_report_view"),
            }
            required = {
                "schema_version", "run_id", "protocol_id", "review_gate",
                "access_kind", "accessed_utc", "outcomes_may_be_read_after_this_receipt",
            }
            if isinstance(kind, str) and kind.startswith("explicit_"):
                required.add("report_id")
            if set(content) != required \
                    or content.get("schema_version") != 1 \
                    or content.get("protocol_id") != GLOBAL_EVENT_V2_PROTOCOL_ID \
                    or content.get("outcomes_may_be_read_after_this_receipt") is not True \
                    or (gate, kind) not in allowed:
                raise ValueError("unauthorized early outcome access blocks final review")
            _timestamp(content.get("accessed_utc"))

    label_rows = store._rows(
        "SELECT label,details_json FROM paper_run_labels "
        "WHERE run_id=:run_id ORDER BY label",
        {"run_id": run_id},
    )
    if not isinstance(label_rows, list) or any(
        not isinstance(row, dict) for row in label_rows
    ):
        raise ValueError("formal governance label ledger is malformed")
    allowed_reviews = {
        "formal-review-20-operations",
        "formal-review-60-calibration",
        "formal-review-126-descriptive",
        FINAL_REVIEW_LABEL,
    }
    for row in label_rows:
        label = row.get("label")
        if isinstance(label, str) and label.startswith("formal-review-") \
                and label not in allowed_reviews:
            raise ValueError("unauthorized early efficacy label blocks final review")
        if isinstance(label, str) and any(
            token in label for token in ("efficacy", "promotion", "candidate", "performance")
        ):
            raise ValueError("unauthorized early efficacy label blocks final review")
        if label != "formal-review-126-descriptive":
            if isinstance(row.get("details_json"), str):
                try:
                    details = json.loads(row["details_json"])
                except json.JSONDecodeError:
                    details = None
                if isinstance(details, dict) and strong_efficacy_fields.intersection(details):
                    raise ValueError(
                        "unauthorized early efficacy label blocks final review"
                    )
            continue
        details = _decode_json_object(
            row.get("details_json"), "formal gate-126 label"
        )
        artifact_id = details.get("report_artifact_id")
        artifact = artifacts.get(artifact_id)
        if artifact is None or artifact[0] != _GATE_126_REPORT_TYPE:
            raise ValueError("unauthorized or missing gate-126 report blocks final review")
        report = artifact[1]
        forbidden = {
            "strategy_order", "strategy_descriptives", "strategy_returns",
            "benchmark_returns", "readout", "machine_statistical_candidate",
        }
        if report.get("outcomes_read") is not False \
                or forbidden.intersection(report):
            raise ValueError("gate-126 report exposed unauthorized early efficacy")


def materialize_final_formal_review(
    store, run_id: str, created_utc: float
) -> dict:
    """Build and persist the final report once, returning outcome-blind IDs only."""
    created = _timestamp(created_utc)
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("formal review run ID must be a non-empty string")
    _require_registered_outcome_semantics(store, run_id)
    _require_final_clock(store, run_id)
    existing = _completion(store, run_id)
    verification = None
    # On an idempotent view/retry, authenticate the already-durable manifest
    # before governance inspects any persisted final outcome artifact.
    if existing is not None or _has_persisted_final_outcomes(store):
        verification = require_final_verification_manifest(store, run_id)
    _require_no_unauthorized_early_efficacy(store, run_id)
    if existing is not None:
        assert verification is not None
        if any(existing.get(key) != value for key, value in verification.items()):
            raise ValueError("formal final review is not bound to its verification manifest")
        return {**existing, "already_materialized": True}

    try:
        verification = verification or materialize_final_verification_manifest(
            store, run_id, created
        )
    except Exception as exc:
        try:
            store.record_artifact(
                "formal_review_integrity_failure",
                {
                    "schema_version": 1,
                    "run_id": run_id,
                    "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
                    "review_gate": _FINAL_GATE,
                    "reason_code": "offline_verification_failed",
                },
                created,
            )
        except Exception:
            exc.add_note("formal offline-verification failure receipt could not be appended")
        raise

    # Verification is complete and durable before this receipt permits any
    # return read. A crash or integrity failure cannot create an unverified or
    # unlabeled look at formal outcomes.
    access_artifact_id = store.record_artifact(
        "formal_outcome_access",
        {
            "schema_version": 1,
            "run_id": run_id,
            "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
            "review_gate": _FINAL_GATE,
            "access_kind": "automatic_final_report_materialization",
            "accessed_utc": created,
            "outcomes_may_be_read_after_this_receipt": True,
        },
        created,
    )
    try:
        result = build_formal_readout(store, run_id)
    except Exception as exc:
        try:
            store.record_artifact(
                "formal_review_integrity_failure",
                {
                    "schema_version": 1,
                    "run_id": run_id,
                    "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
                    "review_gate": _FINAL_GATE,
                    "access_artifact_id": access_artifact_id,
                    "reason_code": "integrity_validation_failed",
                },
                created,
            )
        except Exception:
            exc.add_note("formal review failure receipt could not be appended")
        raise

    if any(result.get(key) != value for key, value in verification.items()):
        raise ValueError("formal readout is not bound to its verification manifest")

    outcome_bundle = result["outcome_bundle"]
    report = {key: value for key, value in result.items() if key != "outcome_bundle"}
    outcome_artifact_id = store.record_artifact(
        "formal_outcome_bundle", outcome_bundle, created
    )
    report_artifact_id = store.record_artifact(
        "formal_confirmatory_report", report, created
    )
    details = {
        "schema_version": 2,
        "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
        "review_gate": _FINAL_GATE,
        "outcome_bundle_id": result["outcome_bundle_id"],
        "outcome_bundle_artifact_id": outcome_artifact_id,
        "report_id": result["report_id"],
        "report_artifact_id": report_artifact_id,
        "verification_manifest_id": verification["verification_manifest_id"],
        "verification_manifest_artifact_id": verification[
            "verification_manifest_artifact_id"
        ],
        "live_capital_approved": False,
    }
    store.label_run(run_id, FINAL_REVIEW_LABEL, created, details)
    return {**details, "already_materialized": False}


def load_final_formal_report(store, run_id: str, accessed_utc: float) -> dict:
    """Record a human-facing access receipt, then return the frozen final report."""
    accessed = _timestamp(accessed_utc)
    _require_registered_outcome_semantics(store, run_id)
    details = _completion(store, run_id)
    if details is None:
        details = materialize_final_formal_review(store, run_id, accessed)
    else:
        _require_final_clock(store, run_id)
        verification = require_final_verification_manifest(store, run_id)
        _require_no_unauthorized_early_efficacy(store, run_id)
        if any(details.get(key) != value for key, value in verification.items()):
            raise ValueError("formal final report is not bound to its verification manifest")
    store.record_artifact(
        "formal_outcome_access",
        {
            "schema_version": 1,
            "run_id": run_id,
            "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
            "review_gate": _FINAL_GATE,
            "access_kind": "explicit_final_report_view",
            "accessed_utc": accessed,
            "report_id": details["report_id"],
            "outcomes_may_be_read_after_this_receipt": True,
        },
        accessed,
    )
    rows = store._rows(
        "SELECT artifact_type,content_json FROM paper_artifacts "
        "WHERE artifact_id=:artifact_id",
        {"artifact_id": details["report_artifact_id"]},
    )
    if len(rows) != 1 or rows[0].get("artifact_type") != "formal_confirmatory_report":
        raise ValueError("formal final report artifact is missing")
    try:
        report = json.loads(rows[0]["content_json"])
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("formal final report artifact is malformed") from exc
    base = {key: value for key, value in report.items() if key != "report_id"}
    if report.get("report_id") != details["report_id"] \
            or content_id(base, prefix="formal_report_") != details["report_id"] \
            or report.get("protocol_id") != GLOBAL_EVENT_V2_PROTOCOL_ID \
            or report.get("run_id") != run_id \
            or report.get("review_gate") != _FINAL_GATE \
            or report.get("interim") is not False \
            or report.get("verification_manifest_id") \
            != details["verification_manifest_id"] \
            or report.get("verification_manifest_artifact_id") \
            != details["verification_manifest_artifact_id"] \
            or report.get("readout", {}).get("live_capital_approved") is not False:
        raise ValueError("formal final report artifact failed content validation")
    return report


__all__ = [
    "FINAL_REVIEW_LABEL",
    "load_final_formal_report",
    "materialize_final_formal_review",
]
