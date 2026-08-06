"""Immutable release authorization for the formal forward experiment.

An environment flag is an emergency pause, not authority to start a trial.
This module builds and validates the content-addressed administrative record
that binds a registered run to exact release evidence and container images.
The running paper worker can authenticate its Fly deployment tag locally; the
image digest is attested out of band from the Fly Machines control plane and is
never accepted from a worker-controlled environment variable.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Any

from tradingagents.formal_configuration import validate_release_configuration
from tradingagents.formal_roles import ROLE_SPLIT_CONTRACT_ID
from tradingagents.research_protocol import (
    GLOBAL_EVENT_V2_PROTOCOL,
    GLOBAL_EVENT_V2_PROTOCOL_ID,
    content_id,
    runtime_build_manifest,
)

ACTIVATION_SCHEMA_VERSION = 2
ACTIVATION_TYPE = "formal-trial-release-authorization"
IMAGE_ROLES = ("collector", "paper_decision", "paper_marker")
RELEASE_RECEIPT_TYPES = (
    "configuration",
    "collector_preflight",
    "paper_decision_preflight",
    "paper_marker_preflight",
    "restore_rehearsal",
    "alert_delivery",
    "runtime_role_decommission",
)
FORMAL_MIGRATION_HEAD = "013_formal_runtime_role_split.sql"
RELEASE_EVIDENCE_MAX_AGE_SECONDS = 86_400

_CONTENT_ID = re.compile(r"^[a-z][a-z0-9_]*_[0-9a-f]{24}$")
_OUTCOME_SEMANTICS_ID = re.compile(r"^outcome_semantics_[0-9a-f]{64}$")
_IMAGE_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_FLY_IMAGE_REF = re.compile(
    r"^registry\.fly\.io/"
    r"(?P<app>[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)"
    r":deployment-(?P<deployment>[0-9A-HJKMNP-TV-Z]{26})$"
)
_DIGEST_FINGERPRINT = _IMAGE_DIGEST
_COLLECTION_CYCLE_ID = re.compile(r"^cycle_[0-9a-f]{24}$")
_COLLECTION_CYCLE_MANIFEST_ID = re.compile(r"^cycle_manifest_[0-9a-f]{24}$")
_FORMAL_COLLECTOR_REHEARSAL_KIND = "formal-release-rehearsal-v1"
_FORMAL_COLLECTOR_REHEARSAL_PERIOD = re.compile(
    r"^release-[0-9]{8}T[0-9]{6}\.[0-9]{6}Z$"
)

_COLLECTION_CYCLE_MANIFEST_KEYS = {
    "schema_version",
    "collection_cycle_id",
    "cycle_kind",
    "period_key",
    "protocol_id",
    "collector_semantics_id",
    "collector_build_id",
    "started_utc",
    "completed_utc",
    "server_started_utc",
    "server_terminal_utc",
    "status",
    "expected_static_slots",
    "expected_dynamic_slots",
    "slot_receipts",
}
_COLLECTION_CYCLE_SLOT_KEYS = {"provider", "query_key"}
_COLLECTION_CYCLE_RECEIPT_KEYS = {
    "slot_kind",
    "provider",
    "query_key",
    "fetch_run_id",
    "status",
    "item_count",
    "raw_content_ids",
}
_ALERT_DELIVERY_KEYS = {
    "schema_version",
    "delivery_type",
    "role",
    "delivered",
    "build_id",
    "component_configuration_id",
    "route_fingerprint",
    "client_observed_utc",
    "delivery_id",
}
_MARKER_REPLAY_KEYS = {
    "ok",
    "run_id",
    "decision_date",
    "entry_date",
    "session_date",
    "protocol_id",
    "build_id",
    "outcome_semantics_id",
    "capture_batch_id",
    "return_vector_id",
    "marker_input_id",
    "champion_mark_id",
    "strategy_mark_ids",
    "marks_replayed",
    "strategies_replayed",
    "external_calls",
    "marker_replay_id",
}


class FormalActivationError(ValueError):
    """Raised when release evidence or runtime identity fails closed."""


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FormalActivationError(f"{label} must be an object")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise FormalActivationError(f"{label} has an invalid exact schema")


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise FormalActivationError(f"{label} must be a non-empty canonical string")
    return value


def _content_identifier(value: Any, label: str, *, prefix: str | None = None) -> str:
    normalized = _nonempty(value, label)
    if _CONTENT_ID.fullmatch(normalized) is None:
        raise FormalActivationError(f"{label} must be a content identifier")
    if prefix is not None and not normalized.startswith(prefix):
        raise FormalActivationError(f"{label} has the wrong identifier type")
    return normalized


def _finite_time(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FormalActivationError(f"{label} must be a finite timestamp")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise FormalActivationError(f"{label} must be a finite timestamp")
    return normalized


def _fingerprint(value: Any, label: str) -> str:
    normalized = _nonempty(value, label)
    if _DIGEST_FINGERPRINT.fullmatch(normalized) is None:
        raise FormalActivationError(f"{label} must be a full sha256 fingerprint")
    return normalized


def build_marker_replay_receipt(
    *,
    run_id: str,
    decision_date: str,
    entry_date: str,
    session_date: str,
    protocol_id: str,
    build_id: str,
    outcome_semantics_id: str,
    capture_batch_id: str,
    return_vector_id: str,
    marker_input_id: str,
    champion_mark_id: str,
    strategy_mark_ids: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build the compact identity receipt for a zero-provider marker replay."""

    expected_strategies = list(GLOBAL_EVENT_V2_PROTOCOL["strategies"])
    if not isinstance(strategy_mark_ids, list):
        raise FormalActivationError("marker strategy mark identities must be a list")
    normalized_strategies: list[dict[str, str]] = []
    for index, item in enumerate(strategy_mark_ids):
        row = _object(item, f"marker strategy mark identity[{index}]")
        _exact_keys(
            row,
            {"strategy_id", "mark_id"},
            f"marker strategy mark identity[{index}]",
        )
        normalized_strategies.append(
            {
                "strategy_id": _nonempty(
                    row["strategy_id"], "marker strategy ID"
                ),
                "mark_id": _content_identifier(
                    row["mark_id"], "marker strategy mark ID", prefix="mark_"
                ),
            }
        )
    if [row["strategy_id"] for row in normalized_strategies] != expected_strategies:
        raise FormalActivationError(
            "marker replay did not cover the exact frozen strategy order"
        )
    outcome_id = _nonempty(outcome_semantics_id, "marker outcome semantics ID")
    if _OUTCOME_SEMANTICS_ID.fullmatch(outcome_id) is None:
        raise FormalActivationError("marker outcome semantics ID is malformed")
    base = {
        "ok": True,
        "run_id": _nonempty(run_id, "marker replay run ID"),
        "decision_date": _nonempty(
            decision_date, "marker replay decision date"
        ),
        "entry_date": _nonempty(entry_date, "marker replay entry date"),
        "session_date": _nonempty(session_date, "marker replay session date"),
        "protocol_id": _content_identifier(
            protocol_id, "marker replay protocol ID", prefix="protocol_"
        ),
        "build_id": _build_identifier(build_id, "marker replay build ID"),
        "outcome_semantics_id": outcome_id,
        "capture_batch_id": _content_identifier(
            capture_batch_id,
            "marker replay capture batch ID",
            prefix="capture_batch_",
        ),
        "return_vector_id": _content_identifier(
            return_vector_id,
            "marker replay return vector ID",
            prefix="return_vector_",
        ),
        "marker_input_id": _content_identifier(
            marker_input_id, "marker replay input ID", prefix="marker_input_"
        ),
        "champion_mark_id": _content_identifier(
            champion_mark_id, "marker champion mark ID", prefix="mark_"
        ),
        "strategy_mark_ids": normalized_strategies,
        "marks_replayed": 1 + len(normalized_strategies),
        "strategies_replayed": len(normalized_strategies),
        "external_calls": 0,
    }
    return {**base, "marker_replay_id": content_id(base, prefix="marker_replay_")}


