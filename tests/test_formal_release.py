from __future__ import annotations

import copy
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from tests.test_formal_activation import (
    OUTCOME_ID,
    _configuration_payload,
    _images,
    _receipt_payloads,
)
from tradingagents import formal_release, ops_cli
from tradingagents.formal_activation import (
    IMAGE_ROLES,
    RELEASE_RECEIPT_TYPES,
    build_alert_delivery_payload,
    build_alert_delivery_receipt,
    build_collector_rehearsal_payload,
    build_release_receipt,
    build_restore_rehearsal_payload,
    build_runtime_preflight_payload,
    build_trial_authorization,
    image_attestation,
)
from tradingagents.research_protocol import (
    GLOBAL_EVENT_V2_PROTOCOL,
    canonical_json,
)


def _release_inputs(monkeypatch):
    configuration = _configuration_payload()
    images = dict(zip(IMAGE_ROLES, _images(), strict=True))
    payloads = _receipt_payloads(
        images["collector"]["build_id"],
        images["paper_decision"]["build_id"],
        images["paper_marker"]["build_id"],
    )
    runtime_materials = {
        role: {
            "component_configuration": configuration[f"{role}_configuration"],
            "preflight_payload": payloads[f"{role}_preflight"],
        }
        for role in IMAGE_ROLES
    }
    machine_inventories = {
        role: [
            {
                "id": f"machine-{role}",
                "state": "started",
                "config": {"image": images[role]["image_ref"]},
                "image_ref": {"digest": images[role]["image_digest"]},
            }
        ]
        for role in IMAGE_ROLES
    }
    decision_id = configuration["paper_decision_configuration"]["settings"]["decision_semantics_id"]
    decision_semantics = {
        "schema_version": 2,
        "policy": "release-orchestration-test",
        "semantic_id": decision_id,
    }
    monkeypatch.setattr(formal_release, "outcome_semantics_id", lambda: OUTCOME_ID)
    monkeypatch.setattr(formal_release, "require_outcome_semantics", lambda value: value)
    monkeypatch.setattr(formal_release, "formal_decision_semantics", lambda: decision_semantics)
    return {
        "runtime_materials": runtime_materials,
        "machine_inventories": machine_inventories,
        "restore_rehearsal": payloads["restore_rehearsal"],
        "alert_delivery": payloads["alert_delivery"],
    }


def _plan(monkeypatch):
    return formal_release.build_formal_release_plan(**_release_inputs(monkeypatch))


@pytest.mark.unit
def test_plan_builds_exact_receipts_v2_authorization_and_safe_summary(monkeypatch):
    plan = _plan(monkeypatch)
    summary = plan.safe_summary(status="planned", database_writes=False)

    assert set(plan.receipts) == set(RELEASE_RECEIPT_TYPES)
    assert plan.authorization["schema_version"] == 2
    assert plan.authorization["outcome_semantics_id"] == OUTCOME_ID
    assert plan.authorization["registration_id"] == plan.registration["registration_id"]
    assert summary["status"] == "planned"
    assert summary["database_writes"] is False
    assert set(summary["release_receipt_ids"]) == set(RELEASE_RECEIPT_TYPES)
    rendered = canonical_json(summary)
    assert "registry.fly.io" not in rendered
    assert "sha256:" not in rendered
    assert "payload" not in rendered


@pytest.mark.unit
@pytest.mark.parametrize("extra_slot", ["analysis", "legacy_paper"])
def test_release_plan_rejects_extra_runtime_roles(monkeypatch, extra_slot):
    inputs = _release_inputs(monkeypatch)
    inputs["runtime_materials"][extra_slot] = copy.deepcopy(
        inputs["runtime_materials"]["collector"]
    )

    with pytest.raises(formal_release.FormalReleaseError, match="exact schema"):
        formal_release.build_formal_release_plan(**inputs)


