"""Execution report tree tests."""

from __future__ import annotations

from tradingagents.execution import format_execution_report
from tradingagents.reporting import write_report_tree


def test_format_execution_report_includes_cash_percent():
    text = format_execution_report(
        {
            "enabled": False,
            "ticker": "NVDA",
            "order_action": "buy",
            "cash_allocation_pct": 50,
            "time_horizon": "3-6 months",
            "order_submitted": False,
            "order_type": "none",
            "quantity": 0,
            "decision": {"rating": "Buy"},
            "message": "Recommendation: buy 50% of available cash.",
        }
    )
    assert "Percent of available cash**: 50" in text
    assert "NVDA" in text
    assert "buy" in text.lower()


def test_write_report_tree_writes_execution_section(tmp_path):
    final_state = {
        "execution_report": {
            "enabled": False,
            "ticker": "AAPL",
            "order_action": "hold",
            "cash_allocation_pct": 10,
            "time_horizon": "3-6 months",
            "order_submitted": False,
            "order_type": "none",
            "quantity": 0,
            "decision": {"rating": "Hold"},
            "message": "Hold.",
        }
    }
    complete = write_report_tree(final_state, "AAPL", tmp_path)
    execution_md = tmp_path / "6_execution" / "execution.md"
    assert execution_md.exists()
    body = execution_md.read_text(encoding="utf-8")
    assert "AAPL" in body
    assert "hold" in body.lower()
    assert "VI. Execution Agent" in complete.read_text(encoding="utf-8")
