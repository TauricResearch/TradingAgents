"""Fail-closed reconstruction of the final confirmatory portfolio readout.

This module deliberately has one public operation and no analysis parameters.
It will not return a partial/interim result: all 252 registered holding
intervals and every immutable input needed to reconstruct them must validate
before the frozen statistical readout is invoked.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from copy import deepcopy
from datetime import date
from typing import Any

from tradingagents.outcome_semantics import require_outcome_semantics
from tradingagents.research_protocol import (
    GLOBAL_EVENT_V2_PROTOCOL,
    GLOBAL_EVENT_V2_PROTOCOL_ID,
    canonical_json,
    content_id,
)
from tradingagents.research_statistics import formal_complete_readout


class FormalReadoutIntegrityError(ValueError):
    """The immutable ledger cannot support the registered final readout."""


_CONFIRMATORY_LABEL = "confirmatory-trial"
_MARK_NUMERIC_FIELDS = (
    "captured_utc",
    "nav",
    "benchmark_nav",
    "period_return",
    "benchmark_period_return",
    "turnover",
    "trading_cost",
    "borrow_cost",
    "benchmark_open",
)
_PARITY_FIELDS = (
    *_MARK_NUMERIC_FIELDS,
    "weights",
    "opens",
    "target_decision_date",
)
_TOLERANCE = 1e-12
_FINAL_VERIFICATION_ARTIFACT_TYPE = "formal_final_verification_manifest"
_FINAL_VERIFICATION_PREFIX = "formal_verification_"


def _fail(message: str) -> None:
    raise FormalReadoutIntegrityError(message)


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(f"{label} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        _fail(f"{label} must be a finite number")
    return number


def _exact_integer(value: Any, label: str) -> int:
    if type(value) is not int:
        _fail(f"{label} must be an integer")
    return value


def _date_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(f"{label} must be an ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        _fail(f"{label} must be an ISO date")
    if parsed.isoformat() != value:
        _fail(f"{label} must be a canonical ISO date")
    return value


def _close(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return (
            math.isfinite(float(left))
            and math.isfinite(float(right))
            and math.isclose(float(left), float(right), rel_tol=_TOLERANCE, abs_tol=_TOLERANCE)
        )
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        return set(left) == set(right) and all(_close(left[key], right[key]) for key in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _close(a, b) for a, b in zip(left, right, strict=True)
        )
    return left == right


def _require_close(actual: Any, expected: Any, label: str) -> None:
    if not _close(actual, expected):
        _fail(f"{label} disagrees with immutable inputs")


def _decode_object(value: Any, label: str) -> dict:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            _fail(f"{label} is not valid JSON")
    if not isinstance(value, dict):
        _fail(f"{label} must be an object")
    return value


def _read_rows(store: Any, sql: str, params: dict) -> list[dict]:
    reader = getattr(store, "_rows", None)
    if not callable(reader):
        _fail("paper store does not expose its read-only ledger interface")
    rows = reader(sql, params)
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        _fail("paper store returned malformed ledger rows")
    return rows


def _require_registered_outcome_semantics(
    store: Any,
    run_id: str,
) -> tuple[dict, dict]:
    """Authenticate the preregistered outcome implementation before any outcome read.

    The identity comes only from the two immutable ledger projections.  Callers
    cannot nominate an executable identity, and disagreement between the run
    configuration and registration fails before an artifact, price, return,
    mark, statistic, or report is loaded.
    """
    if not isinstance(run_id, str) or not run_id:
        _fail("formal outcome run ID must be a non-empty string")
    config = store.run_config(run_id)
    registration = store.confirmatory_registration(run_id)
    if not isinstance(config, dict):
        _fail("formal run configuration is malformed")
    if (
        not isinstance(registration, dict)
        or registration.get("label") != _CONFIRMATORY_LABEL
        or not isinstance(registration.get("details"), dict)
    ):
        _fail("formal run has no unique confirmatory registration")
    configured_id = config.get("outcome_semantics_id")
    registered_id = registration["details"].get("outcome_semantics_id")
    if (
        not isinstance(configured_id, str)
        or not configured_id
        or configured_id != registered_id
    ):
        _fail(
            "formal run configuration and registration disagree on outcome semantics"
        )
    require_outcome_semantics(configured_id)
    return config, registration


def _validate_decision_attempt_bindings(
    event_rows: list[dict], bundle_rows: list[dict], *, run_id: str
) -> dict:
    """Resolve only the exact latest started ordinal named by each bundle.

    An older unmatched start on a date that later succeeds is still a crash; a
    date match alone must never convert every unmatched start into a success.
    """
    starts: dict[tuple[str, int], dict] = {}
    failures: dict[tuple[str, int], dict] = {}
    ordinals_by_date: dict[str, set[int]] = {}
    for row in event_rows:
        if row.get("run_id") != run_id:
            _fail("formal attempt event belongs to another run")
        decision_date = _date_string(
            row.get("decision_date"), "formal attempt decision date"
        )
        entry_date = _date_string(row.get("entry_date"), "formal attempt entry date")
        ordinal = _exact_integer(row.get("attempt_ordinal"), "formal attempt ordinal")
        if ordinal < 1 or row.get("event_type") not in {"started", "failed"}:
            _fail("formal attempt event identity is malformed")
        created = _finite_number(row.get("created_utc"), "formal attempt timestamp")
        key = (decision_date, ordinal)
        target = starts if row["event_type"] == "started" else failures
        if key in target:
            _fail("formal attempt event is duplicated")
        target[key] = {
            "entry_date": entry_date,
            "created_utc": created,
            "reason_code": row.get("reason_code"),
        }
        ordinals_by_date.setdefault(decision_date, set()).add(ordinal)
    for decision_date, ordinals in ordinals_by_date.items():
        started_ordinals = {
            ordinal for date_value, ordinal in starts if date_value == decision_date
        }
        if started_ordinals != set(range(1, max(started_ordinals, default=0) + 1)):
            _fail("formal attempt starts are not contiguous from ordinal one")
        if not ordinals.issubset(started_ordinals):
            _fail("formal failed attempt lacks its start event")
    for key, failure in failures.items():
        start = starts.get(key)
        if (
            start is None
            or failure["entry_date"] != start["entry_date"]
            or failure["created_utc"] < start["created_utc"]
            or not isinstance(failure["reason_code"], str)
            or not failure["reason_code"]
        ):
            _fail("formal failed attempt lacks a coherent start event")

    successful_attempts: set[tuple[str, int]] = set()
    bundle_dates: set[str] = set()
    for row in bundle_rows:
        decision_date = _date_string(
            row.get("decision_date"), "formal decision-bundle date"
        )
        ordinal = _exact_integer(
            row.get("attempt_ordinal"), "formal decision-bundle attempt ordinal"
        )
        key = (decision_date, ordinal)
        if ordinal < 1 or decision_date in bundle_dates:
            _fail("formal decision-bundle attempt identity is malformed")
        bundle_dates.add(decision_date)
        started_for_date = [
            value for date_value, value in starts if date_value == decision_date
        ]
        if (
            key not in starts
            or key in failures
            or not started_for_date
            or ordinal != max(started_for_date)
        ):
            _fail("formal decision bundle does not bind its exact latest live attempt")
        successful_attempts.add(key)

    unmatched = set(starts) - set(failures)
    unresolved = unmatched - successful_attempts
    return {
        "starts": starts,
        "failures": failures,
        "successful_attempts": successful_attempts,
        "unmatched_attempts": unmatched,
        "unresolved_attempts": unresolved,
    }


def _verification_cohort(store: Any, run_id: str, assignments: list[dict]) -> list[str]:
    """Return the exact applied-decision cohort without reading outcomes."""
    decision_dates = [
        row["applied_target_decision_date"]
        for row in assignments
        if row["disposition"] == "target_applied"
    ]
    if len(decision_dates) != len(set(decision_dates)):
        _fail("formal applied-decision verification cohort contains duplicates")
    bundle_rows = _read_rows(
        store,
        "SELECT decision_date,attempt_ordinal FROM paper_decision_bundles "
        "WHERE run_id=:run_id ORDER BY decision_date",
        {"run_id": run_id},
    )
    bundle_dates = [
        _date_string(row.get("decision_date"), "formal decision-bundle date") for row in bundle_rows
    ]
    if len(bundle_dates) != len(set(bundle_dates)):
        _fail("formal decision-bundle verification cohort contains duplicates")
    if set(bundle_dates) != set(decision_dates):
        _fail("formal verification cohort does not exactly cover successful applied decisions")
    event_rows = _read_rows(
        store,
        "SELECT run_id,decision_date,entry_date,attempt_ordinal,event_type,"
        "created_utc,reason_code FROM paper_decision_attempt_events "
        "WHERE run_id=:run_id ORDER BY decision_date,attempt_ordinal,event_type",
        {"run_id": run_id},
    )
    _validate_decision_attempt_bindings(event_rows, bundle_rows, run_id=run_id)
    return decision_dates


def _verification_manifest_rows(store: Any) -> list[dict]:
    return _read_rows(
        store,
        "SELECT artifact_id,artifact_type,content_json FROM paper_artifacts "
        "WHERE artifact_type=:artifact_type ORDER BY artifact_id",
        {"artifact_type": _FINAL_VERIFICATION_ARTIFACT_TYPE},
    )


def _price_capture_operational_identity(store: Any, run_id: str, assignments: list[dict]) -> str:
    """Authenticate opaque capture IDs/timing without reading any price outcome."""
    try:
        manifest = store.price_capture_operational_manifest(run_id)
    except Exception as exc:
        raise FormalReadoutIntegrityError(
            "formal price capture operational manifest is unavailable"
        ) from exc
    if (
        not isinstance(manifest, dict)
        or set(manifest) != {"attempt_events", "batches", "terminal_failures"}
        or manifest.get("terminal_failures") != []
    ):
        _fail("terminal or malformed price capture state blocks formal review")
    batches = manifest.get("batches")
    attempt_events = manifest.get("attempt_events")
    expected_sessions = [
        assignments[0]["from_session_date"],
        *(assignment["session_date"] for assignment in assignments),
    ]
    symbols = sorted(
        {
            *GLOBAL_EVENT_V2_PROTOCOL["universe"]["symbols"],
            GLOBAL_EVENT_V2_PROTOCOL["portfolio"]["benchmark"],
        }
    )
    if (
        not isinstance(batches, list)
        or len(batches) != len(expected_sessions)
        or not isinstance(attempt_events, list)
    ):
        _fail("formal price capture batch coverage is incomplete")
    attempts_by_session: dict[str, list[dict]] = {}
    for event in attempt_events:
        if not isinstance(event, dict) or set(event) != {
            "session_date",
            "attempt_ordinal",
            "event_type",
            "created_utc",
            "observed_utc",
            "reason_code",
        }:
            _fail("formal price capture attempt event is malformed")
        attempts_by_session.setdefault(event["session_date"], []).append(event)
    if set(attempts_by_session) != set(expected_sessions):
        _fail("formal price capture attempts do not exactly cover captured sessions")
    opaque_batches = []
    assignments_by_end = {assignment["session_date"]: assignment for assignment in assignments}
    for index, (session, batch) in enumerate(zip(expected_sessions, batches, strict=True)):
        if not isinstance(batch, dict) or batch.get("session_date") != session:
            _fail("formal price capture batches are not consecutive and exact")
        scheduled = _finite_number(batch.get("scheduled_utc"), "price schedule")
        started = _finite_number(batch.get("started_utc"), "price attempt start")
        completed = _finite_number(batch.get("completed_utc"), "price completion")
        persisted = _finite_number(batch.get("persisted_utc"), "price persistence")
        deadline = _finite_number(batch.get("deadline_utc"), "price deadline")
        from tradingagents.paper_trading import formal_price_capture_window

        expected_scheduled, expected_deadline = formal_price_capture_window(session)
        if (
            not math.isclose(scheduled, expected_scheduled.timestamp(), abs_tol=_TOLERANCE)
            or not math.isclose(deadline, expected_deadline.timestamp(), abs_tol=_TOLERANCE)
            or not scheduled <= started <= completed < deadline
            or persisted >= deadline
            or completed - persisted > 30.0
            or persisted - completed > 300.0
        ):
            _fail("formal price capture batch violates the frozen timing window")
        prior = None if index == 0 else expected_sessions[index - 1]
        if (
            batch.get("from_session_date") != prior
            or batch.get("vendor") != "yfinance"
            or not isinstance(batch.get("paper_build_id"), str)
            or re.fullmatch(r"build_[0-9a-f]{24}", batch["paper_build_id"]) is None
            or type(batch.get("attempt_ordinal")) is not int
            or batch["attempt_ordinal"] < 1
        ):
            _fail("formal price capture batch header is malformed")
        by_ordinal: dict[int, list[dict]] = {}
        for event in attempts_by_session[session]:
            ordinal = event.get("attempt_ordinal")
            if type(ordinal) is not int or ordinal < 1:
                _fail("formal price capture attempt ordinal is malformed")
            by_ordinal.setdefault(ordinal, []).append(event)
        if sorted(by_ordinal) != list(range(1, batch["attempt_ordinal"] + 1)):
            _fail("formal price capture attempt ledger is not contiguous")
        normalized_attempts = []
        prior_event_time = scheduled
        for ordinal in range(1, batch["attempt_ordinal"] + 1):
            events = by_ordinal[ordinal]
            by_type = {event.get("event_type"): event for event in events}
            if (
                len(by_type) != len(events)
                or "started" not in by_type
                or set(by_type) - {"started", "failed"}
            ):
                _fail("formal price capture attempt lifecycle is ambiguous")
            started_event = by_type["started"]
            started_at = _finite_number(
                started_event.get("created_utc"), "price attempt event time"
            )
            observed_at = _finite_number(
                started_event.get("observed_utc"), "server-observed attempt time"
            )
            if (
                started_event.get("reason_code") is not None
                or not scheduled <= started_at < deadline
                or abs(started_at - observed_at) > 30.0
                or started_at < prior_event_time
            ):
                _fail("formal price capture attempt start is inconsistent")
            failed_event = by_type.get("failed")
            status = "crashed"
            failed_at = None
            failure_observed = None
            reason_code = None
            if failed_event is not None:
                failed_at = _finite_number(
                    failed_event.get("created_utc"), "price attempt failure time"
                )
                failure_observed = _finite_number(
                    failed_event.get("observed_utc"),
                    "server-observed attempt failure time",
                )
                reason_code = failed_event.get("reason_code")
                if (
                    reason_code
                    not in {
                        "market_data_failed",
                        "capture_window_expired",
                        "persistence_failed",
                        "unexpected_failure",
                    }
                    or not started_at <= failed_at < deadline
                    or abs(failed_at - failure_observed) > 30.0
                ):
                    _fail("formal price capture attempt failure is inconsistent")
                status = "failed"
                prior_event_time = failed_at
            else:
                prior_event_time = started_at
            if ordinal == batch["attempt_ordinal"]:
                if failed_event is not None or not math.isclose(
                    started_at, started, abs_tol=_TOLERANCE
                ):
                    _fail("formal successful capture attempt is not the latest start")
                status = "succeeded"
            normalized_attempts.append(
                {
                    "attempt_ordinal": ordinal,
                    "started_utc": started_at,
                    "observed_started_utc": observed_at,
                    "failed_utc": failed_at,
                    "observed_failed_utc": failure_observed,
                    "reason_code": reason_code,
                    "status": status,
                }
            )
        capture_id = batch.get("capture_batch_id")
        if not isinstance(capture_id, str) or not capture_id.startswith("price_batch_"):
            _fail("formal price capture batch identity is malformed")
        expected_vector_id = None if index == 0 else assignments_by_end[session]["return_vector_id"]
        if batch.get("return_vector_id") != expected_vector_id:
            _fail("formal price batch and interval return-vector identities disagree")
        receipt_manifest = batch.get("receipt_manifest")
        if (
            not isinstance(receipt_manifest, list)
            or [item.get("ticker") for item in receipt_manifest] != symbols
        ):
            _fail("formal price receipt manifest does not match the frozen universe")
        for item in receipt_manifest:
            if (
                not isinstance(item, dict)
                or set(item) != {"ticker", "price_receipt_id", "vendor_snapshot_id"}
                or not isinstance(item.get("price_receipt_id"), str)
                or not item["price_receipt_id"].startswith("price_receipt_")
                or not isinstance(item.get("vendor_snapshot_id"), str)
                or not item["vendor_snapshot_id"].startswith("price_snapshot_")
            ):
                _fail("formal price receipt manifest identity is malformed")
        opaque_batches.append(
            {
                "session_date": session,
                "capture_batch_id": capture_id,
                "return_vector_id": expected_vector_id,
                "paper_build_id": batch["paper_build_id"],
                "scheduled_utc": scheduled,
                "completed_utc": completed,
                "persisted_utc": persisted,
                "deadline_utc": deadline,
                "receipt_manifest": receipt_manifest,
                "attempts": normalized_attempts,
            }
        )
    return content_id(
        {
            "schema_version": 1,
            "run_id": run_id,
            "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
            "batches": opaque_batches,
        },
        prefix="price_manifest_",
    )


def _decode_verification_manifest(row: dict) -> dict:
    if row.get("artifact_type") != _FINAL_VERIFICATION_ARTIFACT_TYPE:
        _fail("formal verification manifest has the wrong artifact type")
    manifest = _decode_object(row.get("content_json"), "formal final verification manifest")
    expected_artifact_id = content_id(
        {
            "artifact_type": _FINAL_VERIFICATION_ARTIFACT_TYPE,
            "content": manifest,
        },
        prefix="artifact_",
    )
    if row.get("artifact_id") != expected_artifact_id:
        _fail("formal verification manifest artifact identity is invalid")
    return manifest


def _validate_verification_manifest(
    manifest: dict,
    *,
    run_id: str,
    decision_dates: list[str],
    price_capture_manifest_id: str,
) -> dict:
    required_keys = {
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
    }
    if (
        set(manifest) != required_keys
        or manifest.get("schema_version") != 1
        or manifest.get("manifest_type") != "global-event-v2-final-offline-verification"
        or manifest.get("protocol_id") != GLOBAL_EVENT_V2_PROTOCOL_ID
        or manifest.get("run_id") != run_id
        or manifest.get("coverage_rule") != "every-successful-applied-decision-exactly-once"
        or manifest.get("successful_applied_decisions") != len(decision_dates)
        or manifest.get("decision_dates") != decision_dates
        or manifest.get("external_calls_total") != 0
        or manifest.get("exact_coverage") is not True
    ):
        _fail("formal final verification manifest differs from the frozen contract")
    if manifest.get("price_capture_manifest_id") != price_capture_manifest_id:
        _fail("formal final verification manifest has the wrong price capture identity")

    verifications = manifest.get("verifications")
    verification_keys = {
        "decision_date",
        "entry_date",
        "protocol_id",
        "build_id",
        "artifact_id",
        "strategies_replayed",
        "external_calls",
    }
    expected_replayed = len(GLOBAL_EVENT_V2_PROTOCOL["strategies"])
    if not isinstance(verifications, list) or len(verifications) != len(decision_dates):
        _fail("formal final verification manifest coverage is incomplete")
    for expected_date, receipt in zip(decision_dates, verifications, strict=True):
        if (
            not isinstance(receipt, dict)
            or set(receipt) != verification_keys
            or receipt.get("decision_date") != expected_date
            or receipt.get("protocol_id") != GLOBAL_EVENT_V2_PROTOCOL_ID
            or receipt.get("strategies_replayed") != expected_replayed
            or receipt.get("external_calls") != 0
            or not isinstance(receipt.get("entry_date"), str)
            or not isinstance(receipt.get("build_id"), str)
            or not receipt["build_id"]
            or not isinstance(receipt.get("artifact_id"), str)
            or not receipt["artifact_id"].startswith("artifact_")
        ):
            _fail("formal final verification receipt is malformed or incomplete")
        _date_string(receipt["entry_date"], "formal verification entry date")

    base = {key: value for key, value in manifest.items() if key != "verification_manifest_id"}
    expected_manifest_id = content_id(base, prefix=_FINAL_VERIFICATION_PREFIX)
    if manifest.get("verification_manifest_id") != expected_manifest_id:
        _fail("formal final verification manifest content identity is invalid")
    return manifest


def require_final_verification_manifest(
    store: Any,
    run_id: str,
    assignments: list[dict] | None = None,
) -> dict:
    """Require one immutable exact-coverage manifest before outcome access."""
    if assignments is None:
        _validate_run(store, run_id)
        assignments, _ = _validate_assignments(store, run_id)
    else:
        _require_registered_outcome_semantics(store, run_id)
    decision_dates = _verification_cohort(store, run_id, assignments)
    price_capture_manifest_id = _price_capture_operational_identity(store, run_id, assignments)
    matching: list[tuple[dict, dict]] = []
    for row in _verification_manifest_rows(store):
        manifest = _decode_verification_manifest(row)
        if manifest.get("run_id") == run_id:
            matching.append((row, manifest))
    if len(matching) != 1:
        _fail("formal readout requires exactly one final verification manifest")
    row, manifest = matching[0]
    _validate_verification_manifest(
        manifest,
        run_id=run_id,
        decision_dates=decision_dates,
        price_capture_manifest_id=price_capture_manifest_id,
    )
    return {
        "verification_manifest_id": manifest["verification_manifest_id"],
        "verification_manifest_artifact_id": row["artifact_id"],
    }


def materialize_final_verification_manifest(store: Any, run_id: str, created_utc: float) -> dict:
    """Offline-replay every applied decision and append the sole manifest."""
    created = _finite_number(created_utc, "formal verification timestamp")
    _validate_run(store, run_id)
    assignments, _ = _validate_assignments(store, run_id)
    decision_dates = _verification_cohort(store, run_id, assignments)
    price_capture_manifest_id = _price_capture_operational_identity(store, run_id, assignments)

    from tradingagents.formal_verifier import verify_formal

    verifications = []
    expected_replayed = len(GLOBAL_EVENT_V2_PROTOCOL["strategies"])
    for decision_date in decision_dates:
        receipt = verify_formal(store, run_id, decision_date)
        if (
            not isinstance(receipt, dict)
            or receipt.get("ok") is not True
            or receipt.get("run_id") != run_id
            or receipt.get("decision_date") != decision_date
            or receipt.get("protocol_id") != GLOBAL_EVENT_V2_PROTOCOL_ID
            or receipt.get("strategies_replayed") != expected_replayed
            or receipt.get("external_calls") != 0
        ):
            _fail("formal final offline verification did not authenticate exactly")
        verifications.append(
            {
                "decision_date": decision_date,
                "entry_date": receipt.get("entry_date"),
                "protocol_id": receipt.get("protocol_id"),
                "build_id": receipt.get("build_id"),
                "artifact_id": receipt.get("artifact_id"),
                "strategies_replayed": receipt.get("strategies_replayed"),
                "external_calls": receipt.get("external_calls"),
            }
        )

    base = {
        "schema_version": 1,
        "manifest_type": "global-event-v2-final-offline-verification",
        "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
        "run_id": run_id,
        "coverage_rule": "every-successful-applied-decision-exactly-once",
        "successful_applied_decisions": len(decision_dates),
        "decision_dates": decision_dates,
        "verifications": verifications,
        "external_calls_total": 0,
        "exact_coverage": True,
        "price_capture_manifest_id": price_capture_manifest_id,
    }
    manifest = {
        **base,
        "verification_manifest_id": content_id(base, prefix=_FINAL_VERIFICATION_PREFIX),
    }
    _assert_json_finite(manifest, "formal final verification manifest")
    _validate_verification_manifest(
        manifest,
        run_id=run_id,
        decision_dates=decision_dates,
        price_capture_manifest_id=price_capture_manifest_id,
    )

    existing = []
    for row in _verification_manifest_rows(store):
        decoded = _decode_verification_manifest(row)
        if decoded.get("run_id") == run_id:
            existing.append((row, decoded))
    if len(existing) > 1 or (
        existing and canonical_json(existing[0][1]) != canonical_json(manifest)
    ):
        _fail("formal run already has a different final verification manifest")
    artifact_id = store.record_artifact(_FINAL_VERIFICATION_ARTIFACT_TYPE, manifest, created)
    if existing and existing[0][0].get("artifact_id") != artifact_id:
        _fail("formal final verification manifest artifact identity drifted")
    return require_final_verification_manifest(store, run_id, assignments)


def _expected_registration(
    run_id: str,
    *,
    outcome_semantics_id: str,
    configuration_binding: Mapping[str, str],
) -> dict:
    analysis = GLOBAL_EVENT_V2_PROTOCOL["analysis"]
    base = {
        "schema_version": 2,
        "registration_type": "confirmatory",
        "run_id": run_id,
        "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
        "analysis_id": content_id(analysis, prefix="analysis_"),
        "review_gates_id": content_id(GLOBAL_EVENT_V2_PROTOCOL["review_gates"], prefix="reviews_"),
        "decision_semantics_id": GLOBAL_EVENT_V2_PROTOCOL["forecast"][
            "expected_decision_semantics_id"
        ],
        "outcome_semantics_id": outcome_semantics_id,
        "configuration_binding": {
            key: configuration_binding[key]
            for key in sorted(configuration_binding)
        },
        "registered_strategies": list(GLOBAL_EVENT_V2_PROTOCOL["strategies"]),
        "confirmatory_family": list(analysis["multiplicity"]["confirmatory_family"]),
        "secondary_family": list(analysis["multiplicity"]["secondary_family"]),
        "trial_clock": analysis["trial_clock"],
        "parent_run_id": None,
        "outcomes_accessed_before_registration": False,
    }
    return {**base, "registration_id": content_id(base, prefix="registration_")}


def _validate_run(store: Any, run_id: str) -> tuple[dict, dict, list[str], str]:
    config, registration = _require_registered_outcome_semantics(store, run_id)
    portfolio = GLOBAL_EVENT_V2_PROTOCOL["portfolio"]
    tickers = list(GLOBAL_EVENT_V2_PROTOCOL["universe"]["symbols"])
    benchmark = portfolio["benchmark"]
    exact_fields = {
        "engine": "formal-global-v2",
        "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
        "tickers": tickers,
        "benchmark": benchmark,
        "cost_bps": portfolio["trading_cost_bps"],
        "slippage_bps": portfolio["slippage_bps"],
        "annual_borrow_bps": 0.0,
        "cash_policy": portfolio["cash"],
    }
    for field, expected in exact_fields.items():
        if field not in config or not _close(config[field], expected):
            _fail(f"formal run configuration field {field!r} is not protocol-exact")
    if len(set(tickers)) != len(tickers) or benchmark in tickers:
        _fail("formal protocol return universe is ambiguous")

    protocol_rows = _read_rows(
        store,
        "SELECT manifest_json FROM experiment_registry WHERE protocol_id=:protocol_id",
        {"protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID},
    )
    if len(protocol_rows) != 1:
        _fail("formal protocol registry must contain exactly one manifest")
    manifest = _decode_object(protocol_rows[0].get("manifest_json"), "protocol manifest")
    if manifest != GLOBAL_EVENT_V2_PROTOCOL:
        _fail("registered formal protocol manifest differs from the frozen protocol")

    _finite_number(registration.get("created_utc"), "registration timestamp")
    details = registration.get("details")
    configuration_binding = config.get("configuration_binding")
    expected_configuration_fields = {
        "configuration_manifest_id",
        "collector_configuration_id",
        "paper_decision_configuration_id",
        "paper_marker_configuration_id",
    }
    if (
        not isinstance(configuration_binding, dict)
        or set(configuration_binding) != expected_configuration_fields
    ):
        _fail("formal run configuration binding is malformed")
    expected_registration = _expected_registration(
        run_id,
        outcome_semantics_id=config["outcome_semantics_id"],
        configuration_binding=configuration_binding,
    )
    if details != expected_registration:
        _fail("confirmatory registration is not the exact frozen registration")
    if config.get("trial_registration_id") != expected_registration["registration_id"]:
        _fail("run configuration is not bound to its confirmatory registration")

    expected_strategies = list(GLOBAL_EVENT_V2_PROTOCOL["strategies"])
    stored_strategies = store.formal_strategies(run_id)
    if (
        not isinstance(stored_strategies, list)
        or len(stored_strategies) != len(expected_strategies)
        or set(stored_strategies) != set(expected_strategies)
    ):
        _fail("formal run does not contain exactly the eight registered strategies")
    return config, expected_registration, tickers, benchmark


def _validate_assignments(store: Any, run_id: str) -> tuple[list[dict], dict]:
    required = int(GLOBAL_EVENT_V2_PROTOCOL["analysis"]["trial_clock"]["holding_intervals"])
    assignments = _read_rows(
        store,
        "SELECT run_id,interval_index,from_session_date,session_date,"
        "scheduled_decision_date,created_utc,disposition,"
        "applied_target_decision_date,return_vector_id "
        "FROM paper_interval_assignments WHERE run_id=:run_id "
        "ORDER BY interval_index",
        {"run_id": run_id},
    )
    if len(assignments) != required:
        _fail(f"formal readout requires exactly {required} immutable assignments")

    # Use the same exchange calendar contract as the writer, but independently
    # validate every stored link rather than trusting its ordinal alone.
    from tradingagents.paper_trading import next_session_date

    normalized = []
    prior_end = None
    successful = 0
    for ordinal, raw in enumerate(assignments, start=1):
        if raw.get("run_id") != run_id:
            _fail("interval assignment belongs to a different run")
        if _exact_integer(raw.get("interval_index"), "interval index") != ordinal:
            _fail("formal assignment indices are not contiguous from one")
        start = _date_string(raw.get("from_session_date"), "assignment start date")
        end = _date_string(raw.get("session_date"), "assignment end date")
        scheduled = _date_string(raw.get("scheduled_decision_date"), "scheduled decision date")
        if next_session_date(start) != end or next_session_date(scheduled) != start:
            _fail("formal assignment dates are not consecutive XNYS sessions")
        if prior_end is not None and prior_end != start:
            _fail("formal assignments do not form one contiguous holding path")
        prior_end = end
        created = _finite_number(raw.get("created_utc"), "assignment timestamp")
        disposition = raw.get("disposition")
        applied = raw.get("applied_target_decision_date")
        if disposition == "target_applied":
            if applied != scheduled:
                _fail("applied formal target is not the scheduled target")
            successful += 1
        elif disposition == "carry_forward_missing_decision":
            if applied is not None:
                _fail("carry-forward assignment unexpectedly names a target")
        else:
            _fail("formal interval disposition is invalid")
        vector_id = raw.get("return_vector_id")
        if not isinstance(vector_id, str) or not vector_id.startswith("return_vector_"):
            _fail("formal assignment return-vector identity is malformed")
        normalized.append(
            {
                "interval_index": ordinal,
                "from_session_date": start,
                "session_date": end,
                "scheduled_decision_date": scheduled,
                "created_utc": created,
                "disposition": disposition,
                "applied_target_decision_date": applied,
                "return_vector_id": vector_id,
            }
        )

    counts = store.formal_trial_counts(run_id)
    if not isinstance(counts, dict):
        _fail("formal trial counts are malformed")
    completed = _exact_integer(counts.get("completed_intervals"), "completed intervals")
    recorded_successes = _exact_integer(
        counts.get("successful_decision_sets"), "successful decision sets"
    )
    carries = _exact_integer(counts.get("carry_forward_intervals"), "carry-forward intervals")
    if (
        completed != required
        or recorded_successes != successful
        or carries != required - successful
    ):
        _fail("formal trial counts disagree with immutable assignments")
    if (
        counts.get("assignment_indices_contiguous") is not True
        or counts.get("assignment_dates_contiguous") is not True
    ):
        _fail("formal trial counts do not certify contiguous assignments")
    if (
        "synchronized_marks" in counts
        and _exact_integer(counts["synchronized_marks"], "synchronized marks") != required
    ):
        _fail("formal trial counts do not certify synchronized marks")
    return normalized, counts


def _mark_from_row(row: dict, *, run_id: str, tickers: list[str], strategy_id: str | None) -> dict:
    if row.get("run_id") != run_id:
        _fail("paper mark belongs to a different run")
    if strategy_id is not None and row.get("strategy_id") != strategy_id:
        _fail("paper strategy mark has the wrong strategy identity")
    session = _date_string(row.get("session_date"), "mark session date")
    mark = {"session_date": session}
    for field in _MARK_NUMERIC_FIELDS:
        mark[field] = _finite_number(row.get(field), f"{session} {field}")
    if mark["nav"] <= 0 or mark["benchmark_nav"] <= 0 or mark["benchmark_open"] <= 0:
        _fail("paper mark NAV and benchmark open must be positive")
    if mark["period_return"] <= -1 or mark["benchmark_period_return"] <= -1:
        _fail("paper mark stored returns must be greater than -100%")
    if not 0 <= mark["turnover"] <= 2.0 + _TOLERANCE:
        _fail("paper mark turnover violates long-only bounds")
    if not 0 <= mark["trading_cost"] < 1 or mark["borrow_cost"] < 0:
        _fail("paper mark costs are invalid")

    weights = _decode_object(row.get("weights_json", row.get("weights")), f"{session} weights")
    opens = _decode_object(row.get("opens_json", row.get("opens")), f"{session} opens")
    if set(weights) != set(tickers) or set(opens) != set(tickers):
        _fail("paper mark cross-section differs from the frozen universe")
    normalized_weights = {}
    normalized_opens = {}
    for ticker in tickers:
        weight = _finite_number(weights[ticker], f"{session} {ticker} weight")
        opened = _finite_number(opens[ticker], f"{session} {ticker} open")
        if weight < 0 or opened <= 0:
            _fail("paper mark violates finite long-only price/weight constraints")
        normalized_weights[ticker] = weight
        normalized_opens[ticker] = opened
    gross = sum(normalized_weights.values())
    if gross > float(GLOBAL_EVENT_V2_PROTOCOL["portfolio"]["gross_limit"]) + _TOLERANCE:
        _fail("paper mark exceeds the registered long-only gross limit")
    mark["weights"] = normalized_weights
    mark["opens"] = normalized_opens
    target_date = row.get("target_decision_date")
    if target_date is not None:
        target_date = _date_string(target_date, "mark target decision date")
    mark["target_decision_date"] = target_date
    return mark


def _index_marks(
    rows: list[dict], *, run_id: str, tickers: list[str], strategy_id: str | None
) -> dict[str, dict]:
    indexed = {}
    for row in rows:
        mark = _mark_from_row(row, run_id=run_id, tickers=tickers, strategy_id=strategy_id)
        session = mark["session_date"]
        if session in indexed:
            _fail("paper ledger contains duplicate marks for one session")
        indexed[session] = mark
    return indexed


def _load_marks(
    store: Any,
    run_id: str,
    tickers: list[str],
    strategies: list[str],
    assignments: list[dict],
) -> tuple[dict[str, dict], dict[str, dict[str, dict]], list[str]]:
    expected_sessions = [assignments[0]["from_session_date"]] + [
        row["session_date"] for row in assignments
    ]
    champion_rows = _read_rows(
        store,
        "SELECT * FROM paper_marks WHERE run_id=:run_id ORDER BY session_date",
        {"run_id": run_id},
    )
    strategy_rows = _read_rows(
        store,
        "SELECT * FROM paper_strategy_marks WHERE run_id=:run_id ORDER BY strategy_id,session_date",
        {"run_id": run_id},
    )
    if len(champion_rows) != len(expected_sessions):
        _fail("formal run does not have the exact complete champion mark path")
    if len(strategy_rows) != len(expected_sessions) * len(strategies):
        _fail("formal run does not have the exact complete strategy mark matrix")
    champion = _index_marks(champion_rows, run_id=run_id, tickers=tickers, strategy_id=None)
    grouped_rows = {strategy: [] for strategy in strategies}
    for row in strategy_rows:
        strategy = row.get("strategy_id")
        if strategy not in grouped_rows:
            _fail("paper ledger contains an unregistered strategy mark")
        grouped_rows[strategy].append(row)
    marks = {
        strategy: _index_marks(
            grouped_rows[strategy],
            run_id=run_id,
            tickers=tickers,
            strategy_id=strategy,
        )
        for strategy in strategies
    }
    if list(champion) != expected_sessions or any(
        list(marks[strategy]) != expected_sessions for strategy in strategies
    ):
        _fail("formal strategy marks are missing, extra, or asymmetric")

    champion_strategy = marks["global_events_champion"]
    for session in expected_sessions:
        official = champion[session]
        shadow = champion_strategy[session]
        for field in _PARITY_FIELDS:
            _require_close(
                shadow[field], official[field], f"{session} champion official-mark {field}"
            )
    return champion, marks, expected_sessions


def _load_targets(
    store: Any,
    run_id: str,
    tickers: list[str],
    strategies: list[str],
    expected_sessions: list[str],
) -> tuple[dict[str, dict], dict[str, dict[str, dict]]]:
    official_rows = _read_rows(
        store,
        "SELECT run_id,decision_date,entry_date,weights_json FROM paper_targets "
        "WHERE run_id=:run_id ORDER BY entry_date",
        {"run_id": run_id},
    )
    strategy_rows = _read_rows(
        store,
        "SELECT run_id,decision_date,strategy_id,entry_date,weights_json "
        "FROM paper_strategy_targets WHERE run_id=:run_id "
        "ORDER BY strategy_id,entry_date",
        {"run_id": run_id},
    )
    expected_session_set = set(expected_sessions)

    def normalize(row: dict, label: str) -> dict:
        if row.get("run_id") != run_id:
            _fail(f"{label} belongs to a different run")
        entry = _date_string(row.get("entry_date"), f"{label} entry date")
        decision = _date_string(row.get("decision_date"), f"{label} decision date")
        weights = _decode_object(row.get("weights_json"), f"{label} weights")
        if set(weights) != set(tickers):
            _fail(f"{label} target differs from the frozen universe")
        normalized_weights = {
            ticker: _finite_number(weights[ticker], f"{label} {ticker} weight")
            for ticker in tickers
        }
        if any(value < 0 for value in normalized_weights.values()):
            _fail(f"{label} target violates long-only constraints")
        portfolio = GLOBAL_EVENT_V2_PROTOCOL["portfolio"]
        if sum(normalized_weights.values()) > float(portfolio["gross_limit"]) + _TOLERANCE:
            _fail(f"{label} target exceeds the registered gross limit")
        if any(
            value > float(portfolio["max_weight"]) + _TOLERANCE
            for value in normalized_weights.values()
        ):
            _fail(f"{label} target exceeds the registered single-name limit")
        sectors = GLOBAL_EVENT_V2_PROTOCOL["universe"]["sectors"]
        sector_totals: dict[str, float] = {}
        for ticker, weight in normalized_weights.items():
            sector_totals[sectors[ticker]] = sector_totals.get(sectors[ticker], 0.0) + weight
        if any(
            value > float(portfolio["max_sector_weight"]) + _TOLERANCE
            for value in sector_totals.values()
        ):
            _fail(f"{label} target exceeds the registered sector limit")
        return {"entry_date": entry, "decision_date": decision, "weights": normalized_weights}

    official = {}
    for row in official_rows:
        target = normalize(row, "champion")
        entry = target["entry_date"]
        if entry in official or entry not in expected_session_set:
            _fail("champion targets are duplicate or extend beyond the frozen trial path")
        official[entry] = target

    by_strategy = {strategy: {} for strategy in strategies}
    for row in strategy_rows:
        strategy = row.get("strategy_id")
        if strategy not in by_strategy:
            _fail("paper ledger contains a target for an unregistered strategy")
        target = normalize(row, f"{strategy}")
        entry = target["entry_date"]
        if entry in by_strategy[strategy] or entry not in expected_session_set:
            _fail("strategy targets are duplicate or extend beyond the frozen trial path")
        by_strategy[strategy][entry] = target

    for session in expected_sessions:
        present = {strategy for strategy in strategies if session in by_strategy[strategy]}
        if bool(session in official) != bool(present) or (present and present != set(strategies)):
            _fail("formal targets are incomplete or asymmetric")
        if session in official:
            champion_target = by_strategy["global_events_champion"][session]
            _require_close(
                champion_target,
                official[session],
                f"{session} champion official target",
            )
    return official, by_strategy


def _validate_mark_target(
    mark: dict,
    target: dict | None,
    *,
    label: str,
    require_zero_trade_without_target: bool = True,
) -> None:
    if target is None:
        if mark["target_decision_date"] is not None:
            _fail(f"{label} mark names a target that does not exist")
        if require_zero_trade_without_target and (
            not math.isclose(mark["turnover"], 0.0, abs_tol=_TOLERANCE)
            or not math.isclose(mark["trading_cost"], 0.0, abs_tol=_TOLERANCE)
        ):
            _fail(f"{label} carry-forward mark contains a trade")
        return
    if mark["target_decision_date"] != target["decision_date"]:
        _fail(f"{label} mark is bound to the wrong target decision")
    _require_close(mark["weights"], target["weights"], f"{label} target weights")


def _validate_vector(
    vector: Any,
    assignment: dict,
    *,
    symbols: list[str],
) -> dict:
    if not isinstance(vector, dict):
        _fail("formal interval is missing its authenticated return vector")
    required_keys = {
        "return_vector_id",
        "schema_version",
        "from_session",
        "to_session",
        "captured_utc",
        "scheduled_utc",
        "deadline_utc",
        "vendor",
        "components",
        "cash_component",
    }
    if (
        set(vector) != required_keys
        or type(vector.get("schema_version")) is not int
        or vector["schema_version"] != 2
    ):
        _fail("formal return vector has the wrong schema")
    if vector.get("return_vector_id") != assignment["return_vector_id"]:
        _fail("formal assignment and return-vector identities disagree")
    if (
        vector.get("from_session") != assignment["from_session_date"]
        or vector.get("to_session") != assignment["session_date"]
    ):
        _fail("formal return vector dates disagree with its assignment")
    captured = _finite_number(vector.get("captured_utc"), "return-vector timestamp")
    _require_close(captured, assignment["created_utc"], "return-vector capture time")
    scheduled = _finite_number(vector.get("scheduled_utc"), "price capture schedule")
    deadline = _finite_number(vector.get("deadline_utc"), "price capture deadline")
    from tradingagents.paper_trading import formal_price_capture_window

    expected_scheduled, expected_deadline = formal_price_capture_window(assignment["session_date"])
    _require_close(scheduled, expected_scheduled.timestamp(), "price capture schedule")
    _require_close(deadline, expected_deadline.timestamp(), "price capture deadline")
    if not scheduled <= captured < deadline:
        _fail("formal return vector was captured outside the frozen price window")
    if not isinstance(vector.get("vendor"), str) or not vector["vendor"]:
        _fail("formal return-vector vendor is malformed")

    components = vector.get("components")
    if not isinstance(components, dict) or set(components) != set(symbols):
        _fail("formal return-vector symbols do not match the frozen return universe")
    normalized_components = {}
    for symbol in symbols:
        component = components[symbol]
        component_keys = {
            "price_receipt_id",
            "vendor_snapshot_id",
            "previous_adjusted_open",
            "current_adjusted_open",
            "current_raw_open",
            "cash_dividend",
            "split_ratio",
            "open_return",
        }
        if not isinstance(component, dict) or set(component) != component_keys:
            _fail("formal return-vector component is malformed")
        receipt_id = component.get("price_receipt_id")
        snapshot_id = component.get("vendor_snapshot_id")
        if (
            not isinstance(receipt_id, str)
            or not receipt_id.startswith("price_receipt_")
            or not isinstance(snapshot_id, str)
            or not snapshot_id.startswith("price_snapshot_")
        ):
            _fail("formal return-vector receipt identity is malformed")
        previous = _finite_number(
            component.get("previous_adjusted_open"), f"{symbol} previous adjusted open"
        )
        current = _finite_number(
            component.get("current_adjusted_open"), f"{symbol} current adjusted open"
        )
        returned = _finite_number(component.get("open_return"), f"{symbol} open return")
        raw_open = _finite_number(component.get("current_raw_open"), f"{symbol} raw open")
        dividend = _finite_number(component.get("cash_dividend"), f"{symbol} dividend")
        split_ratio = _finite_number(component.get("split_ratio"), f"{symbol} split ratio")
        if (
            previous <= 0
            or current <= 0
            or raw_open <= 0
            or dividend < 0
            or split_ratio < 0
            or not math.isclose(
                returned, current / previous - 1.0, rel_tol=_TOLERANCE, abs_tol=_TOLERANCE
            )
        ):
            _fail("formal return-vector component arithmetic is invalid")
        normalized_components[symbol] = {
            "price_receipt_id": receipt_id,
            "vendor_snapshot_id": snapshot_id,
            "previous_adjusted_open": previous,
            "current_adjusted_open": current,
            "current_raw_open": raw_open,
            "cash_dividend": dividend,
            "split_ratio": split_ratio,
            "open_return": returned,
        }

    cash = vector.get("cash_component")
    cash_keys = {
        "instrument",
        "annual_yield_proxy",
        "observation_session",
        "annual_yield_percent",
        "accrual_days",
        "day_count_basis",
        "open_return",
    }
    if (
        not isinstance(cash, dict)
        or set(cash) != cash_keys
        or cash.get("instrument") != "USD"
        or cash.get("annual_yield_proxy") != "^IRX"
        or type(cash.get("accrual_days")) is not int
        or cash.get("day_count_basis") != 360
    ):
        _fail("formal return-vector cash component is malformed")
    observation = _date_string(cash.get("observation_session"), "cash observation date")
    start = date.fromisoformat(assignment["from_session_date"])
    end = date.fromisoformat(assignment["session_date"])
    annual_yield = _finite_number(cash.get("annual_yield_percent"), "cash annual yield")
    cash_return = _finite_number(cash.get("open_return"), "cash return")
    accrual_days = cash["accrual_days"]
    if (
        date.fromisoformat(observation) >= start
        or accrual_days != (end - start).days
        or accrual_days <= 0
        or not -20.0 <= annual_yield <= 100.0
    ):
        _fail("formal return-vector cash timing is invalid")
    expected_cash = annual_yield / 100.0 * accrual_days / 360.0
    if not math.isclose(cash_return, expected_cash, rel_tol=_TOLERANCE, abs_tol=_TOLERANCE):
        _fail("formal return-vector cash arithmetic is invalid")

    base = {
        "schema_version": 2,
        "from_session": assignment["from_session_date"],
        "to_session": assignment["session_date"],
        "captured_utc": captured,
        "scheduled_utc": scheduled,
        "deadline_utc": deadline,
        "vendor": vector["vendor"],
        "components": normalized_components,
        "cash_component": {
            **cash,
            "annual_yield_percent": annual_yield,
            "open_return": cash_return,
        },
    }
    if content_id(base, prefix="return_vector_") != vector["return_vector_id"]:
        _fail("formal return-vector content identity is invalid")
    return {"return_vector_id": vector["return_vector_id"], **base}


def _expected_trade_cost(turnover: float, config: dict) -> float:
    return turnover * (float(config["cost_bps"]) + float(config["slippage_bps"])) / 10_000.0


def _validate_initial_marks(
    marks: dict[str, dict[str, dict]],
    targets: dict[str, dict[str, dict]],
    *,
    first_session: str,
    strategies: list[str],
    config: dict,
) -> None:
    for strategy in strategies:
        mark = marks[strategy][first_session]
        target = targets[strategy].get(first_session)
        if target is None:
            _fail("the initial formal mark has no registered entering target")
        _validate_mark_target(mark, target, label=f"{first_session}/{strategy}")
        expected_turnover = sum(target["weights"].values())
        expected_cost = _expected_trade_cost(expected_turnover, config)
        _require_close(mark["turnover"], expected_turnover, "initial mark turnover")
        _require_close(mark["trading_cost"], expected_cost, "initial mark trading cost")
        _require_close(mark["borrow_cost"], 0.0, "initial mark borrow cost")
        _require_close(mark["period_return"], -expected_cost, "initial stored return")
        _require_close(mark["nav"], 1.0 - expected_cost, "initial NAV")
        _require_close(mark["benchmark_nav"], 1.0, "initial benchmark NAV")
        _require_close(mark["benchmark_period_return"], 0.0, "initial benchmark return")


def _reconstruct_interval(
    *,
    strategy: str,
    start_mark: dict,
    end_mark: dict,
    end_target: dict | None,
    vector: dict,
    tickers: list[str],
    config: dict,
) -> float:
    weights = start_mark["weights"]
    gross_asset_return = sum(
        weights[ticker] * vector["components"][ticker]["open_return"] for ticker in tickers
    )
    cash_weight = 1.0 - sum(weights.values())
    if cash_weight < -_TOLERANCE:
        _fail(f"{strategy} start weights imply negative cash in a long-only run")
    cash_return = max(0.0, cash_weight) * vector["cash_component"]["open_return"]
    short_exposure = sum(-weight for weight in weights.values() if weight < 0)
    borrow_cost = short_exposure * float(config["annual_borrow_bps"]) / 10_000.0 / 252.0
    holding_return = gross_asset_return + cash_return - borrow_cost
    if not math.isfinite(holding_return) or holding_return <= -1.0:
        _fail(f"{strategy} reconstructed holding return is invalid")

    entry_cost = start_mark["trading_cost"]
    decision_aligned_return = (1.0 - entry_cost) * (1.0 + holding_return) - 1.0
    if not math.isfinite(decision_aligned_return) or decision_aligned_return <= -1.0:
        _fail(f"{strategy} reconstructed decision-aligned return is invalid")

    denominator = 1.0 + holding_return
    pre_trade_weights = {
        ticker: weights[ticker] * (1.0 + vector["components"][ticker]["open_return"]) / denominator
        for ticker in tickers
    }
    if any(not math.isfinite(value) or value < 0 for value in pre_trade_weights.values()):
        _fail(f"{strategy} reconstructed endpoint weights violate long-only constraints")
    if end_target is None:
        expected_turnover = 0.0
        expected_weights = pre_trade_weights
    else:
        expected_weights = end_target["weights"]
        expected_turnover = sum(
            abs(expected_weights[ticker] - pre_trade_weights[ticker]) for ticker in tickers
        )
    expected_endpoint_cost = _expected_trade_cost(expected_turnover, config)
    expected_stored_return = (1.0 + holding_return) * (1.0 - expected_endpoint_cost) - 1.0
    _validate_mark_target(end_mark, end_target, label=f"{end_mark['session_date']}/{strategy}")
    _require_close(end_mark["weights"], expected_weights, "reconstructed endpoint weights")
    _require_close(end_mark["turnover"], expected_turnover, "endpoint turnover")
    _require_close(end_mark["trading_cost"], expected_endpoint_cost, "endpoint cost")
    _require_close(end_mark["borrow_cost"], borrow_cost, "registered borrow cost")
    _require_close(end_mark["period_return"], expected_stored_return, "stored endpoint return")
    _require_close(
        end_mark["nav"],
        start_mark["nav"] * (1.0 + expected_stored_return),
        "reconstructed endpoint NAV",
    )
    benchmark_return = vector["components"][config["benchmark"]]["open_return"]
    _require_close(end_mark["benchmark_period_return"], benchmark_return, "stored benchmark return")
    _require_close(
        end_mark["benchmark_nav"],
        start_mark["benchmark_nav"] * (1.0 + benchmark_return),
        "reconstructed benchmark NAV",
    )
    return decision_aligned_return


def _assert_json_finite(value: Any, label: str) -> None:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            _fail(f"{label} contains a non-finite value")
        return
    if isinstance(value, list):
        for item in value:
            _assert_json_finite(item, label)
        return
    if isinstance(value, dict):
        for item in value.values():
            _assert_json_finite(item, label)
        return
    _fail(f"{label} contains a non-JSON value")


def build_formal_readout(store: Any, run_id: str) -> dict:
    """Reconstruct and execute the sole 252-interval confirmatory readout.

    The only inputs are the ledger and its run identity. Analysis horizon,
    costs, strategies, tests, seeds, thresholds, and review gate are all read
    from the frozen protocol. The function is read-only and raises before
    reading any outcome unless one exact offline-verification manifest covers
    every successful applied decision.
    """
    config, registration, tickers, benchmark = _validate_run(store, run_id)
    strategies = list(GLOBAL_EVENT_V2_PROTOCOL["strategies"])
    assignments, counts = _validate_assignments(store, run_id)
    verification = require_final_verification_manifest(store, run_id, assignments)
    champion_marks, marks, sessions = _load_marks(store, run_id, tickers, strategies, assignments)
    # Targets belong only at interval starts. A target at the final endpoint
    # would be a 253rd, post-horizon decision whose cost must not enter or sit
    # alongside the confirmatory trial.
    target_sessions = [row["from_session_date"] for row in assignments]
    official_targets, targets = _load_targets(store, run_id, tickers, strategies, target_sessions)
    _validate_initial_marks(
        marks,
        targets,
        first_session=sessions[0],
        strategies=strategies,
        config=config,
    )

    # All strategies must share the champion's capture timestamp, market
    # snapshot, benchmark, and target timing on every formal mark.
    for session in sessions:
        official = champion_marks[session]
        official_target = official_targets.get(session)
        _validate_mark_target(official, official_target, label=f"{session}/official-champion")
        for strategy in strategies:
            mark = marks[strategy][session]
            _require_close(mark["captured_utc"], official["captured_utc"], "mark capture time")
            _require_close(mark["opens"], official["opens"], "mark open cross-section")
            _require_close(mark["benchmark_open"], official["benchmark_open"], "benchmark open")
            _require_close(
                mark["target_decision_date"],
                official["target_decision_date"],
                "synchronized target timing",
            )

    strategy_returns = {strategy: [] for strategy in strategies}
    benchmark_returns = []
    vector_symbols = [*tickers, benchmark]
    for assignment in assignments:
        vector = store.return_vector_for_session(run_id, assignment["session_date"], vector_symbols)
        vector = _validate_vector(vector, assignment, symbols=vector_symbols)
        end_official = champion_marks[assignment["session_date"]]
        _require_close(
            vector["captured_utc"], end_official["captured_utc"], "vector/mark capture time"
        )
        for ticker in tickers:
            _require_close(
                end_official["opens"][ticker],
                vector["components"][ticker]["current_adjusted_open"],
                f"{assignment['session_date']} {ticker} current adjusted open",
            )
        _require_close(
            end_official["benchmark_open"],
            vector["components"][benchmark]["current_adjusted_open"],
            f"{assignment['session_date']} benchmark current adjusted open",
        )
        benchmark_returns.append(vector["components"][benchmark]["open_return"])

        start_session = assignment["from_session_date"]
        end_session = assignment["session_date"]
        applied = assignment["applied_target_decision_date"]
        for strategy in strategies:
            start_mark = marks[strategy][start_session]
            start_target = targets[strategy].get(start_session)
            if assignment["disposition"] == "target_applied":
                if start_target is None or start_target["decision_date"] != applied:
                    _fail("formal target-applied assignment has no matching strategy target")
            elif start_target is not None:
                _fail("formal carry-forward assignment unexpectedly has a strategy target")
            _validate_mark_target(start_mark, start_target, label=f"{start_session}/{strategy}")
            strategy_returns[strategy].append(
                _reconstruct_interval(
                    strategy=strategy,
                    start_mark=start_mark,
                    end_mark=marks[strategy][end_session],
                    end_target=targets[strategy].get(end_session),
                    vector=vector,
                    tickers=tickers,
                    config=config,
                )
            )

    required = len(assignments)
    # The ledger-derived completed count becomes synchronized_marks only after
    # the exact 8 x (252 + initialization) matrix has independently validated.
    synchronized_marks = _exact_integer(
        counts.get("synchronized_marks", counts["completed_intervals"]),
        "synchronized marks",
    )
    if synchronized_marks != required:
        _fail("formal mark matrix is not synchronized for every completed interval")
    successful_decision_sets = _exact_integer(
        counts["successful_decision_sets"], "successful decision sets"
    )
    final_counts = store.formal_trial_counts(run_id)
    count_keys = {
        "completed_intervals",
        "successful_decision_sets",
        "carry_forward_intervals",
        "assignment_indices_contiguous",
        "assignment_dates_contiguous",
    }
    if not isinstance(final_counts, dict) or any(
        final_counts.get(key) != counts.get(key) for key in count_keys
    ):
        _fail("formal trial ledger changed while the outcome bundle was reconstructed")
    readout = formal_complete_readout(
        deepcopy(strategy_returns),
        list(benchmark_returns),
        successful_decision_sets=successful_decision_sets,
        synchronized_marks=synchronized_marks,
    )
    if (
        not isinstance(readout, dict)
        or readout.get("protocol_id") != GLOBAL_EVENT_V2_PROTOCOL_ID
        or readout.get("paired_intervals") != required
        or readout.get("live_capital_approved") is not False
    ):
        _fail("frozen statistical readout returned an invalid report contract")

    assignment_manifest = [
        {
            key: row[key]
            for key in (
                "interval_index",
                "from_session_date",
                "session_date",
                "scheduled_decision_date",
                "disposition",
                "applied_target_decision_date",
                "return_vector_id",
            )
        }
        for row in assignments
    ]
    outcome_bundle = {
        "schema_version": 1,
        "bundle_type": "global-event-v2-final-outcomes",
        "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
        "run_id": run_id,
        "registration_id": registration["registration_id"],
        "holding_intervals": required,
        "successful_decision_sets": successful_decision_sets,
        "synchronized_marks": synchronized_marks,
        **verification,
        "assignments": assignment_manifest,
        "strategy_returns": strategy_returns,
        "benchmark_returns": benchmark_returns,
    }
    _assert_json_finite(outcome_bundle, "formal outcome bundle")
    outcome_bundle_id = content_id(outcome_bundle, prefix="outcome_bundle_")
    report_base = {
        "schema_version": 1,
        "report_type": "global-event-v2-sole-confirmatory-readout",
        "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
        "run_id": run_id,
        "registration_id": registration["registration_id"],
        "review_gate": 252,
        "interim": False,
        "outcome_bundle_id": outcome_bundle_id,
        **verification,
        "readout": readout,
    }
    _assert_json_finite(report_base, "formal readout report")
    report_id = content_id(report_base, prefix="formal_report_")
    # Returning (rather than recording) leaves outcome access labeling and
    # durable publication to the separately controlled final-review workflow.
    return {
        **report_base,
        "report_id": report_id,
        "outcome_bundle": outcome_bundle,
    }


__all__ = [
    "FormalReadoutIntegrityError",
    "build_formal_readout",
    "materialize_final_verification_manifest",
    "require_final_verification_manifest",
]
