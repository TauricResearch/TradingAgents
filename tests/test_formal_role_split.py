"""Least-privilege and forced-RLS contracts for formal runtime roles."""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from tradingagents.dataflows.media_store import _normalize_pg_url
from tradingagents.formal_roles import (
    DECISION_ARTIFACT_TYPES,
    DECISION_HELD_WEIGHT_POLICY,
    DECISION_INSERT_TABLES,
    DECISION_ROLE,
    DECISION_SELECT_TABLES,
    DECISION_SLOT_PROJECTION_SQL,
    DECISION_WEIGHT_PROJECTION_SQL,
    LEGACY_PAPER_ROLE,
    MARKER_INSERT_TABLES,
    MARKER_ROLE,
    MARKER_SELECT_TABLES,
    OUTCOME_TABLES,
    PREAUTHORIZATION_ACTIVITY_TABLES,
    PROTECTED_TABLES,
    ROLE_SPLIT_CONTRACT_ID,
    RUNTIME_HEALTH_PROJECTION_SQL,
    RUNTIME_HEARTBEAT_EVENTS,
    RUNTIME_HEARTBEAT_SQL,
    SCHEMA_ADMIN_LOGIN,
    SCHEMA_ADMIN_ROLE,
    FormalRoleContractError,
    build_legacy_role_decommission_receipt,
    is_formal_schema_admin_identity,
    runtime_role_decommission_release_payload,
    validate_decision_slot_projection,
    validate_runtime_role_preflight,
)
from tradingagents.research_protocol import content_id

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "013_formal_runtime_role_split.sql"
)


@pytest.fixture(scope="module")
def migration_sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


@pytest.mark.unit
def test_role_matrix_has_no_decision_outcome_or_marker_decision_write_path():
    assert OUTCOME_TABLES.isdisjoint(DECISION_SELECT_TABLES)
    assert OUTCOME_TABLES.isdisjoint(DECISION_INSERT_TABLES)
    assert MARKER_INSERT_TABLES.isdisjoint(DECISION_INSERT_TABLES)
    assert "paper_artifacts" not in MARKER_SELECT_TABLES
    assert "paper_artifacts" not in MARKER_INSERT_TABLES
    assert "paper_forecasts" not in MARKER_SELECT_TABLES
    assert "paper_forecasts" not in MARKER_INSERT_TABLES
    assert "formal_llm_budget_counters" not in DECISION_SELECT_TABLES
    assert "formal_llm_budget_counters" not in MARKER_SELECT_TABLES
    assert {
        "llm_invocation_reserved",
        "llm_invocation_result",
        "global_forecast_bundle",
    } == DECISION_ARTIFACT_TYPES
    assert {"success", "failure", "paused"} == RUNTIME_HEARTBEAT_EVENTS
    assert "formal_runtime_heartbeat_events" in PROTECTED_TABLES
    assert "formal_runtime_heartbeat_events" not in DECISION_SELECT_TABLES
    assert "formal_runtime_heartbeat_events" not in MARKER_SELECT_TABLES
    assert {
        "paper_decision_attempt_events",
        "paper_decision_bundles",
        "paper_decisions",
        "paper_events",
        "paper_forecasts",
        "paper_interval_assignments",
        "paper_marks",
        "paper_price_capture_attempt_events",
        "paper_price_capture_batches",
        "paper_price_integrity_failures",
        "paper_price_receipts",
        "paper_strategy_marks",
        "paper_strategy_targets",
        "paper_targets",
    } == PREAUTHORIZATION_ACTIVITY_TABLES


@pytest.mark.unit
def test_role_contract_identity_is_frozen():
    assert ROLE_SPLIT_CONTRACT_ID == "role_contract_a9f9c18629547e56b6330eb1"
    receipt = build_legacy_role_decommission_receipt()
    assert receipt == {
        "schema_version": 1,
        "contract_id": ROLE_SPLIT_CONTRACT_ID,
        "legacy_role": LEGACY_PAPER_ROLE,
        "decision_role": DECISION_ROLE,
        "marker_role": MARKER_ROLE,
        "decommission_id": "decommission_aa29f46dfa70a6b14d79edeb",
    }
    assert runtime_role_decommission_release_payload() == {
        "passed": True,
        "decommission_id": receipt["decommission_id"],
        "legacy_role": LEGACY_PAPER_ROLE,
        "decision_role": DECISION_ROLE,
        "marker_role": MARKER_ROLE,
    }


@pytest.mark.unit
def test_schema_admin_identity_accepts_direct_and_exact_fly_default_role_only():
    membership = {
        "current_is_schema_admin": True,
        "session_is_schema_admin": True,
    }
    assert is_formal_schema_admin_identity(
        current_role="release-admin",
        session_role="release-admin",
        **membership,
    )
    assert is_formal_schema_admin_identity(
        current_role=SCHEMA_ADMIN_ROLE,
        session_role=SCHEMA_ADMIN_LOGIN,
        **membership,
    )
    assert not is_formal_schema_admin_identity(
        current_role=SCHEMA_ADMIN_ROLE,
        session_role="fly-user",
        **membership,
    )
    assert not is_formal_schema_admin_identity(
        current_role=SCHEMA_ADMIN_ROLE,
        session_role=SCHEMA_ADMIN_LOGIN,
        current_is_schema_admin=True,
        session_is_schema_admin=False,
    )


@pytest.mark.unit
def test_migration_forces_rls_on_every_protected_table(migration_sql):
    assert MIGRATION.name == "013_formal_runtime_role_split.sql"
    assert migration_sql.count("BEGIN;") == 1
    assert migration_sql.count("COMMIT;") == 1
    assert "SET LOCAL search_path = pg_catalog, public;" in migration_sql
    assert "ENABLE ROW LEVEL SECURITY" in migration_sql
    assert "FORCE ROW LEVEL SECURITY" in migration_sql
    for table in PROTECTED_TABLES:
        assert f"'{table}'" in migration_sql
    assert "formal_decision_select" in migration_sql
    assert "formal_marker_select" in migration_sql
    assert "formal_role_policy_contracts" in migration_sql
    assert "formal_role_policy_contract_matches" in migration_sql
    assert "INSERT 0" not in migration_sql