def _validated_marker_replay_receipt(value: Any) -> dict[str, Any]:
    receipt = _object(value, "marker replay receipt")
    _exact_keys(receipt, _MARKER_REPLAY_KEYS, "marker replay receipt")
    if (
        receipt["ok"] is not True
        or receipt["marks_replayed"] != 9
        or receipt["strategies_replayed"] != 8
        or receipt["external_calls"] != 0
    ):
        raise FormalActivationError("marker replay did not verify the frozen experiment")
    rebuilt = build_marker_replay_receipt(
        run_id=receipt["run_id"],
        decision_date=receipt["decision_date"],
        entry_date=receipt["entry_date"],
        session_date=receipt["session_date"],
        protocol_id=receipt["protocol_id"],
        build_id=receipt["build_id"],
        outcome_semantics_id=receipt["outcome_semantics_id"],
        capture_batch_id=receipt["capture_batch_id"],
        return_vector_id=receipt["return_vector_id"],
        marker_input_id=receipt["marker_input_id"],
        champion_mark_id=receipt["champion_mark_id"],
        strategy_mark_ids=receipt["strategy_mark_ids"],
    )
    if dict(receipt) != rebuilt:
        raise FormalActivationError(
            "marker replay receipt is not exact and content-addressed"
        )
    return rebuilt


def _validated_cycle_slots(value: Any, label: str) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise FormalActivationError(f"{label} must be a list")
    normalized: list[dict[str, str]] = []
    for index, item in enumerate(value):
        slot = _object(item, f"{label}[{index}]")
        _exact_keys(slot, _COLLECTION_CYCLE_SLOT_KEYS, f"{label}[{index}]")
        normalized.append({
            "provider": _nonempty(slot["provider"], f"{label}[{index}].provider"),
            "query_key": _nonempty(slot["query_key"], f"{label}[{index}].query_key"),
        })
    if normalized != sorted(normalized, key=lambda row: (row["provider"], row["query_key"])):
        raise FormalActivationError(f"{label} must be canonically ordered")
    if len({(row["provider"], row["query_key"]) for row in normalized}) != len(normalized):
        raise FormalActivationError(f"{label} must not contain duplicates")
    return normalized


