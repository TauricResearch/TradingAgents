"""Static contracts for the PostgreSQL formal source-integrity migration."""

import re
from pathlib import Path

import pytest

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "003_formal_source_integrity.sql"
)
EARLY_MIGRATIONS = tuple(
    MIGRATION.parent / name
    for name in (
        "001_formal_experiment_roles.sql",
        "002_ingest_identity_rotation.sql",
        "003_formal_source_integrity.sql",
    )
)


@pytest.fixture(scope="module")
def migration_sql() -> str:
    return MIGRATION.read_text()


@pytest.mark.unit
@pytest.mark.parametrize("path", EARLY_MIGRATIONS, ids=lambda path: path.name)
def test_early_migrations_are_internally_atomic(path):
    migration = path.read_text()

    assert migration.count("BEGIN;") == 1
    assert migration.count("COMMIT;") == 1
    assert migration.index("BEGIN;") < migration.index("COMMIT;")


@pytest.mark.unit
def test_fetch_receipt_trigger_guards_the_complete_lifecycle(migration_sql):
    assert "CREATE OR REPLACE FUNCTION enforce_fetch_run_lifecycle()" in migration_sql
    assert re.search(
        r"CREATE TRIGGER immutable_fetch_runs\s+"
        r"BEFORE INSERT OR UPDATE OR DELETE ON fetch_runs\s+"
        r"FOR EACH ROW EXECUTE FUNCTION enforce_fetch_run_lifecycle\(\)",
        migration_sql,
    )
    assert "IF TG_OP = 'INSERT'" in migration_sql
    assert "NEW.status <> 'running'" in migration_sql
    assert "IF TG_OP = 'DELETE'" in migration_sql
    assert "IF OLD.status IS DISTINCT FROM 'running'" in migration_sql
    assert "NEW.status NOT IN ('success', 'empty', 'failed')" in migration_sql


@pytest.mark.unit
def test_fetch_receipt_completion_has_an_exact_mutable_field_allowlist(migration_sql):
    declaration = re.search(
        r"mutable_finish_fields CONSTANT TEXT\[\] := ARRAY\[(?P<fields>.*?)\]::TEXT\[\]",
        migration_sql,
        flags=re.DOTALL,
    )
    assert declaration is not None
    mutable_fields = set(re.findall(r"'([a-z_]+)'", declaration.group("fields")))

    assert mutable_fields == {
        "status",
        "received_utc",
        "completed_utc",
        "item_count",
        "inserted_count",
        "error",
        "formal_eligible_item_count",
        "formal_eligible_evidence_ids_json",
        "cursor_after",
    }
    assert "to_jsonb(NEW) - mutable_finish_fields" in migration_sql
    assert "to_jsonb(OLD) - mutable_finish_fields" in migration_sql

    # These request-identity and provenance fields are therefore immutable.
    assert not {
        "fetch_run_id",
        "provider",
        "query_key",
        "started_utc",
        "cursor_before",
        "metadata_json",
        "cost_units",
    } & mutable_fields


@pytest.mark.unit
def test_fetch_receipt_cost_is_reserved_once_and_cannot_be_rewritten(migration_sql):
    assert "NEW.cost_units IS DISTINCT FROM OLD.cost_units" in migration_sql
    assert "fetch_runs cost_units is fixed when the request starts" in migration_sql


@pytest.mark.unit
def test_fetch_receipt_lifecycle_ddl_is_idempotent(migration_sql):
    assert "CREATE OR REPLACE FUNCTION enforce_fetch_run_lifecycle()" in migration_sql
    assert "DROP TRIGGER IF EXISTS immutable_fetch_runs ON fetch_runs" in migration_sql
