"""Static contracts for the PostgreSQL formal ITT provenance migration."""

import re
from pathlib import Path

import pytest

from tradingagents import ops_cli
from tradingagents.paper_trading import (
    FORMAL_ATTEMPT_FAILURE_REASON_CODES,
    FORMAL_HOLDING_INTERVALS,
    FORMAL_INTERVAL_DISPOSITIONS,
)

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "004_formal_itt_provenance.sql"
)

EXPECTED_DOUBLE_PRECISION_COLUMNS = {
    ("schema_migrations", "applied_utc"),
    ("paper_runs", "created_utc"),
    ("paper_decisions", "created_utc"),
    ("paper_decisions", "score"),
    ("paper_targets", "created_utc"),
    ("paper_marks", "captured_utc"),
    ("paper_marks", "nav"),
    ("paper_marks", "benchmark_nav"),
    ("paper_marks", "period_return"),
    ("paper_marks", "benchmark_period_return"),
    ("paper_marks", "turnover"),
    ("paper_marks", "trading_cost"),
    ("paper_marks", "borrow_cost"),
    ("paper_marks", "benchmark_open"),
    ("experiment_registry", "created_utc"),
    ("paper_run_labels", "created_utc"),
    ("paper_artifacts", "created_utc"),
    ("paper_decision_bundles", "created_utc"),
    ("paper_strategy_targets", "created_utc"),
    ("paper_strategy_marks", "captured_utc"),
    ("paper_strategy_marks", "nav"),
    ("paper_strategy_marks", "benchmark_nav"),
    ("paper_strategy_marks", "period_return"),
    ("paper_strategy_marks", "benchmark_period_return"),
    ("paper_strategy_marks", "turnover"),
    ("paper_strategy_marks", "trading_cost"),
    ("paper_strategy_marks", "borrow_cost"),
    ("paper_strategy_marks", "benchmark_open"),
    ("paper_price_receipts", "captured_utc"),
    ("paper_price_receipts", "raw_open"),
    ("paper_price_receipts", "adjusted_open"),
    ("paper_price_receipts", "dividend"),
    ("paper_price_receipts", "split_ratio"),
    ("paper_decision_attempt_events", "created_utc"),
    ("paper_interval_assignments", "created_utc"),
    ("media_posts", "created_utc"),
    ("media_posts", "fetched_utc"),
    ("media_labels", "linked_utc"),
    ("media_observations", "observed_utc"),
    ("macro_odds", "captured_utc"),
    ("macro_odds", "probability"),
    ("macro_odds", "volume"),
    ("macro_odds", "resolution_utc"),
    ("poll_state", "value"),
    ("fetch_runs", "started_utc"),
    ("fetch_runs", "received_utc"),
    ("fetch_runs", "completed_utc"),
    ("fetch_runs", "cost_units"),
    ("fetch_runs", "cursor_before"),
    ("fetch_runs", "cursor_after"),
}


@pytest.fixture(scope="module")
def migration_sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _normalized(sql: str) -> str:
    return " ".join(sql.split())


@pytest.mark.unit
def test_migration_is_transactional_idempotent_and_schema_pinned(migration_sql):
    assert migration_sql.count("BEGIN;") == 1
    assert migration_sql.count("COMMIT;") == 1
    assert "SET LOCAL search_path = pg_catalog, public;" in migration_sql
    assert "ALTER TABLE public.%I" in migration_sql
    assert "'public.paper_interval_assignments'::regclass" in migration_sql
    assert "CREATE TABLE IF NOT EXISTS public.paper_decision_attempt_events" in migration_sql
    assert "CREATE TABLE IF NOT EXISTS public.paper_interval_assignments" in migration_sql
    assert "DROP TRIGGER IF EXISTS immutable_paper_decision_attempt_events" in migration_sql
    assert "DROP TRIGGER IF EXISTS immutable_paper_interval_assignments" in migration_sql


