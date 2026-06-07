import json

import pytest

from cli.main import INDIA_COMPLIANCE_DISCLAIMER, run_doctor_checks, save_report_to_disk


@pytest.mark.unit
def test_doctor_validates_india_ticker():
    checks = run_doctor_checks("RELIANCE")
    assert checks["ticker_validation"] == "RELIANCE.NS"
    assert checks["package_import"] is True


@pytest.mark.unit
def test_report_writer_creates_disclaimer_and_summary(tmp_path):
    final_state = {
        "trade_date": "2026-06-05",
        "india_market_report": "Market section",
        "india_fundamentals_report": "Fundamentals section",
        "india_news_filings_report": "News section",
        "india_macro_policy_report": "Macro section",
        "india_flows_report": "Flows section",
        "india_compliance_report": "Compliance section",
        "final_trade_decision": "Model view: Hold",
        "investment_debate_state": {"bull_history": "Bull", "bear_history": "Bear", "judge_decision": "Manager"},
        "risk_debate_state": {"aggressive_history": "Aggressive", "conservative_history": "Conservative", "neutral_history": "Neutral"},
    }
    report = save_report_to_disk(final_state, "RELIANCE.NS", tmp_path)
    assert report.exists()
    assert INDIA_COMPLIANCE_DISCLAIMER in report.read_text(encoding="utf-8")
    assert (tmp_path / "disclaimer.md").exists()
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["symbol"] == "RELIANCE.NS"
