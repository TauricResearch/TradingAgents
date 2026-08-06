"""Static contracts for the PostgreSQL primary confirmatory-run registry."""

import re
from pathlib import Path

import pytest

from tradingagents import ops_cli
from tradingagents.paper_trading import PaperStore

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "005_formal_primary_run_registry.sql"
)


@pytest.fixture(scope="module")
def migration_sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _normalized(sql: str) -> str:
    return " ".join(sql.split())


def _function_source(sql: str, name: str) -> str:
    match = re.search(
        rf"CREATE OR REPLACE FUNCTION public\.{re.escape(name)}\(\).*?"
        r"AS \$\$(.*?)\$\$;",
        sql,
        flags=re.DOTALL,
    )
    assert match is not None
    return match.group(1)


@pytest.mark.unit
def test_primary_registry_migration_is_transactional_and_schema_pinned(migration_sql):
    assert migration_sql.count("BEGIN;") == 1
    assert migration_sql.count("COMMIT;") == 1
    assert "SET LOCAL search_path = pg_catalog, public;" in migration_sql
    assert "CREATE TABLE IF NOT EXISTS public.formal_trial_registry" in migration_sql
    assert "'public.formal_trial_registry'::pg_catalog.regclass" in migration_sql
    assert "formal_trial_registry_pkey PRIMARY KEY (protocol_id)" in migration_sql
    assert "formal_trial_registry_run_id_key UNIQUE (run_id)" in migration_sql
    assert "formal_trial_registry_registration_id_key UNIQUE (registration_id)" \
        in migration_sql
    assert "valid_constraints <> 3" in migration_sql


@pytest.mark.unit
def test_primary_registry_is_append_only_and_confirmatory_labels_are_guarded(
    migration_sql,
):
    assert re.search(
        r"CREATE TRIGGER immutable_formal_trial_registry\s+"
        r"BEFORE UPDATE OR DELETE ON public\.formal_trial_registry",
        migration_sql,
    )
    assert re.search(
        r"CREATE TRIGGER validate_formal_trial_registry_insert\s+"
        r"BEFORE INSERT ON public\.formal_trial_registry",
        migration_sql,
    )
    assert re.search(
        r"CREATE TRIGGER guard_confirmatory_run_label\s+"
        r"BEFORE INSERT ON public\.paper_run_labels",
        migration_sql,
    )
    assert "label.details_json IS DISTINCT FROM NEW.details_json" in migration_sql
    assert "another same-protocol run was already labeled confirmatory" in migration_sql


@pytest.mark.unit
def test_registry_insert_detects_protocol_wide_activity_and_outcome_access(migration_sql):
    function = migration_sql.split(
        "CREATE OR REPLACE FUNCTION public.enforce_formal_trial_registry_insert()",
        maxsplit=1,
    )[1].split("DROP TRIGGER IF EXISTS validate_formal_trial_registry_insert", maxsplit=1)[0]
    price_tables = {
        "paper_price_capture_attempt_events",
        "paper_price_capture_batches",
        "paper_price_integrity_failures",
    }
    for table in set(PaperStore._TRIAL_ACTIVITY_TABLES) - price_tables:
        assert f"public.{table}" in function
    assert "public.paper_run_labels" in function
    assert "label.label <> 'confirmatory-trial'" in function
    assert "public.paper_artifacts" in function
    assert "artifact.content_json::jsonb ->> 'run_id'" in function
    assert "same-protocol activity predates primary registration" in function
    assert "pg_catalog.pg_advisory_xact_lock" in function
    assert "'tradingagents:formal-protocol:' || NEW.protocol_id" in function
    # The flag is validated for internal consistency, but actual ledger and
    # access-receipt scans are the evidence that registration is not too late.
    assert "outcomes_accessed_before_registration" in function


