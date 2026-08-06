"""Migration-010 contracts and direct PostgreSQL bypass probes."""

from __future__ import annotations

import math
import os
import statistics
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from tradingagents.dataflows.media_store import _normalize_pg_url
from tradingagents.formal_governance import FORMAL_ARTIFACT_SCHEMAS
from tradingagents.paper_trading import PaperStore
from tradingagents.research_protocol import canonical_json, content_id

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "010_formal_artifact_governance.sql"
)


@pytest.fixture(scope="module")
def migration_sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


@pytest.mark.unit
def test_governance_migration_is_atomic_ordered_and_canonical(migration_sql):
    assert MIGRATION.name == "010_formal_artifact_governance.sql"
    assert "after migration 009" in migration_sql
    assert migration_sql.count("BEGIN;") == 1
    assert migration_sql.count("COMMIT;") == 1
    assert "SET LOCAL search_path = pg_catalog, public;" in migration_sql
    assert "NEW.content_json := public.canonical_jsonb_text(content);" in migration_sql
    assert "public.formal_jsonb_content_id(" in migration_sql
    assert "content - 'audit_id', 'selection_audit_'" in migration_sql
    assert "content - 'report_id', 'interim_report_'" in migration_sql
    assert "content - 'report_id', 'formal_report_'" in migration_sql
    assert (
        "content - 'verification_manifest_id', 'formal_verification_'"
        in migration_sql
    )


@pytest.mark.unit
def test_only_development_audit_can_exist_without_primary_scope(migration_sql):
    special = migration_sql.split(
        "IF NEW.artifact_type = 'formal_development_selection_audit' THEN", maxsplit=1
    )[1].split("formal_candidate :=", maxsplit=1)[0]
    assert "'run_id'" not in special.split("expected_keys :=", maxsplit=1)[1].split(
        "];", maxsplit=1
    )[0]
    assert "RETURN NEW;" in special

    governed = migration_sql.split("formal_candidate :=", maxsplit=1)[1]
    assert "primary_count = 0" not in governed
    assert "public.formal_jsonb_has_forbidden_outcome_key(content)" in governed
    assert "public.formal_jsonb_contains_key_value(" in governed
    assert "formal artifact has an unscoped or wrong primary identity" in governed
    for artifact_type in set(FORMAL_ARTIFACT_SCHEMAS) - {
        "formal_development_selection_audit"
    }:
        assert f"'{artifact_type}'" in governed


@pytest.mark.unit
def test_registration_v2_and_final_cross_artifact_bindings_are_exact(migration_sql):
    registration = migration_sql.split(
        "IF NEW.label = 'confirmatory-trial' THEN", maxsplit=1
    )[1].split("gate := CASE NEW.label", maxsplit=1)[0]
    for field in (
        "outcome_semantics_id",
        "configuration_binding",
        "configuration_manifest_id",
        "collector_configuration_id",
        "paper_decision_configuration_id",
        "paper_marker_configuration_id",
    ):
        assert f"'{field}'" in registration
    assert "details ->> 'schema_version' IS DISTINCT FROM '2'" in registration
    assert "details - 'registration_id', 'registration_'" in registration
    assert "^outcome_semantics_[0-9a-f]{64}$" in registration
    assert "^config_[0-9a-f]{24}$" in registration
    for durable_binding in (
        "protocol_manifest -> 'analysis'",
        "protocol_manifest -> 'review_gates'",
        "protocol_manifest -> 'strategies'",
        "protocol_manifest -> 'analysis' -> 'trial_clock'",
        "run_config -> 'decision_semantics'",
        "run_config ->> 'outcome_semantics_id'",
        "run_config -> 'configuration_binding'",
        "run_config ->> 'trial_registration_id'",
    ):
        assert durable_binding in registration

    final_label = migration_sql.split(
        "expected_keys := ARRAY[\n        'schema_version', 'protocol_id', 'review_gate', "
        "'outcome_bundle_id'",
        maxsplit=1,
    )[1]
    assert "'outcome_bundle_'" in final_label
    assert "artifact.content_json::JSONB ->> 'outcome_bundle_id'" in final_label
    assert "artifact.content_json::JSONB ->> 'verification_manifest_id'" in final_label
    assert (
        "artifact.content_json::JSONB\n                    "
        "->> 'verification_manifest_artifact_id'"
        in final_label
    )


