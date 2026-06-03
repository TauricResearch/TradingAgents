import json

from tradingagents.analysis_pack.builder import build_pack_content_from_runs
from tradingagents.persistence.db import connect
from tradingagents.persistence import store


def test_build_pack_content_from_run_artifact(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    data_dir = tmp_path / "data"
    artifact_dir = data_dir / "runs" / "r1"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "pm_synthesis.md").write_text("Final BUY", encoding="utf-8")
    (artifact_dir / "state.json").write_text(
        json.dumps(
            {
                "market_report": "market",
                "news_report": "news",
                "fundamentals_report": "fundamentals",
                "derivatives_report": "derivatives",
                "investment_debate_state": {"history": "bull bear"},
                "risk_debate_state": {"history": "risk"},
            }
        ),
        encoding="utf-8",
    )
    store.insert_run(
        conn,
        run_id="r1",
        ticker="NVDA",
        persona_id="balanced",
        started_ts="2026-06-01T00:00:00+00:00",
        artifact_dir="runs/r1",
    )
    content = build_pack_content_from_runs(
        conn=conn,
        data_dir=data_dir,
        event_id="ev1",
        ticker="NVDA",
        trade_date="2026-06-01",
        event_context="event text",
        run_ids=["r1"],
    )
    assert content["ticker"] == "NVDA"
    assert content["reports"]["market_report"] == "market"
    assert content["final_trade_decisions"][0]["body"] == "Final BUY"
