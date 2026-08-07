"""Point-in-time availability projection for the bounded daily X sample.

The collector records one immutable ``x-daily`` collection cycle per UTC day.
An evidence snapshot may use only X rows proven to belong to the exact cycle
immediately preceding its cutoff.  Missing or incomplete X collection is an
explicit neutral state; it never prevents the independent editorial-news arm
from proceeding.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

from tradingagents import global_research
from tradingagents.dataflows import media_store
from tradingagents.global_research import is_formally_eligible_evidence
from tradingagents.research_protocol import GLOBAL_EVENT_V2_PROTOCOL, content_id


def _finalize(payload: dict[str, Any]) -> dict[str, Any]:
    return {"availability_id": content_id(payload, prefix="xavail_"), **payload}


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
    period_instant = datetime.combine(
        period_date, datetime.min.time(), tzinfo=timezone.utc
    ).timestamp()

    # This is the collector's single source of truth for its content-addressed
    # daily identity.  Import lazily so the pure research contracts do not load
    # collector adapters merely by being imported.
    from tradingagents.poller import _x_collection_cycle_spec

    spec = _x_collection_cycle_spec(
        period_instant,
        int(GLOBAL_EVENT_V2_PROTOCOL["evidence"]["max_x_search_requests_per_utc_day"]),
    )
    return policy, period_key, spec


def _accepted_cycles(
    cutoff: datetime,
) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
    """Return the primary cycle plus only explicitly registered equivalents."""
    policy, period_key, primary = _expected_cycle(cutoff)
    candidates = [
        {
            "spec": primary,
            "compatibility_reason": None,
            "primary": True,
        }
    ]
    identity = primary["identity"]
    compatible = GLOBAL_EVENT_V2_PROTOCOL["evidence"].get(
        "compatible_collector_identities", []
    )
    if not isinstance(compatible, list):
        raise ValueError("compatible collector identities must be a list")
    static_slots = [
        (slot["provider"], slot["query_key"])
        for slot in identity["expected_static_slots"]
    ]
    for item in compatible:
        if not isinstance(item, dict):
            raise ValueError("compatible collector identity is malformed")
        protocol_id = item.get("protocol_id")
        collector_semantics_id = item.get("collector_semantics_id")
        reason = item.get("reason")
        if not all(
            isinstance(value, str) and value
            for value in (protocol_id, collector_semantics_id, reason)
        ):
            raise ValueError("compatible collector identity is incomplete")
        candidates.append(
            {
                "spec": media_store.collection_cycle_spec(
                    cycle_kind=identity["cycle_kind"],
                    period_key=identity["period_key"],
                    protocol_id=protocol_id,
                    collector_semantics_id=collector_semantics_id,
                    expected_static_slots=static_slots,
                    max_dynamic_slots=identity["max_dynamic_slots"],
                ),
                "compatibility_reason": reason,
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
        "compatibility_reason": candidate["compatibility_reason"],
        "primary": candidate["primary"],
    }


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
                "eligible_lineage": [],
            }
        ), non_x_rows
    if cycle.get("identity_valid") is not True or cycle.get("identity") != spec["identity"]:
        raise ValueError("X collection cycle identity is invalid")

    server_started = cycle.get("server_started_utc")
    server_terminal = cycle.get("server_terminal_utc")
    trusted_terminal = (
        cycle.get("status") in {"complete", "incomplete"}
        and cycle.get("manifest_valid") is True
        and isinstance(server_started, (int, float))
        and not isinstance(server_started, bool)
        and math.isfinite(float(server_started))
        and isinstance(server_terminal, (int, float))
        and not isinstance(server_terminal, bool)
        and math.isfinite(float(server_terminal))
        and float(server_started) <= float(server_terminal) <= cutoff.timestamp()
        and isinstance(cycle.get("collector_build_id"), str)
        and media_store._COLLECTOR_BUILD_ID.fullmatch(cycle["collector_build_id"])
        is not None
    )
    observed_manifest = cycle.get("manifest") if trusted_terminal else None
    if trusted_terminal and (
        not isinstance(observed_manifest, dict)
        or observed_manifest.get("schema_version") != 2
        or observed_manifest.get("server_started_utc") != server_started
        or observed_manifest.get("server_terminal_utc") != server_terminal
        or observed_manifest.get("collector_build_id") != cycle.get("collector_build_id")
    ):
        raise ValueError("X collection cycle manifest omits server/build provenance")
    provenance = {
        **base,
        "collection_cycle_id": expected_cycle_id,
        "manifest_id": cycle.get("manifest_id") if trusted_terminal else None,
        "cycle_manifest": observed_manifest,
        "collector_semantics_id": cycle.get("collector_semantics_id"),
        "collector_build_id": cycle.get("collector_build_id") if trusted_terminal else None,
        "server_started_utc": server_started if trusted_terminal else None,
        "server_terminal_utc": server_terminal if trusted_terminal else None,
    }
    if not trusted_terminal or cycle.get("status") != "complete":
        return _finalize(
            {**provenance, "state": "incomplete", "eligible_lineage": []}
        ), non_x_rows

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

    eligible_rows: list[dict[str, Any]] = []
    eligible_pairs: set[tuple[str, str]] = set()
    for row in candidate_rows:
        if row.get("source") != policy["eligible_source"]:
            continue
        pair = (
            global_research._evidence_id(row),
            global_research._raw_content_id(row),
        )
        if pair in receipt_runs_by_pair and is_formally_eligible_evidence(
            row, as_of_utc=cutoff.timestamp()
        ):
            eligible_rows.append(row)
            eligible_pairs.add(pair)
    eligible_lineage = [
        {
            "evidence_id": evidence_id,
            "raw_content_id": raw_content_id,
            "fetch_run_ids": sorted(receipt_runs_by_pair[(evidence_id, raw_content_id)]),
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
    if selected_cycle is None:
        if (
            availability.get("expected_collection_cycle_id")
            != accepted_cycles[0]["spec"]["collection_cycle_id"]
            or availability.get("collection_cycle_id") is not None
        ):
            raise ValueError("missing X availability names an unexpected cycle")
    elif selected_cycle not in accepted_summaries:
        raise ValueError("X availability selected an unregistered collector identity")
    elif (
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
    lineage = availability.get("eligible_lineage")
    if not isinstance(lineage, list):
        raise ValueError("X availability lineage must be a list")
    lineage_pairs = {
        (item.get("evidence_id"), item.get("raw_content_id"))
        for item in lineage
        if isinstance(item, dict)
        and isinstance(item.get("evidence_id"), str)
        and isinstance(item.get("raw_content_id"), str)
        and isinstance(item.get("fetch_run_ids"), list)
        and all(isinstance(value, str) for value in item["fetch_run_ids"])
    }
    if len(lineage_pairs) != len(lineage):
        raise ValueError("X availability lineage is malformed or duplicated")
    raw_x_pairs = {
        (
            global_research._evidence_id(row),
            global_research._raw_content_id(row),
        )
        for row in raw_evidence
        if row.get("source") == "x"
    }
    if raw_x_pairs != lineage_pairs:
        raise ValueError("snapshot X rows differ from exact-cycle availability lineage")
    if (state == "complete_with_eligible") != bool(lineage_pairs):
        raise ValueError("X availability state disagrees with its eligible lineage")
