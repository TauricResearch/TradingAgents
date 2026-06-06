import json
import re
import uuid
from datetime import datetime, timezone

import pytest


@pytest.fixture
def conn(tmp_path):
    from tradingagents.persistence.db import connect
    return connect(str(tmp_path / "iic.db"))


def _seed(conn):
    """Seed a closed backtest with 3 personas × 1 ticker (AAPL)."""
    from tradingagents.persistence import store

    cur = conn.execute(
        "INSERT INTO backtests (universe, start_date, end_date, status, "
        "report_path, created_ts) VALUES (?, ?, ?, 'closed', NULL, ?)",
        (json.dumps(["AAPL"]), "2026-04-26", "2026-05-26",
         datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    backtest_id = cur.lastrowid

    samples = [
        ("macro",    0.10, 0.08, 1.4,  -0.02, 0.60),
        ("value",    0.03, 0.01, 0.4,  -0.03, 0.55),
        ("momentum", -0.05, -0.07, -0.6, -0.12, 0.35),
    ]
    for persona_id, tr, alpha, sharpe, mdd, wr in samples:
        run_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        store.insert_run(conn, run_id=run_id, ticker="AAPL",
                         persona_id=persona_id, started_ts=now,
                         artifact_dir=f"runs/{run_id}")
        metrics = {
            "status": "closed", "run_id": run_id,
            "decision": "BUY" if tr > 0 else "SELL",
            "position": 1 if tr > 0 else -1,
            "entry_date": "2026-04-26", "entry_price": 200.0,
            "close_date": "2026-05-26", "exit_price": 220.0 if tr > 0 else 190.0,
            "benchmark": "SPY",
            "total_return": tr, "benchmark_return": tr - alpha,
            "alpha": alpha, "sharpe": sharpe, "max_drawdown": mdd, "win_rate": wr,
            "returns": [0.01] * 22, "holding_days_elapsed": 30,
            "price_source": "yfinance", "resolution": "1d",
        }
        conn.execute(
            "INSERT INTO backtest_runs (backtest_id, persona_id, ticker, metrics)"
            " VALUES (?, ?, ?, ?)",
            (backtest_id, persona_id, "AAPL", json.dumps(metrics)),
        )
    conn.commit()
    return backtest_id


@pytest.mark.unit
def test_report_contains_three_persona_rows(conn):
    from tradingagents.backtest.report import render_report
    bt = _seed(conn)
    md = render_report(conn, backtest_id=bt)
    for persona in ("macro", "value", "momentum"):
        assert persona in md
    # Required metric columns
    for col in ("Sharpe", "Total Return", "Alpha", "Win Rate"):
        assert col in md


@pytest.mark.unit
def test_report_includes_buy_and_hold_baseline(conn):
    from tradingagents.backtest.report import render_report
    bt = _seed(conn)
    md = render_report(conn, backtest_id=bt)
    assert "Buy-and-hold" in md or "buy-and-hold" in md.lower()


@pytest.mark.unit
def test_report_is_byte_equal_modulo_generated_ts(conn):
    from tradingagents.backtest.report import render_report
    bt = _seed(conn)
    a = render_report(conn, backtest_id=bt)
    b = render_report(conn, backtest_id=bt)
    rx = re.compile(r"^generated_ts:.*$", re.MULTILINE)
    a_norm = rx.sub("", a)
    b_norm = rx.sub("", b)
    assert a_norm == b_norm