def _validated_cycle_receipts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise FormalActivationError("final collection cycle must contain slot receipts")
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        receipt = _object(item, f"final collection cycle receipt[{index}]")
        _exact_keys(
            receipt,
            _COLLECTION_CYCLE_RECEIPT_KEYS,
            f"final collection cycle receipt[{index}]",
        )
        slot_kind = _nonempty(receipt["slot_kind"], "collection cycle slot kind")
        status = _nonempty(receipt["status"], "collection cycle receipt status")
        if slot_kind not in {"static", "dynamic"} or status not in {"success", "empty"}:
            raise FormalActivationError("final collection cycle is not an exact complete pass")
        fetch_run_id = receipt["fetch_run_id"]
        if not isinstance(fetch_run_id, str) or not fetch_run_id:
            raise FormalActivationError("final collection cycle receipt lacks a fetch identity")
        item_count = receipt["item_count"]
        if isinstance(item_count, bool) or not isinstance(item_count, int) or item_count < 0:
            raise FormalActivationError("final collection cycle receipt count is invalid")
        raw_ids = receipt["raw_content_ids"]
        if (
            not isinstance(raw_ids, list)
            or any(not isinstance(item_id, str) or not item_id for item_id in raw_ids)
            or raw_ids != sorted(set(raw_ids))
        ):
            raise FormalActivationError("final collection cycle raw lineage is invalid")
        if status == "empty" and (item_count != 0 or raw_ids):
            raise FormalActivationError("empty collection cycle receipt claims content")
        if status == "success" and (item_count < 1 or len(raw_ids) > item_count):
            raise FormalActivationError("collection cycle receipt count differs from lineage")
        normalized.append({
            "slot_kind": slot_kind,
            "provider": _nonempty(receipt["provider"], "collection cycle provider"),
            "query_key": _nonempty(receipt["query_key"], "collection cycle query key"),
            "fetch_run_id": fetch_run_id,
            "status": status,
            "item_count": item_count,
            "raw_content_ids": list(raw_ids),
        })
    expected_order = sorted(
        normalized,
        key=lambda row: (
            0 if row["slot_kind"] == "static" else 1,
            row["provider"],
            row["query_key"],
        ),
    )
    if normalized != expected_order:
        raise FormalActivationError("final collection cycle receipts are not canonically ordered")
    if len({(row["provider"], row["query_key"]) for row in normalized}) != len(normalized):
        raise FormalActivationError("final collection cycle receipts contain duplicate slots")
    return normalized


def _validated_final_collection_cycle_manifest(value: Any) -> dict[str, Any]:
    manifest = _object(value, "final collection cycle manifest")
    _exact_keys(
        manifest,
        _COLLECTION_CYCLE_MANIFEST_KEYS,
        "final collection cycle manifest",
    )
    if manifest["schema_version"] != 2 or manifest["status"] != "complete":
        raise FormalActivationError("final collection cycle is not a complete v2 manifest")
    cycle_id = _nonempty(manifest["collection_cycle_id"], "collection cycle ID")
    if _COLLECTION_CYCLE_ID.fullmatch(cycle_id) is None:
        raise FormalActivationError("collection cycle ID is malformed")
    started = _finite_time(manifest["started_utc"], "collection cycle start time")
    completed = _finite_time(manifest["completed_utc"], "collection cycle completion time")
    server_started = _finite_time(
        manifest["server_started_utc"], "collection cycle server start time"
    )
    server_terminal = _finite_time(
        manifest["server_terminal_utc"], "collection cycle server terminal time"
    )
    if completed < started or server_terminal < server_started:
        raise FormalActivationError("final collection cycle timestamps are incoherent")
    static_slots = _validated_cycle_slots(
        manifest["expected_static_slots"], "collection cycle static slots"
    )
    dynamic_slots = _validated_cycle_slots(
        manifest["expected_dynamic_slots"], "collection cycle dynamic slots"
    )
    receipts = _validated_cycle_receipts(manifest["slot_receipts"])
    declared = {
        ("static", slot["provider"], slot["query_key"]) for slot in static_slots
    } | {
        ("dynamic", slot["provider"], slot["query_key"]) for slot in dynamic_slots
    }
    observed = {
        (row["slot_kind"], row["provider"], row["query_key"]) for row in receipts
    }
    if not declared or observed != declared:
        raise FormalActivationError("final collection cycle manifest has incomplete slot coverage")
    normalized = {
        "schema_version": 2,
        "collection_cycle_id": cycle_id,
        "cycle_kind": _nonempty(manifest["cycle_kind"], "collection cycle kind"),
        "period_key": _nonempty(manifest["period_key"], "collection cycle period key"),
        "protocol_id": _content_identifier(
            manifest["protocol_id"], "collection cycle protocol ID", prefix="protocol_"
        ),
        "collector_semantics_id": _content_identifier(
            manifest["collector_semantics_id"],
            "collection cycle collector semantics ID",
            prefix="collector_",
        ),
        "collector_build_id": _build_identifier(
            manifest["collector_build_id"], "collection cycle collector build ID"
        ),
        "started_utc": started,
        "completed_utc": completed,
        "server_started_utc": server_started,
        "server_terminal_utc": server_terminal,
        "status": "complete",
        "expected_static_slots": static_slots,
        "expected_dynamic_slots": dynamic_slots,
        "slot_receipts": receipts,
    }
    evidence = GLOBAL_EVENT_V2_PROTOCOL["evidence"]
    expected_static = sorted(
        [
            {"provider": "globalnews", "query_key": f"{theme}:{query}"}
            for theme, queries in evidence["broad_news_queries"].items()
            for query in queries
        ]
        + [
            {"provider": "xtrend", "query_key": f"woeid:{int(woeid)}"}
            for woeid in evidence["x_trend_woeids"]
        ]
        + [
            {
                "provider": "trendnews",
                "query_key": "ranked-global-discovery",
            }
        ],
        key=lambda row: (row["provider"], row["query_key"]),
    )
    max_dynamic = int(evidence["max_x_search_requests_per_utc_day"])
    allowed_empty = set(
        evidence["query_cycle"]["allowed_observed_empty_providers"]
    )
    if (
        normalized["cycle_kind"] != _FORMAL_COLLECTOR_REHEARSAL_KIND
        or _FORMAL_COLLECTOR_REHEARSAL_PERIOD.fullmatch(normalized["period_key"])
        is None
        or normalized["protocol_id"] != GLOBAL_EVENT_V2_PROTOCOL_ID
        or normalized["collector_semantics_id"]
        != evidence["expected_collector_semantics_id"]
        or normalized["expected_static_slots"] != expected_static
        or len(normalized["expected_dynamic_slots"]) > max_dynamic
        or any(
            slot["provider"] != "x"
            for slot in normalized["expected_dynamic_slots"]
        )
    ):
        raise FormalActivationError(
            "final collection cycle differs from the frozen release rehearsal"
        )
    for receipt in normalized["slot_receipts"]:
        provider = receipt["provider"]
        if receipt["status"] == "empty" and provider not in allowed_empty:
            raise FormalActivationError(
                "final collection cycle has a forbidden empty provider"
            )
        if provider == "globalnews" and (
            receipt["slot_kind"] != "static"
            or receipt["status"] != "success"
            or receipt["item_count"] < 1
            or not receipt["raw_content_ids"]
        ):
            raise FormalActivationError(
                "every release-rehearsal global-news slot needs raw success lineage"
            )
        if receipt["status"] == "success" and not receipt["raw_content_ids"]:
            raise FormalActivationError(
                "successful release-rehearsal slots need raw content lineage"
            )
    return normalized


