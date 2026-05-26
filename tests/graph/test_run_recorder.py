import pytest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import MagicMock


@pytest.fixture
def db_and_dir(tmp_path):
    from tradingagents.persistence.db import connect
    conn = connect(str(tmp_path / "iic.db"))
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return conn, str(data_dir)


@pytest.fixture
def sample_state():
    return {
        "company_of_interest": "AAPL",
        "asset_type": "stock",
        "trade_date": "2026-05-25",
        "market_report": "Market analyst: AAPL trending up.",
        "sentiment_report": "Sentiment positive.",
        "news_report": "News positive.",
        "fundamentals_report": "Fundamentals strong.",
        "derivatives_report": "",
        "investment_plan": "Hold position.",
        "trader_investment_plan": "BUY 100 shares at $190.",
        "final_trade_decision": "BUY",
        "investment_debate_state": {"history": "bull/bear summary"},
        "risk_debate_state": {"history": "risk summary"},
    }


@pytest.mark.unit
def test_run_recorder_writes_db_row_and_artifact_files(db_and_dir, sample_state):
    from tradingagents.graph.run_recorder import RunRecorder
    conn, data_dir = db_and_dir
    rec = RunRecorder(
        conn=conn,
        data_dir=data_dir,
        run_id="testrun123",
        persona_id="macro",
        cost_callback=MagicMock(totals_by_model=lambda: {
            "deepseek-v4-pro": {"in_tokens": 1000, "out_tokens": 500}
        }),
    )
    rec.start("AAPL", started_ts=datetime.now(timezone.utc).isoformat())
    new_state = rec.record(sample_state)

    # DB: one runs row, status=complete, decision parsed
    row = conn.execute("SELECT * FROM runs WHERE run_id=?", ("testrun123",)).fetchone()
    assert row is not None
    assert row["status"] == "complete"
    assert row["decision"] == "BUY"
    assert row["artifact_dir"] == "runs/testrun123"

    # DB: at least one cost row
    cost_rows = list(conn.execute("SELECT * FROM costs WHERE run_id=?", ("testrun123",)))
    assert len(cost_rows) >= 1
    assert cost_rows[0]["in_tokens"] == 1000

    # Filesystem: per-analyst MD files
    run_path = Path(data_dir) / "runs" / "testrun123"
    assert (run_path / "meta.json").exists()
    assert (run_path / "analysts" / "market.md").exists()
    assert (run_path / "trader_plan.md").exists()
    assert (run_path / "risk_debate.md").exists()

    # State is returned unchanged so it flows through the graph.
    assert new_state["company_of_interest"] == "AAPL"


@pytest.mark.unit
def test_decision_parser_extracts_buy_hold_sell(db_and_dir, sample_state):
    """The recorder parses the trader / final_trade_decision string into
    one of BUY/HOLD/SELL when possible; None otherwise."""
    from tradingagents.graph.run_recorder import parse_decision
    assert parse_decision("FINAL TRANSACTION PROPOSAL: **BUY**") == "BUY"
    assert parse_decision("hold the position") == "HOLD"
    assert parse_decision("...we recommend a SELL") == "SELL"
    assert parse_decision("ambiguous text") is None
