"""Point-in-time availability projection for the bounded daily X sample.

The collector records one immutable ``x-daily`` collection cycle per UTC day.
An evidence snapshot may use only X rows proven to belong to the exact cycle
immediately preceding its cutoff.  Missing or incomplete X collection is an
explicit neutral state; it never prevents the independent editorial-news arm
from proceeding.
"""

from __future__ import annotations

import json
import math
import re
import uuid
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

from tradingagents.dataflows import media_store
from tradingagents.evidence_lineage import evidence_id, raw_content_id
from tradingagents.global_research import (
    evidence_selection_manifest,
    is_formally_eligible_evidence,
)
from tradingagents.research_protocol import (
    GLOBAL_EVENT_V2_COMPATIBLE_COLLECTOR_IDENTITIES,
    GLOBAL_EVENT_V2_CURRENT_COLLECTOR_IDENTITY,
    GLOBAL_EVENT_V2_PROTOCOL,
    content_id,
)
from tradingagents.x_cycle import x_cycle_structural_state

_EVIDENCE_ID = re.compile(r"evidence_[0-9a-f]{24}")
_RAW_ID = re.compile(r"raw_[0-9a-f]{24}")
_LINEAGE_KEYS = {"evidence_id", "raw_content_id", "fetch_run_ids", "labels"}