@pytest.mark.unit
def test_governance_helpers_and_runtime_mutation_surface_are_locked(migration_sql):
    compact = " ".join(migration_sql.split())
    assert "WHERE pg_catalog.lower(key) = ANY" in migration_sql
    assert "formal operations report contract is invalid" in migration_sql
    assert "formal calibration report contract is invalid" in migration_sql
    assert "formal operational-integrity report contract is invalid" in migration_sql
    assert "pg_catalog.isfinite(" in migration_sql
    for signature in (
        "formal_jsonb_exact_keys(JSONB, TEXT[])",
        "formal_jsonb_has_forbidden_outcome_key(JSONB)",
        "formal_jsonb_contains_key_value(JSONB, TEXT, TEXT)",
        "formal_jsonb_content_id(JSONB, TEXT)",
        "enforce_formal_artifact_governance()",
        "enforce_formal_label_governance()",
    ):
        assert f"REVOKE ALL ON FUNCTION public.{signature} FROM PUBLIC" in compact
    assert "REVOKE UPDATE, DELETE, TRUNCATE ON TABLE public.paper_artifacts" in compact
    assert "REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON TABLE public.paper_artifacts" in (
        compact
    )


def _registration_material(run_id: str, protocol_id: str) -> tuple[dict, dict, dict]:
    analysis = {
        "multiplicity": {
            "confirmatory_family": ["primary"],
            "secondary_family": [],
        },
        "trial_clock": {"holding_intervals": 252},
    }
    review_gates = {"20": {"scope": "operations-only"}}
    protocol_manifest = {
        "fixture_protocol": protocol_id,
        "analysis": analysis,
        "review_gates": review_gates,
        "strategies": ["champion"],
    }
    decision_semantics_base = {
        "schema_version": 1,
        "policy": "direct-postgres-governance-fixture",
    }
    decision_semantics = {
        **decision_semantics_base,
        "semantic_id": content_id(decision_semantics_base, prefix="semantics_"),
    }
    configuration_binding = {
        "collector_configuration_id": "config_" + "2" * 24,
        "paper_decision_configuration_id": "config_" + "3" * 24,
        "paper_marker_configuration_id": "config_" + "4" * 24,
        "configuration_manifest_id": "config_" + "5" * 24,
    }
    base = {
        "schema_version": 2,
        "registration_type": "confirmatory",
        "run_id": run_id,
        "protocol_id": protocol_id,
        "analysis_id": content_id(analysis, prefix="analysis_"),
        "review_gates_id": content_id(review_gates, prefix="reviews_"),
        "decision_semantics_id": decision_semantics["semantic_id"],
        "outcome_semantics_id": "outcome_semantics_" + "1" * 64,
        "configuration_binding": configuration_binding,
        "registered_strategies": ["champion"],
        "confirmatory_family": ["primary"],
        "secondary_family": [],
        "trial_clock": {"holding_intervals": 252},
        "parent_run_id": None,
        "outcomes_accessed_before_registration": False,
    }
    registration = {
        **base,
        "registration_id": content_id(base, prefix="registration_"),
    }
    run_config = {
        "engine": "formal-global-v2",
        "protocol_id": protocol_id,
        "decision_semantics": decision_semantics,
        "outcome_semantics_id": registration["outcome_semantics_id"],
        "configuration_binding": configuration_binding,
        "trial_registration_id": registration["registration_id"],
    }
    return registration, protocol_manifest, run_config