@pytest.mark.unit
def test_collector_has_only_nonpaper_activation_projection(migration_sql):
    assert not re.search(
        r"GRANT\s+(?:SELECT|INSERT|UPDATE|DELETE|TRUNCATE)[^;]+"
        r"(?:tradingagents-ingest-v2|tradingagents-ingest)",
        migration_sql,
        flags=re.DOTALL,
    )
    collector_grant_block = migration_sql.split(
        "FOREACH role_name IN ARRAY ARRAY['tradingagents-ingest-v2'",
        maxsplit=1,
    )[1].split("END\n$$;", maxsplit=1)[0]
    assert "GRANT EXECUTE ON FUNCTION" in collector_grant_block
    assert "formal_collector_release_projection" in collector_grant_block
    projection = migration_sql.split(
        "CREATE OR REPLACE FUNCTION public.formal_collector_release_projection",
        maxsplit=1,
    )[1].split("REVOKE ALL ON FUNCTION", maxsplit=1)[0]
    for forbidden in (
        "paper_marks",
        "paper_strategy_marks",
        "paper_targets",
        "paper_artifacts",
        "paper_forecasts",
        "period_return",
        "benchmark_period_return",
        "nav",
    ):
        assert forbidden not in projection


@pytest.mark.unit
def test_decision_position_projection_exposes_lineage_but_no_outcomes(migration_sql):
    projection = migration_sql.split(
        "CREATE OR REPLACE FUNCTION public.formal_decision_weight_projection",
        maxsplit=1,
    )[1].split(
        "-- Marker consumes only frozen target intent", maxsplit=1
    )[0]
    for strategy in (
        "global_events_champion",
        "global_events_without_public_reaction",
        "public_reaction_only",
        "market_only",
        "equal_weight",
        "momentum",
        "stale_events_negative_control",
        "shuffled_events_negative_control",
    ):
        assert f"'{strategy}'" in projection
    for required in (
        "weights_json",
        "source_kind",
        "source_session_date",
        "source_decision_date",
        "initial_zero",
        "target_decision_date",
    ):
        assert required in projection
    for forbidden in (
        "period_return",
        "benchmark_period_return",
        "benchmark_nav",
        "raw_open",
        "adjusted_open",
        "trading_cost",
        "borrow_cost",
        "turnover",
    ):
        assert forbidden not in projection
    assert "formal_decision_weight_projection(:run_id)" in DECISION_WEIGHT_PROJECTION_SQL
    assert DECISION_HELD_WEIGHT_POLICY["classification"] == (
        "point-in-time-operational-state"
    )
    assert "exact-preregistered-turnover" in DECISION_HELD_WEIGHT_POLICY["purpose"]
    assert "latest champion-mark session" in migration_sql
    assert "coherent.strategy_ids IS NOT DISTINCT FROM" in projection


@pytest.mark.unit
def test_decision_slot_projection_returns_only_frozen_eligibility(migration_sql):
    projection = migration_sql.split(
        "CREATE OR REPLACE FUNCTION public.formal_decision_slot_projection",
        maxsplit=1,
    )[1].split("-- Marker consumes only frozen target intent", maxsplit=1)[0]
    returns = projection.split("RETURNS TABLE", maxsplit=1)[1].split(
        ")\nLANGUAGE", maxsplit=1
    )[0]
    for required in (
        "decision_chain_valid",
        "horizon_open",
        "slot_is_next",
        "terminal_price_integrity_failure",
        "eligible_for_requested_slot",
        "expected.mark_count = expected.completed_intervals + 1",
        "ledger.completed_intervals < 251",
    ):
        assert required in projection
    assert "marker carry-forward rows" in migration_sql
    for forbidden in (
        "period_return",
        "benchmark_period_return",
        "weights_json",
        "opens_json",
        "nav",
        "turnover",
        "interval_index",
        "bundle_count",
    ):
        assert forbidden not in returns
    assert "formal_decision_slot_projection(" in DECISION_SLOT_PROJECTION_SQL


@pytest.mark.unit
def test_heartbeat_is_server_owned_append_only_and_outcome_free(migration_sql):
    recorder = migration_sql.split(
        "CREATE OR REPLACE FUNCTION public.record_formal_runtime_heartbeat",
        maxsplit=1,
    )[1].split("DROP TRIGGER IF EXISTS govern_formal_runtime_heartbeat_event", maxsplit=1)[0]
    health = migration_sql.split(
        "CREATE OR REPLACE FUNCTION public.formal_runtime_latest_health_projection",
        maxsplit=1,
    )[1].split("REVOKE ALL ON FUNCTION", maxsplit=1)[0]
    assert "pg_catalog.clock_timestamp()" in migration_sql
    assert "pg_catalog.current_setting('role') IS DISTINCT FROM 'none'" in migration_sql
    assert "formal runtime heartbeat events are append-only" in migration_sql
    assert "poll_state" not in recorder
    assert "p_observed" not in recorder
    assert "run_id" not in health.split("RETURNS TABLE", maxsplit=1)[1].split(
        ")\nLANGUAGE", maxsplit=1
    )[0]
    assert "latest_success_utc" in health
    assert "latest_failure_utc" in health
    assert "latest_paused_utc" in health
    assert ":runtime_build_id" in RUNTIME_HEARTBEAT_SQL
    assert "latest_success_utc" in RUNTIME_HEALTH_PROJECTION_SQL


@pytest.mark.unit
def test_legacy_decommission_is_irreversible_server_owned_and_activation_blocking(
    migration_sql,
):
    assert "CREATE TABLE public.formal_role_split_decommissions" in migration_sql
    assert "decommission_[0-9a-f]{24}" in migration_sql
    assert "document - 'decommission_id'" in migration_sql
    assert "pg_catalog.clock_timestamp()" in migration_sql
    assert "formal role decommission receipts are append-only" in migration_sql
    assert "REVOKE INSERT, UPDATE, DELETE, TRUNCATE" in migration_sql
    assert "REVOKE EXECUTE ON FUNCTION" in migration_sql
    assert "formal authorization requires exact decommissioned role split" in migration_sql
    assert "BEFORE INSERT ON public.formal_trial_authorizations" in migration_sql
    assert "formal_role_split_catalog_ready()" in migration_sql
    assert "->>'runtime_role_decommission'" in migration_sql
    assert "receipt.receipt_type = 'runtime_role_decommission'" in migration_sql
    assert "release_receipt->'payload'->>'decommission_id'" in migration_sql
    assert "IS DISTINCT FROM durable_decommission_id" in migration_sql
    for column in (
        "collector_configuration_id",
        "paper_decision_configuration_id",
        "paper_marker_configuration_id",
        "collector_build_id",
        "paper_decision_build_id",
        "paper_marker_build_id",
    ):
        assert f"'{column}'" in migration_sql


