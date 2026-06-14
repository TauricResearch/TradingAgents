"""The report tree is written by a reusable library function (not locked inside
the CLI), so the CLI and the Python API produce identical artifacts."""

from __future__ import annotations

import pytest

from tradingagents.reporting import write_reports


def _full_state():
    return {
        "company_of_interest": "NVDA",
        "trade_date": "2026-06-12",
        "market_report": "Market looks strong.",
        "sentiment_report": "Sentiment positive.",
        "news_report": "News neutral.",
        "fundamentals_report": "Fundamentals solid.",
        "investment_debate_state": {
            "bull_history": "Bull case.",
            "bear_history": "Bear case.",
            "history": "...",
            "current_response": "...",
            "judge_decision": "Research manager says buy.",
        },
        "trader_investment_plan": "Trader: buy with stop.",
        "risk_debate_state": {
            "aggressive_history": "Aggressive: lean in.",
            "conservative_history": "Conservative: trim.",
            "neutral_history": "Neutral: balanced.",
            "history": "...",
            "judge_decision": "Final: Buy.",
        },
        "investment_plan": "Plan.",
        "final_trade_decision": "Buy",
    }


@pytest.mark.unit
def test_write_reports_full_tree(tmp_path):
    report = write_reports(_full_state(), "NVDA", tmp_path)

    assert report == tmp_path / "complete_report.md"
    # Per-section files
    assert (tmp_path / "1_analysts" / "market.md").read_text() == "Market looks strong."
    assert (tmp_path / "1_analysts" / "fundamentals.md").exists()
    assert (tmp_path / "2_research" / "bull.md").read_text() == "Bull case."
    assert (tmp_path / "2_research" / "manager.md").exists()
    assert (tmp_path / "3_trading" / "trader.md").exists()
    assert (tmp_path / "4_risk" / "neutral.md").exists()
    assert (tmp_path / "5_portfolio" / "decision.md").read_text() == "Final: Buy."

    # Consolidated report stitches the sections together
    text = report.read_text()
    assert "# Trading Analysis Report: NVDA" in text
    assert "I. Analyst Team Reports" in text
    assert "V. Portfolio Manager Decision" in text


@pytest.mark.unit
def test_write_reports_omits_absent_sections(tmp_path):
    """A run with only a market analyst writes no research/risk folders."""
    state = {
        "company_of_interest": "NVDA",
        "trade_date": "2026-06-12",
        "market_report": "Only market.",
        "investment_debate_state": {},
        "risk_debate_state": {},
    }
    write_reports(state, "NVDA", tmp_path)

    assert (tmp_path / "1_analysts" / "market.md").exists()
    assert not (tmp_path / "2_research").exists()
    assert not (tmp_path / "4_risk").exists()
    assert not (tmp_path / "5_portfolio").exists()


@pytest.mark.unit
def test_cli_wrapper_delegates_to_library(tmp_path):
    """cli.save_report_to_disk is now a thin wrapper over the library function."""
    from cli.main import save_report_to_disk

    out = save_report_to_disk(_full_state(), "NVDA", tmp_path)
    assert out == tmp_path / "complete_report.md"
    assert out.exists()
