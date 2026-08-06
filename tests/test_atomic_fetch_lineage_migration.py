"""Static contracts for migration 006's atomic content-bound fetch lineage."""

import hashlib
import re
from pathlib import Path

import pytest

MIGRATION = Path(__file__).resolve().parents[1] / "migrations/006_atomic_fetch_lineage.sql"


@pytest.fixture(scope="module")
def migration_sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _normalized(value: str) -> str:
    return "\n".join(line.rstrip() for line in value.strip().splitlines())


@pytest.mark.unit
def test_migration_is_transactional_idempotent_and_schema_pinned(migration_sql):
    assert migration_sql.count("BEGIN;") == 1
    assert migration_sql.count("COMMIT;") == 1
    assert "SET LOCAL search_path = pg_catalog, public;" in migration_sql
    assert "WHERE status = 'running'" in migration_sql
    assert "requires zero running fetch receipts" in migration_sql
    assert "CREATE TABLE IF NOT EXISTS public.fetch_run_items" in migration_sql
    assert "ADD COLUMN IF NOT EXISTS formal_eligible_lineage_json TEXT" in migration_sql
    assert "ADD COLUMN IF NOT EXISTS collection_cycle_id TEXT" in migration_sql
    assert "DROP TRIGGER IF EXISTS immutable_fetch_runs ON public.fetch_runs" in migration_sql
    assert "DROP TRIGGER IF EXISTS immutable_fetch_run_items" in migration_sql
    assert "DROP TRIGGER IF EXISTS validate_fetch_run_content_completion" in migration_sql


@pytest.mark.unit
def test_item_table_has_exact_content_and_parent_associations(migration_sql):
    for column in (
        "fetch_run_id TEXT NOT NULL",
        "source TEXT NOT NULL",
        "external_id TEXT NOT NULL",
        "raw_content_id TEXT NOT NULL",
        "evidence_id TEXT NOT NULL",
        "observed_utc DOUBLE PRECISION NOT NULL",
        "formal_eligible BOOLEAN NOT NULL",
    ):
        assert column in migration_sql
    assert "PRIMARY KEY (fetch_run_id, source, external_id)" in migration_sql
    assert "UNIQUE (fetch_run_id, raw_content_id)" in migration_sql
    assert "REFERENCES public.fetch_runs(fetch_run_id)" in migration_sql
    assert "REFERENCES public.media_posts(source, external_id)" in migration_sql
    assert "^raw_[0-9a-f]{24}$" in migration_sql
    assert "^evidence_[0-9a-f]{24}$" in migration_sql
    assert "fetch_run_items_observed_utc_finite" in migration_sql
    assert "fetch_runs_lineage_times_finite" in migration_sql
    assert "'-Infinity'::DOUBLE PRECISION" in migration_sql
    assert "'Infinity'::DOUBLE PRECISION" in migration_sql


@pytest.mark.unit
def test_running_to_terminal_allowlist_includes_only_new_lineage_field(migration_sql):
    function = re.search(
        r"CREATE OR REPLACE FUNCTION public\.enforce_fetch_run_lifecycle\(\).*?"
        r"mutable_finish_fields CONSTANT TEXT\[\] := ARRAY\[(?P<fields>.*?)\]::TEXT\[\]",
        migration_sql,
        flags=re.DOTALL,
    )
    assert function is not None
    fields = set(re.findall(r"'([a-z_]+)'", function.group("fields")))
    assert fields == {
        "status",
        "received_utc",
        "completed_utc",
        "item_count",
        "inserted_count",
        "error",
        "formal_eligible_item_count",
        "formal_eligible_evidence_ids_json",
        "formal_eligible_lineage_json",
        "cursor_after",
    }
    assert "collection_cycle_id" not in fields
    assert "pg_catalog.to_jsonb(NEW) - mutable_finish_fields" in migration_sql
    assert "NEW.cost_units IS DISTINCT FROM OLD.cost_units" in migration_sql


