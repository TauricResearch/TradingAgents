"""Immutable collection-cycle identities, child binding, and terminal manifests."""

import os
import sqlite3
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from tradingagents.dataflows import media_store as media_store_module
from tradingagents.dataflows.media_store import (
    SqlAlchemyMediaStore,
    SqliteMediaStore,
    collection_cycle_spec,
)

_MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
_CHECK_RENDERING_COLUMNS = {
    "collection_cycles": (
        "status",
        "manifest_id",
        "manifest_json",
        "collector_build_id",
    ),
    "collection_cycle_slots": ("provider", "query_key"),
    "fetch_runs": ("collector_build_id",),
}
_DUAL_RENDERING_CONSTRAINTS = {
    ("collection_cycles", "collection_cycles_server_observation_shape"),
    ("collection_cycles", "collection_cycles_terminal_shape"),
    ("collection_cycle_slots", "collection_cycle_slots_fields_valid"),
    ("fetch_runs", "fetch_runs_server_observation_shape"),
}


def _migration_admin_dsn(url: str) -> str:
    from sqlalchemy.engine import make_url

    return make_url(url).set(
        drivername="postgresql",
        username="schema_admin",
        password=None,
    ).render_as_string(hide_password=False)


def _run_collector_migration(url: str, migration: str) -> None:
    import psycopg

    with psycopg.connect(_migration_admin_dsn(url), autocommit=True) as conn:
        conn.execute(
            (_MIGRATIONS / migration).read_text(encoding="utf-8"),
            prepare=False,
        )


def _drop_dual_rendering_constraints(conn) -> None:
    from psycopg import sql

    for table, constraint in _DUAL_RENDERING_CONSTRAINTS:
        conn.execute(sql.SQL(
            "ALTER TABLE public.{} DROP CONSTRAINT IF EXISTS {}"
        ).format(sql.Identifier(table), sql.Identifier(constraint)))


def _set_check_rendering_column_types(conn, type_names: dict) -> None:
    from psycopg import sql

    allowed = {"text": sql.SQL("TEXT"), "character varying": sql.SQL("VARCHAR")}
    for table, columns in _CHECK_RENDERING_COLUMNS.items():
        for column in columns:
            type_name = type_names[(table, column)]
            if type_name not in allowed:
                raise AssertionError(f"unexpected fixture type: {type_name}")
            conn.execute(sql.SQL(
                "ALTER TABLE public.{} ALTER COLUMN {} TYPE {}"
            ).format(
                sql.Identifier(table),
                sql.Identifier(column),
                allowed[type_name],
            ))


def _check_rendering_column_types(conn) -> dict:
    rows = conn.execute(
        "SELECT relation.relname, attribute.attname, type_record.typname "
        "FROM pg_catalog.pg_attribute AS attribute "
        "JOIN pg_catalog.pg_class AS relation "
        "ON relation.oid = attribute.attrelid "
        "JOIN pg_catalog.pg_namespace AS namespace "
        "ON namespace.oid = relation.relnamespace "
        "JOIN pg_catalog.pg_type AS type_record "
        "ON type_record.oid = attribute.atttypid "
        "WHERE namespace.nspname = 'public' "
        "AND (relation.relname, attribute.attname) IN ("
        "('collection_cycles', 'status'), "
        "('collection_cycles', 'manifest_id'), "
        "('collection_cycles', 'manifest_json'), "
        "('collection_cycles', 'collector_build_id'), "
        "('collection_cycle_slots', 'provider'), "
        "('collection_cycle_slots', 'query_key'), "
        "('fetch_runs', 'collector_build_id'))"
    ).fetchall()
    type_name = {"text": "text", "varchar": "character varying"}
    return {
        (table, column): type_name[postgres_type]
        for table, column, postgres_type in rows
    }


def _dual_check_constraint_hashes(conn) -> dict:
    rows = conn.execute(
        "SELECT relation.relname, constraint_record.conname, "
        "pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to("
        "pg_catalog.regexp_replace(pg_catalog.btrim("
        "pg_catalog.pg_get_constraintdef(constraint_record.oid, false), "
        "E' \\n\\r\\t'), E'[ \\t]+\\n', E'\\n', 'g'), "
        "'UTF8')), 'hex') "
        "FROM pg_catalog.pg_constraint AS constraint_record "
        "JOIN pg_catalog.pg_class AS relation "
        "ON relation.oid = constraint_record.conrelid "
        "JOIN pg_catalog.pg_namespace AS namespace "
        "ON namespace.oid = relation.relnamespace "
        "WHERE namespace.nspname = 'public' "
        "AND constraint_record.conname = ANY(%s) "
        "ORDER BY relation.relname, constraint_record.conname",
        ([constraint for _, constraint in _DUAL_RENDERING_CONSTRAINTS],),
    ).fetchall()
    return {(table, constraint): digest for table, constraint, digest in rows}


