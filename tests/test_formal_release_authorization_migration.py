"""Static contracts for durable image-bound formal activation."""

import hashlib
import os
import re
import time
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from tradingagents.dataflows.media_store import _normalize_pg_url
from tradingagents.formal_activation import (
    RELEASE_RECEIPT_TYPES,
    build_trial_authorization,
    image_attestation,
)
from tradingagents.research_protocol import canonical_json, content_id

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "012_formal_release_authorization.sql"
)


@pytest.fixture(scope="module")
def migration_sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _normalized(value: str) -> str:
    return "\n".join(line.rstrip() for line in value.strip().splitlines())


@pytest.mark.unit
def test_release_authorization_migration_is_atomic_and_schema_pinned(migration_sql):
    assert MIGRATION.name == "012_formal_release_authorization.sql"
    assert migration_sql.count("BEGIN;") == 1
    assert migration_sql.count("COMMIT;") == 1
    assert "SET LOCAL search_path = pg_catalog, public;" in migration_sql
    assert "CREATE TABLE IF NOT EXISTS public.formal_release_receipts" in migration_sql
    assert "CREATE TABLE IF NOT EXISTS public.formal_trial_authorizations" in migration_sql
    assert "UNIQUE (protocol_id, run_id, receipt_type)" in migration_sql
    assert "protocol_id TEXT PRIMARY KEY" in migration_sql
    assert "run_id TEXT NOT NULL UNIQUE" in migration_sql
    assert "authorization_id TEXT NOT NULL UNIQUE" in migration_sql
    assert "pg_catalog.pg_attribute" in migration_sql
    assert "pg_catalog.format_type" in migration_sql
    assert "valid_keys <> 6" in migration_sql
    assert "formal release table primary/unique keys are incomplete" in migration_sql


@pytest.mark.unit
def test_authorization_binds_all_external_release_evidence(migration_sql):
    for receipt_type in (
        "configuration",
        "collector_preflight",
        "paper_decision_preflight",
        "paper_marker_preflight",
        "restore_rehearsal",
        "alert_delivery",
        "runtime_role_decommission",
    ):
        assert f"'{receipt_type}'" in migration_sql
    for binding in (
        "outcome_semantics_id",
        "configuration_manifest_id",
        "collector_configuration_id",
        "paper_decision_configuration_id",
        "paper_marker_configuration_id",
        "collector_build_id",
        "paper_decision_build_id",
        "paper_marker_build_id",
        "image_digest",
        "backup_fingerprint",
        "route_fingerprint",
    ):
        assert binding in migration_sql
    assert "formal_image_build_id(images->'collector')" in migration_sql
    assert "formal_image_build_id(images->'paper_decision')" in migration_sql
    assert "formal_image_build_id(images->'paper_marker')" in migration_sql
    assert "restore rehearsal differs from the empty released trial" in migration_sql
    assert "preflight used a different image" in migration_sql
    assert "formal-restored-cluster-initial-empty-trial-check" in migration_sql
    assert "formal_trial_activity_rows" in migration_sql
    assert "offline_replay_receipt" not in migration_sql
    assert "marker_replay_receipt" not in migration_sql
    assert "client_observed_utc" in migration_sql
    assert "alert delivery used different executable material" in migration_sql
    assert "restore rehearsal does not bind the final completed cycle" in migration_sql
    assert "public.formal_jsonb_content_id" in migration_sql


@pytest.mark.unit
def test_receipt_and_authorization_times_and_ids_are_database_derived(migration_sql):
    assert migration_sql.count(
        "pg_catalog.date_part('epoch', pg_catalog.clock_timestamp())"
    ) == 2
    assert "NEW.created_utc := server_now" in migration_sql
    assert "NEW.authorized_utc := server_now" in migration_sql
    assert "document - 'receipt_id'" in migration_sql
    assert "document - 'authorization_id'" in migration_sql
    assert "public.canonical_jsonb_text" in migration_sql
    assert "pg_catalog.sha256" in migration_sql
    assert "server_now - 86400.0" in migration_sql
    assert "server_now + 300.0" in migration_sql
    assert "restore rehearsal evidence is stale or future-dated" in migration_sql
    assert "alert delivery evidence is stale or future-dated" in migration_sql


