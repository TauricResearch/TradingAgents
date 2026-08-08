"""Shared structural validation for immutable daily X collection cycles."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from datetime import date, datetime, time, timezone
from typing import Literal

XCycleState = Literal["missing", "running", "complete", "incomplete", "invalid"]

_BUILD_ID = re.compile(r"build_[0-9a-f]{24}")
_FETCH_ID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
)
_RAW_ID = re.compile(r"raw_[0-9a-f]{24}")
_PERIOD_KEY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_SPEC_KEYS = {"collection_cycle_id", "identity"}
_IDENTITY_KEYS = {
    "schema_version",
    "cycle_kind",
    "period_key",
    "protocol_id",
    "collector_semantics_id",
    "expected_static_slots",
    "max_dynamic_slots",
}
_TERMINAL_MANIFEST_KEYS = {
    "schema_version",
    "collection_cycle_id",
    "cycle_kind",
    "period_key",
    "protocol_id",
    "collector_semantics_id",
    "started_utc",
    "completed_utc",
    "status",
    "expected_static_slots",
    "expected_dynamic_slots",
    "slot_receipts",
    "server_started_utc",
    "server_terminal_utc",
    "collector_build_id",
}
_SLOT_KEYS = {"provider", "query_key"}
_RECEIPT_KEYS = {
    "slot_kind",
    "provider",
    "query_key",
    "fetch_run_id",
    "status",
    "item_count",
    "raw_content_ids",
}


def _finite_number(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(float(value))
    except (OverflowError, ValueError):
        return False


def _utc_period_bounds(period_key: object) -> tuple[float, float] | None:
    if not isinstance(period_key, str) or _PERIOD_KEY.fullmatch(period_key) is None:
        return None
    try:
        period = date.fromisoformat(period_key)
    except ValueError:
        return None
    if period.isoformat() != period_key:
        return None
    start = datetime.combine(period, time.min, tzinfo=timezone.utc).timestamp()
    return start, start + 86400.0


def _content_id(prefix: str, payload: Mapping[str, object]) -> str:
    payload = json.dumps(
        dict(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return prefix + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _exact_slot(slot: object) -> tuple[str, str] | None:
    if (
        not isinstance(slot, Mapping)
        or set(slot) != _SLOT_KEYS
        or not isinstance(slot.get("provider"), str)
        or not slot["provider"]
        or not isinstance(slot.get("query_key"), str)
        or not slot["query_key"]
    ):
        return None
    return slot["provider"], slot["query_key"]


def x_cycle_structural_state(
    spec: Mapping[str, object], cycle: Mapping[str, object] | None,
) -> XCycleState:
    """Classify one exact X cycle using only authenticated stored structure."""
    if not isinstance(spec, Mapping):
        return "invalid"
    identity = spec.get("identity")
    if (
        set(spec) != _SPEC_KEYS
        or not isinstance(identity, Mapping)
        or set(identity) != _IDENTITY_KEYS
        or identity.get("schema_version") != 1
        or identity.get("cycle_kind") != "x-daily"
        or any(
            not isinstance(identity.get(key), str) or not identity[key]
            for key in ("period_key", "protocol_id", "collector_semantics_id")
        )
    ):
        return "invalid"
    static_slots = identity.get("expected_static_slots")
    max_dynamic_slots = identity.get("max_dynamic_slots")
    period_bounds = _utc_period_bounds(identity.get("period_key"))
    if (
        not isinstance(static_slots, list)
        or not static_slots
        or period_bounds is None
        or isinstance(max_dynamic_slots, bool)
        or not isinstance(max_dynamic_slots, int)
        or not 0 <= max_dynamic_slots <= 100
    ):
        return "invalid"
    parsed_static = [_exact_slot(slot) for slot in static_slots]
    if (
        any(slot is None for slot in parsed_static)
        or len(parsed_static) != len(set(parsed_static))
        or parsed_static != sorted(parsed_static)
    ):
        return "invalid"
    cycle_id = spec.get("collection_cycle_id")
    if (
        not isinstance(cycle_id, str)
        or cycle_id != _content_id("cycle_", identity)
    ):
        return "invalid"
    if cycle is None:
        return "missing"
    if (
        cycle.get("identity_valid") is not True
        or cycle.get("identity") != identity
        or cycle.get("collection_cycle_id") != spec.get("collection_cycle_id")
        or any(
            cycle.get(key) != identity.get(key)
            for key in (
                "cycle_kind",
                "period_key",
                "protocol_id",
                "collector_semantics_id",
            )
        )
    ):
        return "invalid"
    server_started = cycle.get("server_started_utc")
    started = cycle.get("started_utc")
    build_id = cycle.get("collector_build_id")
    if (
        not _finite_number(server_started)
        or not _finite_number(started)
        or not period_bounds[0] <= float(server_started) < period_bounds[1]
        or not isinstance(build_id, str)
        or _BUILD_ID.fullmatch(build_id) is None
    ):
        return "invalid"

    status = cycle.get("status")
    if status == "running":
        return "running" if all(
            cycle.get(key) is None
            for key in (
                "completed_utc",
                "server_terminal_utc",
                "manifest_id",
                "manifest",
            )
        ) else "invalid"
    if status not in {"complete", "incomplete"}:
        return "invalid"
    manifest = cycle.get("manifest")
    if (
        cycle.get("manifest_valid") is not True
        or not isinstance(manifest, Mapping)
        or set(manifest) != _TERMINAL_MANIFEST_KEYS
        or manifest.get("schema_version") != 2
        or cycle.get("manifest_id") != _content_id("cycle_manifest_", manifest)
    ):
        return "invalid"

    completed = cycle.get("completed_utc")
    server_terminal = cycle.get("server_terminal_utc")
    if (
        not _finite_number(started)
        or not _finite_number(completed)
        or float(started) > float(completed)
        or not _finite_number(server_terminal)
        or float(server_started) > float(server_terminal)
        or not period_bounds[0] <= float(server_terminal) < period_bounds[1]
    ):
        return "invalid"
    expected_manifest = {
        "collection_cycle_id": spec["collection_cycle_id"],
        "cycle_kind": identity.get("cycle_kind"),
        "period_key": identity.get("period_key"),
        "protocol_id": identity.get("protocol_id"),
        "collector_semantics_id": identity.get("collector_semantics_id"),
        "started_utc": started,
        "completed_utc": completed,
        "status": status,
        "expected_static_slots": identity.get("expected_static_slots"),
        "server_started_utc": server_started,
        "server_terminal_utc": server_terminal,
        "collector_build_id": build_id,
    }
    if any(manifest.get(key) != value for key, value in expected_manifest.items()):
        return "invalid"

    dynamic_slots = manifest.get("expected_dynamic_slots")
    receipts = manifest.get("slot_receipts")
    if (
        not isinstance(dynamic_slots, list)
        or not isinstance(receipts, list)
        or len(dynamic_slots) > max_dynamic_slots
    ):
        return "invalid"
    parsed_dynamic = [_exact_slot(slot) for slot in dynamic_slots]
    if any(slot is None or slot[0] != "x" for slot in parsed_dynamic):
        return "invalid"
    expected_slots = [*parsed_static, *parsed_dynamic]
    if (
        parsed_dynamic != sorted(parsed_dynamic)
        or len(expected_slots) != len(set(expected_slots))
    ):
        return "invalid"

    receipt_slots: list[tuple[str, str]] = []
    receipt_statuses: list[str] = []
    fetch_run_ids: list[str] = []
    successful_trends: set[tuple[str, str]] = set()
    static_set = set(parsed_static)
    for receipt in receipts:
        if not isinstance(receipt, Mapping) or set(receipt) != _RECEIPT_KEYS:
            return "invalid"
        slot = _exact_slot({key: receipt.get(key) for key in _SLOT_KEYS})
        receipt_status = receipt.get("status")
        raw_ids = receipt.get("raw_content_ids")
        item_count = receipt.get("item_count")
        if (
            slot is None
            or receipt.get("slot_kind")
            != ("static" if slot in static_set else "dynamic")
            or receipt_status not in {"success", "empty", "failed", "missing"}
            or not isinstance(raw_ids, list)
            or any(
                not isinstance(raw_id, str) or _RAW_ID.fullmatch(raw_id) is None
                for raw_id in raw_ids
            )
            or raw_ids != sorted(set(raw_ids))
            or (
                item_count is not None
                and (
                    isinstance(item_count, bool)
                    or not isinstance(item_count, int)
                    or item_count < 0
                )
            )
        ):
            return "invalid"
        fetch_run_id = receipt.get("fetch_run_id")
        if receipt_status == "missing":
            if fetch_run_id is not None or item_count is not None or raw_ids:
                return "invalid"
        else:
            if (
                not isinstance(fetch_run_id, str)
                or _FETCH_ID.fullmatch(fetch_run_id) is None
                or isinstance(item_count, bool)
                or not isinstance(item_count, int)
            ):
                return "invalid"
            if (
                receipt_status == "success" and item_count < 1
            ) or (
                receipt_status in {"empty", "failed"} and item_count != 0
            ):
                return "invalid"
        receipt_slots.append(slot)
        receipt_statuses.append(receipt_status)
        if fetch_run_id is not None:
            fetch_run_ids.append(fetch_run_id)
        if slot[0] == "xtrend" and receipt_status == "success":
            successful_trends.add(slot)
    if (
        len(receipt_slots) != len(set(receipt_slots))
        or len(fetch_run_ids) != len(set(fetch_run_ids))
        or receipt_slots != expected_slots
    ):
        return "invalid"
    derived_status = (
        "complete"
        if all(value in {"success", "empty"} for value in receipt_statuses)
        else "incomplete"
    )
    if derived_status != status:
        return "invalid"
    required_trends = {slot for slot in static_set if slot[0] == "xtrend"}
    if successful_trends != required_trends:
        return "incomplete"
    return status