def build_collector_rehearsal_payload(
    *,
    final_collection_cycle_manifest: Mapping[str, Any],
    component_configuration_id: str,
) -> dict[str, Any]:
    """Bind a real, exact collector cycle to its paused runtime configuration."""

    manifest = _validated_final_collection_cycle_manifest(
        final_collection_cycle_manifest
    )
    manifest_id = content_id(manifest, prefix="cycle_manifest_")
    base = {
        "schema_version": 1,
        "evidence_type": "formal-collector-release-rehearsal",
        "passed": True,
        "protocol_id": manifest["protocol_id"],
        "collector_build_id": manifest["collector_build_id"],
        "component_configuration_id": _content_identifier(
            component_configuration_id,
            "collector rehearsal component configuration ID",
            prefix="config_",
        ),
        "collection_cycle_id": manifest["collection_cycle_id"],
        "manifest_id": manifest_id,
        "server_completed_utc": manifest["server_terminal_utc"],
        "manifest": manifest,
    }
    return {
        **base,
        "collector_rehearsal_id": content_id(
            base, prefix="collector_rehearsal_"
        ),
    }


def validate_collector_rehearsal_payload(value: Any) -> dict[str, Any]:
    """Rebuild an exact collector rehearsal and reject hand-edited material."""

    payload = _object(value, "collector rehearsal payload")
    _exact_keys(
        payload,
        {
            "schema_version",
            "evidence_type",
            "passed",
            "protocol_id",
            "collector_build_id",
            "component_configuration_id",
            "collection_cycle_id",
            "manifest_id",
            "server_completed_utc",
            "manifest",
            "collector_rehearsal_id",
        },
        "collector rehearsal payload",
    )
    if (
        payload["schema_version"] != 1
        or payload["evidence_type"] != "formal-collector-release-rehearsal"
        or payload["passed"] is not True
    ):
        raise FormalActivationError("collector rehearsal is not an exact pass")
    rebuilt = build_collector_rehearsal_payload(
        final_collection_cycle_manifest=payload["manifest"],
        component_configuration_id=payload["component_configuration_id"],
    )
    if dict(payload) != rebuilt:
        raise FormalActivationError(
            "collector rehearsal is not exact and content-addressed"
        )
    return rebuilt


def _build_identifier(value: Any, label: str) -> str:
    return _content_identifier(value, label, prefix="build_")


def _validated_runtime_manifest(value: Any, label: str) -> dict[str, Any]:
    manifest = _object(value, label)
    _exact_keys(
        manifest,
        {"schema_version", "platform", "app_name", "image_ref", "deployment_id"},
        label,
    )
    if manifest["schema_version"] != 1 or manifest["platform"] != "fly":
        raise FormalActivationError(f"{label} is not an exact Fly runtime identity")
    app_name = _nonempty(manifest["app_name"], f"{label}.app_name")
    image_ref = _nonempty(manifest["image_ref"], f"{label}.image_ref")
    deployment_id = _nonempty(
        manifest["deployment_id"], f"{label}.deployment_id"
    )
    match = _FLY_IMAGE_REF.fullmatch(image_ref)
    if match is None \
            or match.group("app") != app_name \
            or match.group("deployment") != deployment_id:
        raise FormalActivationError(f"{label} has inconsistent Fly image material")
    return {
        "schema_version": 1,
        "platform": "fly",
        "app_name": app_name,
        "image_ref": image_ref,
        "deployment_id": deployment_id,
    }


def image_attestation(*, app_name: str, image_ref: str, image_digest: str) -> dict:
    """Build one exact Fly image attestation from control-plane material."""
    runtime = _validated_runtime_manifest(
        {
            "schema_version": 1,
            "platform": "fly",
            "app_name": app_name,
            "image_ref": image_ref,
            "deployment_id": image_ref.rsplit("deployment-", 1)[-1],
        },
        "runtime_build_manifest",
    )
    digest = _nonempty(image_digest, "image_digest")
    if _IMAGE_DIGEST.fullmatch(digest) is None:
        raise FormalActivationError("image_digest must be a full sha256 digest")
    return {
        "schema_version": 1,
        "app_name": runtime["app_name"],
        "image_ref": runtime["image_ref"],
        "image_digest": digest,
        "build_id": content_id(runtime, prefix="build_"),
        "runtime_build_manifest": runtime,
    }


