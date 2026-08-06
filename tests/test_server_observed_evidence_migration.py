"""Server-authenticated evidence clocks and build provenance (migration 009)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from pathlib import Path

import pytest

from tradingagents.dataflows.media_store import (
    SqlAlchemyMediaStore,
    collection_cycle_spec,
)

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations/009_server_observed_evidence.sql"
)


@pytest.fixture(scope="module")
def migration_sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _normalized(value: str) -> str:
    return "\n".join(line.rstrip() for line in value.strip().splitlines())


@pytest.mark.unit
def test_migration_is_transactional_and_requires_a_paused_collector(migration_sql):
    assert MIGRATION.name == "009_server_observed_evidence.sql"
    assert migration_sql.count("BEGIN;") == 1
    assert migration_sql.count("COMMIT;") == 1
    assert "SET LOCAL search_path = pg_catalog, public;" in migration_sql
    assert "requires zero running fetches/cycles" in migration_sql
    assert "status = 'running'" in migration_sql


@pytest.mark.unit
def test_server_observation_and_build_shape_fail_closed_for_legacy_rows(migration_sql):
    for table in ("fetch_runs", "collection_cycles"):
        assert f"ALTER TABLE public.{table}" in migration_sql
    assert migration_sql.count(
        "ADD COLUMN IF NOT EXISTS server_started_utc DOUBLE PRECISION"
    ) == 2
    assert migration_sql.count(
        "ADD COLUMN IF NOT EXISTS server_terminal_utc DOUBLE PRECISION"
    ) == 2
    assert migration_sql.count("ADD COLUMN IF NOT EXISTS collector_build_id TEXT") == 2
    assert "collector_build_id ~ '^build_[0-9a-f]{24}$'" in migration_sql
    assert "server_terminal_utc >= server_started_utc" in migration_sql
    assert "server_started_utc IS NULL" in migration_sql
    assert "server_terminal_utc IS NULL" in migration_sql
    assert "collector_build_id IS NULL" in migration_sql


@pytest.mark.unit
def test_database_overrides_caller_times_and_derives_cycle_manifest_v2(migration_sql):
    assert migration_sql.count(
        "NEW.server_started_utc := pg_catalog.date_part("
    ) == 2
    assert migration_sql.count(
        "NEW.server_terminal_utc := pg_catalog.date_part("
    ) == 2
    assert "NEW.server_started_utc := OLD.server_started_utc;" in migration_sql
    assert "NEW.collector_build_id := OLD.collector_build_id;" in migration_sql
    assert "'schema_version', 2" in migration_sql
    assert "'server_started_utc', OLD.server_started_utc" in migration_sql
    assert "'server_terminal_utc', NEW.server_terminal_utc" in migration_sql
    assert "'collector_build_id', OLD.collector_build_id" in migration_sql
    assert "NEW.manifest_json := canonical_manifest" in migration_sql
    assert "idx_fetch_query_server_time" in migration_sql
    assert migration_sql.count('COLLATE "C"') >= 8


@pytest.mark.unit
@pytest.mark.parametrize(
    ("signature", "contract"),
    [
        ("canonical_jsonb_text(value JSONB)", "canonical-jsonb-text.v1"),
        ("enforce_fetch_run_lifecycle()", "fetch-run-lifecycle.v3"),
        (
            "enforce_collection_cycle_lifecycle()",
            "collection-cycle-lifecycle.v2",
        ),
        ("enforce_fetch_run_cycle_binding()", "fetch-run-cycle-binding.v2"),
    ],
)
def test_function_contract_comments_hash_exact_normalized_bodies(
    migration_sql: str, signature: str, contract: str,
):
    match = re.search(
        rf"CREATE OR REPLACE FUNCTION public\.{re.escape(signature)}.*?"
        rf"AS \$\$(?P<body>.*?)\$\$;.*?"
        rf"tradingagents\.{re.escape(contract)};"
        rf"normalized-prosrc-sha256=(?P<digest>[0-9a-f]{{64}})",
        migration_sql,
        flags=re.DOTALL,
    )
    assert match is not None
    actual = hashlib.sha256(_normalized(match.group("body")).encode()).hexdigest()
    assert actual == match.group("digest")


@pytest.mark.integration
def test_postgres_rejects_caller_backdating_for_fetches_and_cycles():
    url = os.getenv("TRADINGAGENTS_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("TRADINGAGENTS_TEST_POSTGRES_URL is not configured")

    from sqlalchemy import create_engine, text

    engine = create_engine(url)
    suffix = uuid.uuid4().hex
    fetch_run_id = str(uuid.uuid4())
    provider = f"server-time-test-{suffix}"
    query_key = f"query-{suffix}"
    build_id = f"build_{suffix[:24]}"
    cycle_spec = collection_cycle_spec(
        cycle_kind="x-daily",
        period_key=f"test-{suffix}",
        protocol_id=f"protocol-{suffix}",
        collector_semantics_id=f"collector-{suffix}",
        expected_static_slots=[(provider, query_key)],
        max_dynamic_slots=0,
    )
    try:
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO fetch_runs "
                "(fetch_run_id,provider,query_key,started_utc,status,cost_units,"
                "metadata_json,server_started_utc,server_terminal_utc,collector_build_id) "
                "VALUES (:id,:provider,:query,1,'running',0,'{}',-1,-1,:build)"
            ), {
                "id": fetch_run_id,
                "provider": provider,
                "query": query_key,
                "build": build_id,
            })
            fetch_started = float(conn.execute(text(
                "SELECT server_started_utc FROM fetch_runs WHERE fetch_run_id=:id"
            ), {"id": fetch_run_id}).scalar_one())
            cutoff_before_fetch_terminal = float(conn.execute(text(
                "SELECT pg_catalog.date_part('epoch', pg_catalog.clock_timestamp())"
            )).scalar_one())
            conn.execute(text(
                "UPDATE fetch_runs SET status='success',received_utc=2,"
                "completed_utc=3,item_count=1,inserted_count=0,error=NULL,"
                "server_started_utc=-2,server_terminal_utc=-3,collector_build_id=:other "
                "WHERE fetch_run_id=:id"
            ), {"id": fetch_run_id, "other": f"build_{'f' * 24}"})
            fetch_row = conn.execute(text(
                "SELECT started_utc,completed_utc,server_started_utc,"
                "server_terminal_utc,collector_build_id "
                "FROM fetch_runs WHERE fetch_run_id=:id"
            ), {"id": fetch_run_id}).mappings().one()

            identity_json = json.dumps(
                cycle_spec["identity"],
                sort_keys=True,
                separators=(",", ":"),
            )
            conn.execute(text(
                "INSERT INTO collection_cycles "
                "(collection_cycle_id,cycle_kind,period_key,protocol_id,"
                "collector_semantics_id,identity_json,started_utc,status,"
                "server_started_utc,server_terminal_utc,collector_build_id) "
                "VALUES (:id,'x-daily',:period,:protocol,:collector,:identity,"
                "1,'running',-1,-1,:build)"
            ), {
                "id": cycle_spec["collection_cycle_id"],
                "period": cycle_spec["identity"]["period_key"],
                "protocol": cycle_spec["identity"]["protocol_id"],
                "collector": cycle_spec["identity"]["collector_semantics_id"],
                "identity": identity_json,
                "build": build_id,
            })
            conn.execute(text(
                "INSERT INTO collection_cycle_slots "
                "(collection_cycle_id,provider,query_key,slot_kind,declared_utc) "
                "VALUES (:id,:provider,:query,'static',1)"
            ), {
                "id": cycle_spec["collection_cycle_id"],
                "provider": provider,
                "query": query_key,
            })
            cutoff_before_cycle_terminal = float(conn.execute(text(
                "SELECT pg_catalog.date_part('epoch', pg_catalog.clock_timestamp())"
            )).scalar_one())
            conn.execute(text(
                "UPDATE collection_cycles SET status='incomplete',completed_utc=2,"
                "manifest_id='cycle_manifest_000000000000000000000000',"
                "manifest_json='{}',server_started_utc=-2,server_terminal_utc=-3,"
                "collector_build_id=:other WHERE collection_cycle_id=:id"
            ), {
                "id": cycle_spec["collection_cycle_id"],
                "other": f"build_{'f' * 24}",
            })
            cycle_row = conn.execute(text(
                "SELECT started_utc,completed_utc,server_started_utc,"
                "server_terminal_utc,collector_build_id,manifest_id,manifest_json "
                "FROM collection_cycles WHERE collection_cycle_id=:id"
            ), {"id": cycle_spec["collection_cycle_id"]}).mappings().one()

        assert fetch_row["started_utc"] == 1
        assert fetch_row["completed_utc"] == 3
        assert fetch_row["server_started_utc"] == fetch_started
        assert fetch_row["server_started_utc"] > 1
        assert fetch_row["server_terminal_utc"] >= cutoff_before_fetch_terminal
        assert fetch_row["collector_build_id"] == build_id
        assert cycle_row["started_utc"] == 1
        assert cycle_row["completed_utc"] == 2
        assert cycle_row["server_started_utc"] > 1
        assert cycle_row["server_terminal_utc"] >= cutoff_before_cycle_terminal
        assert cycle_row["collector_build_id"] == build_id
        manifest = json.loads(cycle_row["manifest_json"])
        assert manifest["schema_version"] == 2
        assert manifest["server_started_utc"] == cycle_row["server_started_utc"]
        assert manifest["server_terminal_utc"] == cycle_row["server_terminal_utc"]
        assert manifest["collector_build_id"] == build_id

        store = SqlAlchemyMediaStore(url)
        try:
            before = store.coverage_report(
                cutoff_before_fetch_terminal,
                [],
                expected_query_slots=[(provider, query_key)],
            )
            after = store.coverage_report(
                float(fetch_row["server_terminal_utc"]) + 1.0,
                [],
                expected_query_slots=[(provider, query_key)],
            )
        finally:
            store.close()
        assert not before["complete"]
        assert before["missing_query_slots"][0]["reason"] == "incomplete"
        assert after["complete"]
    finally:
        engine.dispose()
