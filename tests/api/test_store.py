import pytest
import sqlite3 as _sqlite3
from api.store.runs_store import RunsStore
from api.models.run import RunConfig, RunStatus


def test_create_and_get_run(tmp_path):
    store = RunsStore(tmp_path / "test.sqlite")
    config = RunConfig(ticker="NVDA", date="2024-05-10")
    run = store.create(config)
    assert run.id is not None
    assert run.status == RunStatus.QUEUED
    fetched = store.get(run.id)
    assert fetched.ticker == "NVDA"


def test_list_runs(tmp_path):
    store = RunsStore(tmp_path / "test.sqlite")
    store.create(RunConfig(ticker="NVDA", date="2024-05-10"))
    store.create(RunConfig(ticker="AAPL", date="2024-05-09"))
    runs = store.list_all()
    assert len(runs) == 2


def test_update_run_status(tmp_path):
    store = RunsStore(tmp_path / "test.sqlite")
    run = store.create(RunConfig(ticker="NVDA", date="2024-05-10"))
    store.update_status(run.id, RunStatus.RUNNING)
    assert store.get(run.id).status == RunStatus.RUNNING


def test_add_report(tmp_path):
    store = RunsStore(tmp_path / "test.sqlite")
    run = store.create(RunConfig(ticker="NVDA", date="2024-05-10"))
    store.add_report(run.id, "market_analyst:0", "bullish")
    assert store.get(run.id).reports == {"market_analyst:0": "bullish"}


def test_set_error(tmp_path):
    store = RunsStore(tmp_path / "test.sqlite")
    run = store.create(RunConfig(ticker="NVDA", date="2024-05-10"))
    store.set_error(run.id, "timeout")
    fetched = store.get(run.id)
    assert fetched.status == RunStatus.ERROR
    assert fetched.error == "timeout"


def test_clear_reports(tmp_path):
    store = RunsStore(tmp_path / "test.sqlite")
    run = store.create(RunConfig(ticker="NVDA", date="2024-05-10"))
    store.add_report(run.id, "market_analyst:0", "bullish")
    store.clear_reports(run.id)
    assert store.get(run.id).reports == {}


def test_update_decision(tmp_path):
    store = RunsStore(tmp_path / "test.sqlite")
    run = store.create(RunConfig(ticker="NVDA", date="2024-05-10"))
    store.update_decision(run.id, "BUY")
    assert store.get(run.id).decision == "BUY"


def test_migration_adds_token_usage_column_to_existing_db(tmp_path):
    """DB created without token_usage gets the column added on RunsStore.__init__."""
    db_path = tmp_path / "old.sqlite"
    # Create a DB without the token_usage column (simulate pre-migration state)
    conn = _sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE runs (
            id TEXT PRIMARY KEY, ticker TEXT NOT NULL, date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued', decision TEXT,
            created_at TEXT NOT NULL, config TEXT,
            reports TEXT NOT NULL DEFAULT '{}', error TEXT
        )
    """)
    conn.commit()
    conn.close()

    # Initialising the store should migrate the column
    store = RunsStore(db_path)
    cols = {
        row["name"]
        for row in store._conn.execute("PRAGMA table_info(runs)")
    }
    assert "token_usage" in cols


def test_migration_is_idempotent(tmp_path):
    """Re-initialising the store after migration does not crash."""
    db_path = tmp_path / "test.sqlite"
    RunsStore(db_path)   # first init — creates table + column
    RunsStore(db_path)   # second init — column already present, should not crash


def test_add_token_usage(tmp_path):
    store = RunsStore(tmp_path / "test.sqlite")
    run = store.create(RunConfig(ticker="NVDA", date="2026-03-23"))
    store.add_token_usage(run.id, "market_analyst:0", {"tokens_in": 1200, "tokens_out": 400})
    result = store.get(run.id)
    assert "market_analyst:0" in result.token_usage
    assert result.token_usage["market_analyst:0"].tokens_in == 1200
    assert result.token_usage["market_analyst:0"].tokens_out == 400


def test_clear_token_usage(tmp_path):
    store = RunsStore(tmp_path / "test.sqlite")
    run = store.create(RunConfig(ticker="NVDA", date="2026-03-23"))
    store.add_token_usage(run.id, "market_analyst:0", {"tokens_in": 1200, "tokens_out": 400})
    store.clear_token_usage(run.id)
    assert store.get(run.id).token_usage == {}


def test_clear_token_usage_does_not_affect_reports(tmp_path):
    store = RunsStore(tmp_path / "test.sqlite")
    run = store.create(RunConfig(ticker="NVDA", date="2026-03-23"))
    store.add_report(run.id, "market_analyst:0", "bullish")
    store.add_token_usage(run.id, "market_analyst:0", {"tokens_in": 100, "tokens_out": 50})
    store.clear_token_usage(run.id)
    fetched = store.get(run.id)
    assert fetched.reports == {"market_analyst:0": "bullish"}
    assert fetched.token_usage == {}