def _spec(*, static=None, dynamic=2):
    return collection_cycle_spec(
        cycle_kind="x-daily",
        period_key="2026-08-05",
        protocol_id="protocol_test",
        collector_semantics_id="collector_test",
        expected_static_slots=static or [
            ("trendnews", "ranked-global-discovery"),
            ("xtrend", "woeid:1"),
        ],
        max_dynamic_slots=dynamic,
    )


def _finish(store, run_id, status, *, started=101.0):
    store.finish_fetch(
        run_id,
        status=status,
        received_utc=started,
        completed_utc=started + 1,
        item_count=1 if status == "success" else 0,
        inserted_count=0,
        error="upstream_failure" if status == "failed" else None,
        formal_eligible_item_count=0,
        formal_eligible_evidence_ids=[],
        formal_eligible_lineage=[],
    )


@pytest.fixture
def store(tmp_path):
    value = SqliteMediaStore(tmp_path / "cycles.db")
    yield value
    value.close()


@pytest.mark.unit
def test_cycle_identity_is_deterministic_canonical_and_known_before_requests():
    first = _spec()
    second = _spec(static=[("xtrend", "woeid:1"), (
        "trendnews", "ranked-global-discovery"
    )])

    assert first == second
    assert first["collection_cycle_id"].startswith("cycle_")
    assert len(first["collection_cycle_id"]) == 30
    assert first["identity"]["expected_static_slots"] == [
        {"provider": "trendnews", "query_key": "ranked-global-discovery"},
        {"provider": "xtrend", "query_key": "woeid:1"},
    ]


@pytest.mark.unit
@pytest.mark.parametrize("backend", ["sqlite", "sqlalchemy"])
def test_cycle_identity_inventory_is_distinct_ordered_and_kind_scoped(
    backend, tmp_path,
):
    value = (
        SqliteMediaStore(tmp_path / "identity-inventory.db")
        if backend == "sqlite"
        else SqlAlchemyMediaStore(
            f"sqlite+pysqlite:///{tmp_path / 'identity-inventory-sa.db'}"
        )
    )
    try:
        specs = [
            collection_cycle_spec(
                cycle_kind=kind,
                period_key=period,
                protocol_id=protocol,
                collector_semantics_id=collector,
                expected_static_slots=[("xtrend", "woeid:1")],
                max_dynamic_slots=0,
            )
            for kind, period, protocol, collector in [
                ("x-daily", "2026-08-05", "protocol_b", "collector_b"),
                ("x-daily", "2026-08-06", "protocol_a", "collector_a"),
                ("x-daily", "2026-08-07", "protocol_a", "collector_a"),
                ("global-hourly", "2026-08-07T00", "protocol_c", "collector_c"),
            ]
        ]
        for offset, spec in enumerate(specs):
            value.start_collection_cycle(spec, started_utc=100.0 + offset)

        assert value.collection_cycle_identity_pairs("x-daily") == [
            ("protocol_a", "collector_a"),
            ("protocol_b", "collector_b"),
        ]
        assert value.collection_cycle_identity_pairs("global-hourly") == [
            ("protocol_c", "collector_c")
        ]
        with pytest.raises(ValueError, match="lowercase slug"):
            value.collection_cycle_identity_pairs("X Daily")
    finally:
        value.close()


@pytest.mark.unit
def test_cycle_spec_rejects_tampering_and_unbounded_slots(store):
    spec = _spec()
    tampered = {**spec, "collection_cycle_id": f"cycle_{1:024x}"}
    with pytest.raises(ValueError, match="content-addressed"):
        store.start_collection_cycle(tampered, started_utc=100.0)
    with pytest.raises(ValueError, match="dynamic-slot cap"):
        collection_cycle_spec(
            cycle_kind="x-daily",
            period_key="2026-08-05",
            protocol_id="protocol_test",
            collector_semantics_id="collector_test",
            expected_static_slots=[("xtrend", "woeid:1")],
            max_dynamic_slots=101,
        )


@pytest.mark.unit
def test_child_receipts_require_declared_running_slots_and_are_unique(store):
    cycle_id = store.start_collection_cycle(_spec(), started_utc=100.0)

    with pytest.raises(ValueError, match="declared running cycle slot"):
        store.start_fetch("x", "undeclared", 101.0, collection_cycle_id=cycle_id)
    store.declare_collection_cycle_slots(
        cycle_id, [("x", "broad global story")], declared_utc=101.0
    )
    run = store.start_fetch(
        "x", "broad global story", 102.0, collection_cycle_id=cycle_id
    )
    with pytest.raises(ValueError, match="already has a receipt"):
        store.start_fetch(
            "x", "broad global story", 103.0, collection_cycle_id=cycle_id
        )
    _finish(store, run, "empty", started=104.0)