@pytest.mark.unit
def test_runtime_material_rejects_extra_keys(monkeypatch):
    inputs = _release_inputs(monkeypatch)
    inputs["runtime_materials"]["collector"]["caller_build_id"] = "build_" + "0" * 24

    with pytest.raises(formal_release.FormalReleaseError, match="exact schema"):
        formal_release.build_formal_release_plan(**inputs)


@pytest.mark.unit
def test_release_plan_rejects_decision_marker_outcome_disagreement(monkeypatch):
    inputs = _release_inputs(monkeypatch)
    marker = inputs["runtime_materials"]["paper_marker"]
    marker["preflight_payload"] = build_runtime_preflight_payload(
        role="paper_marker",
        build_id=marker["preflight_payload"]["build_id"],
        component_configuration_id=marker["component_configuration"]["configuration_id"],
        outcome_semantics_id="outcome_semantics_" + "0" * 64,
    )

    with pytest.raises(formal_release.FormalReleaseError, match="outcome semantics differ"):
        formal_release.build_formal_release_plan(**inputs)


@pytest.mark.unit
def test_release_plan_binds_preflight_and_restore_to_machine_inventory(monkeypatch):
    inputs = _release_inputs(monkeypatch)
    inventory = inputs["machine_inventories"]["paper_marker"][0]
    inventory["config"]["image"] = (
        "registry.fly.io/tradagent-paper-marker:deployment-01KZAF9N3MYKKKYCY3KKX9F559"
    )

    with pytest.raises(formal_release.FormalReleaseError, match="preflight build"):
        formal_release.build_formal_release_plan(**inputs)


@pytest.mark.unit
def test_release_plan_binds_each_alert_to_its_image_and_configuration(monkeypatch):
    inputs = _release_inputs(monkeypatch)
    deliveries = copy.deepcopy(inputs["alert_delivery"]["deliveries"])
    original = deliveries["paper_marker"]
    deliveries["paper_marker"] = build_alert_delivery_receipt(
        role="paper_marker",
        build_id=original["build_id"],
        component_configuration_id="config_" + "0" * 24,
        route_fingerprint=original["route_fingerprint"],
        client_observed_utc=original["client_observed_utc"],
    )
    inputs["alert_delivery"] = build_alert_delivery_payload(deliveries=deliveries)

    with pytest.raises(formal_release.FormalReleaseError, match="alert delivery differs"):
        formal_release.build_formal_release_plan(**inputs)


@pytest.mark.unit
def test_machine_inventory_rejects_swapped_or_foreign_role_app(monkeypatch):
    inputs = _release_inputs(monkeypatch)
    inputs["machine_inventories"]["collector"] = copy.deepcopy(
        inputs["machine_inventories"]["paper_marker"]
    )

    with pytest.raises(formal_release.FormalReleaseError, match="runtime role"):
        formal_release.build_formal_release_plan(**inputs)