@pytest.mark.unit
def test_no_formal_activity_can_precede_or_bypass_authorization(migration_sql):
    authorization_body = migration_sql.split(
        "CREATE OR REPLACE FUNCTION public.enforce_formal_trial_authorization()",
        maxsplit=1,
    )[1].split(
        "COMMENT ON FUNCTION public.enforce_formal_trial_authorization()",
        maxsplit=1,
    )[0]
    activity_tables = {
        "paper_decisions",
        "paper_decision_bundles",
        "paper_events",
        "paper_forecasts",
        "paper_targets",
        "paper_strategy_targets",
        "paper_marks",
        "paper_strategy_marks",
        "paper_price_receipts",
        "paper_price_capture_attempt_events",
        "paper_price_capture_batches",
        "paper_price_integrity_failures",
        "paper_decision_attempt_events",
        "paper_interval_assignments",
    }
    for table in activity_tables:
        assert f"public.{table}" in authorization_body
        assert f"'{table}'" in migration_sql
    assert "formal trial activity predates release authorization" in migration_sql
    assert "formal activity requires exact durable release authorization" in migration_sql
    assert "paper_decision_build_id" in migration_sql
    assert "paper_marker_build_id" in migration_sql
    assert "formal_development_selection_audit" in migration_sql
    assert "NEW.label = 'confirmatory-trial'" in migration_sql
    assert "formal artifact requires durable release authorization" in migration_sql
    assert "formal run label requires durable release authorization" in migration_sql
    assert "JOIN public.paper_run_labels AS label" in authorization_body
    assert "label.label = 'confirmatory-trial'" in authorization_body
    assert "label.created_utc = registry.created_utc" in authorization_body
    assert "pg_catalog.convert_to(label.details_json, 'UTF8')" in authorization_body
    assert "pg_catalog.convert_to(registry.details_json, 'UTF8')" in authorization_body
    assert "formal authorization requires exact validated confirmatory label" in (
        authorization_body
    )


@pytest.mark.unit
def test_runtime_roles_cannot_create_release_authority(migration_sql):
    assert (
        "REVOKE ALL PRIVILEGES ON TABLE public.formal_release_receipts,\n"
        "    public.formal_trial_authorizations FROM PUBLIC"
    ) in migration_sql
    assert "'tradingagents-paper', 'tradingagents-paper-decision'" in migration_sql
    assert "'tradingagents-paper-marker'" in migration_sql
    assert "GRANT SELECT ON TABLE public.formal_release_receipts" in migration_sql
    assert "tradingagents-ingest-v2" in migration_sql
    assert "GRANT INSERT" not in migration_sql
    assert "GRANT UPDATE" not in migration_sql
    assert "GRANT DELETE" not in migration_sql
    for function in (
        "enforce_formal_release_receipt()",
        "formal_image_build_id(JSONB)",
        "enforce_formal_trial_authorization()",
        "enforce_formal_activity_authorization()",
        "enforce_formal_artifact_authorization()",
        "enforce_formal_label_authorization()",
    ):
        assert f"REVOKE ALL ON FUNCTION public.{function} FROM PUBLIC" in migration_sql


@pytest.mark.unit
@pytest.mark.parametrize(
    ("function_name", "contract"),
    [
        ("enforce_formal_release_receipt", "formal-release-receipt.v5"),
        ("formal_image_build_id", "formal-image-attestation.v1"),
        ("enforce_formal_trial_authorization", "formal-release-authorization.v5"),
        ("enforce_formal_activity_authorization", "formal-activity-authorization.v2"),
        ("enforce_formal_artifact_authorization", "formal-artifact-authorization.v1"),
        ("enforce_formal_label_authorization", "formal-label-authorization.v1"),
    ],
)
def test_trigger_function_bodies_have_exact_contract_hashes(
    migration_sql, function_name, contract
):
    match = re.search(
        rf"CREATE OR REPLACE FUNCTION public\.{function_name}\([^)]*\).*?"
        rf"AS \$\$(?P<body>.*?)\$\$;.*?"
        rf"tradingagents\.{re.escape(contract)};"
        rf"normalized-prosrc-sha256=(?P<digest>[0-9a-f]{{64}})",
        migration_sql,
        flags=re.DOTALL,
    )
    assert match is not None
    actual = hashlib.sha256(_normalized(match.group("body")).encode()).hexdigest()
    assert actual == match.group("digest")