@pytest.mark.unit
def test_terminal_manifest_distinguishes_success_empty_failed_and_missing(store):
    cycle_id = store.start_collection_cycle(_spec(), started_utc=100.0)
    store.declare_collection_cycle_slots(
        cycle_id,
        [("x", "first broad story"), ("x", "second broad story")],
        declared_utc=100.5,
    )
    success = store.start_fetch(
        "xtrend", "woeid:1", 101.0, collection_cycle_id=cycle_id
    )
    empty = store.start_fetch(
        "trendnews", "ranked-global-discovery", 101.0,
        collection_cycle_id=cycle_id,
    )
    failed = store.start_fetch(
        "x", "first broad story", 101.0, collection_cycle_id=cycle_id
    )
    _finish(store, success, "success")
    _finish(store, empty, "empty")
    _finish(store, failed, "failed")

    cycle = store.finish_collection_cycle(cycle_id, completed_utc=104.0)

    outcomes = {
        (row["provider"], row["query_key"]): row
        for row in cycle["manifest"]["slot_receipts"]
    }
    assert cycle["status"] == "incomplete"
    assert cycle["identity_valid"] is True
    assert cycle["manifest_valid"] is True
    assert outcomes[("xtrend", "woeid:1")]["status"] == "success"
    assert outcomes[("trendnews", "ranked-global-discovery")]["status"] == "empty"
    assert outcomes[("x", "first broad story")]["status"] == "failed"
    assert outcomes[("x", "second broad story")] == {
        "slot_kind": "dynamic",
        "provider": "x",
        "query_key": "second broad story",
        "fetch_run_id": None,
        "status": "missing",
        "item_count": None,
        "raw_content_ids": [],
    }
    assert outcomes[("x", "first broad story")]["fetch_run_id"] == failed


@pytest.mark.unit
def test_observed_empty_is_a_complete_cycle_not_an_availability_failure(store):
    spec = _spec(static=[("xtrend", "woeid:1")], dynamic=0)
    cycle_id = store.start_collection_cycle(spec, started_utc=100.0)
    run = store.start_fetch(
        "xtrend", "woeid:1", 101.0, collection_cycle_id=cycle_id
    )
    _finish(store, run, "empty")

    cycle = store.finish_collection_cycle(cycle_id, completed_utc=103.0)

    assert cycle["status"] == "complete"
    assert cycle["manifest"]["schema_version"] == 2
    assert cycle["manifest"]["collector_build_id"] == cycle["collector_build_id"]
    assert cycle["manifest"]["server_started_utc"] == cycle["server_started_utc"]
    assert cycle["manifest"]["server_terminal_utc"] == cycle["server_terminal_utc"]
    assert cycle["manifest"]["slot_receipts"][0]["status"] == "empty"


@pytest.mark.unit
def test_crash_leaves_running_cycle_and_conservative_paid_receipt(store, monkeypatch):
    clock = {"now": 1_000.0}
    monkeypatch.setattr(
        "tradingagents.dataflows.media_store.time.time", lambda: clock["now"]
    )
    spec = _spec(static=[("xtrend", "woeid:1")], dynamic=0)
    cycle_id = store.start_collection_cycle(spec, started_utc=100.0)
    run = store.start_budgeted_fetch(
        "xtrend",
        "woeid:1",
        101.0,
        collection_cycle_id=cycle_id,
        budget_limits={"x-budget:trend:day:total": 1.0},
    )

    cycle = store.collection_cycle(cycle_id)
    receipt = store.fetch_runs(provider="xtrend")[0]
    assert run is not None
    assert cycle["status"] == "running"
    assert cycle["manifest"] is None
    assert receipt["status"] == "running"
    assert receipt["cost_units"] == 1.0
    assert store.get_meta("x-budget:trend:day:total") == 1.0
    with pytest.raises(ValueError, match="child receipt is running"):
        store.finish_collection_cycle(cycle_id, completed_utc=102.0)

    with pytest.raises(ValueError, match="not stale enough"):
        store.recover_collection_cycle(
            cycle_id, recovered_utc=100.5, minimum_age_seconds=1.0
        )
    clock["now"] = 1_002.0
    recovered = store.recover_collection_cycle(
        cycle_id, recovered_utc=103.0, minimum_age_seconds=1.0
    )
    receipt = store.fetch_runs(provider="xtrend")[0]
    assert recovered["status"] == "incomplete"
    assert receipt["status"] == "failed"
    assert receipt["error"] == "collector_restart_recovery"
    assert receipt["cost_units"] == 1.0