@pytest.mark.unit
def test_lifecycle_hash_marker_matches_exact_normalized_function_body(migration_sql):
    match = re.search(
        r"CREATE OR REPLACE FUNCTION public\.enforce_fetch_run_lifecycle\(\).*?"
        r"AS \$\$(?P<body>.*?)\$\$;.*?"
        r"tradingagents\.fetch-run-lifecycle\.v2;"
        r"normalized-prosrc-sha256=(?P<digest>[0-9a-f]{64})",
        migration_sql,
        flags=re.DOTALL,
    )
    assert match is not None
    actual = hashlib.sha256(_normalized(match.group("body")).encode("utf-8")).hexdigest()
    assert actual == match.group("digest")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("function_name", "contract"),
    [
        ("formal_evidence_lineage_is_valid", "formal-evidence-lineage.v1"),
        ("enforce_fetch_run_item_lifecycle", "fetch-run-item-lifecycle.v1"),
        (
            "enforce_fetch_run_content_completion",
            "fetch-run-content-completion.v1",
        ),
    ],
)
def test_supporting_function_hash_markers_match_exact_bodies(
    migration_sql, function_name, contract,
):
    match = re.search(
        rf"CREATE OR REPLACE FUNCTION public\.{function_name}\(.*?"
        rf"AS \$\$(?P<body>.*?)\$\$;.*?"
        rf"tradingagents\.{re.escape(contract)};"
        rf"normalized-prosrc-sha256=(?P<digest>[0-9a-f]{{64}})",
        migration_sql,
        flags=re.DOTALL,
    )
    assert match is not None
    actual = hashlib.sha256(_normalized(match.group("body")).encode("utf-8")).hexdigest()
    assert actual == match.group("digest")


@pytest.mark.unit
def test_database_forces_atomic_counts_times_and_formal_projection(migration_sql):
    assert "parent.status IS DISTINCT FROM 'running'" in migration_sql
    assert "parent.provider IS DISTINCT FROM NEW.source" in migration_sql
    assert "NEW.observed_utc < parent.started_utc" in migration_sql
    assert "observed_utc IS DISTINCT FROM NEW.received_utc" in migration_sql
    assert "lineage_count IS DISTINCT FROM NEW.item_count" in migration_sql
    assert "eligible_count IS DISTINCT FROM NEW.formal_eligible_item_count" in migration_sql
    assert "lineage_payload IS DISTINCT FROM" in migration_sql
    assert "formal news receipt requires content-bound lineage" in migration_sql
    assert "fetch_run_items lineage is append-only" in migration_sql


@pytest.mark.unit
def test_content_lineage_is_canonical_and_explicit_empty_is_valid(migration_sql):
    assert "CREATE OR REPLACE FUNCTION public.formal_evidence_lineage_is_valid" in migration_sql
    assert "ARRAY['evidence_id', 'raw_content_id']::TEXT[]" in migration_sql
    assert "ORDER BY item->>'evidence_id', item->>'raw_content_id'" in migration_sql
    assert "'[]'::pg_catalog.jsonb" in migration_sql
    assert "formal_eligible_lineage_json IS NULL" in migration_sql
    assert "formal_eligible_lineage_json IS NOT NULL" in migration_sql


@pytest.mark.unit
def test_runtime_grants_preserve_owner_separation(migration_sql):
    assert "REVOKE ALL PRIVILEGES ON TABLE public.fetch_run_items FROM PUBLIC" in migration_sql
    assert (
        "GRANT SELECT, INSERT ON TABLE public.fetch_run_items\n"
        "            TO \"tradingagents-ingest-v2\""
    ) in migration_sql
    assert (
        "GRANT SELECT ON TABLE public.fetch_run_items\n"
        "            TO \"tradingagents-paper\""
    ) in migration_sql
    ingest_grant = migration_sql.split(
        'TO "tradingagents-ingest-v2";', maxsplit=1
    )[0].rsplit("GRANT", maxsplit=1)[-1]
    assert "UPDATE" not in ingest_grant
    assert "DELETE" not in ingest_grant
