"""Administrator-only formal trial bootstrap and release orchestration.

The release inputs are offline JSON evidence produced by the three paused
runtime images, the Fly Machines control plane, the restore rehearsal, and the
alert-delivery check.  This module never invokes Fly or a provider.  It builds
all content-addressed documents locally, preregisters the paused trial through
the existing bootstrap, and commits the irreversible role decommission plus
the seven receipts and authorization in one PostgreSQL transaction.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from tradingagents.formal_activation import (
    IMAGE_ROLES,
    RELEASE_RECEIPT_TYPES,
    build_release_receipt,
    build_runtime_preflight_payload,
    build_trial_authorization,
    image_attestation,
    validate_image_attestation,
    validate_release_receipt,
    validate_trial_authorization,
)
from tradingagents.formal_configuration import (
    build_release_configuration,
    validate_component_configuration,
    validate_release_configuration,
)
from tradingagents.formal_experiment import (
    bootstrap_formal_trial,
    formal_decision_semantics,
    formal_run_configuration,
    formal_trial_registration,
)
from tradingagents.formal_roles import (
    build_legacy_role_decommission_receipt,
    is_formal_schema_admin_identity,
    runtime_role_decommission_release_payload,
)
from tradingagents.outcome_semantics import (
    outcome_semantics_id,
    require_outcome_semantics,
)
from tradingagents.research_protocol import (
    GLOBAL_EVENT_V2_PROTOCOL,
    GLOBAL_EVENT_V2_PROTOCOL_ID,
    canonical_json,
)

_FLY_DEPLOYMENT_REF = re.compile(
    r"^registry\.fly\.io/"
    r"(?P<app>[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)"
    r":deployment-(?P<deployment>[0-9A-HJKMNP-TV-Z]{26})$"
)
_IMAGE_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_EXPECTED_FLY_APPS = {
    "collector": "tradagent",
    "paper_decision": "tradagent-paper-decision",
    "paper_marker": "tradagent-paper-marker",
}
_RUNTIME_MATERIAL_KEYS = frozenset({"component_configuration", "preflight_payload"})
_BOOTSTRAP_RESULT_KEYS = frozenset(
    {
        "run_id",
        "protocol_id",
        "registration_id",
        "outcome_semantics_id",
        "configuration_binding",
        "provider_calls",
        "trial_authorized",
    }
)


class FormalReleaseError(RuntimeError):
    """Release evidence, database state, or administrator authority drifted."""


@dataclass(frozen=True)
class FormalReleasePlan:
    """Fully validated release documents; payloads are never CLI output."""

    release_configuration: dict[str, Any]
    images: dict[str, dict[str, Any]]
    receipts: dict[str, dict[str, Any]]
    authorization: dict[str, Any]
    decommission_receipt: dict[str, Any]
    run_config: dict[str, Any]
    registration: dict[str, Any]

    def safe_summary(self, *, status: str, database_writes: bool) -> dict[str, Any]:
        """Return only non-secret content identities and release status."""

        return {
            "schema_version": 1,
            "status": status,
            "database_writes": database_writes,
            "protocol_id": self.authorization["protocol_id"],
            "run_id": self.authorization["run_id"],
            "registration_id": self.authorization["registration_id"],
            "outcome_semantics_id": self.authorization["outcome_semantics_id"],
            "configuration_binding": dict(self.authorization["configuration_binding"]),
            "build_ids": {
                role: self.authorization["images"][role]["build_id"] for role in IMAGE_ROLES
            },
            "preflight_manifest_ids": {
                role: self.receipts[f"{role}_preflight"]["payload"]["preflight_manifest_id"]
                for role in IMAGE_ROLES
            },
            "release_receipt_ids": {
                receipt_type: self.receipts[receipt_type]["receipt_id"]
                for receipt_type in RELEASE_RECEIPT_TYPES
            },
            "decommission_id": self.decommission_receipt["decommission_id"],
            "authorization_id": self.authorization["authorization_id"],
        }


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FormalReleaseError(f"{label} must be an object")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str] | frozenset[str], label: str) -> None:
    if set(value) != set(expected):
        raise FormalReleaseError(f"{label} has an invalid exact schema")


def _mapping_rows(result: Any) -> list[dict[str, Any]]:
    try:
        return [dict(row) for row in result.mappings().all()]
    except (AttributeError, TypeError) as exc:
        raise FormalReleaseError("administrator query returned an invalid row shape") from exc


def _finite_timestamp(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FormalReleaseError(f"{label} is not a finite database timestamp")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise FormalReleaseError(f"{label} is not a finite database timestamp")
    return normalized


def validate_in_image_runtime_material(value: Any, *, expected_role: str) -> dict[str, Any]:
    """Validate one exact document emitted inside its paused runtime image."""

    if expected_role not in IMAGE_ROLES:
        raise FormalReleaseError("runtime material role is not allowed")
    material = _object(value, f"{expected_role} runtime material")
    _exact_keys(
        material,
        _RUNTIME_MATERIAL_KEYS,
        f"{expected_role} runtime material",
    )
    component = validate_component_configuration(
        material["component_configuration"], expected_role=expected_role
    )
    preflight = _object(material["preflight_payload"], f"{expected_role} preflight payload")
    expected_preflight_keys = {
        "role",
        "runtime_ready",
        "build_id",
        "component_configuration_id",
        "preflight_manifest_id",
    }
    if expected_role != "collector":
        expected_preflight_keys.add("outcome_semantics_id")
    _exact_keys(
        preflight,
        expected_preflight_keys,
        f"{expected_role} preflight payload",
    )
    if preflight.get("role") != expected_role:
        raise FormalReleaseError("runtime material role differs from its evidence slot")
    rebuilt = build_runtime_preflight_payload(
        role=expected_role,
        build_id=preflight.get("build_id"),
        component_configuration_id=preflight.get("component_configuration_id"),
        outcome_semantics_id=preflight.get("outcome_semantics_id"),
    )
    if dict(preflight) != rebuilt:
        raise FormalReleaseError("runtime preflight payload is not exact and content-addressed")
    if rebuilt["component_configuration_id"] != component["configuration_id"]:
        raise FormalReleaseError("runtime preflight differs from its component configuration")
    return {
        "component_configuration": component,
        "preflight_payload": rebuilt,
    }


def image_attestation_from_machine_inventory(value: Any, *, expected_role: str) -> dict[str, Any]:
    """Project one exact Fly machine-list inventory into an image attestation.

    Destroyed historical entries are ignored. Exactly one current Machine must
    remain, and its deployment tag and registry-provided full digest are the
    only control-plane fields used as release authority.
    """

    if expected_role not in IMAGE_ROLES:
        raise FormalReleaseError("Fly inventory role is not allowed")
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise FormalReleaseError("Fly Machine inventory must be a JSON array")
    current: list[Mapping[str, Any]] = []
    for index, item in enumerate(value):
        machine = _object(item, f"Fly Machine inventory item {index}")
        state = machine.get("state")
        if not isinstance(state, str) or not state.strip() or state != state.strip():
            raise FormalReleaseError("Fly Machine inventory state is malformed")
        if state != "destroyed":
            current.append(machine)
    if len(current) != 1:
        raise FormalReleaseError(
            "Fly Machine inventory must contain exactly one non-destroyed Machine"
        )
    machine = current[0]
    config = _object(machine.get("config"), "Fly Machine config")
    image_ref_document = _object(machine.get("image_ref"), "Fly Machine image_ref")
    deployment_ref = config.get("image")
    digest = image_ref_document.get("digest")
    if not isinstance(deployment_ref, str):
        raise FormalReleaseError("Fly Machine config.image is missing")
    match = _FLY_DEPLOYMENT_REF.fullmatch(deployment_ref)
    if match is None:
        raise FormalReleaseError("Fly Machine config.image is not an exact deployment tag")
    if match.group("app") != _EXPECTED_FLY_APPS[expected_role]:
        raise FormalReleaseError("Fly Machine application differs from its runtime role")
    if not isinstance(digest, str) or _IMAGE_DIGEST.fullmatch(digest) is None:
        raise FormalReleaseError("Fly Machine image_ref.digest is not a full sha256 digest")
    return image_attestation(
        app_name=match.group("app"),
        image_ref=deployment_ref,
        image_digest=digest,
    )


def build_formal_release_plan(
    *,
    runtime_materials: Mapping[str, Any],
    machine_inventories: Mapping[str, Any],
    restore_rehearsal: Mapping[str, Any],
    alert_delivery: Mapping[str, Any],
) -> FormalReleasePlan:
    """Build all release documents without network access or database writes."""

    materials_input = _object(runtime_materials, "runtime_materials")
    inventories_input = _object(machine_inventories, "machine_inventories")
    _exact_keys(materials_input, set(IMAGE_ROLES), "runtime_materials")
    _exact_keys(inventories_input, set(IMAGE_ROLES), "machine_inventories")
    materials = {
        role: validate_in_image_runtime_material(materials_input[role], expected_role=role)
        for role in IMAGE_ROLES
    }
    images = {
        role: image_attestation_from_machine_inventory(inventories_input[role], expected_role=role)
        for role in IMAGE_ROLES
    }
    for role in IMAGE_ROLES:
        if materials[role]["preflight_payload"]["build_id"] != images[role]["build_id"]:
            raise FormalReleaseError(
                "runtime preflight build differs from its Fly Machine inventory"
            )

    release_configuration = build_release_configuration(
        materials["collector"]["component_configuration"],
        materials["paper_decision"]["component_configuration"],
        materials["paper_marker"]["component_configuration"],
    )
    decision_settings = release_configuration["paper_decision_configuration"]["settings"]
    collector_settings = release_configuration["collector_configuration"]["settings"]
    if (
        collector_settings["collector_semantics_id"]
        != GLOBAL_EVENT_V2_PROTOCOL["evidence"]["expected_collector_semantics_id"]
    ):
        raise FormalReleaseError("collector semantics differ from the frozen protocol")
    decision_outcome_id = materials["paper_decision"]["preflight_payload"].get(
        "outcome_semantics_id"
    )
    marker_outcome_id = materials["paper_marker"]["preflight_payload"].get("outcome_semantics_id")
    if decision_outcome_id != marker_outcome_id:
        raise FormalReleaseError("decision and marker runtime outcome semantics differ")
    local_outcome_id = outcome_semantics_id()
    require_outcome_semantics(local_outcome_id)
    if decision_outcome_id != local_outcome_id:
        raise FormalReleaseError("runtime outcome semantics differ from the administrator package")
    decision_semantics = formal_decision_semantics()
    if decision_semantics.get("semantic_id") != decision_settings["decision_semantics_id"]:
        raise FormalReleaseError("decision implementation differs from the runtime configuration")

    run_id = decision_settings["run_id"]
    run_config = formal_run_configuration(
        release_configuration=release_configuration,
        decision_semantics=decision_semantics,
        outcome_semantics_id=local_outcome_id,
    )
    registration = formal_trial_registration(
        run_id,
        decision_semantics,
        outcome_semantics_id=local_outcome_id,
        configuration_binding=release_configuration["configuration_binding"],
    )
    decommission = build_legacy_role_decommission_receipt()
    payloads: dict[str, Mapping[str, Any]] = {
        "configuration": release_configuration,
        "collector_preflight": materials["collector"]["preflight_payload"],
        "paper_decision_preflight": materials["paper_decision"]["preflight_payload"],
        "paper_marker_preflight": materials["paper_marker"]["preflight_payload"],
        "restore_rehearsal": restore_rehearsal,
        "alert_delivery": alert_delivery,
        "runtime_role_decommission": runtime_role_decommission_release_payload(),
    }
    receipts = {
        receipt_type: build_release_receipt(
            receipt_type=receipt_type,
            protocol_id=GLOBAL_EVENT_V2_PROTOCOL_ID,
            run_id=run_id,
            payload=payloads[receipt_type],
        )
        for receipt_type in RELEASE_RECEIPT_TYPES
    }
    restore_payload = receipts["restore_rehearsal"]["payload"]
    alert_payload = receipts["alert_delivery"]["payload"]
    collector_rehearsal = restore_payload["collector_rehearsal"]
    cycle_manifest = collector_rehearsal["manifest"]
    for role in IMAGE_ROLES:
        alert_receipt = alert_payload["deliveries"][role]
        if (
            alert_receipt["build_id"] != images[role]["build_id"]
            or alert_receipt["component_configuration_id"]
            != release_configuration["configuration_binding"][f"{role}_configuration_id"]
        ):
            raise FormalReleaseError(
                "alert delivery differs from a released image or configuration"
            )
    if (
        cycle_manifest["protocol_id"] != GLOBAL_EVENT_V2_PROTOCOL_ID
        or cycle_manifest["collector_build_id"] != images["collector"]["build_id"]
        or cycle_manifest["collector_semantics_id"]
        != collector_settings["collector_semantics_id"]
        or collector_rehearsal["component_configuration_id"]
        != release_configuration["configuration_binding"][
            "collector_configuration_id"
        ]
    ):
        raise FormalReleaseError(
            "restore collection cycle differs from the released collector protocol"
        )
    authorization = build_trial_authorization(
        protocol_id=GLOBAL_EVENT_V2_PROTOCOL_ID,
        run_id=run_id,
        registration_id=registration["registration_id"],
        outcome_semantics_id=local_outcome_id,
        configuration_binding=release_configuration["configuration_binding"],
        collector_image=images["collector"],
        paper_decision_image=images["paper_decision"],
        paper_marker_image=images["paper_marker"],
        release_receipt_ids={
            receipt_type: receipts[receipt_type]["receipt_id"]
            for receipt_type in RELEASE_RECEIPT_TYPES
        },
    )
    return FormalReleasePlan(
        release_configuration=release_configuration,
        images=images,
        receipts=receipts,
        authorization=authorization,
        decommission_receipt=decommission,
        run_config=run_config,
        registration=registration,
    )


def _validate_plan(plan: FormalReleasePlan) -> FormalReleasePlan:
    if not isinstance(plan, FormalReleasePlan):
        raise FormalReleaseError("formal release plan has an invalid type")
    release = validate_release_configuration(plan.release_configuration)
    image_documents = _object(plan.images, "release plan images")
    _exact_keys(image_documents, set(IMAGE_ROLES), "release plan images")
    images = {
        role: validate_image_attestation(image_documents[role], f"{role} image")
        for role in IMAGE_ROLES
    }
    if any(images[role]["app_name"] != _EXPECTED_FLY_APPS[role] for role in IMAGE_ROLES):
        raise FormalReleaseError("release plan image application differs from its runtime role")
    receipt_documents = _object(plan.receipts, "release plan receipts")
    _exact_keys(receipt_documents, set(RELEASE_RECEIPT_TYPES), "release plan receipts")
    receipts = {
        receipt_type: validate_release_receipt(receipt_documents[receipt_type])
        for receipt_type in RELEASE_RECEIPT_TYPES
    }
    authorization = validate_trial_authorization(plan.authorization)
    decommission = build_legacy_role_decommission_receipt()
    if plan.decommission_receipt != decommission:
        raise FormalReleaseError("release plan decommission receipt has drifted")
    local_outcome_id = outcome_semantics_id()
    require_outcome_semantics(local_outcome_id)
    decision_semantics = formal_decision_semantics()
    if authorization["outcome_semantics_id"] != local_outcome_id:
        raise FormalReleaseError("release plan outcome implementation has drifted")
    decision_settings = release["paper_decision_configuration"]["settings"]
    collector_settings = release["collector_configuration"]["settings"]
    if (
        authorization["protocol_id"] != GLOBAL_EVENT_V2_PROTOCOL_ID
        or authorization["run_id"] != decision_settings["run_id"]
        or decision_semantics.get("semantic_id") != decision_settings["decision_semantics_id"]
        or collector_settings["collector_semantics_id"]
        != GLOBAL_EVENT_V2_PROTOCOL["evidence"]["expected_collector_semantics_id"]
    ):
        raise FormalReleaseError("release plan executable protocol identity has drifted")
    expected_run_config = formal_run_configuration(
        release_configuration=release,
        decision_semantics=decision_semantics,
        outcome_semantics_id=local_outcome_id,
    )
    expected_registration = formal_trial_registration(
        authorization["run_id"],
        decision_semantics,
        outcome_semantics_id=local_outcome_id,
        configuration_binding=release["configuration_binding"],
    )
    if plan.run_config != expected_run_config or plan.registration != expected_registration:
        raise FormalReleaseError("release plan bootstrap documents have drifted")
    if expected_run_config["trial_registration_id"] != expected_registration["registration_id"]:
        raise FormalReleaseError("release plan bootstrap identity is inconsistent")
    if (
        authorization["registration_id"] != expected_registration["registration_id"]
        or authorization["configuration_binding"] != release["configuration_binding"]
        or authorization["images"] != images
        or authorization["release_receipt_ids"]
        != {
            receipt_type: receipts[receipt_type]["receipt_id"]
            for receipt_type in RELEASE_RECEIPT_TYPES
        }
    ):
        raise FormalReleaseError("release plan authorization bindings have drifted")
    for receipt in receipts.values():
        if (
            receipt["protocol_id"] != authorization["protocol_id"]
            or receipt["run_id"] != authorization["run_id"]
        ):
            raise FormalReleaseError("release plan receipt identity has drifted")
    if receipts["configuration"]["payload"] != release:
        raise FormalReleaseError("release plan configuration receipt has drifted")
    for role in IMAGE_ROLES:
        preflight = receipts[f"{role}_preflight"]["payload"]
        if (
            preflight["build_id"] != images[role]["build_id"]
            or preflight["component_configuration_id"]
            != release["configuration_binding"][f"{role}_configuration_id"]
            or (role != "collector" and preflight["outcome_semantics_id"] != local_outcome_id)
        ):
            raise FormalReleaseError("release plan preflight binding has drifted")
        alert_receipt = receipts["alert_delivery"]["payload"]["deliveries"][role]
        if (
            alert_receipt["build_id"] != images[role]["build_id"]
            or alert_receipt["component_configuration_id"]
            != release["configuration_binding"][f"{role}_configuration_id"]
        ):
            raise FormalReleaseError("release plan alert binding has drifted")
    restore_payload = receipts["restore_rehearsal"]["payload"]
    collector_rehearsal = restore_payload["collector_rehearsal"]
    cycle_manifest = collector_rehearsal["manifest"]
    if (
        cycle_manifest["protocol_id"] != authorization["protocol_id"]
        or cycle_manifest["collector_build_id"] != images["collector"]["build_id"]
        or cycle_manifest["collector_semantics_id"]
        != collector_settings["collector_semantics_id"]
        or collector_rehearsal["component_configuration_id"]
        != release["configuration_binding"]["collector_configuration_id"]
    ):
        raise FormalReleaseError("release plan restore protocol binding has drifted")
    if (
        receipts["runtime_role_decommission"]["payload"]
        != runtime_role_decommission_release_payload()
    ):
        raise FormalReleaseError("release plan role decommission binding has drifted")
    return FormalReleasePlan(
        release_configuration=release,
        images=images,
        receipts=receipts,
        authorization=authorization,
        decommission_receipt=decommission,
        run_config=expected_run_config,
        registration=expected_registration,
    )


def _require_schema_admin(conn: Any) -> None:
    rows = _mapping_rows(
        conn.execute(
            text(
                "SELECT current_user::text AS current_role, "
                "session_user::text AS session_role, "
                "pg_catalog.pg_has_role(current_user,'schema_admin','MEMBER') "
                "AS current_is_schema_admin, "
                "pg_catalog.pg_has_role(session_user,'schema_admin','MEMBER') "
                "AS session_is_schema_admin"
            )
        )
    )
    expected = {
        "current_role",
        "session_role",
        "current_is_schema_admin",
        "session_is_schema_admin",
    }
    if len(rows) != 1 or set(rows[0]) != expected:
        raise FormalReleaseError("administrator identity query returned a wrong schema")
    row = rows[0]
    if not is_formal_schema_admin_identity(**row):
        raise FormalReleaseError("formal release requires one direct schema-administrator session")


def _load_exact_bootstrap(conn: Any, plan: FormalReleasePlan) -> None:
    authorization = plan.authorization
    rows = _mapping_rows(
        conn.execute(
            text(
                "SELECT protocol.protocol_id AS manifest_protocol_id, "
                "protocol.manifest_json AS protocol_manifest_json, "
                "registry.protocol_id AS registry_protocol_id, "
                "registry.run_id AS registry_run_id, "
                "registry.registration_id AS registry_registration_id, "
                "registry.created_utc AS registry_created_utc, "
                "registry.details_json AS registration_json, "
                "run.created_utc AS run_created_utc, run.config_json AS run_config_json, "
                "label.label AS label_name, label.created_utc AS label_created_utc, "
                "label.details_json AS label_details_json "
                "FROM public.formal_trial_registry AS registry "
                "JOIN public.experiment_registry AS protocol "
                "ON protocol.protocol_id=registry.protocol_id "
                "JOIN public.paper_runs AS run ON run.run_id=registry.run_id "
                "JOIN public.paper_run_labels AS label ON label.run_id=registry.run_id "
                "WHERE registry.protocol_id=:protocol_id OR registry.run_id=:run_id "
                "ORDER BY registry.protocol_id,registry.run_id,label.label "
                "FOR UPDATE OF protocol,registry,run,label"
            ),
            {
                "protocol_id": authorization["protocol_id"],
                "run_id": authorization["run_id"],
            },
        )
    )
    expected_keys = {
        "manifest_protocol_id",
        "protocol_manifest_json",
        "registry_protocol_id",
        "registry_run_id",
        "registry_registration_id",
        "registry_created_utc",
        "registration_json",
        "run_created_utc",
        "run_config_json",
        "label_name",
        "label_created_utc",
        "label_details_json",
    }
    if len(rows) != 1 or set(rows[0]) != expected_keys:
        raise FormalReleaseError("formal bootstrap registry/run/label is not exact")
    row = rows[0]
    registry_time = _finite_timestamp(row["registry_created_utc"], "formal registry creation time")
    _finite_timestamp(row["run_created_utc"], "formal run creation time")
    if _finite_timestamp(row["label_created_utc"], "formal label creation time") != registry_time:
        raise FormalReleaseError("formal bootstrap timestamps are inconsistent")
    if (
        row["manifest_protocol_id"] != authorization["protocol_id"]
        or row["registry_protocol_id"] != authorization["protocol_id"]
        or row["registry_run_id"] != authorization["run_id"]
        or row["registry_registration_id"] != authorization["registration_id"]
        or row["label_name"] != "confirmatory-trial"
    ):
        raise FormalReleaseError("formal bootstrap identities are inconsistent")
    expected_registration = canonical_json(plan.registration)
    if (
        row["protocol_manifest_json"] != canonical_json(GLOBAL_EVENT_V2_PROTOCOL)
        or row["registration_json"] != expected_registration
        or row["label_details_json"] != expected_registration
        or row["run_config_json"] != canonical_json(plan.run_config)
    ):
        raise FormalReleaseError("formal bootstrap immutable documents differ")


def _load_decommission_rows(conn: Any) -> list[dict[str, Any]]:
    return _mapping_rows(
        conn.execute(
            text(
                "SELECT decommission_id,legacy_role,decommissioned_utc,"
                "contract_id,details_json "
                "FROM public.formal_role_split_decommissions "
                "ORDER BY decommission_id FOR UPDATE"
            )
        )
    )


def _validate_decommission_rows(rows: list[dict[str, Any]], expected: Mapping[str, Any]) -> bool:
    if not rows:
        return False
    required = {
        "decommission_id",
        "legacy_role",
        "decommissioned_utc",
        "contract_id",
        "details_json",
    }
    if len(rows) != 1 or set(rows[0]) != required:
        raise FormalReleaseError("durable role decommission state is not exact")
    row = rows[0]
    _finite_timestamp(row["decommissioned_utc"], "role decommission time")
    if (
        row["decommission_id"] != expected["decommission_id"]
        or row["legacy_role"] != expected["legacy_role"]
        or row["contract_id"] != expected["contract_id"]
        or row["details_json"] != canonical_json(expected)
    ):
        raise FormalReleaseError("durable role decommission receipt differs")
    return True


def _load_receipt_rows(conn: Any, plan: FormalReleasePlan) -> list[dict[str, Any]]:
    return _mapping_rows(
        conn.execute(
            text(
                "SELECT receipt_id,receipt_type,protocol_id,run_id,created_utc,"
                "content_json FROM public.formal_release_receipts "
                "WHERE protocol_id=:protocol_id OR run_id=:run_id "
                "ORDER BY receipt_type FOR UPDATE"
            ),
            {
                "protocol_id": plan.authorization["protocol_id"],
                "run_id": plan.authorization["run_id"],
            },
        )
    )


def _validate_receipt_rows(rows: list[dict[str, Any]], plan: FormalReleasePlan) -> set[str]:
    required = {
        "receipt_id",
        "receipt_type",
        "protocol_id",
        "run_id",
        "created_utc",
        "content_json",
    }
    found: set[str] = set()
    for row in rows:
        if set(row) != required:
            raise FormalReleaseError("durable release receipt row has a wrong schema")
        receipt_type = row["receipt_type"]
        if receipt_type in found or receipt_type not in plan.receipts:
            raise FormalReleaseError("durable release receipt set is not exact")
        expected = plan.receipts[receipt_type]
        _finite_timestamp(row["created_utc"], "release receipt creation time")
        if (
            row["receipt_id"] != expected["receipt_id"]
            or row["protocol_id"] != expected["protocol_id"]
            or row["run_id"] != expected["run_id"]
            or row["content_json"] != canonical_json(expected)
        ):
            raise FormalReleaseError("durable release receipt differs from the plan")
        found.add(receipt_type)
    return found


def _load_authorization_rows(conn: Any, plan: FormalReleasePlan) -> list[dict[str, Any]]:
    authorization = plan.authorization
    return _mapping_rows(
        conn.execute(
            text(
                "SELECT protocol_id,run_id,registration_id,authorization_id,"
                "authorized_utc,outcome_semantics_id,configuration_manifest_id,"
                "collector_configuration_id,paper_decision_configuration_id,"
                "paper_marker_configuration_id,collector_build_id,"
                "paper_decision_build_id,paper_marker_build_id,authorization_json "
                "FROM public.formal_trial_authorizations "
                "WHERE protocol_id=:protocol_id OR run_id=:run_id "
                "OR registration_id=:registration_id "
                "OR authorization_id=:authorization_id "
                "ORDER BY protocol_id FOR UPDATE"
            ),
            {
                "protocol_id": authorization["protocol_id"],
                "run_id": authorization["run_id"],
                "registration_id": authorization["registration_id"],
                "authorization_id": authorization["authorization_id"],
            },
        )
    )


def _authorization_columns(authorization: Mapping[str, Any]) -> dict[str, Any]:
    binding = authorization["configuration_binding"]
    images = authorization["images"]
    return {
        "protocol_id": authorization["protocol_id"],
        "run_id": authorization["run_id"],
        "registration_id": authorization["registration_id"],
        "authorization_id": authorization["authorization_id"],
        "outcome_semantics_id": authorization["outcome_semantics_id"],
        "configuration_manifest_id": binding["configuration_manifest_id"],
        "collector_configuration_id": binding["collector_configuration_id"],
        "paper_decision_configuration_id": binding["paper_decision_configuration_id"],
        "paper_marker_configuration_id": binding["paper_marker_configuration_id"],
        "collector_build_id": images["collector"]["build_id"],
        "paper_decision_build_id": images["paper_decision"]["build_id"],
        "paper_marker_build_id": images["paper_marker"]["build_id"],
        "authorization_json": canonical_json(authorization),
    }


def _validate_authorization_rows(rows: list[dict[str, Any]], plan: FormalReleasePlan) -> bool:
    if not rows:
        return False
    expected = _authorization_columns(plan.authorization)
    required = {*expected, "authorized_utc"}
    if len(rows) != 1 or set(rows[0]) != required:
        raise FormalReleaseError("durable formal authorization state is not exact")
    row = rows[0]
    _finite_timestamp(row["authorized_utc"], "formal authorization time")
    if any(row[key] != value for key, value in expected.items()):
        raise FormalReleaseError("durable formal authorization differs from the plan")
    return True


def _insert_decommission(conn: Any, receipt: Mapping[str, Any]) -> None:
    conn.execute(
        text(
            "INSERT INTO public.formal_role_split_decommissions "
            "(decommission_id,legacy_role,decommissioned_utc,contract_id,details_json) "
            "VALUES (:decommission_id,:legacy_role,0,:contract_id,:details_json)"
        ),
        {
            "decommission_id": receipt["decommission_id"],
            "legacy_role": receipt["legacy_role"],
            "contract_id": receipt["contract_id"],
            "details_json": canonical_json(receipt),
        },
    )


def _insert_receipt(conn: Any, receipt: Mapping[str, Any]) -> None:
    conn.execute(
        text(
            "INSERT INTO public.formal_release_receipts "
            "(receipt_id,receipt_type,protocol_id,run_id,created_utc,content_json) "
            "VALUES (:receipt_id,:receipt_type,:protocol_id,:run_id,0,:content_json)"
        ),
        {
            "receipt_id": receipt["receipt_id"],
            "receipt_type": receipt["receipt_type"],
            "protocol_id": receipt["protocol_id"],
            "run_id": receipt["run_id"],
            "content_json": canonical_json(receipt),
        },
    )


def _insert_authorization(conn: Any, authorization: Mapping[str, Any]) -> None:
    columns = _authorization_columns(authorization)
    conn.execute(
        text(
            "INSERT INTO public.formal_trial_authorizations "
            "(protocol_id,run_id,registration_id,authorization_id,authorized_utc,"
            "outcome_semantics_id,configuration_manifest_id,"
            "collector_configuration_id,paper_decision_configuration_id,"
            "paper_marker_configuration_id,collector_build_id,"
            "paper_decision_build_id,paper_marker_build_id,authorization_json) "
            "VALUES (:protocol_id,:run_id,:registration_id,:authorization_id,0,"
            ":outcome_semantics_id,:configuration_manifest_id,"
            ":collector_configuration_id,:paper_decision_configuration_id,"
            ":paper_marker_configuration_id,:collector_build_id,"
            ":paper_decision_build_id,:paper_marker_build_id,:authorization_json)"
        ),
        columns,
    )


def _persist_release_transaction(conn: Any, plan: FormalReleasePlan) -> str:
    _require_schema_admin(conn)
    conn.execute(text("SET LOCAL search_path = pg_catalog, public"))
    conn.execute(
        text(
            "SELECT pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(:lock_identity,0))"
        ),
        {"lock_identity": f"tradingagents:formal-release:{plan.authorization['protocol_id']}"},
    )
    _load_exact_bootstrap(conn, plan)
    has_decommission = _validate_decommission_rows(
        _load_decommission_rows(conn), plan.decommission_receipt
    )
    found_receipts = _validate_receipt_rows(_load_receipt_rows(conn, plan), plan)
    has_authorization = _validate_authorization_rows(_load_authorization_rows(conn, plan), plan)
    expected_receipts = set(RELEASE_RECEIPT_TYPES)
    if has_authorization:
        if not has_decommission or found_receipts != expected_receipts:
            raise FormalReleaseError("durable authorization has incomplete release dependencies")
        return "already_released"
    if not has_decommission:
        _insert_decommission(conn, plan.decommission_receipt)
    for receipt_type in RELEASE_RECEIPT_TYPES:
        if receipt_type not in found_receipts:
            _insert_receipt(conn, plan.receipts[receipt_type])
    _insert_authorization(conn, plan.authorization)
    return "released"


def _validate_bootstrap_result(result: Any, plan: FormalReleasePlan) -> None:
    document = _object(result, "formal bootstrap result")
    _exact_keys(document, _BOOTSTRAP_RESULT_KEYS, "formal bootstrap result")
    authorization = plan.authorization
    if (
        document["run_id"] != authorization["run_id"]
        or document["protocol_id"] != authorization["protocol_id"]
        or document["registration_id"] != authorization["registration_id"]
        or document["outcome_semantics_id"] != authorization["outcome_semantics_id"]
        or document["configuration_binding"] != authorization["configuration_binding"]
        or document["provider_calls"] != 0
        or document["trial_authorized"] is not False
    ):
        raise FormalReleaseError("formal bootstrap result differs from the release plan")


def execute_formal_release(*, admin_db_url: str, plan: FormalReleasePlan) -> dict[str, Any]:
    """Bootstrap and atomically commit an exact formal release as schema admin."""

    normalized_plan = _validate_plan(plan)
    if not isinstance(admin_db_url, str) or not admin_db_url.strip():
        raise FormalReleaseError("administrator database URL is not configured")
    database_url = admin_db_url.strip()
    if database_url.startswith("postgres://"):
        database_url = "postgresql://" + database_url.removeprefix("postgres://")
    try:
        parsed_url = make_url(database_url)
    except Exception as exc:  # SQLAlchemy errors may embed credentials in text.
        raise FormalReleaseError("administrator database URL is invalid") from exc
    if parsed_url.get_backend_name() not in {"postgres", "postgresql"}:
        raise FormalReleaseError("formal release requires PostgreSQL")
    engine = create_engine(database_url)
    try:
        if engine.dialect.name != "postgresql":
            raise FormalReleaseError("formal release requires PostgreSQL")
        # Check authority before bootstrap can append even paused registry rows.
        with engine.connect() as conn:
            _require_schema_admin(conn)
        bootstrap_result = bootstrap_formal_trial(
            db_url=database_url,
            release_configuration=normalized_plan.release_configuration,
        )
        _validate_bootstrap_result(bootstrap_result, normalized_plan)
        with engine.begin() as conn:
            status = _persist_release_transaction(conn, normalized_plan)
    finally:
        engine.dispose()
    return normalized_plan.safe_summary(
        status=status,
        database_writes=status == "released",
    )


__all__ = [
    "FormalReleaseError",
    "FormalReleasePlan",
    "build_formal_release_plan",
    "execute_formal_release",
    "image_attestation_from_machine_inventory",
    "validate_in_image_runtime_material",
]