@pytest.mark.unit
def test_migration_defines_its_append_only_dependency_before_triggers(migration_sql):
    function = "CREATE OR REPLACE FUNCTION public.reject_append_only_mutation()"
    first_trigger = "CREATE TRIGGER immutable_paper_decision_attempt_events"
    assert function in migration_sql
    assert migration_sql.index(function) < migration_sql.index(first_trigger)
    assert "SET search_path = pg_catalog" in migration_sql
    source = re.search(
        r"CREATE OR REPLACE FUNCTION public\.reject_append_only_mutation\(\).*?"
        r"AS \$\$(.*?)\$\$;",
        migration_sql,
        flags=re.DOTALL,
    )
    assert source is not None
    assert ops_cli._normalized_pg_prosrc_sha256(source.group(1)) \
        == ops_cli._APPEND_ONLY_PROSRC_SHA256
    assert (
        "COMMENT ON FUNCTION public.reject_append_only_mutation() IS\n"
        f"    '{ops_cli._APPEND_ONLY_CONTRACT}';"
    ) in migration_sql
    assert migration_sql.count(
        "FOR EACH ROW EXECUTE FUNCTION public.reject_append_only_mutation()"
    ) == 2
    assert re.search(
        r"CREATE TRIGGER immutable_paper_decision_attempt_events\s+"
        r"BEFORE UPDATE OR DELETE ON public\.paper_decision_attempt_events",
        migration_sql,
    )
    assert re.search(
        r"CREATE TRIGGER immutable_paper_interval_assignments\s+"
        r"BEFORE UPDATE OR DELETE ON public\.paper_interval_assignments",
        migration_sql,
    )


@pytest.mark.unit
def test_precision_conversion_and_postcondition_cover_the_same_exact_inventory(
    migration_sql,
):
    inventories = re.findall(
        r"FROM \(VALUES(?P<values>.*?)\) AS columns_to_check",
        migration_sql,
        flags=re.DOTALL,
    )
    assert len(inventories) == 2
    parsed = [
        set(re.findall(r"\('([a-z_]+)', '([a-z_]+)'\)", inventory))
        for inventory in inventories
    ]
    assert parsed[0] == EXPECTED_DOUBLE_PRECISION_COLUMNS
    assert parsed[1] == EXPECTED_DOUBLE_PRECISION_COLUMNS
    assert "actual.udt_name IS DISTINCT FROM 'float8'" in migration_sql


@pytest.mark.unit
def test_attempt_and_interval_checks_match_paper_store_contracts(migration_sql):
    attempt_table, interval_tail = migration_sql.split(
        "CREATE TABLE IF NOT EXISTS public.paper_interval_assignments", maxsplit=1
    )
    attempt_tokens = set(re.findall(r"'([a-z_]+)'", attempt_table))
    assert attempt_tokens >= FORMAL_ATTEMPT_FAILURE_REASON_CODES
    assert {"started", "failed"} <= attempt_tokens

    interval_table = interval_tail.split(");", maxsplit=1)[0]
    interval_tokens = set(re.findall(r"'([a-z_]+)'", interval_table))
    assert interval_tokens >= FORMAL_INTERVAL_DISPOSITIONS
    assert f"interval_index <= {FORMAL_HOLDING_INTERVALS}" in interval_table


@pytest.mark.unit
def test_runtime_grants_are_fail_closed_and_paper_is_insert_only(migration_sql):
    sql = _normalized(migration_sql)
    tables = (
        "public.paper_decision_attempt_events, "
        "public.paper_interval_assignments"
    )
    assert f"REVOKE ALL PRIVILEGES ON TABLE {tables} FROM PUBLIC" in sql
    assert (
        f"REVOKE ALL PRIVILEGES ON TABLE {tables} "
        'FROM "tradingagents-paper"'
    ) in sql
    assert (
        "GRANT SELECT, INSERT ON TABLE public.paper_decision_attempt_events, "
        'public.paper_interval_assignments TO "tradingagents-paper"'
    ) in sql
    assert (
        f"REVOKE ALL PRIVILEGES ON TABLE {tables} "
        'FROM "tradingagents-ingest-v2"'
    ) in sql
    assert (
        f"REVOKE ALL PRIVILEGES ON TABLE {tables} "
        'FROM "tradingagents-ingest"'
    ) in sql
    assert 'GRANT UPDATE' not in sql
    assert 'GRANT DELETE' not in sql
    assert 'GRANT TRUNCATE' not in sql