@pytest.mark.unit
def test_cycle_and_slots_are_immutable_and_malformed_transition_fails_closed(store):
    cycle_id = store.start_collection_cycle(_spec(), started_utc=100.0)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        store.conn.execute(
            "UPDATE collection_cycle_slots SET query_key='tampered' "
            "WHERE collection_cycle_id=?", (cycle_id,),
        )
    store.conn.rollback()
    with pytest.raises(sqlite3.IntegrityError, match="server-current"):
        store.conn.execute(
            "UPDATE collection_cycles SET status='complete',completed_utc=101.0,"
            "manifest_id=?,manifest_json='{}' WHERE collection_cycle_id=?",
            (f"cycle_manifest_{1:024x}", cycle_id),
        )
    store.conn.rollback()
    cycle = store.finish_collection_cycle(cycle_id, completed_utc=102.0)
    assert cycle["status"] == "incomplete"
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        store.conn.execute(
            "DELETE FROM collection_cycles WHERE collection_cycle_id=?", (cycle_id,)
        )
    store.conn.rollback()


@pytest.mark.unit
def test_dynamic_slot_cap_is_enforced_before_any_child_request(store):
    cycle_id = store.start_collection_cycle(_spec(dynamic=1), started_utc=100.0)
    with pytest.raises(ValueError, match="exceed cap"):
        store.declare_collection_cycle_slots(
            cycle_id,
            [("x", "first broad story"), ("x", "second broad story")],
            declared_utc=101.0,
        )
    assert store.collection_cycle_slots(cycle_id) == [
        {
            "collection_cycle_id": cycle_id,
            "provider": "trendnews",
            "query_key": "ranked-global-discovery",
            "slot_kind": "static",
            "declared_utc": 100.0,
        },
        {
            "collection_cycle_id": cycle_id,
            "provider": "xtrend",
            "query_key": "woeid:1",
            "slot_kind": "static",
            "declared_utc": 100.0,
        },
    ]


@pytest.mark.unit
def test_sqlalchemy_backend_has_collection_cycle_parity(tmp_path):
    store = SqlAlchemyMediaStore(f"sqlite+pysqlite:///{tmp_path / 'cycles-sa.db'}")
    try:
        cycle_id = store.start_collection_cycle(
            _spec(static=[("xtrend", "woeid:1")], dynamic=1),
            started_utc=100.0,
        )
        store.declare_collection_cycle_slots(
            cycle_id, [("x", "global event")], declared_utc=101.0
        )
        trend = store.start_fetch(
            "xtrend", "woeid:1", 102.0, collection_cycle_id=cycle_id
        )
        search = store.start_fetch(
            "x", "global event", 102.0, collection_cycle_id=cycle_id
        )
        _finish(store, trend, "success", started=103.0)
        _finish(store, search, "empty", started=103.0)
        cycle = store.finish_collection_cycle(cycle_id, completed_utc=105.0)
        assert cycle["status"] == "complete"
        assert cycle["manifest_valid"] is True
        assert {run["collection_cycle_id"] for run in store.fetch_runs()} == {cycle_id}
    finally:
        store.close()


@pytest.mark.unit
def test_postgres_cycle_binding_locks_only_mutable_cycle_parent(tmp_path):
    from sqlalchemy.dialects import postgresql

    store = SqlAlchemyMediaStore(f"sqlite+pysqlite:///{tmp_path / 'lock-scope.db'}")
    cycle_id = f"cycle_{'a' * 24}"
    statements = []

    class _Result:
        @staticmethod
        def first():
            return (cycle_id,)

    class _Connection:
        @staticmethod
        def execute(statement):
            statements.append(str(statement.compile(dialect=postgresql.dialect())))
            return _Result()

    try:
        assert store._validate_cycle_fetch_binding(
            _Connection(), cycle_id, "xtrend", "woeid:1", 1.0
        ) == cycle_id
    finally:
        store.close()

    sql = " ".join(statements[0].split())
    assert "JOIN collection_cycle_slots" in sql
    assert sql.endswith("FOR UPDATE OF collection_cycles")


@pytest.mark.integration
def test_pgbouncer_transaction_pool_disables_named_prepared_statements():
    """Two psycopg clients must safely share one transaction-pooled backend."""
    url = os.getenv("TRADINGAGENTS_TEST_POSTGRES_POOL_URL")
    if not url:
        pytest.skip("TRADINGAGENTS_TEST_POSTGRES_POOL_URL is not configured")

    from sqlalchemy import text

    clients = []
    statement = text("SELECT CAST(:probe_value AS INTEGER)")
    try:
        clients.append(SqlAlchemyMediaStore(url, auto_migrate=False))
        clients.append(SqlAlchemyMediaStore(url, auto_migrate=False))
        # psycopg's default threshold is five executions. Alternating seven
        # committed transactions per independent frontend deterministically
        # crosses that threshold while PgBouncer reuses its sole backend.
        for sequence in range(7):
            for client_number, client in enumerate(clients):
                expected = sequence * len(clients) + client_number
                with client.engine.connect() as conn:
                    assert conn.execute(
                        statement, {"probe_value": expected}
                    ).scalar_one() == expected
                    conn.commit()
    finally:
        for client in clients:
            client.close()