def _registry_only_authorization_material(token: str) -> dict:
    analysis = {
        "multiplicity": {
            "confirmatory_family": ["primary"],
            "secondary_family": [],
        },
        "trial_clock": {"holding_intervals": 252},
    }
    protocol_manifest = {
        "fixture": token,
        "analysis": analysis,
        "review_gates": {"20": {"scope": "operations-only"}},
        "strategies": ["champion"],
    }
    protocol_id = content_id(protocol_manifest, prefix="protocol_")
    run_id = f"release-label-guard-{token}"
    decision_base = {"schema_version": 1, "policy": "release-label-guard"}
    decision_semantics = {
        **decision_base,
        "semantic_id": content_id(decision_base, prefix="semantics_"),
    }
    configuration_binding = {
        field: content_id({"token": token, "field": field}, prefix="config_")
        for field in (
            "configuration_manifest_id",
            "collector_configuration_id",
            "paper_decision_configuration_id",
            "paper_marker_configuration_id",
        )
    }
    outcome_semantics_id = "outcome_semantics_" + hashlib.sha256(
        token.encode()
    ).hexdigest()
    registration_base = {
        "schema_version": 2,
        "registration_type": "confirmatory",
        "run_id": run_id,
        "protocol_id": protocol_id,
        "analysis_id": content_id(analysis, prefix="analysis_"),
        "review_gates_id": content_id(
            protocol_manifest["review_gates"], prefix="reviews_"
        ),
        "decision_semantics_id": decision_semantics["semantic_id"],
        "outcome_semantics_id": outcome_semantics_id,
        "configuration_binding": configuration_binding,
        "registered_strategies": ["champion"],
        "confirmatory_family": ["primary"],
        "secondary_family": [],
        "trial_clock": analysis["trial_clock"],
        "parent_run_id": None,
        "outcomes_accessed_before_registration": False,
    }
    registration = {
        **registration_base,
        "registration_id": content_id(registration_base, prefix="registration_"),
    }
    run_config = {
        "engine": "formal-global-v2",
        "protocol_id": protocol_id,
        "decision_semantics": decision_semantics,
        "outcome_semantics_id": outcome_semantics_id,
        "configuration_binding": configuration_binding,
        "trial_registration_id": registration["registration_id"],
    }
    collector = image_attestation(
        app_name="tradagent",
        image_ref=(
            "registry.fly.io/tradagent:"
            "deployment-01KZAE0P4ER12SS2215QXBSN0H"
        ),
        image_digest="sha256:" + "1" * 64,
    )
    paper_decision = image_attestation(
        app_name="tradagent-paper-decision",
        image_ref=(
            "registry.fly.io/tradagent-paper-decision:"
            "deployment-01KZAD8T2KXJJJXAM2JJW8E447"
        ),
        image_digest="sha256:" + "2" * 64,
    )
    paper_marker = image_attestation(
        app_name="tradagent-paper-marker",
        image_ref=(
            "registry.fly.io/tradagent-paper-marker:"
            "deployment-01KZAF9N3MYKKKYCY3KKX9F558"
        ),
        image_digest="sha256:" + "3" * 64,
    )
    receipt_ids = {
        receipt_type: content_id(
            {"token": token, "receipt_type": receipt_type}, prefix="release_"
        )
        for receipt_type in RELEASE_RECEIPT_TYPES
    }
    authorization = build_trial_authorization(
        protocol_id=protocol_id,
        run_id=run_id,
        registration_id=registration["registration_id"],
        outcome_semantics_id=outcome_semantics_id,
        configuration_binding=configuration_binding,
        collector_image=collector,
        paper_decision_image=paper_decision,
        paper_marker_image=paper_marker,
        release_receipt_ids=receipt_ids,
    )
    return {
        "protocol_manifest": protocol_manifest,
        "protocol_id": protocol_id,
        "run_id": run_id,
        "run_config": run_config,
        "registration": registration,
        "authorization": authorization,
    }