def _development_audit(protocol_id: str) -> dict:
    paths = {
        "candidate-a": [0.01, -0.005, 0.02, -0.01],
        "candidate-b": [0.002, -0.001, 0.003, -0.002],
    }
    base = {
        "schema_version": 1,
        "audit_type": "complete-development-selection-universe",
        "protocol_id": protocol_id,
        "development_sample_id": "development-sample-direct-pg",
        "selected_candidate_id": "candidate-a",
        "candidate_ids": sorted(paths),
        "candidate_sharpes": {
            candidate: statistics.fmean(path)
            / statistics.stdev(path)
            * math.sqrt(252)
            for candidate, path in paths.items()
        },
        "candidate_return_paths": paths,
        "observation_count": 4,
        "periods_per_year": 252,
        "completeness_attested": True,
    }
    return {**base, "audit_id": content_id(base, prefix="selection_audit_")}


def _insert_artifact(
    engine, artifact_type: str, content: dict, *, created_utc: float | None = None
) -> str:
    artifact_id = content_id(
        {"artifact_type": artifact_type, "content": content}, prefix="artifact_"
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO paper_artifacts "
                "(artifact_id,created_utc,artifact_type,content_json) VALUES "
                "(:artifact_id,:created_utc,:artifact_type,:content_json)"
            ),
            {
                "artifact_id": artifact_id,
                "created_utc": time.time() if created_utc is None else created_utc,
                "artifact_type": artifact_type,
                "content_json": canonical_json(content),
            },
        )
    return artifact_id


