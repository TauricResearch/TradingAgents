"""Migration-011 LLM budget and decision-attempt binding contracts."""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from tradingagents import ops_cli
from tradingagents.dataflows.media_store import _normalize_pg_url

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "011_formal_llm_budget_and_attempt_binding.sql"
)


@pytest.fixture(scope="module")
def migration_sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _function_source(sql: str, name: str) -> str:
    match = re.search(
        rf"CREATE OR REPLACE FUNCTION public\.{re.escape(name)}\([^)]*\).*?"
        r"AS \$\$(.*?)\$\$;",
        sql,
        flags=re.DOTALL,
    )
    assert match is not None
    return match.group(1)


@pytest.mark.unit
def test_budget_migration_is_transactional_and_schema_exact(migration_sql):
    assert MIGRATION.name == "011_formal_llm_budget_and_attempt_binding.sql"
    assert migration_sql.count("BEGIN;") == 1
    assert migration_sql.count("COMMIT;") == 1
    assert "SET LOCAL search_path = pg_catalog, public;" in migration_sql
    assert "CREATE TABLE IF NOT EXISTS public.formal_llm_budget_counters" in migration_sql
    for column in (
        "counter_key TEXT PRIMARY KEY",
        "scope TEXT NOT NULL",
        "protocol_id TEXT NOT NULL",
        "run_id TEXT NOT NULL",
        "counter_kind TEXT NOT NULL",
        "bucket_date DATE NOT NULL",
        "reserved_calls INTEGER NOT NULL",
        "frozen_limit INTEGER NOT NULL",
        "first_reserved_utc DOUBLE PRECISION NOT NULL",
        "last_reserved_utc DOUBLE PRECISION NOT NULL",
    ):
        assert column in migration_sql
    assert "valid_keys <> 2 OR total_keys <> 2" in migration_sql
    assert "formal LLM budget counter keys are not exact" in migration_sql


@pytest.mark.unit
def test_only_security_definer_function_can_mutate_budget_and_day_is_server_owned(
    migration_sql,
):
    signature = (
        "TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, INTEGER, INTEGER, INTEGER"
    )
    function = migration_sql.split(
        "CREATE OR REPLACE FUNCTION public.reserve_formal_llm_invocation_budget(",
        maxsplit=1,
    )[1].split("COMMENT ON FUNCTION", maxsplit=1)[0]
    assert "SECURITY DEFINER" in function
    assert "SET search_path = pg_catalog" in function
    assert "pg_catalog.pg_advisory_xact_lock" in function
    assert "server_timestamp := pg_catalog.clock_timestamp();" in function
    assert "utc_day := (server_timestamp AT TIME ZONE 'UTC')::DATE::TEXT;" in function
    assert "max_calls_per_decision" not in signature
    assert "max_calls_per_utc_day" not in signature
    assert "p_utc_day" not in function
    assert "INSERT INTO public.formal_llm_budget_counters" in function
    assert "INSERT INTO public.paper_artifacts" in function
    assert "'llm_invocation_reserved', receipt_text" in function
    assert "formal LLM counter and immutable receipts disagree" in function
    compact = " ".join(migration_sql.split())
    assert (
        "REVOKE ALL PRIVILEGES ON TABLE public.formal_llm_budget_counters FROM PUBLIC"
        in compact
    )
    for role in (
        "tradingagents-paper",
        "tradingagents-paper-decision",
        "tradingagents-paper-marker",
        "tradingagents-ingest-v2",
        "tradingagents-ingest",
    ):
        assert f"'{role}'" in migration_sql


@pytest.mark.unit
def test_decision_bundle_resolves_only_exact_latest_started_ordinal(migration_sql):
    assert "ALTER COLUMN attempt_ordinal SET NOT NULL" in migration_sql
    assert "CHECK (attempt_ordinal > 0)" in migration_sql
    function = _function_source(migration_sql, "enforce_formal_decision_bundle_attempt")
    assert "pg_catalog.max(attempt.attempt_ordinal)" in function
    assert "NEW.attempt_ordinal IS DISTINCT FROM latest_ordinal" in function
    assert "attempt.attempt_ordinal = NEW.attempt_ordinal" in function
    assert "artifact -> 'attempt_ordinal'" in function
    retry_guard = _function_source(
        migration_sql, "enforce_no_attempt_retry_after_llm_reservation"
    )
    assert "NEW.event_type = 'started'" in retry_guard
    assert "artifact.artifact_type = 'llm_invocation_reserved'" in retry_guard


