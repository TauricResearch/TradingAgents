"""Reusing a report directory must reconcile stale sections (#1566)."""

from __future__ import annotations

import pytest

from tradingagents.reporting import write_report_tree


def _full_state() -> dict:
    return {
        "market_report": "MKT",
        "news_report": "NEWS",
        "investment_debate_state": {"bull_history": "BULL"},
        "investment_plan": "RM PLAN",
        "trader_investment_plan": "TRADE",
        "risk_debate_state": {"neutral_history": "NEUTRAL"},
        "final_trade_decision": "PM DECISION",
    }


@pytest.mark.unit
class TestReportDirectoryReuse:
    def test_second_save_removes_stale_sections(self, tmp_path):
        write_report_tree(_full_state(), "AAPL", tmp_path, html=False)
        assert (tmp_path / "1_analysts" / "news.md").exists()

        write_report_tree(
            {"market_report": "NEW MKT", "final_trade_decision": "SELL"}, "AAPL", tmp_path, html=False
        )
        # Sections the new run did not produce are gone...
        assert not (tmp_path / "1_analysts" / "news.md").exists()
        assert not (tmp_path / "2_research" / "manager.md").exists()
        assert not (tmp_path / "3_trading" / "trader.md").exists()
        # ...and the produced ones carry the new content.
        assert (tmp_path / "1_analysts" / "market.md").read_text() == "NEW MKT"
        assert "NEW MKT" in (tmp_path / "complete_report.md").read_text()
        assert "NEWS" not in (tmp_path / "complete_report.md").read_text()

    def test_caller_files_survive_reconciliation(self, tmp_path):
        write_report_tree(_full_state(), "AAPL", tmp_path, html=False)
        (tmp_path / "caller_notes.txt").write_text("caller file")
        (tmp_path / "1_analysts" / "my_notes.md").write_text("user file in section dir")

        write_report_tree(
            {"market_report": "NEW MKT", "final_trade_decision": "SELL"}, "AAPL", tmp_path, html=False
        )
        # Neither a file outside the section dirs nor a caller file inside one
        # is managed by the writer, so both survive.
        assert (tmp_path / "caller_notes.txt").read_text() == "caller file"
        assert (tmp_path / "1_analysts" / "my_notes.md").read_text() == "user file in section dir"
        # Our own news.md was still removed — only managed names reconcile.
        assert not (tmp_path / "1_analysts" / "news.md").exists()

    def test_fresh_directory_unchanged_behavior(self, tmp_path):
        out = write_report_tree(_full_state(), "AAPL", tmp_path, html=False)
        assert out.name == "complete_report.md"
        assert (tmp_path / "1_analysts" / "market.md").read_text() == "MKT"
        assert (tmp_path / "1_analysts" / "news.md").read_text() == "NEWS"
        assert (tmp_path / "2_research" / "manager.md").read_text() == "RM PLAN"
        assert (tmp_path / "3_trading" / "trader.md").read_text() == "TRADE"
        assert (tmp_path / "5_portfolio" / "decision.md").read_text() == "PM DECISION"