@pytest.mark.unit
def test_execute_revalidates_role_app_mapping_for_consistent_tampered_plan(monkeypatch):
    plan = _plan(monkeypatch)
    foreign_images = {}
    preflights = {}
    for index, role in enumerate(IMAGE_ROLES, start=1):
        app_name = f"foreign-{role.replace('_', '-')}"
        image_ref = f"registry.fly.io/{app_name}:deployment-01KZAE0P4ER12SS2215QXBSN0{index}"
        foreign_images[role] = image_attestation(
            app_name=app_name,
            image_ref=image_ref,
            image_digest="sha256:" + str(index) * 64,
        )
        preflights[role] = build_runtime_preflight_payload(
            role=role,
            build_id=foreign_images[role]["build_id"],
            component_configuration_id=plan.release_configuration["configuration_binding"][
                f"{role}_configuration_id"
            ],
            outcome_semantics_id=None if role == "collector" else OUTCOME_ID,
        )
    original_restore = plan.receipts["restore_rehearsal"]["payload"]
    foreign_cycle = copy.deepcopy(
        original_restore["collector_rehearsal"]["manifest"]
    )
    foreign_cycle["collector_build_id"] = foreign_images["collector"]["build_id"]
    restore = build_restore_rehearsal_payload(
        source_cluster_fingerprint=original_restore["backup"][
            "source_cluster_fingerprint"
        ],
        restored_cluster_fingerprint=original_restore["verification"][
            "restored_cluster_fingerprint"
        ],
        backup_fingerprint=original_restore["backup"]["backup_fingerprint"],
        backup_completed_utc=original_restore["backup"]["completed_utc"],
        collector_rehearsal=build_collector_rehearsal_payload(
            final_collection_cycle_manifest=foreign_cycle,
            component_configuration_id=original_restore[
                "collector_rehearsal"
            ]["component_configuration_id"],
        ),
        formal_trial_activity_rows=0,
        verification_completed_utc=original_restore["verification"]["completed_utc"],
    )
    original_alert = plan.receipts["alert_delivery"]["payload"]
    alert = build_alert_delivery_payload(
        deliveries={
            role: build_alert_delivery_receipt(
                role=role,
                build_id=foreign_images[role]["build_id"],
                component_configuration_id=plan.release_configuration[
                    "configuration_binding"
                ][f"{role}_configuration_id"],
                route_fingerprint=original_alert["route_fingerprint"],
                client_observed_utc=original_alert["deliveries"][role][
                    "client_observed_utc"
                ],
            )
            for role in IMAGE_ROLES
        }
    )
    payloads = {
        "configuration": plan.release_configuration,
        **{f"{role}_preflight": preflights[role] for role in IMAGE_ROLES},
        "restore_rehearsal": restore,
        "alert_delivery": alert,
        "runtime_role_decommission": plan.receipts["runtime_role_decommission"]["payload"],
    }
    receipts = {
        receipt_type: build_release_receipt(
            receipt_type=receipt_type,
            protocol_id=plan.authorization["protocol_id"],
            run_id=plan.authorization["run_id"],
            payload=payloads[receipt_type],
        )
        for receipt_type in RELEASE_RECEIPT_TYPES
    }
    authorization = build_trial_authorization(
        protocol_id=plan.authorization["protocol_id"],
        run_id=plan.authorization["run_id"],
        registration_id=plan.authorization["registration_id"],
        outcome_semantics_id=OUTCOME_ID,
        configuration_binding=plan.release_configuration["configuration_binding"],
        collector_image=foreign_images["collector"],
        paper_decision_image=foreign_images["paper_decision"],
        paper_marker_image=foreign_images["paper_marker"],
        release_receipt_ids={
            receipt_type: receipts[receipt_type]["receipt_id"]
            for receipt_type in RELEASE_RECEIPT_TYPES
        },
    )
    tampered = replace(
        plan,
        images=foreign_images,
        receipts=receipts,
        authorization=authorization,
    )
    opened = []
    monkeypatch.setattr(formal_release, "create_engine", lambda _url: opened.append(True))

    with pytest.raises(formal_release.FormalReleaseError, match="runtime role"):
        formal_release.execute_formal_release(
            admin_db_url="postgresql://admin:secret@example.invalid/formal",
            plan=tampered,
        )

    assert opened == []


@pytest.mark.unit
def test_machine_inventory_requires_one_current_machine_and_full_digest(monkeypatch):
    inputs = _release_inputs(monkeypatch)
    inventory = inputs["machine_inventories"]["collector"]
    inventory.append(copy.deepcopy(inventory[0]))

    with pytest.raises(formal_release.FormalReleaseError, match="exactly one"):
        formal_release.build_formal_release_plan(**inputs)

    inventory[1]["state"] = "destroyed"
    inventory[0]["image_ref"]["digest"] = "sha256:short"
    with pytest.raises(formal_release.FormalReleaseError, match="full sha256"):
        formal_release.build_formal_release_plan(**inputs)