@pytest.mark.unit
def test_budget_and_attempt_function_bodies_match_frozen_hashes(migration_sql):
    contracts = {
        "enforce_formal_decision_bundle_attempt": (
            ops_cli._FORMAL_LLM_ATTEMPT_BINDING_PROSRC_SHA256,
            ops_cli._FORMAL_LLM_ATTEMPT_BINDING_CONTRACT,
        ),
        "enforce_no_attempt_retry_after_llm_reservation": (
            ops_cli._FORMAL_LLM_NO_RETRY_PROSRC_SHA256,
            ops_cli._FORMAL_LLM_NO_RETRY_CONTRACT,
        ),
        "reserve_formal_llm_invocation_budget": (
            ops_cli._FORMAL_LLM_RESERVATION_PROSRC_SHA256,
            ops_cli._FORMAL_LLM_RESERVATION_CONTRACT,
        ),
    }
    for name, (expected_hash, expected_contract) in contracts.items():
        assert ops_cli._normalized_pg_prosrc_sha256(
            _function_source(migration_sql, name)
        ) == expected_hash
        assert expected_contract in migration_sql


@pytest.mark.integration
def test_runtime_roles_cannot_directly_read_or_mutate_budget_table():
    url = os.getenv("TRADINGAGENTS_TEST_POSTGRES_ADMIN_URL")
    if not url:
        pytest.skip("TRADINGAGENTS_TEST_POSTGRES_ADMIN_URL is not configured")
    engine = create_engine(_normalize_pg_url(url))
    counter_key = f"rls-test-{uuid.uuid4().hex}"
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO public.formal_llm_budget_counters "
                    "(counter_key,scope,protocol_id,run_id,counter_kind,bucket_date,"
                    "reserved_calls,frozen_limit,first_reserved_utc,last_reserved_utc) "
                    "VALUES (:key,'formal-global-v2','p','r','utc_day',CURRENT_DATE,"
                    "1,2,1,1)"
                ),
                {"key": counter_key},
            )
        for role in ("tradingagents-paper-decision", "tradingagents-paper-marker"):
            with engine.begin() as conn:
                conn.execute(text(f'SET LOCAL ROLE "{role}"'))
                assert conn.execute(
                    text(
                        "SELECT count(*) FROM public.formal_llm_budget_counters "
                        "WHERE counter_key=:key"
                    ),
                    {"key": counter_key},
                ).scalar_one() == 0
                for statement in (
                    "UPDATE public.formal_llm_budget_counters "
                    "SET reserved_calls=2 WHERE counter_key=:key",
                    "DELETE FROM public.formal_llm_budget_counters "
                    "WHERE counter_key=:key",
                ):
                    with pytest.raises(DBAPIError), conn.begin_nested():
                        conn.execute(text(statement), {"key": counter_key})
                with pytest.raises(DBAPIError), conn.begin_nested():
                    conn.execute(
                        text(
                            "INSERT INTO public.formal_llm_budget_counters "
                            "(counter_key,scope,protocol_id,run_id,counter_kind,"
                            "bucket_date,reserved_calls,frozen_limit,first_reserved_utc,"
                            "last_reserved_utc) VALUES "
                            "(:key,'formal-global-v2','p','r','utc_day',CURRENT_DATE,"
                            "1,1,1,1)"
                        ),
                        {"key": f"forged-{role}"},
                    )
        with engine.begin() as conn:
            assert conn.execute(
                text(
                    "SELECT reserved_calls FROM public.formal_llm_budget_counters "
                    "WHERE counter_key=:key"
                ),
                {"key": counter_key},
            ).scalar_one() == 1
    finally:
        engine.dispose()