@pytest.mark.unit
def test_runtime_preflight_requires_exact_login_not_set_role():
    valid = {
        "current_role": DECISION_ROLE,
        "session_role": DECISION_ROLE,
        "contract_id": ROLE_SPLIT_CONTRACT_ID,
        "ready": True,
        "legacy_decommissioned": True,
        "policy_contract_matches": True,
    }
    assert validate_runtime_role_preflight(valid, expected_role=DECISION_ROLE) == valid
    with pytest.raises(FormalRoleContractError, match="exact login role"):
        validate_runtime_role_preflight(
            {**valid, "session_role": "schema-admin"}, expected_role=DECISION_ROLE
        )
    with pytest.raises(FormalRoleContractError, match="legacy combined"):
        validate_runtime_role_preflight(
            {**valid, "legacy_decommissioned": False}, expected_role=DECISION_ROLE
        )
    with pytest.raises(FormalRoleContractError, match="policy contract"):
        validate_runtime_role_preflight(
            {**valid, "policy_contract_matches": False}, expected_role=DECISION_ROLE
        )
    with pytest.raises(ValueError, match="not allowlisted"):
        validate_runtime_role_preflight(valid, expected_role=LEGACY_PAPER_ROLE)


@pytest.mark.unit
def test_decision_slot_validator_is_exact_and_fail_closed():
    valid = {
        "run_id": "formal-run",
        "protocol_id": "protocol_id",
        "registration_id": "registration_id",
        "authorization_id": "authorization_id",
        "paper_decision_build_id": "decision_build_id",
        "paper_decision_configuration_id": "decision_configuration_id",
        "requested_decision_date": "2026-08-06",
        "requested_entry_date": "2026-08-07",
        "decision_chain_valid": True,
        "horizon_open": True,
        "slot_is_next": True,
        "terminal_price_integrity_failure": False,
        "eligible_for_requested_slot": True,
    }
    assert validate_decision_slot_projection(
        valid,
        expected_run_id="formal-run",
        expected_decision_date="2026-08-06",
        expected_entry_date="2026-08-07",
    ) == valid

    for field, message in (
        ("decision_chain_valid", "target chain"),
        ("horizon_open", "horizon"),
        ("slot_is_next", "next frozen slot"),
        ("eligible_for_requested_slot", "not eligible"),
    ):
        with pytest.raises(FormalRoleContractError, match=message):
            validate_decision_slot_projection(
                {**valid, field: False},
                expected_run_id="formal-run",
                expected_decision_date="2026-08-06",
                expected_entry_date="2026-08-07",
            )
    with pytest.raises(FormalRoleContractError, match="price-integrity"):
        validate_decision_slot_projection(
            {**valid, "terminal_price_integrity_failure": True},
            expected_run_id="formal-run",
            expected_decision_date="2026-08-06",
            expected_entry_date="2026-08-07",
        )
    with pytest.raises(FormalRoleContractError, match="wrong identity"):
        validate_decision_slot_projection(
            valid,
            expected_run_id="another-run",
            expected_decision_date="2026-08-06",
            expected_entry_date="2026-08-07",
        )
    with pytest.raises(FormalRoleContractError, match="wrong schema"):
        validate_decision_slot_projection(
            {**valid, "unexpected": True},
            expected_run_id="formal-run",
            expected_decision_date="2026-08-06",
            expected_entry_date="2026-08-07",
        )


@pytest.mark.unit
def test_schema_admin_owns_forced_rls_and_definer_surfaces(migration_sql):
    assert "exact MPG schema_admin NOLOGIN owner role is required" in migration_sql
    assert "ALTER TABLE public.%I OWNER TO schema_admin" in migration_sql
    assert "ALTER FUNCTION %s OWNER TO schema_admin" in migration_sql
    assert "CREATE POLICY formal_definer_select" in migration_sql
    assert "CREATE POLICY formal_definer_insert" in migration_sql
    assert "CREATE POLICY formal_definer_update" in migration_sql
    assert "actual_function_owner IS DISTINCT FROM 'schema_admin'" in migration_sql
    assert "class.relowner <> schema_admin_oid" in migration_sql
    assert "runtime role must not inherit the formal definer owner" in migration_sql