class _Mappings:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Result:
    def __init__(self, rows=()):
        self._rows = rows

    def mappings(self):
        return _Mappings(self._rows)


class _ReleaseConnection:
    def __init__(self, plan, *, admin=True, fail_insert: str | None = None):
        self.plan = plan
        self.admin = admin
        self.fail_insert = fail_insert
        self.decommission = []
        self.receipts = {}
        self.authorization = []
        self.statements = []

    def _bootstrap_row(self):
        return {
            "manifest_protocol_id": self.plan.authorization["protocol_id"],
            "protocol_manifest_json": canonical_json(GLOBAL_EVENT_V2_PROTOCOL),
            "registry_protocol_id": self.plan.authorization["protocol_id"],
            "registry_run_id": self.plan.authorization["run_id"],
            "registry_registration_id": self.plan.authorization["registration_id"],
            "registry_created_utc": 100.0,
            "registration_json": canonical_json(self.plan.registration),
            "run_created_utc": 100.0,
            "run_config_json": canonical_json(self.plan.run_config),
            "label_name": "confirmatory-trial",
            "label_created_utc": 100.0,
            "label_details_json": canonical_json(self.plan.registration),
        }

    def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append(sql)
        params = params or {}
        if "current_user::text AS current_role" in sql:
            return _Result(
                [
                    {
                        "current_role": "release-admin",
                        "session_role": "release-admin",
                        "current_is_schema_admin": self.admin,
                        "session_is_schema_admin": self.admin,
                    }
                ]
            )
        if sql == "SET LOCAL search_path = pg_catalog, public":
            return _Result()
        if "pg_advisory_xact_lock" in sql:
            return _Result()
        if "FROM public.formal_trial_registry AS registry" in sql:
            return _Result([self._bootstrap_row()])
        if sql.lstrip().startswith("SELECT decommission_id"):
            return _Result(copy.deepcopy(self.decommission))
        if sql.lstrip().startswith("SELECT receipt_id"):
            return _Result(copy.deepcopy(list(self.receipts.values())))
        if sql.lstrip().startswith("SELECT protocol_id,run_id,registration_id"):
            return _Result(copy.deepcopy(self.authorization))
        if sql.startswith("INSERT INTO public.formal_role_split_decommissions"):
            self._maybe_fail("decommission")
            self.decommission = [
                {
                    "decommission_id": params["decommission_id"],
                    "legacy_role": params["legacy_role"],
                    "decommissioned_utc": 101.0,
                    "contract_id": params["contract_id"],
                    "details_json": params["details_json"],
                }
            ]
            return _Result()
        if sql.startswith("INSERT INTO public.formal_release_receipts"):
            self._maybe_fail(params["receipt_type"])
            self.receipts[params["receipt_type"]] = {
                **params,
                "created_utc": 102.0,
            }
            return _Result()
        if sql.startswith("INSERT INTO public.formal_trial_authorizations"):
            self._maybe_fail("authorization")
            self.authorization = [{**params, "authorized_utc": 103.0}]
            return _Result()
        raise AssertionError(f"unexpected SQL: {sql}")

    def _maybe_fail(self, stage):
        if self.fail_insert == stage:
            raise RuntimeError("simulated database failure with secret details")

    def snapshot(self):
        return copy.deepcopy((self.decommission, self.receipts, self.authorization))

    def restore(self, snapshot):
        self.decommission, self.receipts, self.authorization = snapshot


class _ConnectionContext:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, *_exc):
        return False


class _TransactionContext(_ConnectionContext):
    def __enter__(self):
        self.snapshot = self.conn.snapshot()
        return self.conn

    def __exit__(self, exc_type, *_exc):
        if exc_type is not None:
            self.conn.restore(self.snapshot)
        return False


