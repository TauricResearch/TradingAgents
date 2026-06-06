import json
from datetime import datetime

from tradingagents.persistence import store
from tradingagents.persistence.db import connect as iic_connect


class FakePriceChain:
    def get_bars(self, ticker, start, end, resolution):
        from tradingagents.backtest.prices import Bars

        return Bars(
            ticker=ticker,
            resolution=resolution,
            bars=[(datetime.combine(start, datetime.min.time()), 100.0)],
            source="fake",
        )


def test_dispatch_backtest_from_brief_uses_restored_f2_harness(tmp_path):
    from tradingagents.orchestrator.action_handler import dispatch_backtest_from_brief

    conn = iic_connect(str(tmp_path / "iic.db"))
    store.insert_run(
        conn,
        run_id="r1",
        ticker="AAPL",
        persona_id="balanced",
        started_ts="2030-01-01T00:00:00+00:00",
        artifact_dir="runs/r1",
    )
    store.finalize_run(
        conn,
        run_id="r1",
        ended_ts="2030-01-01T00:10:00+00:00",
        status="complete",
        decision="BUY",
    )
    store.insert_brief(
        conn,
        brief_id="b1",
        mode="event_alert",
        scope="AAPL",
        generated_ts="2030-01-01T00:15:00+00:00",
        content_path="briefs/b1.md",
        run_ids=["r1"],
    )

    backtest_id = dispatch_backtest_from_brief(
        conn,
        brief_id="b1",
        params={"window_days": 14},
        config={"iic_data_dir": str(tmp_path / "data")},
        price_chain=FakePriceChain(),
    )

    bt = conn.execute(
        "SELECT * FROM backtests WHERE backtest_id = ?", (backtest_id,)
    ).fetchone()
    assert bt["triggered_by_brief_id"] == "b1"
    assert json.loads(bt["universe"]) == ["AAPL"]
    assert bt["start_date"] == "2030-01-01"
    assert bt["end_date"] == "2030-01-15"

    btr = conn.execute(
        "SELECT ticker, persona_id, metrics FROM backtest_runs "
        "WHERE backtest_id = ?",
        (backtest_id,),
    ).fetchone()
    metrics = json.loads(btr["metrics"])
    assert btr["ticker"] == "AAPL"
    assert btr["persona_id"] == "balanced"
    assert metrics["status"] == "open"
    assert metrics["decision"] == "BUY"
    assert metrics["run_id"] == "r1"