@pytest.mark.integration
def test_postgres_rejects_pre_registration_nested_and_rehashed_bypasses():
    """Run against a disposable database migrated through 010 (not 012+)."""
    url = os.getenv("TRADINGAGENTS_TEST_POSTGRES_GOVERNANCE_URL")
    if not url:
        pytest.skip("migration-010 PostgreSQL URL is not configured")

    token = uuid.uuid4().hex[:12]
    run_id = f"governance-direct-{token}"
    protocol_id = f"protocol-governance-direct-{token}"
    registration, protocol_manifest, run_config = _registration_material(
        run_id, protocol_id
    )
    engine = create_engine(_normalize_pg_url(url))
    store = PaperStore(url)
    try:
        with pytest.raises(Exception, match="unscoped or wrong primary"):
            _insert_artifact(
                engine,
                "research_note",
                {"payload": {"returns": [0.1]}},
            )
        with pytest.raises(Exception, match="unscoped or wrong primary"):
            _insert_artifact(
                engine,
                "research_note",
                {"payload": {"Strategy_Returns": [0.1]}},
            )
        development_audit = _development_audit(protocol_id)
        empty_audit_base = {
            **{
                key: value
                for key, value in development_audit.items()
                if key != "audit_id"
            },
            "candidate_ids": [],
            "candidate_sharpes": {},
            "candidate_return_paths": {},
        }
        empty_audit = {
            **empty_audit_base,
            "audit_id": content_id(empty_audit_base, prefix="selection_audit_"),
        }
        with pytest.raises(Exception, match="data is incomplete"):
            _insert_artifact(
                engine,
                "formal_development_selection_audit",
                empty_audit,
            )
        _insert_artifact(
            engine,
            "formal_development_selection_audit",
            development_audit,
        )
        with pytest.raises(Exception, match="not exact pre-activity"):
            _insert_artifact(
                engine,
                "formal_development_selection_audit",
                {**development_audit, "run_id": run_id},
            )
        registered_at = time.time()
        store.register_protocol(protocol_id, protocol_manifest, registered_at)
        store.create_run(run_id, run_config, registered_at)
        with pytest.raises(Exception, match="unscoped or wrong primary"):
            _insert_artifact(
                engine,
                "research_note",
                {"payload": {"run_id": run_id, "note": "nested-only scope"}},
            )

        tamper_run_id = f"{run_id}-semantic-tamper"
        tamper_protocol_id = f"{protocol_id}-semantic-tamper"
        forged, tamper_manifest, tamper_run_config = _registration_material(
            tamper_run_id, tamper_protocol_id
        )
        forged["analysis_id"] = "analysis_" + "f" * 24
        assert forged["analysis_id"] != content_id(
            tamper_manifest["analysis"], prefix="analysis_"
        )
        forged["registration_id"] = content_id(
            {key: value for key, value in forged.items() if key != "registration_id"},
            prefix="registration_",
        )
        tamper_run_config["trial_registration_id"] = forged["registration_id"]
        store.register_protocol(tamper_protocol_id, tamper_manifest, registered_at)
        store.create_run(tamper_run_id, tamper_run_config, registered_at)
        with pytest.raises(Exception, match="confirmatory label is not exact"):
            store.register_confirmatory_trial(tamper_run_id, time.time(), forged)
        assert store.confirmatory_registration(tamper_run_id) is None

        store.register_confirmatory_trial(run_id, time.time(), registration)

        reserved_at = time.time()
        identity = {
            "scope": "formal-global-v2",
            "run_id": run_id,
            "decision_date": "2026-08-05",
            "ordinal": 1,
            "stage": "champion",
            "provider": "openai",
            "requested_model": "gpt-5",
            "input_bundle_id": "input_fixture",
        }
        decision_key = f"llm:formal-global-v2:decision:{run_id}:2026-08-05"
        daily_key = (
            f"llm:formal-global-v2:protocol:{protocol_id}:utc-day:2026-08-06"
        )
        reservation = {
            "schema_version": 2,
            "invocation_id": content_id(identity, prefix="invocation_"),
            **identity,
            "prompt_id": "prompt_fixture",
            "prompt_bytes": 10,
            "max_prompt_bytes": 100,
            "max_completion_tokens": 20,
            "max_calls_per_decision": 3,
            "max_calls_per_utc_day": 3,
            "decision_counter_key": decision_key,
            "daily_counter_key": daily_key,
            "utc_day": "2026-08-06",
            "reserved_utc": datetime.fromtimestamp(
                reserved_at, timezone.utc
            ).isoformat(),
            "reservation_counts": {decision_key: 1, daily_key: 1},
        }
        with pytest.raises(Exception, match="reservation counters are invalid"):
            _insert_artifact(
                engine,
                "llm_invocation_reserved",
                {**reservation, "reserved_utc": "infinity"},
                created_utc=reserved_at,
            )
        reservation_artifact_id = _insert_artifact(
            engine,
            "llm_invocation_reserved",
            reservation,
            created_utc=reserved_at,
        )
        completed_at = reserved_at + 1.0
        result = {
            "schema_version": 2,
            "invocation_id": reservation["invocation_id"],
            **identity,
            "reservation_artifact_id": reservation_artifact_id,
            "status": "failed",
            "error_type": "RuntimeError",
            "completed_utc": datetime.fromtimestamp(
                completed_at, timezone.utc
            ).isoformat(),
            "elapsed_ms": 1000,
        }
        with pytest.raises(Exception, match="result fields are malformed"):
            _insert_artifact(
                engine,
                "llm_invocation_result",
                {**result, "completed_utc": "infinity"},
                created_utc=completed_at,
            )
        _insert_artifact(
            engine, "llm_invocation_result", result, created_utc=completed_at
        )
        duplicate_result = {**result, "error_type": "TimeoutError"}
        with pytest.raises(Exception, match="already has a result"):
            _insert_artifact(
                engine,
                "llm_invocation_result",
                duplicate_result,
                created_utc=completed_at + 1.0,
            )
        wrong_identity = {**result, "stage": "without_public_reaction"}
        wrong_identity["invocation_id"] = content_id(
            {
                key: wrong_identity[key]
                for key in (
                    "scope",
                    "run_id",
                    "decision_date",
                    "ordinal",
                    "stage",
                    "provider",
                    "requested_model",
                    "input_bundle_id",
                )
            },
            prefix="invocation_",
        )
        with pytest.raises(Exception, match="not bound to its reservation"):
            _insert_artifact(
                engine,
                "llm_invocation_result",
                wrong_identity,
                created_utc=completed_at + 1.0,
            )
        second_identity = {**identity, "ordinal": 2, "stage": "market_only"}
        second_reservation = {
            **reservation,
            **second_identity,
            "invocation_id": content_id(second_identity, prefix="invocation_"),
            "reservation_counts": {decision_key: 2, daily_key: 2},
        }
        second_reservation_id = _insert_artifact(
            engine,
            "llm_invocation_reserved",
            second_reservation,
            created_utc=reserved_at,
        )
        backdated = {
            **result,
            **second_identity,
            "invocation_id": second_reservation["invocation_id"],
            "reservation_artifact_id": second_reservation_id,
            "completed_utc": datetime.fromtimestamp(
                reserved_at - 1.0, timezone.utc
            ).isoformat(),
        }
        with pytest.raises(Exception, match="not bound to its reservation"):
            _insert_artifact(
                engine,
                "llm_invocation_result",
                backdated,
                created_utc=reserved_at - 1.0,
            )

        with pytest.raises(Exception, match="unscoped or wrong primary|not allowlisted"):
            _insert_artifact(
                engine,
                "research_note",
                {"payload": {"strategy_returns": [0.1], "run_id": run_id}},
            )
        with pytest.raises(Exception, match="forbidden outcome key"), engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO paper_run_labels "
                    "(run_id,label,created_utc,details_json) VALUES "
                    "(:run_id,'incident',:created_utc,:details_json)"
                ),
                {
                    "run_id": run_id,
                    "created_utc": time.time(),
                    "details_json": canonical_json(
                        {"payload": {"strategy_returns": [0.1]}}
                    ),
                },
            )

        with engine.begin() as conn:
            for interval_index in range(1, 21):
                conn.execute(
                    text(
                        "INSERT INTO paper_interval_assignments "
                        "(run_id,interval_index,from_session_date,session_date,"
                        "scheduled_decision_date,created_utc,disposition,"
                        "applied_target_decision_date,return_vector_id) VALUES "
                        "(:run_id,:interval_index,:from_session_date,:session_date,"
                        ":scheduled_decision_date,:created_utc,"
                        "'carry_forward_missing_decision',NULL,:return_vector_id)"
                    ),
                    {
                        "run_id": run_id,
                        "interval_index": interval_index,
                        "from_session_date": f"2026-07-{interval_index:02d}",
                        "session_date": f"2026-08-{interval_index:02d}",
                        "scheduled_decision_date": f"2026-07-{interval_index:02d}",
                        "created_utc": time.time() + interval_index,
                        "return_vector_id": f"return-vector-{interval_index}",
                    },
                )

        report_base = {
            "schema_version": 1,
            "report_type": "global-event-v2-operations-only-interim",
            "protocol_id": protocol_id,
            "run_id": run_id,
            "registration_id": registration["registration_id"],
            "review_gate": 19.6,
            "interim": True,
            "scope": "operations-only",
            "completed_intervals": 19.6,
            "interpretation": "operations-only integrity review",
            "outcomes_read": False,
            "assignment_completeness": {},
            "attempt_operations": {},
            "mark_completeness": {},
            "receipt_operations": {},
        }
        fractional_report = {
            **report_base,
            "report_id": content_id(report_base, prefix="interim_report_"),
        }
        with pytest.raises(Exception, match="outside its exact gate"):
            _insert_artifact(
                engine,
                "formal_interim_operations_report",
                fractional_report,
            )

        malformed_base = {
            **report_base,
            "review_gate": 20,
            "completed_intervals": 20,
            "outcomes_read": True,
        }
        malformed_report = {
            **malformed_base,
            "report_id": content_id(malformed_base, prefix="interim_report_"),
        }
        with pytest.raises(Exception, match="operations report contract is invalid"):
            _insert_artifact(
                engine,
                "formal_interim_operations_report",
                malformed_report,
            )
    finally:
        store.close()
        engine.dispose()
