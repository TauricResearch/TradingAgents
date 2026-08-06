"""Static contracts for migration 007's immutable collection-cycle ledger."""

import hashlib
import re
from pathlib import Path

import pytest

MIGRATION = Path(__file__).resolve().parents[1] / "migrations/007_collection_cycles.sql"


@pytest.fixture(scope="module")
def migration_sql():
    return MIGRATION.read_text(encoding="utf-8")


def _normalized(value):
    return "\n".join(line.rstrip() for line in value.strip().splitlines())


@pytest.mark.unit
def test_migration_number_transaction_and_pause_precondition_are_pinned(migration_sql):
    assert MIGRATION.name == "007_collection_cycles.sql"
    assert migration_sql.count("BEGIN;") == 1
    assert migration_sql.count("COMMIT;") == 1
    assert "SET LOCAL search_path = pg_catalog, public;" in migration_sql
    assert "collection-cycle migration requires zero running fetch receipts" in migration_sql
    assert "Migration 008 is reserved for market-outcome capture" in migration_sql


@pytest.mark.unit
def test_schema_has_parent_slots_child_fk_and_one_receipt_per_slot(migration_sql):
    assert "CREATE TABLE IF NOT EXISTS public.collection_cycles" in migration_sql
    assert "CREATE TABLE IF NOT EXISTS public.collection_cycle_slots" in migration_sql
    assert "PRIMARY KEY (collection_cycle_id, provider, query_key)" in migration_sql
    assert "fetch_runs_collection_cycle_fk" in migration_sql
    assert "REFERENCES public.collection_cycles(collection_cycle_id)" in migration_sql
    assert "fetch_runs_cycle_slot_unique" in migration_sql
    assert "UNIQUE (collection_cycle_id, provider, query_key)" in migration_sql
    assert "^cycle_[0-9a-f]{24}$" in migration_sql
    assert "^cycle_manifest_[0-9a-f]{24}$" in migration_sql
    assert "'-Infinity'::DOUBLE PRECISION" in migration_sql
    assert "'Infinity'::DOUBLE PRECISION" in migration_sql


@pytest.mark.unit
def test_database_derives_exact_manifest_and_status_from_children(migration_sql):
    assert "'expected_static_slots', static_slots" in migration_sql
    assert "'expected_dynamic_slots', dynamic_slots" in migration_sql
    assert "'slot_receipts', slot_receipts" in migration_sql
    assert "'fetch_run_id', run.fetch_run_id" in migration_sql
    assert "'status', COALESCE(run.status, 'missing')" in migration_sql
    assert "'item_count', run.item_count" in migration_sql
    assert "'raw_content_ids', COALESCE(" in migration_sql
    assert "item.raw_content_id ORDER BY item.raw_content_id" in migration_sql
    assert "NOT IN ('success', 'empty')" in migration_sql
    assert "THEN 'incomplete' ELSE 'complete' END" in migration_sql
    assert "manifest IS DISTINCT FROM expected_manifest" in migration_sql
    assert "terminal manifest differs from stored receipts" in migration_sql
    assert "cannot finish while a child receipt is running" in migration_sql
    assert "sha256(pg_catalog.convert_to(NEW.manifest_json, 'UTF8'))" in migration_sql
    assert migration_sql.count('COLLATE "C"') >= 8


@pytest.mark.unit
def test_slots_and_children_can_only_attach_while_parent_is_running(migration_sql):
    assert "collection cycle slots are append-only" in migration_sql
    assert "parent.status IS DISTINCT FROM 'running'" in migration_sql
    assert "FOR UPDATE;" in migration_sql
    assert "fetch receipt lacks a declared running cycle slot" in migration_sql
    assert "FOR KEY SHARE;" in migration_sql
    assert "BEFORE INSERT ON public.fetch_runs" in migration_sql
    assert "dynamic_count >= (identity->>'max_dynamic_slots')::INTEGER" in migration_sql


@pytest.mark.unit
@pytest.mark.parametrize(
    ("function_name", "contract"),
    [
        ("enforce_collection_cycle_lifecycle", "collection-cycle-lifecycle.v1"),
        (
            "enforce_collection_cycle_slot_lifecycle",
            "collection-cycle-slot-lifecycle.v1",
        ),
        ("enforce_fetch_run_cycle_binding", "fetch-run-cycle-binding.v1"),
    ],
)
def test_function_contract_comments_hash_exact_normalized_bodies(
    migration_sql, function_name, contract,
):
    match = re.search(
        rf"CREATE OR REPLACE FUNCTION public\.{function_name}\(\).*?"
        rf"AS \$\$(?P<body>.*?)\$\$;.*?"
        rf"tradingagents\.{re.escape(contract)};"
        rf"normalized-prosrc-sha256=(?P<digest>[0-9a-f]{{64}})",
        migration_sql,
        flags=re.DOTALL,
    )
    assert match is not None
    actual = hashlib.sha256(_normalized(match.group("body")).encode()).hexdigest()
    assert actual == match.group("digest")


@pytest.mark.unit
def test_runtime_roles_have_only_required_cycle_permissions(migration_sql):
    assert "REVOKE ALL PRIVILEGES ON TABLE public.collection_cycles FROM PUBLIC" in migration_sql
    assert (
        "GRANT SELECT, INSERT, UPDATE ON TABLE public.collection_cycles\n"
        "            TO \"tradingagents-ingest-v2\""
    ) in migration_sql
    assert (
        "GRANT SELECT, INSERT ON TABLE public.collection_cycle_slots\n"
        "            TO \"tradingagents-ingest-v2\""
    ) in migration_sql
    assert (
        "GRANT SELECT ON TABLE public.collection_cycles\n"
        "            TO \"tradingagents-paper\""
    ) in migration_sql
    ingest_slots_grant = migration_sql.split(
        'TO "tradingagents-ingest-v2";', maxsplit=2
    )[1].rsplit("GRANT", maxsplit=1)[-1]
    assert "UPDATE" not in ingest_slots_grant
    assert "DELETE" not in ingest_slots_grant