@pytest.mark.unit
def test_every_formal_insert_is_bound_to_the_registered_primary(migration_sql):
    dynamic_tables = set(
        re.findall(
            r"'(paper_[a-z_]+)'",
            migration_sql.split("FOREACH table_name IN ARRAY ARRAY[", maxsplit=1)[1]
            .split("]", maxsplit=1)[0],
        )
    )
    assert dynamic_tables == set(PaperStore._TRIAL_ACTIVITY_TABLES) - {
        "paper_price_capture_attempt_events",
        "paper_price_capture_batches",
        "paper_price_integrity_failures",
    }
    assert "BEFORE INSERT ON public.%I" in migration_sql
    assert "enforce_formal_primary_run_activity()" in migration_sql
    assert "BEFORE INSERT ON public.paper_artifacts" in migration_sql
    assert "enforce_formal_artifact_primary_run()" in migration_sql
    assert "formal activity requires the registered primary run" in migration_sql


@pytest.mark.unit
def test_runtime_registry_grants_are_least_privilege_and_idempotent(migration_sql):
    sql = _normalized(migration_sql)
    assert "DROP TRIGGER IF EXISTS immutable_formal_trial_registry" in sql
    assert "DROP TRIGGER IF EXISTS validate_formal_trial_registry_insert" in sql
    assert "DROP TRIGGER IF EXISTS guard_confirmatory_run_label" in sql
    assert "REVOKE ALL PRIVILEGES ON TABLE public.formal_trial_registry FROM PUBLIC" in sql
    assert (
        "REVOKE ALL PRIVILEGES ON TABLE public.formal_trial_registry "
        'FROM "tradingagents-paper"'
    ) in sql
    assert (
        "GRANT SELECT, INSERT ON TABLE public.formal_trial_registry "
        'TO "tradingagents-paper"'
    ) in sql
    assert (
        "REVOKE ALL PRIVILEGES ON TABLE public.formal_trial_registry "
        'FROM "tradingagents-ingest-v2"'
    ) in sql
    assert "GRANT UPDATE" not in sql
    assert "GRANT DELETE" not in sql
    assert "GRANT TRUNCATE" not in sql
    for function in (
        "enforce_formal_trial_registry_insert",
        "enforce_formal_primary_run_activity",
        "enforce_formal_artifact_primary_run",
        "enforce_formal_run_label",
    ):
        assert f"REVOKE ALL ON FUNCTION public.{function}() FROM PUBLIC" in sql
    assert migration_sql.count("SET search_path = pg_catalog") >= 5


@pytest.mark.unit
def test_registry_guard_bodies_have_exact_stable_contract_comments(migration_sql):
    contracts = {
        "enforce_formal_trial_registry_insert": (
            ops_cli._FORMAL_REGISTRY_INSERT_PROSRC_SHA256,
            ops_cli._FORMAL_REGISTRY_INSERT_CONTRACT,
        ),
        "enforce_formal_primary_run_activity": (
            ops_cli._FORMAL_PRIMARY_ACTIVITY_PROSRC_SHA256,
            ops_cli._FORMAL_PRIMARY_ACTIVITY_CONTRACT,
        ),
        "enforce_formal_artifact_primary_run": (
            ops_cli._FORMAL_PRIMARY_ARTIFACT_PROSRC_SHA256,
            ops_cli._FORMAL_PRIMARY_ARTIFACT_CONTRACT,
        ),
        "enforce_formal_run_label": (
            ops_cli._FORMAL_PRIMARY_LABEL_PROSRC_SHA256,
            ops_cli._FORMAL_PRIMARY_LABEL_CONTRACT,
        ),
    }

    for function_name, (expected_hash, expected_contract) in contracts.items():
        assert ops_cli._normalized_pg_prosrc_sha256(
            _function_source(migration_sql, function_name)
        ) == expected_hash
        assert (
            f"COMMENT ON FUNCTION public.{function_name}() IS\n"
            f"    '{expected_contract}';"
        ) in migration_sql