class _ReleaseEngine:
    dialect = SimpleNamespace(name="postgresql")

    def __init__(self, conn):
        self.conn = conn
        self.disposed = False

    def connect(self):
        return _ConnectionContext(self.conn)

    def begin(self):
        return _TransactionContext(self.conn)

    def dispose(self):
        self.disposed = True


def _bootstrap_result(plan):
    return {
        "run_id": plan.authorization["run_id"],
        "protocol_id": plan.authorization["protocol_id"],
        "registration_id": plan.authorization["registration_id"],
        "outcome_semantics_id": plan.authorization["outcome_semantics_id"],
        "configuration_binding": plan.authorization["configuration_binding"],
        "provider_calls": 0,
        "trial_authorized": False,
    }


@pytest.mark.unit
def test_execute_is_atomic_and_exact_retry_is_idempotent(monkeypatch):
    plan = _plan(monkeypatch)
    conn = _ReleaseConnection(plan)
    engine = _ReleaseEngine(conn)
    bootstrap_calls = []
    monkeypatch.setattr(formal_release, "create_engine", lambda _url: engine)
    monkeypatch.setattr(
        formal_release,
        "bootstrap_formal_trial",
        lambda **kwargs: bootstrap_calls.append(kwargs) or _bootstrap_result(plan),
    )

    first = formal_release.execute_formal_release(
        admin_db_url="postgres://admin:database-secret@example.invalid/formal",
        plan=plan,
    )
    inserts_after_first = sum(statement.startswith("INSERT INTO") for statement in conn.statements)
    second = formal_release.execute_formal_release(
        admin_db_url="postgresql://admin:database-secret@example.invalid/formal",
        plan=plan,
    )

    assert first["status"] == "released"
    assert first["database_writes"] is True
    assert second["status"] == "already_released"
    assert second["database_writes"] is False
    assert len(conn.receipts) == 7
    assert len(conn.decommission) == 1
    assert len(conn.authorization) == 1
    assert (
        sum(statement.startswith("INSERT INTO") for statement in conn.statements)
        == inserts_after_first
    )
    assert len(bootstrap_calls) == 2
    assert all("auto_migrate" not in call for call in bootstrap_calls)
    assert all(call["db_url"].startswith("postgresql://") for call in bootstrap_calls)
    assert engine.disposed


@pytest.mark.unit
def test_execute_rolls_back_all_release_rows_on_any_insert_failure(monkeypatch):
    plan = _plan(monkeypatch)
    conn = _ReleaseConnection(plan, fail_insert="paper_marker_preflight")
    engine = _ReleaseEngine(conn)
    monkeypatch.setattr(formal_release, "create_engine", lambda _url: engine)
    monkeypatch.setattr(
        formal_release,
        "bootstrap_formal_trial",
        lambda **_kwargs: _bootstrap_result(plan),
    )

    with pytest.raises(RuntimeError, match="simulated database failure"):
        formal_release.execute_formal_release(
            admin_db_url="postgresql://admin:database-secret@example.invalid/formal",
            plan=plan,
        )

    assert conn.decommission == []
    assert conn.receipts == {}
    assert conn.authorization == []
    assert engine.disposed


@pytest.mark.unit
def test_execute_rejects_non_admin_before_bootstrap(monkeypatch):
    plan = _plan(monkeypatch)
    conn = _ReleaseConnection(plan, admin=False)
    engine = _ReleaseEngine(conn)
    bootstrap_calls = []
    monkeypatch.setattr(formal_release, "create_engine", lambda _url: engine)
    monkeypatch.setattr(
        formal_release,
        "bootstrap_formal_trial",
        lambda **kwargs: bootstrap_calls.append(kwargs),
    )

    with pytest.raises(formal_release.FormalReleaseError, match="schema-administrator"):
        formal_release.execute_formal_release(
            admin_db_url="postgresql://admin:database-secret@example.invalid/formal",
            plan=plan,
        )

    assert bootstrap_calls == []
    assert conn.decommission == []