def _canonical_uuid4(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = uuid.UUID(value)
    except (AttributeError, ValueError):
        return False
    return parsed.version == 4 and str(parsed) == value


def _finalize(payload: dict[str, Any]) -> dict[str, Any]:
    return {"availability_id": content_id(payload, prefix="xavail_"), **payload}


def _cycle_spec(period_key: str, identity: Mapping[str, Any]) -> dict[str, Any]:
    return media_store.collection_cycle_spec(
        cycle_kind="x-daily",
        period_key=period_key,
        protocol_id=identity["protocol_id"],
        collector_semantics_id=identity["collector_semantics_id"],
        expected_static_slots=identity["x_daily_static_slots"],
        max_dynamic_slots=identity["x_daily_max_dynamic_slots"],
    )


def _expected_cycle(cutoff: datetime) -> tuple[dict[str, Any], str, dict[str, Any]]:
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("X availability cutoff must be timezone-aware")
    cutoff = cutoff.astimezone(timezone.utc)
    policy = dict(GLOBAL_EVENT_V2_PROTOCOL["evidence"]["x_formal_availability"])
    if (
        policy.get("cycle_kind") != "x-daily"
        or policy.get("period_offset_utc_days") != -1
        or policy.get("eligible_source") != "x"
        or policy.get("cutoff_time_basis") != "server_terminal_utc"
    ):
        raise ValueError("X availability policy is unsupported")
    period_date = cutoff.date() + timedelta(days=int(policy["period_offset_utc_days"]))
    period_key = period_date.isoformat()

    spec = _cycle_spec(period_key, GLOBAL_EVENT_V2_CURRENT_COLLECTOR_IDENTITY)
    return policy, period_key, spec


def _accepted_cycles(
    cutoff: datetime,
) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
    """Return the primary cycle plus only explicitly registered equivalents."""
    policy, period_key, primary = _expected_cycle(cutoff)
    candidates = [
        {
            "spec": primary,
            "primary": True,
        }
    ]
    for identity_entry in GLOBAL_EVENT_V2_COMPATIBLE_COLLECTOR_IDENTITIES:
        candidates.append(
            {
                "spec": _cycle_spec(period_key, identity_entry),
                "primary": False,
            }
        )
    cycle_ids = [item["spec"]["collection_cycle_id"] for item in candidates]
    if len(cycle_ids) != len(set(cycle_ids)):
        raise ValueError("compatible X collection cycle identities are duplicated")
    return policy, period_key, candidates


def _cycle_summary(candidate: dict[str, Any]) -> dict[str, Any]:
    identity = candidate["spec"]["identity"]
    return {
        "collection_cycle_id": candidate["spec"]["collection_cycle_id"],
        "protocol_id": identity["protocol_id"],
        "collector_semantics_id": identity["collector_semantics_id"],
        "primary": candidate["primary"],
    }


def _cycle_discovery_decision(
    store: Any, cycle_id: str, cycle_manifest: dict[str, Any]
) -> dict[str, Any] | None:
    receipt = next(
        (
            item for item in cycle_manifest["slot_receipts"]
            if item["provider"] == "trendnews"
            and item["query_key"] == "ranked-global-discovery"
        ),
        None,
    )
    if receipt is None or receipt["status"] != "success":
        return None
    items = store.collection_cycle_item_rows(
        cycle_id,
        provider="trendnews",
        query_key="ranked-global-discovery",
    )
    decisions = [
        item for item in items
        if (item["row"].get("metadata") or {}).get("evidence_role")
        == "query_free_discovery_decision"
    ]
    if not decisions:
        return None
    if len(decisions) != 1:
        raise ValueError("X cycle must contain exactly one discovery decision")
    item = decisions[0]
    row = item["row"]
    try:
        decision = json.loads(row.get("body"))
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("X cycle discovery decision is malformed") from exc
    from tradingagents.poller import validate_x_discovery_decision

    validate_x_discovery_decision(decision)
    decision_id = decision["discovery_decision_id"]
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    if (
        decision["collection_cycle_id"] != cycle_id
        or row.get("external_id") != decision_id
        or metadata.get("discovery_decision_id") != decision_id
        or item["fetch_run_id"] != receipt["fetch_run_id"]
        or item["raw_content_id"] not in receipt["raw_content_ids"]
    ):
        raise ValueError("X cycle discovery decision lineage is invalid")
    expected_dynamic = [
        {"provider": "x", "query_key": request["query_key"]}
        for request in decision["search_requests"]
    ]
    if expected_dynamic != cycle_manifest["expected_dynamic_slots"]:
        raise ValueError("X cycle searches differ from their discovery decision")
    return {
        "discovery_decision_id": decision_id,
        "fetch_run_id": item["fetch_run_id"],
        "raw_content_id": item["raw_content_id"],
        "manifest": decision,
    }


def _cycle_x_item_rows(
    store: Any, cycle_id: str, cycle_manifest: dict[str, Any]
) -> dict[tuple[str, str], dict[str, Any]]:
    """Rebuild X rows and labels solely from this cycle's exact receipts."""
    rows_by_pair: dict[tuple[str, str], dict[str, Any]] = {}
    for receipt in cycle_manifest["slot_receipts"]:
        if receipt["provider"] != "x" or receipt["fetch_run_id"] is None:
            continue
        items = store.collection_cycle_item_rows(
            cycle_id, provider="x", query_key=receipt["query_key"]
        )
        if sorted(item["raw_content_id"] for item in items) != receipt["raw_content_ids"]:
            raise ValueError("X cycle item replay differs from its receipt")
        for item in items:
            if item["fetch_run_id"] != receipt["fetch_run_id"]:
                raise ValueError("X cycle item belongs to another receipt")
            row = item["row"]
            if row.get("source") != "x":
                raise ValueError("X cycle item has mismatched source provenance")
            metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            labels = metadata.get("receipt_labels")
            if (
                not isinstance(labels, list)
                or not labels
                or labels != sorted(set(labels))
                or any(not isinstance(label, str) or not label for label in labels)
            ):
                raise ValueError("X cycle item lacks exact receipt labels")
            exact_row = {**row, "labels": labels}
            observed = exact_row.get("latest_observed_utc")
            fetched = exact_row.get("fetched_utc")
            if (
                isinstance(observed, bool)
                or not isinstance(observed, (int, float))
                or not math.isfinite(float(observed))
                or isinstance(fetched, bool)
                or not isinstance(fetched, (int, float))
                or not math.isfinite(float(fetched))
            ):
                raise ValueError("X cycle item lacks exact receipt time")
            pair = (
                evidence_id(exact_row),
                raw_content_id(exact_row),
            )
            order = (float(observed), float(fetched), item["fetch_run_id"])
            prior = rows_by_pair.get(pair)
            if prior is None:
                rows_by_pair[pair] = {
                    "row": exact_row,
                    "labels": set(labels),
                    "order": order,
                }
            else:
                prior["labels"].update(labels)
                if order > prior["order"]:
                    prior["row"] = exact_row
                    prior["order"] = order
    for value in rows_by_pair.values():
        value["labels"] = sorted(value["labels"])
        value["row"]["labels"] = value["labels"]
        metadata = value["row"].get("metadata")
        value["row"]["metadata"] = {
            **(metadata if isinstance(metadata, dict) else {}),
            "receipt_labels": value["labels"],
        }
    return rows_by_pair


def _select_cycle_x_rows(
    candidate_rows: list[dict[str, Any]],
    receipt_runs_by_pair: dict[tuple[str, str], set[str]],
    cycle_x_rows: dict[tuple[str, str], dict[str, Any]],
    *,
    cutoff_utc: float,
) -> tuple[list[dict[str, Any]], set[tuple[str, str]]]:
    """Choose the newest eligible exact-cycle vintage per provider identity."""
    candidate_evidence_ids = {
        evidence_id(row)
        for row in candidate_rows
        if row.get("source") == "x"
    }
    latest: dict[str, tuple[tuple, tuple[str, str], dict]] = {}
    for pair, exact in cycle_x_rows.items():
        item_evidence_id, _raw_content_id = pair
        if item_evidence_id not in candidate_evidence_ids:
            continue
        exact_row = exact["row"]
        order = exact["order"]
        prior = latest.get(item_evidence_id)
        if prior is None or order > prior[0]:
            latest[item_evidence_id] = (order, pair, exact_row)
    selected = {
        item_evidence_id: value
        for item_evidence_id, value in latest.items()
        if value[1] in receipt_runs_by_pair
        and is_formally_eligible_evidence(value[2], as_of_utc=cutoff_utc)
    }
    return (
        [value[2] for _evidence_id, value in sorted(selected.items())],
        {value[1] for value in selected.values()},
    )


def project_x_cycle_availability(
    store: Any,
    *,
    cutoff: datetime,
    candidate_rows: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return exact prior-day X availability and the rows it authorizes.

    Non-X candidates always pass through.  X candidates pass only when both
    their evidence and raw-content identities occur in the exact complete daily
    cycle and remain eligible at the decision cutoff.
    """
    if not isinstance(candidate_rows, list) or any(
        not isinstance(row, dict) for row in candidate_rows
    ):
        raise TypeError("X availability candidates must be a list of mappings")
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("X availability cutoff must be timezone-aware")
    cutoff = cutoff.astimezone(timezone.utc)
    policy, period_key, accepted_cycles = _accepted_cycles(cutoff)
    primary = accepted_cycles[0]
    selected = None
    cycle = None
    # Deterministically prefer the primary identity whenever it exists.  An
    # incomplete primary cycle must not be hidden by choosing an older-format
    # compatible cycle for the same day.
    for candidate in accepted_cycles:
        candidate_cycle = store.collection_cycle(candidate["spec"]["collection_cycle_id"])
        if candidate_cycle is not None:
            selected = candidate
            cycle = candidate_cycle
            break
    spec = (selected or primary)["spec"]
    expected_cycle_id = spec["collection_cycle_id"]
    base = {
        "schema_version": 2,
        "policy": policy,
        "period_key": period_key,
        "expected_collection_cycle_id": expected_cycle_id,
        "primary_collection_cycle_id": primary["spec"]["collection_cycle_id"],
        "accepted_collection_cycles": [
            _cycle_summary(candidate) for candidate in accepted_cycles
        ],
        "selected_collection_cycle": (
            _cycle_summary(selected) if selected is not None else None
        ),
    }
    non_x_rows = [row for row in candidate_rows if row.get("source") != "x"]
    if cycle is None:
        return _finalize(
            {
                **base,
                "state": "missing",
                "collection_cycle_id": None,
                "manifest_id": None,
                "cycle_manifest": None,
                "collector_semantics_id": spec["identity"]["collector_semantics_id"],
                "collector_build_id": None,
                "server_started_utc": None,
                "server_terminal_utc": None,
                "discovery_decision": None,
                "eligible_lineage": [],
            }
        ), non_x_rows
    structural_state = x_cycle_structural_state(spec, cycle)
    if structural_state == "invalid":
        raise ValueError("X collection cycle structure is invalid")
    server_started = cycle.get("server_started_utc")
    server_terminal = cycle.get("server_terminal_utc")
    trusted_terminal = (
        structural_state in {"complete", "incomplete"}
        and isinstance(server_terminal, (int, float))
        and not isinstance(server_terminal, bool)
        and float(server_terminal) < cutoff.timestamp()
    )
    observed_manifest = cycle.get("manifest") if trusted_terminal else None
    provenance = {
        **base,
        "collection_cycle_id": expected_cycle_id,
        "manifest_id": cycle.get("manifest_id") if trusted_terminal else None,
        "cycle_manifest": observed_manifest,
        "collector_semantics_id": cycle.get("collector_semantics_id"),
        "collector_build_id": cycle.get("collector_build_id") if trusted_terminal else None,
        "server_started_utc": server_started if trusted_terminal else None,
        "server_terminal_utc": server_terminal if trusted_terminal else None,
        "discovery_decision": None,
    }
    if not trusted_terminal or structural_state != "complete":
        return _finalize(
            {**provenance, "state": "incomplete", "eligible_lineage": []}
        ), non_x_rows

    discovery_decision = _cycle_discovery_decision(
        store, expected_cycle_id, observed_manifest
    )
    if discovery_decision is None:
        return _finalize(
            {**provenance, "state": "incomplete", "eligible_lineage": []}
        ), non_x_rows
    provenance["discovery_decision"] = discovery_decision

    receipt_lineage = store.collection_cycle_formal_lineage(
        expected_cycle_id, provider=policy["eligible_source"]
    )
    manifest_x_lineage = {
        (slot.get("fetch_run_id"), raw_content_id)
        for slot in observed_manifest.get("slot_receipts", [])
        if isinstance(slot, dict) and slot.get("provider") == policy["eligible_source"]
        for raw_content_id in slot.get("raw_content_ids", [])
    }
    if any(
        (item.get("fetch_run_id"), item.get("raw_content_id")) not in manifest_x_lineage
        for item in receipt_lineage
    ):
        raise ValueError("X eligible lineage is absent from the cycle manifest")
    receipt_runs_by_pair: dict[tuple[str, str], set[str]] = {}
    for item in receipt_lineage:
        pair = (item["evidence_id"], item["raw_content_id"])
        receipt_runs_by_pair.setdefault(pair, set()).add(item["fetch_run_id"])
    cycle_x_rows = _cycle_x_item_rows(
        store, expected_cycle_id, observed_manifest
    )

    eligible_rows, eligible_pairs = _select_cycle_x_rows(
        candidate_rows,
        receipt_runs_by_pair,
        cycle_x_rows,
        cutoff_utc=cutoff.timestamp(),
    )
    eligible_lineage = [
        {
            "evidence_id": evidence_id,
            "raw_content_id": raw_content_id,
            "fetch_run_ids": sorted(receipt_runs_by_pair[(evidence_id, raw_content_id)]),
            "labels": cycle_x_rows[(evidence_id, raw_content_id)]["labels"],
        }
        for evidence_id, raw_content_id in sorted(eligible_pairs)
    ]
    state = "complete_with_eligible" if eligible_lineage else "complete_zero_eligible"
    return _finalize(
        {**provenance, "state": state, "eligible_lineage": eligible_lineage}
    ), non_x_rows + eligible_rows


def bind_x_availability_to_selection(
    selection_manifest: dict[str, Any], availability: dict[str, Any]
) -> dict[str, Any]:
    """Content-bind the exact X-cycle projection into an evidence selection."""
    if selection_manifest.get("schema_version") != 2:
        raise ValueError("evidence selection manifest version is unsupported")
    if not isinstance(availability.get("availability_id"), str):
        raise ValueError("X availability projection requires a content identity")
    payload = {
        key: value for key, value in selection_manifest.items() if key != "manifest_id"
    }
    payload["schema_version"] = 3
    payload["x_cycle_availability"] = availability
    return {"manifest_id": content_id(payload, prefix="selection_"), **payload}


def _validate_bound_discovery_decision(
    artifact: object, cycle_manifest: dict[str, Any]
) -> dict[str, list[str]]:
    if not isinstance(artifact, dict) or set(artifact) != {
        "discovery_decision_id", "fetch_run_id", "raw_content_id", "manifest"
    }:
        raise ValueError("complete X availability lacks its discovery decision")
    decision = artifact.get("manifest")
    from tradingagents.poller import (
        validate_x_discovery_decision,
        x_discovery_decision_row,
    )

    validate_x_discovery_decision(decision)
    decision_row = x_discovery_decision_row(decision)
    if (
        artifact.get("discovery_decision_id")
        != decision["discovery_decision_id"]
        or not _canonical_uuid4(artifact.get("fetch_run_id"))
        or not isinstance(artifact.get("raw_content_id"), str)
        or _RAW_ID.fullmatch(artifact["raw_content_id"]) is None
        or raw_content_id(decision_row)
        != artifact["raw_content_id"]
    ):
        raise ValueError("X discovery decision artifact is not content-bound")
    discovery_receipts = [
        receipt for receipt in cycle_manifest["slot_receipts"]
        if receipt["provider"] == "trendnews"
        and receipt["query_key"] == "ranked-global-discovery"
    ]
    if len(discovery_receipts) != 1:
        raise ValueError("X cycle discovery receipt is not unique")
    receipt = discovery_receipts[0]
    if (
        artifact["fetch_run_id"] != receipt["fetch_run_id"]
        or artifact["raw_content_id"] not in receipt["raw_content_ids"]
        or decision["collection_cycle_id"] != cycle_manifest["collection_cycle_id"]
    ):
        raise ValueError("X discovery decision differs from its cycle receipt")
    expected_dynamic = [
        {"provider": "x", "query_key": request["query_key"]}
        for request in decision["search_requests"]
    ]
    if expected_dynamic != cycle_manifest["expected_dynamic_slots"]:
        raise ValueError("X cycle searches differ from their discovery decision")
    labels_by_fetch: dict[str, list[str]] = {}
    request_by_query = {
        request["query_key"]: request for request in decision["search_requests"]
    }
    for receipt in cycle_manifest["slot_receipts"]:
        if receipt["provider"] != "x" or receipt["fetch_run_id"] is None:
            continue
        request = request_by_query.get(receipt["query_key"])
        if request is None:
            raise ValueError("X receipt is absent from its discovery decision")
        labels_by_fetch[receipt["fetch_run_id"]] = request["labels"]
    return labels_by_fetch


def validate_bound_x_selection(
    selection_manifest: dict[str, Any], raw_evidence: tuple[dict[str, Any], ...]
) -> None:
    """Validate that a schema-3 selection contains exactly its authorized X rows."""
    if selection_manifest.get("schema_version") != 3:
        raise ValueError("global-event selection requires bound X availability")
    manifest_payload = {
        key: value
        for key, value in selection_manifest.items()
        if key != "manifest_id"
    }
    if selection_manifest.get("manifest_id") != content_id(
        manifest_payload, prefix="selection_"
    ):
        raise ValueError("evidence selection manifest identity is invalid")
    availability = selection_manifest.get("x_cycle_availability")
    if not isinstance(availability, dict):
        raise ValueError("evidence selection lacks X availability")
    availability_payload = {
        key: value for key, value in availability.items() if key != "availability_id"
    }
    if availability.get("availability_id") != content_id(
        availability_payload, prefix="xavail_"
    ):
        raise ValueError("X availability identity is invalid")
    as_of_utc = selection_manifest.get("as_of_utc")
    if (
        isinstance(as_of_utc, bool)
        or not isinstance(as_of_utc, (int, float))
        or not math.isfinite(float(as_of_utc))
    ):
        raise ValueError("X availability requires the selection cutoff")
    policy, period_key, accepted_cycles = _accepted_cycles(
        datetime.fromtimestamp(float(as_of_utc), timezone.utc)
    )
    accepted_summaries = [
        _cycle_summary(candidate) for candidate in accepted_cycles
    ]
    if (
        availability.get("schema_version") != 2
        or availability.get("policy") != policy
        or availability.get("period_key") != period_key
        or availability.get("primary_collection_cycle_id")
        != accepted_cycles[0]["spec"]["collection_cycle_id"]
        or availability.get("accepted_collection_cycles") != accepted_summaries
    ):
        raise ValueError("X availability collector identity registry is invalid")
    selected_cycle = availability.get("selected_collection_cycle")
    selected_candidate = None
    if selected_cycle is None:
        if (
            availability.get("expected_collection_cycle_id")
            != accepted_cycles[0]["spec"]["collection_cycle_id"]
            or availability.get("collection_cycle_id") is not None
        ):
            raise ValueError("missing X availability names an unexpected cycle")
    elif selected_cycle not in accepted_summaries:
        raise ValueError("X availability selected an unregistered collector identity")
    else:
        selected_candidate = accepted_cycles[accepted_summaries.index(selected_cycle)]
        if (
            availability.get("expected_collection_cycle_id")
            != selected_cycle["collection_cycle_id"]
            or availability.get("collection_cycle_id")
            != selected_cycle["collection_cycle_id"]
            or availability.get("collector_semantics_id")
            != selected_cycle["collector_semantics_id"]
        ):
            raise ValueError("X availability differs from its selected collector identity")
    state = availability.get("state")
    if state not in {
        "missing",
        "incomplete",
        "complete_zero_eligible",
        "complete_with_eligible",
    }:
        raise ValueError("X availability state is invalid")
    if (selected_cycle is None) != (state == "missing"):
        raise ValueError("X availability state disagrees with its selected cycle")
    manifest = availability.get("cycle_manifest")
    manifest_id = availability.get("manifest_id")
    labels_by_fetch: dict[str, list[str]] = {}
    if state in {"complete_zero_eligible", "complete_with_eligible"}:
        if selected_candidate is None or not isinstance(manifest, dict):
            raise ValueError("complete X availability lacks its exact cycle manifest")
        reconstructed_cycle = {
            "collection_cycle_id": selected_cycle["collection_cycle_id"],
            "cycle_kind": manifest.get("cycle_kind"),
            "period_key": manifest.get("period_key"),
            "protocol_id": manifest.get("protocol_id"),
            "collector_semantics_id": manifest.get("collector_semantics_id"),
            "identity_valid": True,
            "identity": selected_candidate["spec"]["identity"],
            "started_utc": manifest.get("started_utc"),
            "completed_utc": manifest.get("completed_utc"),
            "status": manifest.get("status"),
            "manifest_valid": True,
            "manifest": manifest,
            "manifest_id": manifest_id,
            "collector_build_id": availability.get("collector_build_id"),
            "server_started_utc": availability.get("server_started_utc"),
            "server_terminal_utc": availability.get("server_terminal_utc"),
        }
        if x_cycle_structural_state(
            selected_candidate["spec"], reconstructed_cycle
        ) != "complete":
            raise ValueError("complete X availability cycle manifest is invalid")
        labels_by_fetch = _validate_bound_discovery_decision(
            availability.get("discovery_decision"), manifest
        )
        terminal = availability.get("server_terminal_utc")
        if not isinstance(terminal, (int, float)) or isinstance(terminal, bool) \
                or not math.isfinite(float(terminal)) \
                or float(terminal) >= float(as_of_utc):
            raise ValueError("complete X availability is not strictly before cutoff")
    elif manifest is not None or manifest_id is not None:
        if selected_candidate is None or not isinstance(manifest, dict):
            raise ValueError("incomplete X availability manifest is malformed")
        reconstructed_cycle = {
            "collection_cycle_id": selected_cycle["collection_cycle_id"],
            "cycle_kind": manifest.get("cycle_kind"),
            "period_key": manifest.get("period_key"),
            "protocol_id": manifest.get("protocol_id"),
            "collector_semantics_id": manifest.get("collector_semantics_id"),
            "identity_valid": True,
            "identity": selected_candidate["spec"]["identity"],
            "started_utc": manifest.get("started_utc"),
            "completed_utc": manifest.get("completed_utc"),
            "status": manifest.get("status"),
            "manifest_valid": True,
            "manifest": manifest,
            "manifest_id": manifest_id,
            "collector_build_id": availability.get("collector_build_id"),
            "server_started_utc": availability.get("server_started_utc"),
            "server_terminal_utc": availability.get("server_terminal_utc"),
        }
        structural_state = x_cycle_structural_state(
            selected_candidate["spec"], reconstructed_cycle
        )
        if structural_state not in {"complete", "incomplete"}:
            raise ValueError("incomplete X availability cycle manifest is invalid")
        if structural_state == "complete" and availability.get(
            "discovery_decision"
        ) is not None:
            raise ValueError("complete X cycle has inconsistent discovery availability")
        terminal = availability.get("server_terminal_utc")
        if not isinstance(terminal, (int, float)) or isinstance(terminal, bool) \
                or not math.isfinite(float(terminal)) \
                or float(terminal) >= float(as_of_utc):
            raise ValueError("incomplete X availability is not strictly before cutoff")
    elif any(
        availability.get(key) is not None
        for key in ("collector_build_id", "server_started_utc", "server_terminal_utc")
    ):
        raise ValueError("nonterminal X availability carries terminal provenance")
    lineage = availability.get("eligible_lineage")
    if not isinstance(lineage, list):
        raise ValueError("X availability lineage must be a list")
    if any(
        not isinstance(item, dict)
        or set(item) != _LINEAGE_KEYS
        or not isinstance(item.get("evidence_id"), str)
        or _EVIDENCE_ID.fullmatch(item["evidence_id"]) is None
        or not isinstance(item.get("raw_content_id"), str)
        or _RAW_ID.fullmatch(item["raw_content_id"]) is None
        or not isinstance(item.get("fetch_run_ids"), list)
        or not item["fetch_run_ids"]
        or item["fetch_run_ids"] != sorted(set(item["fetch_run_ids"]))
        or any(not _canonical_uuid4(value) for value in item["fetch_run_ids"])
        or not isinstance(item.get("labels"), list)
        or not item["labels"]
        or item["labels"] != sorted(set(item["labels"]))
        or any(not isinstance(value, str) or not value for value in item["labels"])
        for item in lineage
    ):
        raise ValueError("X availability lineage is malformed or duplicated")
    lineage_pairs = {
        (item["evidence_id"], item["raw_content_id"])
        for item in lineage
    }
    if len(lineage_pairs) != len(lineage) or lineage != sorted(
        lineage, key=lambda item: (item["evidence_id"], item["raw_content_id"])
    ):
        raise ValueError("X availability lineage is malformed or duplicated")
    manifest_x_pairs = {
        (receipt.get("fetch_run_id"), raw_id)
        for receipt in (manifest or {}).get("slot_receipts", [])
        if isinstance(receipt, dict) and receipt.get("provider") == "x"
        for raw_id in receipt.get("raw_content_ids", [])
    }
    if any(
        (fetch_run_id, item["raw_content_id"]) not in manifest_x_pairs
        for item in lineage
        for fetch_run_id in item["fetch_run_ids"]
    ):
        raise ValueError("X availability lineage is absent from its cycle manifest")
    if any(
        item["labels"]
        != sorted({
            label
            for fetch_run_id in item["fetch_run_ids"]
            for label in labels_by_fetch.get(fetch_run_id, [])
        })
        for item in lineage
    ):
        raise ValueError("X availability labels differ from exact-cycle receipts")
    raw_x_rows: dict[tuple[str, str], dict[str, Any]] = {}
    for row in raw_evidence:
        if row.get("source") != "x":
            continue
        pair = (
            evidence_id(row),
            raw_content_id(row),
        )
        if pair in raw_x_rows:
            raise ValueError("snapshot X rows contain duplicate exact content")
        raw_x_rows[pair] = row
    raw_x_pairs = set(raw_x_rows)
    if raw_x_pairs != lineage_pairs:
        raise ValueError("snapshot X rows differ from exact-cycle availability lineage")
    lineage_by_pair = {
        (item["evidence_id"], item["raw_content_id"]): item
        for item in lineage
    }
    manifest_started = (manifest or {}).get("started_utc")
    manifest_completed = (manifest or {}).get("completed_utc")
    server_started = availability.get("server_started_utc")
    server_terminal = availability.get("server_terminal_utc")
    for pair, row in raw_x_rows.items():
        labels = row.get("labels")
        latest = row.get("latest_observed_utc")
        fetched = row.get("fetched_utc")
        if (
            not isinstance(labels, list)
            or labels != sorted(set(labels))
            or labels != lineage_by_pair[pair]["labels"]
        ):
            raise ValueError("snapshot X labels differ from exact-cycle availability")
        if (
            row.get("latest_observed_utc_source") != "server_terminal_utc"
            or isinstance(latest, bool)
            or not isinstance(latest, (int, float))
            or not math.isfinite(float(latest))
            or not float(server_started) <= float(latest) <= float(server_terminal)
            or isinstance(fetched, bool)
            or not isinstance(fetched, (int, float))
            or not math.isfinite(float(fetched))
            or not float(manifest_started) <= float(fetched) <= float(manifest_completed)
        ):
            raise ValueError("snapshot X observation time differs from its exact cycle")
        if not is_formally_eligible_evidence(row, as_of_utc=float(as_of_utc)):
            raise ValueError("snapshot X row is not formally eligible at the cutoff")
    if (state == "complete_with_eligible") != bool(lineage_pairs):
        raise ValueError("X availability state disagrees with its eligible lineage")
    if state in {"missing", "incomplete", "complete_zero_eligible"} and lineage:
        raise ValueError("X availability state requires empty eligible lineage")
    expected_selection = bind_x_availability_to_selection(
        evidence_selection_manifest(
            list(raw_evidence), as_of_utc=float(as_of_utc)
        ),
        availability,
    )
    if selection_manifest != expected_selection:
        raise ValueError("evidence selection does not replay from its raw evidence")