def validate_image_attestation(value: Any, label: str = "image") -> dict:
    """Validate and normalize one image attestation without trusting its build ID."""
    image = _object(value, label)
    _exact_keys(
        image,
        {
            "schema_version",
            "app_name",
            "image_ref",
            "image_digest",
            "build_id",
            "runtime_build_manifest",
        },
        label,
    )
    if image["schema_version"] != 1:
        raise FormalActivationError(f"{label} has an unsupported schema version")
    runtime = _validated_runtime_manifest(
        image["runtime_build_manifest"], f"{label}.runtime_build_manifest"
    )
    app_name = _nonempty(image["app_name"], f"{label}.app_name")
    image_ref = _nonempty(image["image_ref"], f"{label}.image_ref")
    digest = _nonempty(image["image_digest"], f"{label}.image_digest")
    build_id = _build_identifier(image["build_id"], f"{label}.build_id")
    if _IMAGE_DIGEST.fullmatch(digest) is None:
        raise FormalActivationError(f"{label}.image_digest is not a full sha256 digest")
    expected_build = content_id(runtime, prefix="build_")
    if app_name != runtime["app_name"] \
            or image_ref != runtime["image_ref"] \
            or build_id != expected_build:
        raise FormalActivationError(f"{label} does not bind one exact runtime image")
    return {
        "schema_version": 1,
        "app_name": app_name,
        "image_ref": image_ref,
        "image_digest": digest,
        "build_id": build_id,
        "runtime_build_manifest": runtime,
    }


def build_runtime_preflight_payload(
    *,
    role: str,
    build_id: str,
    component_configuration_id: str,
    outcome_semantics_id: str | None = None,
) -> dict:
    """Bind a successful in-image preflight to exact executable settings."""
    if role not in IMAGE_ROLES:
        raise FormalActivationError("preflight role is not allowed")
    base: dict[str, Any] = {
        "role": role,
        "runtime_ready": True,
        "build_id": _build_identifier(build_id, "preflight build ID"),
        "component_configuration_id": _content_identifier(
            component_configuration_id,
            "preflight component configuration ID",
            prefix="config_",
        ),
    }
    if role == "collector":
        if outcome_semantics_id is not None:
            raise FormalActivationError(
                "collector preflight must not claim outcome semantics"
            )
    else:
        outcome_id = _nonempty(
            outcome_semantics_id, "preflight outcome semantics ID"
        )
        if _OUTCOME_SEMANTICS_ID.fullmatch(outcome_id) is None:
            raise FormalActivationError(
                "preflight outcome_semantics_id is not an exact executable identity"
            )
        base["outcome_semantics_id"] = outcome_id
    return {
        **base,
        "preflight_manifest_id": content_id(base, prefix="preflight_"),
    }


def build_restore_rehearsal_payload(
    *,
    source_cluster_fingerprint: str,
    restored_cluster_fingerprint: str,
    backup_fingerprint: str,
    backup_completed_utc: float,
    collector_rehearsal: Mapping[str, Any],
    formal_trial_activity_rows: int,
    verification_completed_utc: float,
    migration_head: str = FORMAL_MIGRATION_HEAD,
    role_contract_id: str = ROLE_SPLIT_CONTRACT_ID,
) -> dict[str, Any]:
    """Build exact non-secret restore evidence for later administrator release.

    The clone inspector supplies the zero-activity count and database-observed
    verification time. The caller obtains cluster and backup fingerprints from
    its control planes. Content addressing detects mutation and the production
    database later binds the cycle to its immutable row; neither mechanism is a
    signature from the external backup provider.
    """

    source_fingerprint = _fingerprint(
        source_cluster_fingerprint, "source cluster fingerprint"
    )
    restored_fingerprint = _fingerprint(
        restored_cluster_fingerprint, "restored cluster fingerprint"
    )
    if source_fingerprint == restored_fingerprint:
        raise FormalActivationError("restore rehearsal must use an isolated cluster")
    backup_digest = _fingerprint(backup_fingerprint, "backup fingerprint")
    backup_time = _finite_time(backup_completed_utc, "backup completion time")
    verification_time = _finite_time(
        verification_completed_utc, "restore verification completion time"
    )
    collector = validate_collector_rehearsal_payload(collector_rehearsal)
    manifest = collector["manifest"]
    manifest_id = collector["manifest_id"]
    if not manifest["server_terminal_utc"] <= backup_time <= verification_time:
        raise FormalActivationError(
            "restore evidence must order collection, backup, then verification"
        )
    backup_base = {
        "schema_version": 1,
        "backup_type": "formal-production-database-backup",
        "source_cluster_fingerprint": source_fingerprint,
        "backup_fingerprint": backup_digest,
        "completed_utc": backup_time,
        "final_collection_cycle_id": manifest["collection_cycle_id"],
        "final_collection_cycle_manifest_id": manifest_id,
        "collector_rehearsal_id": collector["collector_rehearsal_id"],
    }
    backup = {**backup_base, "backup_id": content_id(backup_base, prefix="backup_")}
    migration = _nonempty(migration_head, "restore migration head")
    contract = _content_identifier(
        role_contract_id, "restore role contract ID", prefix="role_contract_"
    )
    if migration != FORMAL_MIGRATION_HEAD or contract != ROLE_SPLIT_CONTRACT_ID:
        raise FormalActivationError("restore rehearsal used a drifted schema or role contract")
    if (
        isinstance(formal_trial_activity_rows, bool)
        or not isinstance(formal_trial_activity_rows, int)
        or formal_trial_activity_rows != 0
    ):
        raise FormalActivationError(
            "preauthorization restore must contain zero formal trial activity rows"
        )
    verification_base = {
        "schema_version": 1,
        "verification_type": (
            "formal-restored-cluster-initial-empty-trial-check"
        ),
        "passed": True,
        "restored_cluster_fingerprint": restored_fingerprint,
        "backup_id": backup["backup_id"],
        "migration_head": migration,
        "role_contract_id": contract,
        "formal_trial_activity_rows": formal_trial_activity_rows,
        "external_calls": 0,
        "completed_utc": verification_time,
    }
    verification = {
        **verification_base,
        "verification_id": content_id(verification_base, prefix="verification_"),
    }
    base = {
        "schema_version": 4,
        "evidence_type": "formal-restore-rehearsal",
        "passed": True,
        "backup": backup,
        "collector_rehearsal": collector,
        "verification": verification,
    }
    return {**base, "rehearsal_manifest_id": content_id(base, prefix="rehearsal_")}


