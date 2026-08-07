"""Immutable collection-cycle identities, child binding, and terminal manifests."""

import os
import sqlite3
import time
import uuid

import pytest

from tradingagents.dataflows.media_store import (
    SqlAlchemyMediaStore,
    SqliteMediaStore,
    collection_cycle_spec,
)


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
