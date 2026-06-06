import json
import uuid
from datetime import date, datetime, timezone

import pytest


@pytest.fixture
def conn(tmp_path):
    from tradingagents.persistence.db import connect
    return connect(str(tmp_path / "iic.db"))


def _seed_open_run(conn, ticker, persona_id, scheduled_close_date):
    """Seed a single open backtest_runs row + its parent backtests + runs."""
    from tradingagents.persistence import store

    cur = conn.execute(
        "INSERT INTO backtests (universe, start_date, end_date, status, created_ts)"
        " VALUES (?, ?, ?, 'open', ?)",
        (json.dumps([ticker]), "2026-04-26", scheduled_close_date,
         datetime.now(timezone.utc).isoformat()),
    )
    backtest_id = cur.lastrowid

    run_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    store.insert_run(conn, run_id=run_id, ticker=ticker, persona_id=persona_id,
                     started_ts=now, artifact_dir=f"runs/{run_id}")

    metrics = {
        "status": "open", "run_id": run_id, "decision": "BUY", "position": 1,
        "entry_date": "2026-04-26", "entry_price": 100.0,
        "benchmark": "SPY", "benchmark_entry_price": 500.0,
        "scheduled_close_date": scheduled_close_date,
        "resolution": "1d", "price_source": "fake",
    }
    conn.execute(
        "INSERT INTO backtest_runs (backtest_id, persona_id, ticker, metrics)"
        " VALUES (?, ?, ?, ?)",
        (backtest_id, persona_id, ticker, json.dumps(metrics)),
    )
    conn.commit()
    return backtest_id


@pytest.fixture
def fake_chain():
    from tradingagents.backtest.prices import Bars, Resolution

    class FakeChain:
        def get_bars(self, ticker, start, end, resolution):
            if start == end:
                return Bars(ticker=ticker, resolution=resolution,
                            bars=[(datetime.combine(start, datetime.min.time()), 100.0)],
                            source="fake")
            return Bars(ticker=ticker, resolution=resolution,
                        bars=[(datetime.combine(start, datetime.min.time()), 100.0),
                              (datetime.combine(end,   datetime.min.time()), 110.0)],
                        source="fake")
    return FakeChain()


@pytest.mark.unit
def test_sweep_matures_only_past_due_rows(conn, fake_chain):
    from tradingagents.backtest.sweep import run_maturation_pass

    past_due_bt = _seed_open_run(conn, "AAPL", "macro", "2020-01-01")
    future_bt = _seed_open_run(conn, "MSFT", "value", "2099-01-01")

    result = run_maturation_pass(conn, price_chain=fake_chain)
    assert result["closed"] == 1
    assert result["skipped"] == 1

    rows = list(conn.execute("SELECT backtest_id, metrics FROM backtest_runs"))
    for r in rows:
        m = json.loads(r["metrics"])
        if r["backtest_id"] == past_due_bt:
            assert m["status"] == "closed"
        else:
            assert m["status"] == "open"


@pytest.mark.unit
def test_sweep_returns_zero_when_nothing_due(conn, fake_chain):
    from tradingagents.backtest.sweep import run_maturation_pass
    result = run_maturation_pass(conn, price_chain=fake_chain)
    assert result == {"closed": 0, "skipped": 0, "errored": 0}


@pytest.mark.unit
def test_sweep_does_not_retry_errored_rows_by_default(conn, fake_chain):
    """Errored rows stay errored to avoid retry storms (per design §11)."""
    from tradingagents.backtest.sweep import run_maturation_pass
    from tradingagents.persistence import store

    cur = conn.execute(
        "INSERT INTO backtests (universe, start_date, end_date, status, created_ts)"
        " VALUES (?, '2020-01-01', '2020-02-01', 'open', ?)",
        (json.dumps(["AAPL"]), datetime.now(timezone.utc).isoformat()),
    )
    backtest_id = cur.lastrowid
    run_id = uuid.uuid4().hex
    store.insert_run(conn, run_id=run_id, ticker="AAPL", persona_id="macro",
                     started_ts=datetime.now(timezone.utc).isoformat(),
                     artifact_dir=f"runs/{run_id}")
    conn.execute(
        "INSERT INTO backtest_runs (backtest_id, persona_id, ticker, metrics)"
        " VALUES (?, ?, ?, ?)",
        (backtest_id, "macro", "AAPL",
         json.dumps({"status": "errored", "run_id": run_id,
                      "error": "old", "scheduled_close_date": "2020-02-01"})),
    )
    conn.commit()

    result = run_maturation_pass(conn, price_chain=fake_chain)
    assert result["closed"] == 0
    m = json.loads(conn.execute(
        "SELECT metrics FROM backtest_runs WHERE backtest_id = ?", (backtest_id,)
    ).fetchone()["metrics"])
    assert m["status"] == "errored"
    assert m["error"] == "old"