@pytest.mark.unit
@pytest.mark.parametrize(
    ("function_name", "contract"),
    [
        ("formal_decision_artifact_type_allowed", "formal-decision-artifact-filter.v1"),
        ("formal_legacy_transition_open", "formal-legacy-transition.v1"),
        ("formal_decision_state_projection", "formal-decision-state-projection.v1"),
        ("formal_decision_weight_projection", "formal-decision-weight-projection.v1"),
        ("formal_decision_slot_projection", "formal-decision-slot-projection.v1"),
        ("formal_marker_target_projection", "formal-marker-target-projection.v1"),
        (
            "formal_collector_release_projection",
            "formal-collector-release-projection.v1",
        ),
        (
            "enforce_formal_runtime_heartbeat_event",
            "formal-runtime-heartbeat-trigger.v1",
        ),
        (
            "record_formal_runtime_heartbeat",
            "formal-runtime-heartbeat-recorder.v1",
        ),
        (
            "formal_runtime_latest_health_projection",
            "formal-runtime-health-projection.v1",
        ),
        ("formal_role_policy_contract_matches", "formal-role-policy-audit.v1"),
        ("formal_role_split_catalog_ready", "formal-role-split-readiness.v1"),
        ("formal_role_split_preflight", "formal-role-split-preflight.v1"),
        ("enforce_formal_role_decommission", "formal-role-decommission-trigger.v1"),
        (
            "enforce_formal_role_split_authorization",
            "formal-role-authorization-guard.v1",
        ),
    ],
)
def test_role_function_bodies_have_exact_contract_hashes(
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
    normalized = "\n".join(
        line.rstrip() for line in match.group("body").strip().splitlines()
    )
    assert hashlib.sha256(normalized.encode()).hexdigest() == match.group("digest")


@pytest.mark.integration
def test_postgres_set_role_cannot_cross_decision_marker_or_collector_boundary():
    admin_url = os.getenv("TRADINGAGENTS_TEST_POSTGRES_ADMIN_URL")
    if not admin_url:
        pytest.skip("TRADINGAGENTS_TEST_POSTGRES_ADMIN_URL is not configured")
    engine = create_engine(_normalize_pg_url(admin_url))
    token = uuid.uuid4().hex
    run_id = f"role-split-test-{token}"
    forecast_ticker = f"R{token[:8]}"
    try:
        with engine.connect() as conn, conn.begin():
            conn.execute(
                text(
                    "INSERT INTO paper_runs(run_id,created_utc,config_json) "
                    "VALUES (:run_id,1.0,'{\"engine\":\"role-split-test\"}')"
                ),
                {"run_id": run_id},
            )
            conn.execute(
                text(
                    "INSERT INTO paper_marks(run_id,session_date,captured_utc,nav,"
                    "benchmark_nav,period_return,benchmark_period_return,turnover,"
                    "trading_cost,borrow_cost,weights_json,opens_json,benchmark_open,"
                    "target_decision_date) VALUES "
                    "(:run_id,'2099-01-02',1.0,123.0,100.0,0.23,0.0,0.0,0.0,0.0,"
                    "'{}','{}',100.0,NULL)"
                ),
                {"run_id": run_id},
            )
            conn.execute(
                text(
                    "INSERT INTO paper_forecasts(run_id,decision_date,ticker,payload_json) "
                    "VALUES (:run_id,'2099-01-01',:ticker,'{}')"
                ),
                {"run_id": run_id, "ticker": forecast_ticker},
            )

            conn.execute(text(f'SET LOCAL ROLE "{DECISION_ROLE}"'))
            assert conn.execute(
                text("SELECT count(*) FROM paper_marks WHERE run_id=:run_id"),
                {"run_id": run_id},
            ).scalar_one() == 0
            assert conn.execute(
                text("SELECT count(*) FROM paper_forecasts WHERE run_id=:run_id"),
                {"run_id": run_id},
            ).scalar_one() == 1
            assert conn.execute(
                text("SELECT count(*) FROM formal_llm_budget_counters")
            ).scalar_one() == 0
            with (
                pytest.raises(DBAPIError, match="permission denied|row-level security"),
                conn.begin_nested(),
            ):
                conn.execute(
                    text(
                        "INSERT INTO paper_marks(run_id,session_date,captured_utc,"
                        "nav,benchmark_nav,period_return,benchmark_period_return,"
                        "turnover,trading_cost,borrow_cost,weights_json,opens_json,"
                        "benchmark_open,target_decision_date) VALUES "
                        "(:run_id,'2099-01-03',1,1,1,0,0,0,0,0,'{}','{}',1,NULL)"
                    ),
                    {"run_id": run_id},
                )
            conn.execute(text("RESET ROLE"))

            conn.execute(text(f'SET LOCAL ROLE "{MARKER_ROLE}"'))
            assert conn.execute(
                text("SELECT count(*) FROM paper_marks WHERE run_id=:run_id"),
                {"run_id": run_id},
            ).scalar_one() == 1
            for table in ("paper_forecasts", "paper_artifacts"):
                assert conn.execute(
                    text(f"SELECT count(*) FROM {table}")
                ).scalar_one() == 0
            with (
                pytest.raises(DBAPIError, match="permission denied|row-level security"),
                conn.begin_nested(),
            ):
                conn.execute(
                    text(
                        "INSERT INTO paper_forecasts"
                        "(run_id,decision_date,ticker,payload_json) VALUES "
                        "(:run_id,'2099-01-02','FORBIDDEN','{}')"
                    ),
                    {"run_id": run_id},
                )
            conn.execute(text("RESET ROLE"))

            if conn.execute(
                text("SELECT 1 FROM pg_roles WHERE rolname='tradingagents-ingest-v2'")
            ).first():
                conn.execute(text('SET LOCAL ROLE "tradingagents-ingest-v2"'))
                for table in ("paper_runs", "paper_forecasts", "paper_marks"):
                    assert conn.execute(
                        text(f"SELECT count(*) FROM {table}")
                    ).scalar_one() == 0
                conn.execute(text("RESET ROLE"))

            assert conn.execute(
                text("SELECT public.formal_role_policy_contract_matches()")
            ).scalar_one() is True
            conn.execute(
                text(
                    f"CREATE POLICY formal_test_tamper ON paper_marks FOR SELECT "
                    f'TO "{DECISION_ROLE}" USING (true)'
                )
            )
            assert conn.execute(
                text("SELECT public.formal_role_policy_contract_matches()")
            ).scalar_one() is False
            conn.execute(text("DROP POLICY formal_test_tamper ON paper_marks"))
            assert conn.execute(
                text("SELECT public.formal_role_policy_contract_matches()")
            ).scalar_one() is True
    finally:
        engine.dispose()


@pytest.mark.integration
def test_postgres_formal_slot_horizon_and_heartbeat_lifecycle():
    admin_url = os.getenv("TRADINGAGENTS_TEST_POSTGRES_FIXTURE_URL")
    if not admin_url:
        pytest.skip("TRADINGAGENTS_TEST_POSTGRES_FIXTURE_URL is not configured")

    engine = create_engine(_normalize_pg_url(admin_url))
    token = uuid.uuid4().hex
    run_id = f"formal-role-lifecycle-{token}"
    protocol_id = f"formal-role-protocol-{token}"
    strategies = [
        "global_events_champion",
        "global_events_without_public_reaction",
        "public_reaction_only",
        "market_only",
        "equal_weight",
        "momentum",
        "stale_events_negative_control",
        "shuffled_events_negative_control",
    ]

    def frozen_id(prefix: str, label: str) -> str:
        return content_id({"test": token, "identity": label}, prefix=prefix)

    registration_id = frozen_id("registration_", "registration")
    authorization_id = frozen_id("activation_", "authorization")
    configuration_manifest_id = frozen_id("config_", "manifest")
    collector_configuration_id = frozen_id("config_", "collector")
    decision_configuration_id = frozen_id("config_", "decision")
    marker_configuration_id = frozen_id("config_", "marker")
    collector_build_id = frozen_id("build_", "collector")
    decision_build_id = frozen_id("build_", "decision")
    marker_build_id = frozen_id("build_", "marker")
    outcome_semantics_id = "outcome_semantics_" + hashlib.sha256(
        f"{token}:outcome-semantics".encode()
    ).hexdigest()
    first_decision = date(2090, 1, 2)
    first_entry = first_decision + timedelta(days=1)
    weights_json = '{"ACME":1.0}'
    opens_json = '{"ACME":10.0}'
    fixture_tables = (
        "formal_trial_registry",
        "paper_run_labels",
        "formal_trial_authorizations",
        "paper_decision_attempt_events",
        "paper_decision_bundles",
        "paper_targets",
        "paper_strategy_targets",
        "paper_marks",
        "paper_strategy_marks",
        "paper_interval_assignments",
    )

    def set_user_triggers(conn, *, enabled: bool) -> None:
        action = "ENABLE" if enabled else "DISABLE"
        for table in fixture_tables:
            conn.execute(text(f"ALTER TABLE public.{table} {action} TRIGGER USER"))

    def set_session_authorization(conn, role: str) -> None:
        conn.execute(text(f'SET SESSION AUTHORIZATION "{role}"'))

    def reset_session_authorization(conn) -> None:
        conn.execute(text("RESET SESSION AUTHORIZATION"))

    def projected_slot(conn, decision_date: date, entry_date: date) -> dict:
        return dict(
            conn.execute(
                text(DECISION_SLOT_PROJECTION_SQL),
                {
                    "run_id": run_id,
                    "decision_date": decision_date.isoformat(),
                    "entry_date": entry_date.isoformat(),
                },
            )
            .mappings()
            .one()
        )

    try:
        with engine.connect() as conn, conn.begin():
            if conn.execute(
                text("SELECT count(*) FROM public.formal_role_split_decommissions")
            ).scalar_one() == 0:
                decommission = build_legacy_role_decommission_receipt()
                conn.execute(
                    text(
                        "INSERT INTO public.formal_role_split_decommissions("
                        "decommission_id,legacy_role,decommissioned_utc,contract_id,"
                        "details_json) VALUES ("
                        ":decommission_id,:legacy_role,0,:contract_id,:details_json)"
                    ),
                    {
                        "decommission_id": decommission["decommission_id"],
                        "legacy_role": decommission["legacy_role"],
                        "contract_id": decommission["contract_id"],
                        "details_json": json.dumps(
                            decommission, sort_keys=True, separators=(",", ":")
                        ),
                    },
                )
            assert conn.execute(
                text("SELECT public.formal_role_split_catalog_ready()")
            ).scalar_one() is True

            set_user_triggers(conn, enabled=False)
            conn.execute(
                text(
                    "INSERT INTO public.experiment_registry"
                    "(protocol_id,created_utc,manifest_json) "
                    "VALUES (:protocol_id,10.0,:manifest_json)"
                ),
                {
                    "protocol_id": protocol_id,
                    "manifest_json": json.dumps(
                        {
                            "strategies": strategies,
                            "analysis": {
                                "trial_clock": {"holding_intervals": 252}
                            },
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                },
            )
            run_config = json.dumps(
                {
                    "engine": "formal-global-v2",
                    "protocol_id": protocol_id,
                    "trial_registration_id": registration_id,
                    "tickers": ["ACME"],
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            conn.execute(
                text(
                    "INSERT INTO public.paper_runs(run_id,created_utc,config_json) "
                    "VALUES (:run_id,10.0,:config_json)"
                ),
                {"run_id": run_id, "config_json": run_config},
            )
            conn.execute(
                text(
                    "INSERT INTO public.formal_trial_registry"
                    "(protocol_id,run_id,registration_id,created_utc,details_json) "
                    "VALUES (:protocol_id,:run_id,:registration_id,10.0,'{}')"
                ),
                {
                    "protocol_id": protocol_id,
                    "run_id": run_id,
                    "registration_id": registration_id,
                },
            )
            conn.execute(
                text(
                    "INSERT INTO public.paper_run_labels"
                    "(run_id,label,created_utc,details_json) "
                    "VALUES (:run_id,'confirmatory-trial',10.0,'{}')"
                ),
                {"run_id": run_id},
            )
            conn.execute(
                text(
                    "INSERT INTO public.formal_trial_authorizations("
                    "protocol_id,run_id,registration_id,authorization_id,"
                    "authorized_utc,outcome_semantics_id,configuration_manifest_id,"
                    "collector_configuration_id,paper_decision_configuration_id,"
                    "paper_marker_configuration_id,collector_build_id,"
                    "paper_decision_build_id,paper_marker_build_id,authorization_json"
                    ") VALUES ("
                    ":protocol_id,:run_id,:registration_id,:authorization_id,11.0,"
                    ":outcome_semantics_id,:configuration_manifest_id,"
                    ":collector_configuration_id,:decision_configuration_id,"
                    ":marker_configuration_id,:collector_build_id,"
                    ":decision_build_id,:marker_build_id,'{}')"
                ),
                {
                    "protocol_id": protocol_id,
                    "run_id": run_id,
                    "registration_id": registration_id,
                    "authorization_id": authorization_id,
                    "outcome_semantics_id": outcome_semantics_id,
                    "configuration_manifest_id": configuration_manifest_id,
                    "collector_configuration_id": collector_configuration_id,
                    "decision_configuration_id": decision_configuration_id,
                    "marker_configuration_id": marker_configuration_id,
                    "collector_build_id": collector_build_id,
                    "decision_build_id": decision_build_id,
                    "marker_build_id": marker_build_id,
                },
            )
            set_user_triggers(conn, enabled=True)

            set_session_authorization(conn, DECISION_ROLE)
            try:
                first = projected_slot(conn, first_decision, first_entry)
                validate_decision_slot_projection(
                    first,
                    expected_run_id=run_id,
                    expected_decision_date=first_decision.isoformat(),
                    expected_entry_date=first_entry.isoformat(),
                )
                initial_weights = conn.execute(
                    text(DECISION_WEIGHT_PROJECTION_SQL), {"run_id": run_id}
                ).mappings().all()
                assert len(initial_weights) == 8
                assert {row["source_kind"] for row in initial_weights} == {
                    "initial_zero"
                }
                assert {
                    json.loads(row["weights_json"])["ACME"]
                    for row in initial_weights
                } == {0.0}

                decision_heartbeats = []
                for event_type in ("success", "failure", "paused"):
                    decision_heartbeats.append(
                        dict(
                            conn.execute(
                                text(RUNTIME_HEARTBEAT_SQL),
                                {
                                    "run_id": run_id,
                                    "event_type": event_type,
                                    "runtime_build_id": decision_build_id,
                                },
                            )
                            .mappings()
                            .one()
                        )
                    )
                assert [row["event_type"] for row in decision_heartbeats] == [
                    "success",
                    "failure",
                    "paused",
                ]
                assert {
                    row["runtime_role"] for row in decision_heartbeats
                } == {DECISION_ROLE}

                with (
                    pytest.raises(DBAPIError, match="exact run/build authorization"),
                    conn.begin_nested(),
                ):
                    conn.execute(
                        text(RUNTIME_HEARTBEAT_SQL),
                        {
                            "run_id": run_id,
                            "event_type": "success",
                            "runtime_build_id": frozen_id("build_", "wrong"),
                        },
                    ).all()
                conn.execute(text(f'SET ROLE "{DECISION_ROLE}"'))
                with (
                    pytest.raises(DBAPIError, match="exact split runtime login"),
                    conn.begin_nested(),
                ):
                    conn.execute(
                        text(RUNTIME_HEARTBEAT_SQL),
                        {
                            "run_id": run_id,
                            "event_type": "success",
                            "runtime_build_id": decision_build_id,
                        },
                    ).all()
                conn.execute(text("RESET ROLE"))
                assert conn.execute(
                    text(
                        "SELECT count(*) "
                        "FROM public.formal_runtime_heartbeat_events"
                    )
                ).scalar_one() == 0
                with (
                    pytest.raises(DBAPIError, match="permission denied"),
                    conn.begin_nested(),
                ):
                    conn.execute(
                        text(
                            "SELECT * FROM public.formal_marker_target_projection("
                            ":run_id,:through_date)"
                        ),
                        {
                            "run_id": run_id,
                            "through_date": first_entry.isoformat(),
                        },
                    ).all()
            finally:
                reset_session_authorization(conn)

            set_user_triggers(conn, enabled=False)
            conn.execute(
                text(
                    "INSERT INTO public.paper_decision_attempt_events("
                    "run_id,decision_date,entry_date,attempt_ordinal,event_type,"
                    "created_utc,reason_code) VALUES ("
                    ":run_id,:decision_date,:entry_date,1,'started',20.0,NULL)"
                ),
                {
                    "run_id": run_id,
                    "decision_date": first_decision.isoformat(),
                    "entry_date": first_entry.isoformat(),
                },
            )
            conn.execute(
                text(
                    "INSERT INTO public.paper_decision_bundles("
                    "run_id,decision_date,attempt_ordinal,created_utc,protocol_id,"
                    "build_id,model_id,input_bundle_id,artifact_id,coverage_json) "
                    "VALUES (:run_id,:decision_date,1,21.0,:protocol_id,"
                    ":build_id,'test-model','test-input','test-artifact','{}')"
                ),
                {
                    "run_id": run_id,
                    "decision_date": first_decision.isoformat(),
                    "protocol_id": protocol_id,
                    "build_id": decision_build_id,
                },
            )
            conn.execute(
                text(
                    "INSERT INTO public.paper_targets("
                    "run_id,decision_date,entry_date,created_utc,weights_json) "
                    "VALUES (:run_id,:decision_date,:entry_date,21.0,:weights_json)"
                ),
                {
                    "run_id": run_id,
                    "decision_date": first_decision.isoformat(),
                    "entry_date": first_entry.isoformat(),
                    "weights_json": '{"ACME":1.0}',
                },
            )
            conn.execute(
                text(
                    "INSERT INTO public.paper_strategy_targets("
                    "run_id,decision_date,strategy_id,entry_date,created_utc,"
                    "weights_json,diagnostics_json) "
                    "SELECT :run_id,:decision_date,strategy_id,:entry_date,21.0,"
                    ":weights_json,'{}' FROM "
                    "unnest(CAST(:strategies AS TEXT[])) AS strategy_id"
                ),
                {
                    "run_id": run_id,
                    "decision_date": first_decision.isoformat(),
                    "entry_date": first_entry.isoformat(),
                    "strategies": strategies,
                    "weights_json": weights_json,
                },
            )
            mark_parameters = {
                "run_id": run_id,
                "session_date": first_entry.isoformat(),
                "target_decision_date": first_decision.isoformat(),
                "weights_json": weights_json,
                "opens_json": opens_json,
            }
            conn.execute(
                text(
                    "INSERT INTO public.paper_marks("
                    "run_id,session_date,captured_utc,nav,benchmark_nav,"
                    "period_return,benchmark_period_return,turnover,trading_cost,"
                    "borrow_cost,weights_json,opens_json,benchmark_open,"
                    "target_decision_date) VALUES ("
                    ":run_id,:session_date,22.0,100.0,100.0,0.0,0.0,0.0,0.0,0.0,"
                    ":weights_json,:opens_json,10.0,"
                    ":target_decision_date)"
                ),
                mark_parameters,
            )
            conn.execute(
                text(
                    "INSERT INTO public.paper_strategy_marks("
                    "run_id,strategy_id,session_date,captured_utc,nav,benchmark_nav,"
                    "period_return,benchmark_period_return,turnover,trading_cost,"
                    "borrow_cost,weights_json,opens_json,benchmark_open,"
                    "target_decision_date) SELECT :run_id,strategy_id,:session_date,"
                    "22.0,100.0,100.0,0.0,0.0,0.0,0.0,0.0,:weights_json,"
                    ":opens_json,10.0,:target_decision_date "
                    "FROM unnest(CAST(:strategies AS TEXT[])) AS strategy_id"
                ),
                {**mark_parameters, "strategies": strategies},
            )
            set_user_triggers(conn, enabled=True)

            set_session_authorization(conn, DECISION_ROLE)
            try:
                second = projected_slot(
                    conn, first_entry, first_entry + timedelta(days=1)
                )
                validate_decision_slot_projection(
                    second,
                    expected_run_id=run_id,
                    expected_decision_date=first_entry.isoformat(),
                    expected_entry_date=(first_entry + timedelta(days=1)).isoformat(),
                )
                stale = projected_slot(conn, first_decision, first_entry)
                assert stale["decision_chain_valid"] is True
                assert stale["slot_is_next"] is False
                assert stale["eligible_for_requested_slot"] is False

                held_weights = conn.execute(
                    text(DECISION_WEIGHT_PROJECTION_SQL), {"run_id": run_id}
                ).mappings().all()
                assert len(held_weights) == 8
                assert {row["source_kind"] for row in held_weights} == {
                    "strategy_mark"
                }
                assert {
                    row["source_session_date"] for row in held_weights
                } == {first_entry.isoformat()}
                assert {
                    row["source_decision_date"] for row in held_weights
                } == {first_decision.isoformat()}
            finally:
                reset_session_authorization(conn)

            set_session_authorization(conn, MARKER_ROLE)
            try:
                marker_heartbeat = dict(
                    conn.execute(
                        text(RUNTIME_HEARTBEAT_SQL),
                        {
                            "run_id": run_id,
                            "event_type": "success",
                            "runtime_build_id": marker_build_id,
                        },
                    )
                    .mappings()
                    .one()
                )
                assert marker_heartbeat["runtime_role"] == MARKER_ROLE
                with (
                    pytest.raises(DBAPIError, match="exact run/build authorization"),
                    conn.begin_nested(),
                ):
                    conn.execute(
                        text(RUNTIME_HEARTBEAT_SQL),
                        {
                            "run_id": run_id,
                            "event_type": "success",
                            "runtime_build_id": decision_build_id,
                        },
                    ).all()
                with (
                    pytest.raises(DBAPIError, match="permission denied"),
                    conn.begin_nested(),
                ):
                    projected_slot(conn, first_entry, first_entry + timedelta(days=1))
            finally:
                reset_session_authorization(conn)

            if conn.execute(
                text("SELECT 1 FROM pg_roles WHERE rolname='tradingagents-ingest-v2'")
            ).first():
                set_session_authorization(conn, "tradingagents-ingest-v2")
                try:
                    health = conn.execute(
                        text(RUNTIME_HEALTH_PROJECTION_SQL),
                        {
                            "protocol_id": protocol_id,
                            "collector_build_id": collector_build_id,
                        },
                    ).mappings().all()
                    assert len(health) == 2
                    by_component = {row["runtime_component"]: row for row in health}
                    assert set(by_component) == {"decision", "marker"}
                    assert by_component["decision"]["event_type"] == "paused"
                    assert by_component["decision"]["latest_success_utc"] is not None
                    assert by_component["decision"]["latest_failure_utc"] is not None
                    assert by_component["decision"]["latest_paused_utc"] is not None
                    assert by_component["marker"]["event_type"] == "success"
                    assert by_component["marker"]["latest_success_utc"] is not None
                    assert by_component["marker"]["latest_failure_utc"] is None
                    assert by_component["marker"]["latest_paused_utc"] is None
                    assert conn.execute(
                        text(RUNTIME_HEALTH_PROJECTION_SQL),
                        {
                            "protocol_id": protocol_id,
                            "collector_build_id": frozen_id("build_", "wrong"),
                        },
                    ).all() == []
                    assert conn.execute(
                        text(
                            "SELECT count(*) FROM "
                            "public.formal_runtime_heartbeat_events"
                        )
                    ).scalar_one() == 0
                finally:
                    reset_session_authorization(conn)

            set_user_triggers(conn, enabled=False)
            bulk_parameters = {
                "run_id": run_id,
                "initial_session": first_entry.isoformat(),
                "target_decision_date": first_decision.isoformat(),
                "strategies": strategies,
                "weights_json": weights_json,
                "opens_json": opens_json,
            }
            conn.execute(
                text(
                    "INSERT INTO public.paper_marks("
                    "run_id,session_date,captured_utc,nav,benchmark_nav,"
                    "period_return,benchmark_period_return,turnover,trading_cost,"
                    "borrow_cost,weights_json,opens_json,benchmark_open,"
                    "target_decision_date) SELECT :run_id,"
                    "to_char(CAST(:initial_session AS date) + series.i,'YYYY-MM-DD'),"
                    "100.0 + series.i,100.0,100.0,0.0,0.0,0.0,0.0,0.0,"
                    ":weights_json,:opens_json,10.0,"
                    ":target_decision_date FROM generate_series(1,250) AS series(i)"
                ),
                bulk_parameters,
            )
            conn.execute(
                text(
                    "INSERT INTO public.paper_strategy_marks("
                    "run_id,strategy_id,session_date,captured_utc,nav,benchmark_nav,"
                    "period_return,benchmark_period_return,turnover,trading_cost,"
                    "borrow_cost,weights_json,opens_json,benchmark_open,"
                    "target_decision_date) SELECT :run_id,strategy.strategy_id,"
                    "to_char(CAST(:initial_session AS date) + series.i,'YYYY-MM-DD'),"
                    "100.0 + series.i,100.0,100.0,0.0,0.0,0.0,0.0,0.0,"
                    ":weights_json,:opens_json,10.0,"
                    ":target_decision_date FROM generate_series(1,250) AS series(i) "
                    "CROSS JOIN unnest(CAST(:strategies AS TEXT[])) "
                    "AS strategy(strategy_id)"
                ),
                bulk_parameters,
            )
            conn.execute(
                text(
                    "INSERT INTO public.paper_interval_assignments("
                    "run_id,interval_index,from_session_date,session_date,"
                    "scheduled_decision_date,created_utc,disposition,"
                    "applied_target_decision_date,return_vector_id) SELECT :run_id,"
                    "series.i,to_char(CAST(:initial_session AS date) + series.i - 1,"
                    "'YYYY-MM-DD'),to_char(CAST(:initial_session AS date) + series.i,"
                    "'YYYY-MM-DD'),to_char(CAST(:initial_session AS date) + series.i - 1,"
                    "'YYYY-MM-DD'),200.0 + series.i,'carry_forward_missing_decision',"
                    "NULL,'return-vector-' || series.i "
                    "FROM generate_series(1,250) AS series(i)"
                ),
                bulk_parameters,
            )
            set_user_triggers(conn, enabled=True)

            last_open_decision = first_entry + timedelta(days=250)
            set_session_authorization(conn, DECISION_ROLE)
            try:
                final_open = projected_slot(
                    conn, last_open_decision, last_open_decision + timedelta(days=1)
                )
                validate_decision_slot_projection(
                    final_open,
                    expected_run_id=run_id,
                    expected_decision_date=last_open_decision.isoformat(),
                    expected_entry_date=(
                        last_open_decision + timedelta(days=1)
                    ).isoformat(),
                )
            finally:
                reset_session_authorization(conn)

            set_user_triggers(conn, enabled=False)
            final_parameters = {
                **bulk_parameters,
                "session_date": (first_entry + timedelta(days=251)).isoformat(),
                "from_session_date": last_open_decision.isoformat(),
            }
            conn.execute(
                text(
                    "INSERT INTO public.paper_marks("
                    "run_id,session_date,captured_utc,nav,benchmark_nav,"
                    "period_return,benchmark_period_return,turnover,trading_cost,"
                    "borrow_cost,weights_json,opens_json,benchmark_open,"
                    "target_decision_date) VALUES (:run_id,:session_date,500.0,"
                    "100.0,100.0,0.0,0.0,0.0,0.0,0.0,:weights_json,"
                    ":opens_json,10.0,:target_decision_date)"
                ),
                final_parameters,
            )
            conn.execute(
                text(
                    "INSERT INTO public.paper_strategy_marks("
                    "run_id,strategy_id,session_date,captured_utc,nav,benchmark_nav,"
                    "period_return,benchmark_period_return,turnover,trading_cost,"
                    "borrow_cost,weights_json,opens_json,benchmark_open,"
                    "target_decision_date) SELECT :run_id,strategy_id,:session_date,"
                    "500.0,100.0,100.0,0.0,0.0,0.0,0.0,0.0,:weights_json,"
                    ":opens_json,10.0,:target_decision_date "
                    "FROM unnest(CAST(:strategies AS TEXT[])) AS strategy_id"
                ),
                final_parameters,
            )
            conn.execute(
                text(
                    "INSERT INTO public.paper_interval_assignments("
                    "run_id,interval_index,from_session_date,session_date,"
                    "scheduled_decision_date,created_utc,disposition,"
                    "applied_target_decision_date,return_vector_id) VALUES ("
                    ":run_id,251,:from_session_date,:session_date,:from_session_date,"
                    "501.0,'carry_forward_missing_decision',NULL,'return-vector-251')"
                ),
                final_parameters,
            )
            set_user_triggers(conn, enabled=True)

            terminal_decision = first_entry + timedelta(days=251)
            set_session_authorization(conn, DECISION_ROLE)
            try:
                exhausted = projected_slot(
                    conn, terminal_decision, terminal_decision + timedelta(days=1)
                )
                assert exhausted["decision_chain_valid"] is True
                assert exhausted["slot_is_next"] is True
                assert exhausted["horizon_open"] is False
                assert exhausted["eligible_for_requested_slot"] is False
                with pytest.raises(FormalRoleContractError, match="horizon"):
                    validate_decision_slot_projection(
                        exhausted,
                        expected_run_id=run_id,
                        expected_decision_date=terminal_decision.isoformat(),
                        expected_entry_date=(
                            terminal_decision + timedelta(days=1)
                        ).isoformat(),
                    )
            finally:
                reset_session_authorization(conn)

            heartbeat_rows = conn.execute(
                text(
                    "SELECT heartbeat_id,protocol_id,run_id,runtime_role,"
                    "runtime_build_id,event_type,observed_utc,event_json "
                    "FROM public.formal_runtime_heartbeat_events "
                    "WHERE run_id=:run_id ORDER BY observed_utc"
                ),
                {"run_id": run_id},
            ).mappings().all()
            assert len(heartbeat_rows) == 4
            for heartbeat in heartbeat_rows:
                document = json.loads(heartbeat["event_json"])
                assert set(document) == {
                    "schema_version",
                    "protocol_id",
                    "run_id",
                    "runtime_role",
                    "runtime_build_id",
                    "event_type",
                    "observed_utc",
                }
                assert document["protocol_id"] == protocol_id
                assert document["run_id"] == run_id
                assert document["observed_utc"] == heartbeat["observed_utc"]
                assert heartbeat["heartbeat_id"] == content_id(
                    document, prefix="heartbeat_"
                )

            heartbeat_id = heartbeat_rows[0]["heartbeat_id"]
            for statement in (
                "UPDATE public.formal_runtime_heartbeat_events "
                "SET event_type='failure' WHERE heartbeat_id=:heartbeat_id",
                "DELETE FROM public.formal_runtime_heartbeat_events "
                "WHERE heartbeat_id=:heartbeat_id",
            ):
                with (
                    pytest.raises(DBAPIError, match="append-only"),
                    conn.begin_nested(),
                ):
                    conn.execute(text(statement), {"heartbeat_id": heartbeat_id})
            with (
                pytest.raises(DBAPIError, match="exact split runtime login"),
                conn.begin_nested(),
            ):
                conn.execute(
                    text(
                        "INSERT INTO public.formal_runtime_heartbeat_events("
                        "heartbeat_id,protocol_id,run_id,runtime_role,"
                        "runtime_build_id,event_type,observed_utc,event_json) VALUES ("
                        "'heartbeat_000000000000000000000000',:protocol_id,:run_id,"
                        ":runtime_role,:runtime_build_id,'success',0.0,'{}')"
                    ),
                    {
                        "protocol_id": protocol_id,
                        "run_id": run_id,
                        "runtime_role": DECISION_ROLE,
                        "runtime_build_id": decision_build_id,
                    },
                )
            assert conn.execute(
                text(
                    "SELECT count(*) FROM public.formal_runtime_heartbeat_events "
                    "WHERE run_id=:run_id"
                ),
                {"run_id": run_id},
            ).scalar_one() == 4
            assert conn.execute(
                text("SELECT public.formal_role_policy_contract_matches()")
            ).scalar_one() is True
    finally:
        engine.dispose()
