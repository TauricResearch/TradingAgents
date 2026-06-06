import json
import uuid
from datetime import datetime, timezone

import pytest


@pytest.fixture
def conn(tmp_path):
    from tradingagents.persistence.db import connect
    return connect(str(tmp_path / "iic.db"))


def _seed_run(conn, ticker, persona_id):
    from tradingagents.persistence import store
    run_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    store.insert_run(conn, run_id=run_id, ticker=ticker, persona_id=persona_id,
                     started_ts=now, artifact_dir=f"runs/{run_id}")
    return run_id


def _insert_backtest(conn, universe, start_date="2026-04-26", end_date="2026-05-26",
                      status="open"):
    cur = conn.execute(
        "INSERT INTO backtests (universe, start_date, end_date, status, created_ts)"
        " VALUES (?, ?, ?, ?, ?)",
        (json.dumps(universe), start_date, end_date, status,
         datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    return cur.lastrowid


def _insert_btr(conn, backtest_id, ticker, persona_id, metrics):
    conn.execute(
        "INSERT INTO backtest_runs (backtest_id, persona_id, ticker, metrics)"
        " VALUES (?, ?, ?, ?)",
        (backtest_id, persona_id, ticker, json.dumps(metrics)),
    )
    conn.commit()


@pytest.mark.unit
def test_leaderboard_closed_rows_show_final_alpha(conn):
    from tradingagents.backtest.leaderboard import build_leaderboard

    bt = _insert_backtest(conn, ["AAPL"], status="closed")
    rid = _seed_run(conn, "AAPL", "macro")
    _insert_btr(conn, bt, "AAPL", "macro", {
        "status": "closed", "run_id": rid, "decision": "BUY", "position": 1,
        "entry_date": "2026-04-26", "entry_price": 200.0,
        "close_date": "2026-05-26", "exit_price": 220.0,
        "total_return": 0.10, "benchmark_return": 0.02, "alpha": 0.08,
        "sharpe": 1.4, "max_drawdown": -0.02, "win_rate": 0.6,
    })

    rows = build_leaderboard(conn, price_chain=None)
    assert len(rows) == 1
    assert rows[0]["persona_id"] == "macro"
    assert rows[0]["ticker"] == "AAPL"
    assert rows[0]["status"] == "closed"
    assert rows[0]["alpha"] == pytest.approx(0.08)


@pytest.mark.unit
def test_leaderboard_open_rows_use_lazy_mtm(conn):
    from tradingagents.backtest.leaderboard import build_leaderboard
    from tradingagents.backtest.prices import Bars, Resolution

    bt = _insert_backtest(conn, ["AAPL"], status="open")
    rid = _seed_run(conn, "AAPL", "macro")
    _insert_btr(conn, bt, "AAPL", "macro", {
        "status": "open", "run_id": rid, "decision": "BUY", "position": 1,
        "entry_date": "2026-04-26", "entry_price": 200.0,
        "benchmark": "SPY", "benchmark_entry_price": 500.0,
        "scheduled_close_date": "2026-05-26",
        "resolution": "1d", "price_source": "fake",
    })

    class FakeChain:
        def get_bars(self, ticker, start, end, resolution):
            price = 220.0 if ticker == "AAPL" else 510.0
            return Bars(ticker=ticker, resolution=resolution,
                        bars=[(datetime(2026, 5, 1), price)], source="fake")

    rows = build_leaderboard(conn, price_chain=FakeChain())
    assert len(rows) == 1
    r = rows[0]
    assert r["status"] == "open"
    assert r["current_price"] == pytest.approx(220.0)
    assert r["mtm_return"] == pytest.approx(0.10)
    assert r["mtm_alpha"] == pytest.approx(0.10 - 0.02)


@pytest.mark.unit
def test_leaderboard_open_rows_without_chain_skip_mtm(conn):
    from tradingagents.backtest.leaderboard import build_leaderboard

    bt = _insert_backtest(conn, ["AAPL"], status="open")
    rid = _seed_run(conn, "AAPL", "macro")
    _insert_btr(conn, bt, "AAPL", "macro", {
        "status": "open", "run_id": rid, "decision": "BUY", "position": 1,
        "entry_date": "2026-04-26", "entry_price": 200.0,
        "scheduled_close_date": "2026-05-26",
        "resolution": "1d", "price_source": "fake",
    })

    rows = build_leaderboard(conn, price_chain=None)
    assert rows[0]["status"] == "open"
    assert rows[0]["mtm_return"] is None


@pytest.mark.unit
def test_leaderboard_filter_by_persona(conn):
    from tradingagents.backtest.leaderboard import build_leaderboard

    bt = _insert_backtest(conn, ["AAPL", "MSFT"], status="closed")
    for ticker, persona in [("AAPL", "macro"), ("MSFT", "value")]:
        rid = _seed_run(conn, ticker, persona)
        _insert_btr(conn, bt, ticker, persona, {
            "status": "closed", "run_id": rid, "decision": "BUY", "position": 1,
            "entry_date": "2026-04-26", "entry_price": 100.0,
            "close_date": "2026-05-26", "exit_price": 110.0,
            "total_return": 0.10, "benchmark_return": 0.0, "alpha": 0.10,
            "sharpe": 0.0, "max_drawdown": 0.0, "win_rate": 1.0,
        })

    rows = build_leaderboard(conn, price_chain=None, persona="macro")
    assert {r["persona_id"] for r in rows} == {"macro"}