@pytest.mark.integration
@pytest.mark.parametrize(
    "label_state", ["missing", "created-time-mismatch", "details-byte-mismatch"]
)
def test_postgres_authorization_requires_exact_confirmatory_label(label_state):
    """Run against a disposable administrator database migrated through 012."""
    url = os.getenv("TRADINGAGENTS_TEST_POSTGRES_ADMIN_URL")
    if not url:
        pytest.skip("TRADINGAGENTS_TEST_POSTGRES_ADMIN_URL is not configured")

    token = f"{label_state}-{uuid.uuid4().hex[:12]}"
    material = _registry_only_authorization_material(token)
    registration = material["registration"]
    authorization = material["authorization"]
    created_utc = time.time()
    engine = create_engine(_normalize_pg_url(url))
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO experiment_registry "
                    "(protocol_id,created_utc,manifest_json) VALUES "
                    "(:protocol_id,:created_utc,:manifest_json)"
                ),
                {
                    "protocol_id": material["protocol_id"],
                    "created_utc": created_utc,
                    "manifest_json": canonical_json(material["protocol_manifest"]),
                },
            )
            conn.execute(
                text(
                    "INSERT INTO paper_runs (run_id,created_utc,config_json) VALUES "
                    "(:run_id,:created_utc,:config_json)"
                ),
                {
                    "run_id": material["run_id"],
                    "created_utc": created_utc,
                    "config_json": canonical_json(material["run_config"]),
                },
            )
            conn.execute(
                text(
                    "INSERT INTO formal_trial_registry "
                    "(protocol_id,run_id,registration_id,created_utc,details_json) "
                    "VALUES (:protocol_id,:run_id,:registration_id,:created_utc,"
                    ":details_json)"
                ),
                {
                    "protocol_id": material["protocol_id"],
                    "run_id": material["run_id"],
                    "registration_id": registration["registration_id"],
                    "created_utc": created_utc,
                    "details_json": canonical_json(registration),
                },
            )

        if label_state != "missing":
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE paper_run_labels DISABLE TRIGGER USER")
                )
                conn.execute(
                    text(
                        "INSERT INTO paper_run_labels "
                        "(run_id,label,created_utc,details_json) VALUES "
                        "(:run_id,'confirmatory-trial',:created_utc,:details_json)"
                    ),
                    {
                        "run_id": material["run_id"],
                        "created_utc": (
                            created_utc + 1.0
                            if label_state == "created-time-mismatch"
                            else created_utc
                        ),
                        "details_json": (
                            " " + canonical_json(registration)
                            if label_state == "details-byte-mismatch"
                            else canonical_json(registration)
                        ),
                    },
                )
                conn.execute(
                    text("ALTER TABLE paper_run_labels ENABLE TRIGGER USER")
                )

        with pytest.raises(
            Exception,
            match="formal authorization requires exact validated confirmatory label",
        ), engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO formal_trial_authorizations "
                    "(protocol_id,run_id,registration_id,authorization_id,"
                    "authorized_utc,outcome_semantics_id,configuration_manifest_id,"
                    "collector_configuration_id,paper_decision_configuration_id,"
                    "paper_marker_configuration_id,collector_build_id,"
                    "paper_decision_build_id,paper_marker_build_id,authorization_json) "
                    "VALUES (:protocol_id,:run_id,:registration_id,:authorization_id,"
                    ":authorized_utc,:outcome_semantics_id,:configuration_manifest_id,"
                    ":collector_configuration_id,:paper_decision_configuration_id,"
                    ":paper_marker_configuration_id,:collector_build_id,"
                    ":paper_decision_build_id,:paper_marker_build_id,:authorization_json)"
                ),
                {
                    "protocol_id": material["protocol_id"],
                    "run_id": material["run_id"],
                    "registration_id": registration["registration_id"],
                    "authorization_id": authorization["authorization_id"],
                    "authorized_utc": 0.0,
                    "outcome_semantics_id": authorization["outcome_semantics_id"],
                    **authorization["configuration_binding"],
                    "collector_build_id": authorization["images"]["collector"][
                        "build_id"
                    ],
                    "paper_decision_build_id": authorization["images"][
                        "paper_decision"
                    ]["build_id"],
                    "paper_marker_build_id": authorization["images"]["paper_marker"][
                        "build_id"
                    ],
                    "authorization_json": canonical_json(authorization),
                },
            )
        with engine.connect() as conn:
            assert conn.execute(
                text(
                    "SELECT count(*) FROM formal_trial_authorizations "
                    "WHERE run_id=:run_id"
                ),
                {"run_id": material["run_id"]},
            ).scalar_one() == 0
    finally:
        engine.dispose()