@pytest.mark.integration
def test_postgres_ingest_role_can_start_cycle_bound_fetches():
    """Regression: immutable slots need SELECT, not accidental row-lock authority."""
    url = os.getenv("TRADINGAGENTS_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("TRADINGAGENTS_TEST_POSTGRES_URL is not configured")

    suffix = uuid.uuid4().hex
    started = time.time()
    spec = collection_cycle_spec(
        cycle_kind="x-daily",
        period_key=f"runtime-lock-{suffix}",
        protocol_id=f"protocol-{suffix}",
        collector_semantics_id=f"collector-{suffix}",
        expected_static_slots=[
            ("trendnews", f"discovery-{suffix}"),
            ("xtrend", f"woeid-{suffix}"),
        ],
        max_dynamic_slots=0,
    )
    store = SqlAlchemyMediaStore(url)
    try:
        cycle_id = store.start_collection_cycle(spec, started_utc=started)
        free_run = store.start_fetch(
            "trendnews",
            f"discovery-{suffix}",
            started + 1,
            collection_cycle_id=cycle_id,
        )
        paid_run = store.start_budgeted_fetch(
            "xtrend",
            f"woeid-{suffix}",
            started + 1,
            collection_cycle_id=cycle_id,
            budget_limits={f"integration-budget-{suffix}": 1.0},
        )
        assert paid_run is not None
        store.finish_fetch(
            free_run,
            status="failed",
            received_utc=started + 2,
            completed_utc=started + 3,
            item_count=0,
            inserted_count=0,
            error="integration_test_terminal",
        )
        store.finish_fetch(
            paid_run,
            status="failed",
            received_utc=started + 2,
            completed_utc=started + 3,
            item_count=0,
            inserted_count=0,
            error="integration_test_terminal",
            cost_units=1.0,
        )
        cycle = store.finish_collection_cycle(
            cycle_id, completed_utc=started + 4
        )
        assert cycle["status"] == "incomplete"
    finally:
        store.close()


@pytest.mark.integration
def test_postgres_meta_first_write_is_atomic_under_concurrency():
    """Concurrent first writes must upsert instead of racing two INSERTs."""
    url = os.getenv("TRADINGAGENTS_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("TRADINGAGENTS_TEST_POSTGRES_URL is not configured")

    worker_count = 12
    barrier = threading.Barrier(worker_count)
    key = f"integration-meta-race-{uuid.uuid4().hex}"

    def write(value: int) -> None:
        worker = SqlAlchemyMediaStore(url, auto_migrate=False)
        try:
            barrier.wait(timeout=10)
            worker.set_meta(key, float(value))
        finally:
            worker.close()

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        list(executor.map(write, range(worker_count)))

    verifier = SqlAlchemyMediaStore(url, auto_migrate=False)
    try:
        assert verifier.get_meta(key) in {
            float(value) for value in range(worker_count)
        }
    finally:
        verifier.close()


@pytest.mark.integration
def test_postgres_ingest_role_passes_read_only_runtime_preflight():
    url = os.getenv("TRADINGAGENTS_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("TRADINGAGENTS_TEST_POSTGRES_URL is not configured")

    from sqlalchemy import func, select, text

    store = SqlAlchemyMediaStore(url, auto_migrate=False)
    collector_tables = (
        store.table,
        store.labels,
        store.observations,
        store.odds,
        store.state,
        store.cycles,
        store.cycle_slots,
        store.fetches,
        store.fetch_items_table,
    )

    def row_counts() -> dict[str, int]:
        with store.engine.connect() as conn:
            return {
                table.name: int(conn.execute(
                    select(func.count()).select_from(table)
                ).scalar_one())
                for table in collector_tables
            }

    transaction_settings_query = text(
        "SELECT "
        "pg_catalog.current_setting('lock_timeout')::INTERVAL = "
        "INTERVAL '5 seconds' AS lock_timeout_valid, "
        "pg_catalog.current_setting('statement_timeout')::INTERVAL = "
        "INTERVAL '60 seconds' AS statement_timeout_valid, "
        "pg_catalog.current_setting("
        "'idle_in_transaction_session_timeout')::INTERVAL = "
        "INTERVAL '60 seconds' AS idle_timeout_valid, "
        "pg_catalog.current_schemas(false)::TEXT[] = "
        "ARRAY['pg_catalog','public']::TEXT[] AS search_path_valid"
    )

    try:
        with store.engine.connect() as conn:
            # The begin hook runs before this command. PostgreSQL still permits
            # the release gate to make the transaction read-only afterward.
            conn.execute(text("SET TRANSACTION READ ONLY"))
            first_settings = conn.execute(
                transaction_settings_query
            ).mappings().one()
            assert conn.execute(text(
                "SELECT pg_catalog.current_setting('transaction_read_only') = 'on'"
            )).scalar_one() is True
            conn.rollback()

            # A new implicit transaction on the same logical connection gets
            # the complete SET LOCAL policy again after the prior rollback.
            second_settings = conn.execute(
                transaction_settings_query
            ).mappings().one()
            conn.rollback()
        assert all(first_settings.values())
        assert all(second_settings.values())

        before = row_counts()
        report = store.collector_runtime_preflight()
        after = row_counts()
    finally:
        store.close()

    assert after == before
    assert report["contract_version"] == 3
    assert report["postgresql"] is True
    assert report["connected"] is True
    assert report["database_clock_valid"] is True
    assert report["required_table_count"] == len(collector_tables)
    assert report["selectable_table_count"] == len(collector_tables)
    assert report["resolved_relation_count"] == len(collector_tables)
    assert report["exact_column_table_count"] == len(collector_tables)
    assert report["required_column_count"] == sum(
        len(table.columns) for table in collector_tables
    )
    assert report["selectable_column_count"] == report["required_column_count"]
    assert report["authenticated_column_count"] == report["required_column_count"]
    assert report["required_select_count"] == len(collector_tables)
    assert report["required_insert_count"] == len(collector_tables)
    assert report["required_update_count"] == 3
    assert report["forbidden_update_count"] == 0
    assert report["forbidden_delete_count"] == 0
    assert report["forbidden_truncate_count"] == 0
    assert report["schema_create_count"] == 0
    assert report["database_create_violation_count"] == 0
    assert report["row_security_violation_count"] == 0
    assert report["role_attribute_violation_count"] == 0
    assert report["required_trigger_count"] == 6
    assert report["active_trigger_count"] == 6
    assert report["required_function_contract_count"] == 7
    assert report["authenticated_function_contract_count"] == 7
    assert report["active_constraint_count"] == report["required_constraint_count"]
    assert report["active_index_count"] == report["required_index_count"] == 1
    assert report["search_path_valid"] is True
    assert report["relation_resolution_valid"] is True
    assert report["cycle_parent_lock_authority_valid"] is True
    assert report["direct_endpoint_resolved"] is True
    assert report["session_affinity_valid"] is True
    assert report["advisory_lock_valid"] is True
    assert report["tables_selectable"] is True
    assert report["column_contracts_valid"] is True
    assert report["privileges_valid"] is True
    assert report["role_attributes_valid"] is True
    assert report["integrity_triggers_valid"] is True
    assert report["function_contracts_valid"] is True
    assert report["constraints_valid"] is True
    assert report["indexes_valid"] is True
    assert report["ready"] is True
    assert report["failure_stage"] is None
    assert report["failure_type"] is None
    assert all(
        value is None or isinstance(value, (bool, int))
        for value in report.values()
    )
    assert url not in repr(report)
    assert "tradingagents-ingest-v2" not in repr(report)


@pytest.mark.integration
def test_postgres_preflight_accepts_checks_reparsed_from_migrations_on_text():
    url = os.getenv("TRADINGAGENTS_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("TRADINGAGENTS_TEST_POSTGRES_URL is not configured")
    if not os.getenv("PG_SUPERUSER"):
        pytest.skip("migration administrator is not configured")

    import psycopg

    expected_text_hashes = {
        ("collection_cycles", "collection_cycles_server_observation_shape"):
            "5a7d186cbedb49381bbd640248bc8995ba879b17b3272fc16c10f73b381f5cb5",
        ("collection_cycles", "collection_cycles_terminal_shape"):
            "5f7ed45574b1478a90542be46737165e889ee1b26d5a71fc06982d93b338ef2d",
        ("collection_cycle_slots", "collection_cycle_slots_fields_valid"):
            "c5bf085bba9e3cabf3c608711a145d626f03583a40e2fc95b53a5dd88eff429c",
        ("fetch_runs", "fetch_runs_server_observation_shape"):
            "6888a83094963c822b6eaaae750a7dc442a5ab1292f8b74e9cf93798d1e1c2a1",
    }
    assert all(
        digest in media_store_module._COLLECTOR_CHECK_CONSTRAINT_HASHES[key]
        for key, digest in expected_text_hashes.items()
    )
    admin_dsn = _migration_admin_dsn(url)
    original_types = None
    report = None
    try:
        with psycopg.connect(admin_dsn, autocommit=True) as admin:
            original_types = _check_rendering_column_types(admin)
            assert set(original_types) == {
                (table, column)
                for table, columns in _CHECK_RENDERING_COLUMNS.items()
                for column in columns
            }
            _drop_dual_rendering_constraints(admin)
            _set_check_rendering_column_types(
                admin, dict.fromkeys(original_types, "text")
            )
        # The production migrations, rather than hand-copied CHECK text in the
        # test, reparse the predicates against the legacy TEXT representation.
        _run_collector_migration(url, "007_collection_cycles.sql")
        _run_collector_migration(url, "009_server_observed_evidence.sql")
        with psycopg.connect(admin_dsn, autocommit=True) as admin:
            assert _dual_check_constraint_hashes(admin) == expected_text_hashes
        store = SqlAlchemyMediaStore(url, auto_migrate=False)
        try:
            report = store.collector_runtime_preflight(direct_url=url)
        finally:
            store.close()
    finally:
        if original_types is not None:
            with psycopg.connect(admin_dsn, autocommit=True) as admin:
                _drop_dual_rendering_constraints(admin)
                _set_check_rendering_column_types(admin, original_types)
            _run_collector_migration(url, "007_collection_cycles.sql")
            _run_collector_migration(url, "009_server_observed_evidence.sql")

    assert report is not None
    assert report["authenticated_column_count"] == 75
    assert report["column_contracts_valid"] is True
    assert report["active_constraint_count"] == report["required_constraint_count"]
    assert report["constraints_valid"] is True
    assert report["ready"] is True


@pytest.mark.integration
def test_postgres_preflight_rejects_bounded_string_type():
    url = os.getenv("TRADINGAGENTS_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("TRADINGAGENTS_TEST_POSTGRES_URL is not configured")
    if not os.getenv("PG_SUPERUSER"):
        pytest.skip("migration administrator is not configured")

    import psycopg
    from psycopg import sql

    report = None
    with psycopg.connect(_migration_admin_dsn(url), autocommit=True) as admin:
        row = admin.execute(
            "SELECT type_record.typname, attribute.atttypmod "
            "FROM pg_catalog.pg_attribute AS attribute "
            "JOIN pg_catalog.pg_type AS type_record "
            "ON type_record.oid = attribute.atttypid "
            "WHERE attribute.attrelid = 'public.media_posts'::regclass "
            "AND attribute.attname = 'author'"
        ).fetchone()
        assert row is not None and row[0] in {"text", "varchar"} and row[1] == -1
        original_type = "TEXT" if row[0] == "text" else "VARCHAR"
        admin.execute(
            "ALTER TABLE public.media_posts ALTER COLUMN author TYPE VARCHAR(64)"
        )
    try:
        store = SqlAlchemyMediaStore(url, auto_migrate=False)
        try:
            report = store.collector_runtime_preflight(direct_url=url)
        finally:
            store.close()
    finally:
        with psycopg.connect(_migration_admin_dsn(url), autocommit=True) as admin:
            admin.execute(sql.SQL(
                "ALTER TABLE public.media_posts ALTER COLUMN author TYPE {}"
            ).format(sql.SQL(original_type)))

    assert report is not None
    assert report["authenticated_column_count"] == 74
    assert report["column_contracts_valid"] is False
    assert report["tables_selectable"] is True
    assert report["ready"] is False
    assert report["failure_stage"] == "primary_contract"
    assert report["failure_type"] == "ContractMismatch"


@pytest.mark.integration
def test_postgres_collector_singleton_lease_blocks_overlap_and_releases():
    url = os.getenv("TRADINGAGENTS_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("TRADINGAGENTS_TEST_POSTGRES_URL is not configured")

    owner = SqlAlchemyMediaStore(url, auto_migrate=False)
    contender = SqlAlchemyMediaStore(url, auto_migrate=False)
    first_lease = None
    second_lease = None
    try:
        first_lease = owner.acquire_collector_lease(direct_url=url)
        assert first_lease is not None
        assert first_lease.is_held is True
        first_lease.assert_held()
        assert contender.acquire_collector_lease(direct_url=url) is None

        first_lease.close()
        first_lease = None
        second_lease = contender.acquire_collector_lease(direct_url=url)
        assert second_lease is not None
    finally:
        if first_lease is not None:
            first_lease.close()
        if second_lease is not None:
            second_lease.close()
        owner.close()
        contender.close()


@pytest.mark.integration
def test_postgres_preflight_rejects_pre_009_function_contracts_and_recovers():
    url = os.getenv("TRADINGAGENTS_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("TRADINGAGENTS_TEST_POSTGRES_URL is not configured")
    if not os.getenv("PG_SUPERUSER"):
        pytest.skip("migration administrator is not configured")

    stale_report = None
    try:
        _run_collector_migration(url, "006_atomic_fetch_lineage.sql")
        _run_collector_migration(url, "007_collection_cycles.sql")
        stale = SqlAlchemyMediaStore(url, auto_migrate=False)
        try:
            stale_report = stale.collector_runtime_preflight(direct_url=url)
        finally:
            stale.close()
    finally:
        _run_collector_migration(url, "009_server_observed_evidence.sql")

    assert stale_report is not None
    assert stale_report["authenticated_function_contract_count"] == 4
    assert stale_report["required_function_contract_count"] == 7
    assert stale_report["function_contracts_valid"] is False
    assert stale_report["ready"] is False
    assert stale_report["failure_stage"] == "primary_contract"
    assert stale_report["failure_type"] == "ContractMismatch"

    restored = SqlAlchemyMediaStore(url, auto_migrate=False)
    try:
        restored_report = restored.collector_runtime_preflight(direct_url=url)
    finally:
        restored.close()
    assert restored_report["function_contracts_valid"] is True
    assert restored_report["ready"] is True


@pytest.mark.integration
def test_postgres_preflight_rejects_database_create_authority():
    url = os.getenv("TRADINGAGENTS_TEST_POSTGRES_URL")
    superuser = os.getenv("PG_SUPERUSER")
    if not url:
        pytest.skip("TRADINGAGENTS_TEST_POSTGRES_URL is not configured")
    if not superuser:
        pytest.skip("PostgreSQL superuser is not configured")

    import psycopg
    from psycopg import sql
    from sqlalchemy.engine import make_url

    parsed = make_url(url)
    admin_dsn = parsed.set(
        drivername="postgresql",
        username=superuser,
        password=None,
    ).render_as_string(hide_password=False)
    role = "tradingagents-ingest-v2"
    database = parsed.database
    assert database is not None
    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("GRANT CREATE ON DATABASE {} TO {}").format(
            sql.Identifier(database), sql.Identifier(role),
        ))
    try:
        store = SqlAlchemyMediaStore(url, auto_migrate=False)
        try:
            report = store.collector_runtime_preflight(direct_url=url)
        finally:
            store.close()
    finally:
        with psycopg.connect(admin_dsn, autocommit=True) as admin:
            admin.execute(sql.SQL("REVOKE CREATE ON DATABASE {} FROM {}").format(
                sql.Identifier(database), sql.Identifier(role),
            ))

    assert report["database_create_violation_count"] == 1
    assert report["privileges_valid"] is False
    assert report["ready"] is False


@pytest.mark.integration
def test_postgres_preflight_rejects_weakened_same_name_check_constraint():
    url = os.getenv("TRADINGAGENTS_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("TRADINGAGENTS_TEST_POSTGRES_URL is not configured")
    if not os.getenv("PG_SUPERUSER"):
        pytest.skip("migration administrator is not configured")

    import psycopg

    report = None
    try:
        with psycopg.connect(
            _migration_admin_dsn(url), autocommit=True,
        ) as admin:
            admin.execute(
                "ALTER TABLE public.fetch_runs DROP CONSTRAINT "
                "fetch_runs_server_observation_shape; "
                "ALTER TABLE public.fetch_runs ADD CONSTRAINT "
                "fetch_runs_server_observation_shape CHECK (true)",
                prepare=False,
            )
        store = SqlAlchemyMediaStore(url, auto_migrate=False)
        try:
            report = store.collector_runtime_preflight(direct_url=url)
        finally:
            store.close()
    finally:
        _run_collector_migration(url, "009_server_observed_evidence.sql")

    assert report is not None
    assert report["active_constraint_count"] == (
        report["required_constraint_count"] - 1
    )
    assert report["constraints_valid"] is False
    assert report["ready"] is False


@pytest.mark.integration
def test_postgres_lease_detects_backend_loss_and_cleanup_does_not_raise():
    url = os.getenv("TRADINGAGENTS_TEST_POSTGRES_URL")
    superuser = os.getenv("PG_SUPERUSER")
    if not url:
        pytest.skip("TRADINGAGENTS_TEST_POSTGRES_URL is not configured")
    if not superuser:
        pytest.skip("PostgreSQL superuser is not configured")

    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    admin_url = make_url(url).set(username=superuser, password=None)
    admin = create_engine(admin_url)
    owner = SqlAlchemyMediaStore(url, auto_migrate=False)
    contender = SqlAlchemyMediaStore(url, auto_migrate=False)
    loss_types = []
    first_lease = None
    second_lease = None
    try:
        first_lease = owner.acquire_collector_lease(
            direct_url=url,
            heartbeat_interval_seconds=0.05,
            on_loss=loss_types.append,
        )
        assert first_lease is not None
        with admin.begin() as conn:
            assert conn.execute(text(
                "SELECT pg_catalog.pg_terminate_backend(:backend_pid)"
            ), {"backend_pid": first_lease._backend_pid}).scalar_one() is True

        assert first_lease.wait_until_lost(5.0) is True
        assert first_lease.is_held is False
        with pytest.raises(RuntimeError, match="no longer held"):
            first_lease.assert_held()
        assert loss_types == ["OperationalError"]

        # Cleanup of an already-dead direct connection is explicitly non-raising.
        first_lease.close()
        first_lease = None
        _ = owner.get_meta("poller:last_cycle_utc")

        second_lease = contender.acquire_collector_lease(
            direct_url=url,
            heartbeat_interval_seconds=0.05,
        )
        assert second_lease is not None
        second_lease.assert_held()
    finally:
        if first_lease is not None:
            first_lease.close()
        if second_lease is not None:
            second_lease.close()
        owner.close()
        contender.close()
        admin.dispose()