def validate_restore_rehearsal_payload(value: Any) -> dict[str, Any]:
    """Rebuild one exact restore payload and reject every unbound field."""

    payload = _object(value, "restore rehearsal payload")
    _exact_keys(
        payload,
        {
            "schema_version",
            "evidence_type",
            "passed",
            "backup",
            "collector_rehearsal",
            "verification",
            "rehearsal_manifest_id",
        },
        "restore rehearsal payload",
    )
    if (
        payload["schema_version"] != 4
        or payload["evidence_type"] != "formal-restore-rehearsal"
        or payload["passed"] is not True
    ):
        raise FormalActivationError("restore rehearsal is not an exact v4 pass")
    backup = _object(payload["backup"], "restore backup")
    _exact_keys(
        backup,
        {
            "schema_version",
            "backup_type",
            "source_cluster_fingerprint",
            "backup_fingerprint",
            "completed_utc",
            "final_collection_cycle_id",
            "final_collection_cycle_manifest_id",
            "collector_rehearsal_id",
            "backup_id",
        },
        "restore backup",
    )
    collector = validate_collector_rehearsal_payload(
        payload["collector_rehearsal"]
    )
    verification = _object(payload["verification"], "restore verification")
    _exact_keys(
        verification,
        {
            "schema_version",
            "verification_type",
            "passed",
            "restored_cluster_fingerprint",
            "backup_id",
            "migration_head",
            "role_contract_id",
            "formal_trial_activity_rows",
            "external_calls",
            "completed_utc",
            "verification_id",
        },
        "restore verification",
    )
    rebuilt = build_restore_rehearsal_payload(
        source_cluster_fingerprint=backup["source_cluster_fingerprint"],
        restored_cluster_fingerprint=verification["restored_cluster_fingerprint"],
        backup_fingerprint=backup["backup_fingerprint"],
        backup_completed_utc=backup["completed_utc"],
        collector_rehearsal=collector,
        formal_trial_activity_rows=verification["formal_trial_activity_rows"],
        verification_completed_utc=verification["completed_utc"],
        migration_head=verification["migration_head"],
        role_contract_id=verification["role_contract_id"],
    )
    if dict(payload) != rebuilt:
        raise FormalActivationError("restore rehearsal is not exact and content-addressed")
    return rebuilt


def build_alert_delivery_receipt(
    *,
    role: str,
    build_id: str,
    component_configuration_id: str,
    route_fingerprint: str,
    client_observed_utc: float,
) -> dict[str, Any]:
    """Build one non-secret runtime-specific alert transport receipt.

    ``client_observed_utc`` is intentionally not presented as a provider-signed
    observation. It can enforce recency but cannot authenticate the provider.
    """

    if role not in IMAGE_ROLES:
        raise FormalActivationError("alert delivery role is not allowed")
    base = {
        "schema_version": 1,
        "delivery_type": "formal-runtime-alert-delivery",
        "role": role,
        "delivered": True,
        "build_id": _build_identifier(build_id, "alert delivery build ID"),
        "component_configuration_id": _content_identifier(
            component_configuration_id,
            "alert delivery component configuration ID",
            prefix="config_",
        ),
        "route_fingerprint": _fingerprint(
            route_fingerprint, "alert delivery route fingerprint"
        ),
        "client_observed_utc": _finite_time(
            client_observed_utc, "alert delivery client observation time"
        ),
    }
    return {**base, "delivery_id": content_id(base, prefix="alert_delivery_")}


def _validated_alert_delivery_receipt(value: Any, *, expected_role: str) -> dict[str, Any]:
    receipt = _object(value, f"{expected_role} alert delivery")
    _exact_keys(receipt, _ALERT_DELIVERY_KEYS, f"{expected_role} alert delivery")
    if (
        receipt["schema_version"] != 1
        or receipt["delivery_type"] != "formal-runtime-alert-delivery"
        or receipt["role"] != expected_role
        or receipt["delivered"] is not True
    ):
        raise FormalActivationError("alert delivery receipt is not an exact pass")
    rebuilt = build_alert_delivery_receipt(
        role=expected_role,
        build_id=receipt["build_id"],
        component_configuration_id=receipt["component_configuration_id"],
        route_fingerprint=receipt["route_fingerprint"],
        client_observed_utc=receipt["client_observed_utc"],
    )
    if dict(receipt) != rebuilt:
        raise FormalActivationError("alert delivery receipt is not content-addressed")
    return rebuilt


def build_alert_delivery_payload(*, deliveries: Mapping[str, Any]) -> dict[str, Any]:
    """Aggregate exactly one delivery from each released runtime."""

    delivery_documents = _object(deliveries, "alert deliveries")
    _exact_keys(delivery_documents, set(IMAGE_ROLES), "alert deliveries")
    normalized = {
        role: _validated_alert_delivery_receipt(
            delivery_documents[role], expected_role=role
        )
        for role in IMAGE_ROLES
    }
    route_fingerprints = {
        receipt["route_fingerprint"] for receipt in normalized.values()
    }
    if len(route_fingerprints) != 1:
        raise FormalActivationError("alert deliveries do not share one exact route")
    base = {
        "schema_version": 2,
        "evidence_type": "formal-alert-delivery",
        "delivered": True,
        "route_fingerprint": route_fingerprints.pop(),
        "deliveries": normalized,
    }
    return {**base, "alert_delivery_id": content_id(base, prefix="alert_")}


