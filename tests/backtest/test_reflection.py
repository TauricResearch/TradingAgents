import json
import uuid
from datetime import datetime, timezone

import pytest


@pytest.fixture
def conn(tmp_path):
    from tradingagents.persistence.db import connect
    return connect(str(tmp_path / "iic.db"))


@pytest.fixture
def seeded_run(conn):
    """Insert one runs row so the FK from outcome_log is satisfied."""
    from tradingagents.persistence import store
    run_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    store.insert_run(conn, run_id=run_id, ticker="AAPL", persona_id="macro",
                     started_ts=now, artifact_dir=f"runs/{run_id}")
    return run_id


@pytest.mark.unit
def test_write_outcome_log_on_close_writes_one_row(conn, seeded_run):
    from tradingagents.backtest.reflection import write_outcome_log_on_close

    write_outcome_log_on_close(
        conn,
        run_id=seeded_run,
        ticker="AAPL",
        persona_id="macro",
        decision="BUY",
        alpha=0.0123,
        total_return=0.0274,
        backtest_id=42,
        close_date="2026-05-26",
        benchmark="SPY",
    )

    rows = list(conn.execute(
        "SELECT * FROM outcome_log WHERE run_id = ?", (seeded_run,)
    ))
    assert len(rows) == 1
    row = rows[0]
    assert row["ticker"] == "AAPL"
    assert row["decision"] == "BUY"
    assert row["pnl_proxy"] == pytest.approx(0.0123)
    tags = json.loads(row["tags"])
    assert tags["persona_id"] == "macro"
    assert tags["backtest_id"] == 42
    assert tags["source"] == "forward_test"
    assert "alpha" in row["outcome_md"].lower() or "2026-05-26" in row["outcome_md"]


@pytest.mark.unit
def test_write_outcome_log_on_close_is_idempotent_by_design(conn, seeded_run):
    """Two calls write two rows — uniqueness is the caller's job (close fires once)."""
    from tradingagents.backtest.reflection import write_outcome_log_on_close
    for _ in range(2):
        write_outcome_log_on_close(
            conn, run_id=seeded_run, ticker="AAPL", persona_id="macro",
            decision="HOLD", alpha=0.0, total_return=0.0,
            backtest_id=1, close_date="2026-05-26", benchmark="SPY",
        )
    rows = list(conn.execute(
        "SELECT * FROM outcome_log WHERE run_id = ?", (seeded_run,)
    ))
    assert len(rows) == 2