def _write_release_files(tmp_path, inputs):
    documents = {
        "collector_material": inputs["runtime_materials"]["collector"],
        "paper_decision_material": inputs["runtime_materials"]["paper_decision"],
        "paper_marker_material": inputs["runtime_materials"]["paper_marker"],
        "collector_machines": inputs["machine_inventories"]["collector"],
        "paper_decision_machines": inputs["machine_inventories"]["paper_decision"],
        "paper_marker_machines": inputs["machine_inventories"]["paper_marker"],
        "restore_rehearsal": inputs["restore_rehearsal"],
        "collector_alert": inputs["alert_delivery"]["deliveries"]["collector"],
        "paper_decision_alert": inputs["alert_delivery"]["deliveries"][
            "paper_decision"
        ],
        "paper_marker_alert": inputs["alert_delivery"]["deliveries"]["paper_marker"],
    }
    paths = {}
    for name, document in documents.items():
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        paths[name] = path
    return paths


def _release_namespace(paths, *, execute=False):
    return SimpleNamespace(**paths, execute=execute)


@pytest.mark.unit
def test_ops_release_defaults_to_safe_dry_run_and_never_outputs_dsn(monkeypatch, tmp_path, capsys):
    inputs = _release_inputs(monkeypatch)
    paths = _write_release_files(tmp_path, inputs)
    secret_dsn = "postgresql://admin:super-secret@example.invalid/formal"

    result = ops_cli._formal_release_command(
        _release_namespace(paths),
        env={"TRADINGAGENTS_ADMIN_DB_URL": secret_dsn},
    )
    output = capsys.readouterr().out
    document = json.loads(output)

    assert result == 0
    assert document["status"] == "planned"
    assert document["database_writes"] is False
    assert secret_dsn not in output
    assert "super-secret" not in output
    assert "registry.fly.io" not in output
    assert "sha256:" not in output


@pytest.mark.unit
def test_ops_release_execute_uses_only_admin_dsn_environment(monkeypatch, tmp_path, capsys):
    inputs = _release_inputs(monkeypatch)
    paths = _write_release_files(tmp_path, inputs)
    captured = {}

    def execute(*, admin_db_url, plan):
        captured["admin_db_url"] = admin_db_url
        return plan.safe_summary(status="released", database_writes=True)

    monkeypatch.setattr(formal_release, "execute_formal_release", execute)
    secret_dsn = "postgresql://admin:super-secret@example.invalid/formal"
    result = ops_cli._formal_release_command(
        _release_namespace(paths, execute=True),
        env={"TRADINGAGENTS_ADMIN_DB_URL": secret_dsn},
    )
    output = capsys.readouterr().out

    assert result == 0
    assert json.loads(output)["status"] == "released"
    assert captured["admin_db_url"] == secret_dsn
    assert secret_dsn not in output
    parser_help = ops_cli._parser().format_help()
    assert "--admin-db" not in parser_help
    assert "--database-url" not in parser_help


@pytest.mark.unit
def test_ops_release_redacts_invalid_duplicate_key_evidence(tmp_path, capsys):
    invalid = tmp_path / "invalid.json"
    invalid.write_text('{"secret":"first","secret":"second"}', encoding="utf-8")
    paths = dict.fromkeys(
        (
            "collector_material",
            "paper_decision_material",
            "paper_marker_material",
            "collector_machines",
            "paper_decision_machines",
            "paper_marker_machines",
            "restore_rehearsal",
            "collector_alert",
            "paper_decision_alert",
            "paper_marker_alert",
        ),
        invalid,
    )

    result = ops_cli._formal_release_command(_release_namespace(paths), env={})
    output = capsys.readouterr().out

    assert result == 1
    assert json.loads(output) == {
        "status": "failed",
        "error_code": "evidence_invalid",
    }
    assert "first" not in output
    assert "second" not in output