def validate_alert_delivery_payload(value: Any) -> dict[str, Any]:
    """Rebuild one exact three-runtime alert-delivery aggregate."""

    payload = _object(value, "alert delivery payload")
    _exact_keys(
        payload,
        {
            "schema_version",
            "evidence_type",
            "delivered",
            "route_fingerprint",
            "deliveries",
            "alert_delivery_id",
        },
        "alert delivery payload",
    )
    if (
        payload["schema_version"] != 2
        or payload["evidence_type"] != "formal-alert-delivery"
        or payload["delivered"] is not True
    ):
        raise FormalActivationError("alert delivery aggregate is not an exact v2 pass")
    rebuilt = build_alert_delivery_payload(deliveries=payload["deliveries"])
    if dict(payload) != rebuilt:
        raise FormalActivationError("alert delivery aggregate is not exact and content-addressed")
    return rebuilt


def _validated_release_payload(receipt_type: str, value: Any) -> dict:
    payload = _object(value, f"{receipt_type} payload")
    if receipt_type == "configuration":
        return validate_release_configuration(payload)
    if receipt_type in {
        "collector_preflight",
        "paper_decision_preflight",
        "paper_marker_preflight",
    }:
        role = receipt_type.removesuffix("_preflight")
        expected_keys = {
            "role",
            "runtime_ready",
            "preflight_manifest_id",
            "build_id",
            "component_configuration_id",
        }
        if role != "collector":
            expected_keys.add("outcome_semantics_id")
        _exact_keys(payload, expected_keys, f"{receipt_type} payload")
        if payload["role"] != role or payload["runtime_ready"] is not True:
            raise FormalActivationError(f"{receipt_type} did not pass for its exact role")
        rebuilt = build_runtime_preflight_payload(
            role=role,
            build_id=payload["build_id"],
            component_configuration_id=payload["component_configuration_id"],
            outcome_semantics_id=payload.get("outcome_semantics_id"),
        )
        if payload["preflight_manifest_id"] != rebuilt["preflight_manifest_id"]:
            raise FormalActivationError(f"{receipt_type} is not content-addressed")
        return rebuilt
    if receipt_type == "restore_rehearsal":
        return validate_restore_rehearsal_payload(payload)
    if receipt_type == "alert_delivery":
        return validate_alert_delivery_payload(payload)
    if receipt_type == "runtime_role_decommission":
        _exact_keys(
            payload,
            {
                "passed",
                "decommission_id",
                "legacy_role",
                "decision_role",
                "marker_role",
            },
            "runtime role decommission payload",
        )
        if payload["passed"] is not True \
                or payload["legacy_role"] != "tradingagents-paper" \
                or payload["decision_role"] != "tradingagents-paper-decision" \
                or payload["marker_role"] != "tradingagents-paper-marker":
            raise FormalActivationError("runtime role split was not exactly decommissioned")
        return {
            "passed": True,
            "decommission_id": _content_identifier(
                payload["decommission_id"],
                "runtime role decommission ID",
                prefix="decommission_",
            ),
            "legacy_role": "tradingagents-paper",
            "decision_role": "tradingagents-paper-decision",
            "marker_role": "tradingagents-paper-marker",
        }
    raise FormalActivationError("release receipt type is not allowed")


def build_release_receipt(
    *, receipt_type: str, protocol_id: str, run_id: str, payload: Mapping[str, Any]
) -> dict:
    """Build a content-addressed release receipt for administrator insertion."""
    if receipt_type not in RELEASE_RECEIPT_TYPES:
        raise FormalActivationError("release receipt type is not allowed")
    normalized_protocol_id = _content_identifier(
        protocol_id, "protocol_id", prefix="protocol_"
    )
    normalized_run_id = _nonempty(run_id, "run_id")
    normalized_payload = _validated_release_payload(receipt_type, payload)
    if receipt_type == "configuration":
        components = (
            normalized_payload["collector_configuration"],
            normalized_payload["paper_decision_configuration"],
            normalized_payload["paper_marker_configuration"],
        )
        if any(
            component["protocol_id"] != normalized_protocol_id
            for component in components
        ) or any(
            normalized_payload[key]["settings"]["run_id"] != normalized_run_id
            for key in (
                "paper_decision_configuration",
                "paper_marker_configuration",
            )
        ):
            raise FormalActivationError(
                "configuration release differs from its protocol or run"
            )
    if (
        receipt_type == "restore_rehearsal"
        and normalized_payload["collector_rehearsal"]["manifest"]["protocol_id"]
        != normalized_protocol_id
    ):
        raise FormalActivationError(
            "restore collection cycle differs from its release protocol"
        )
    base = {
        "schema_version": 1,
        "receipt_type": receipt_type,
        "protocol_id": normalized_protocol_id,
        "run_id": normalized_run_id,
        "payload": normalized_payload,
    }
    return {**base, "receipt_id": content_id(base, prefix="release_")}


def validate_release_receipt(value: Any) -> dict:
    """Validate an exact release receipt and recompute its identifier."""
    receipt = _object(value, "release receipt")
    _exact_keys(
        receipt,
        {"schema_version", "receipt_type", "protocol_id", "run_id", "payload", "receipt_id"},
        "release receipt",
    )
    if receipt["schema_version"] != 1:
        raise FormalActivationError("release receipt has an unsupported schema version")
    rebuilt = build_release_receipt(
        receipt_type=_nonempty(receipt["receipt_type"], "release receipt type"),
        protocol_id=receipt["protocol_id"],
        run_id=receipt["run_id"],
        payload=receipt["payload"],
    )
    if receipt["receipt_id"] != rebuilt["receipt_id"]:
        raise FormalActivationError("release receipt is not content-addressed")
    return rebuilt


def build_trial_authorization(
    *,
    protocol_id: str,
    run_id: str,
    registration_id: str,
    outcome_semantics_id: str,
    configuration_binding: Mapping[str, str],
    collector_image: Mapping[str, Any],
    paper_decision_image: Mapping[str, Any],
    paper_marker_image: Mapping[str, Any],
    release_receipt_ids: Mapping[str, str],
) -> dict:
    """Build the sole immutable authorization capable of starting a formal run."""
    receipt_ids = _object(release_receipt_ids, "release_receipt_ids")
    _exact_keys(receipt_ids, set(RELEASE_RECEIPT_TYPES), "release_receipt_ids")
    outcome_id = _nonempty(outcome_semantics_id, "outcome_semantics_id")
    if _OUTCOME_SEMANTICS_ID.fullmatch(outcome_id) is None:
        raise FormalActivationError("outcome_semantics_id is not an exact executable identity")
    images = {
        "collector": validate_image_attestation(collector_image, "collector image"),
        "paper_decision": validate_image_attestation(
            paper_decision_image, "paper decision image"
        ),
        "paper_marker": validate_image_attestation(
            paper_marker_image, "paper marker image"
        ),
    }
    if len({image["app_name"] for image in images.values()}) != len(IMAGE_ROLES):
        raise FormalActivationError("formal runtimes must be distinct Fly applications")
    configurations = _object(configuration_binding, "configuration_binding")
    _exact_keys(
        configurations,
        {
            "configuration_manifest_id",
            "collector_configuration_id",
            "paper_decision_configuration_id",
            "paper_marker_configuration_id",
        },
        "configuration_binding",
    )
    base = {
        "schema_version": ACTIVATION_SCHEMA_VERSION,
        "authorization_type": ACTIVATION_TYPE,
        "protocol_id": _content_identifier(protocol_id, "protocol_id", prefix="protocol_"),
        "run_id": _nonempty(run_id, "run_id"),
        "registration_id": _content_identifier(
            registration_id, "registration_id", prefix="registration_"
        ),
        "outcome_semantics_id": outcome_id,
        "configuration_binding": {
            key: _content_identifier(
                configurations[key], f"configuration_binding.{key}", prefix="config_"
            )
            for key in sorted(configurations)
        },
        "images": images,
        "release_receipt_ids": {
            receipt_type: _content_identifier(
                receipt_ids[receipt_type],
                f"release_receipt_ids.{receipt_type}",
                prefix="release_",
            )
            for receipt_type in RELEASE_RECEIPT_TYPES
        },
    }
    return {**base, "authorization_id": content_id(base, prefix="activation_")}


def validate_trial_authorization(value: Any) -> dict:
    """Validate and normalize one formal release authorization."""
    authorization = _object(value, "trial authorization")
    _exact_keys(
        authorization,
        {
            "schema_version",
            "authorization_type",
            "protocol_id",
            "run_id",
            "registration_id",
            "outcome_semantics_id",
            "configuration_binding",
            "images",
            "release_receipt_ids",
            "authorization_id",
        },
        "trial authorization",
    )
    if authorization["schema_version"] != ACTIVATION_SCHEMA_VERSION \
            or authorization["authorization_type"] != ACTIVATION_TYPE:
        raise FormalActivationError("trial authorization has an unsupported contract")
    images = _object(authorization["images"], "trial authorization images")
    _exact_keys(images, set(IMAGE_ROLES), "trial authorization images")
    rebuilt = build_trial_authorization(
        protocol_id=authorization["protocol_id"],
        run_id=authorization["run_id"],
        registration_id=authorization["registration_id"],
        outcome_semantics_id=authorization["outcome_semantics_id"],
        configuration_binding=authorization["configuration_binding"],
        collector_image=images["collector"],
        paper_decision_image=images["paper_decision"],
        paper_marker_image=images["paper_marker"],
        release_receipt_ids=authorization["release_receipt_ids"],
    )
    if authorization["authorization_id"] != rebuilt["authorization_id"]:
        raise FormalActivationError("trial authorization is not content-addressed")
    return rebuilt


def require_runtime_authorization(
    authorization: Mapping[str, Any],
    *,
    role: str,
    outcome_semantics_id: str,
    component_configuration_id: str,
    env: Mapping[str, str] | None = None,
) -> str:
    """Authenticate the current runtime against a durable authorization.

    This check deliberately does not accept an image digest argument. The digest
    is authenticated by the administrative release process using the control
    plane, while a Fly worker can authenticate only its platform-provided tag.
    """
    if role not in IMAGE_ROLES:
        raise FormalActivationError("runtime role is not authorized")
    normalized = validate_trial_authorization(authorization)
    current_runtime = runtime_build_manifest(env)
    if current_runtime is None or current_runtime.get("platform") != "fly":
        raise FormalActivationError("formal runtime requires a Fly-provided image identity")
    expected_image = normalized["images"][role]
    if current_runtime != expected_image["runtime_build_manifest"] \
            or content_id(current_runtime, prefix="build_") != expected_image["build_id"]:
        raise FormalActivationError("runtime image is not the authorized deployment")
    if outcome_semantics_id != normalized["outcome_semantics_id"]:
        raise FormalActivationError("runtime outcome semantics differ from authorization")
    config_id = _content_identifier(
        component_configuration_id,
        "component_configuration_id",
        prefix="config_",
    )
    # The configuration receipt is also checked against this identifier by the
    # database authorization trigger. This local comparison prevents an exact
    # authorized image from starting with drifted settings.
    if config_id != normalized["configuration_binding"][f"{role}_configuration_id"]:
        raise FormalActivationError("runtime configuration is not authorized")
    return normalized["authorization_id"]
