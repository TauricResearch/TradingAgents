import logging
from unittest.mock import patch

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from tradingagents.agents.scanners.smart_money_scanner import create_smart_money_scanner


class _FakeLlm:
    def bind_tools(self, tools):
        return RunnableLambda(lambda _: AIMessage(content="unused"))


def test_smart_money_preserves_insufficient_evidence_before_provenance(caplog):
    node = create_smart_money_scanner(_FakeLlm())
    insufficient = AIMessage(
        content=(
            "[INSUFFICIENT_EVIDENCE]\n"
            "Node: smart_money_scanner\n"
            "Missing evidence: no successful tool results from required tools: "
            "get_insider_buying_stocks, get_unusual_volume_stocks, "
            "get_breakout_accumulation_stocks."
        )
    )

    with patch(
        "tradingagents.agents.scanners.smart_money_scanner.run_tool_loop",
        return_value=insufficient,
    ), caplog.at_level(logging.WARNING):
        result = node(
            {
                "scan_date": "2026-04-10",
                "messages": [],
                "sector_performance_report": "",
                "smart_money_report": "",
            }
        )

    report = result["smart_money_report"]
    assert report.startswith(
        "[QUALITY: empty | issues=insufficient_evidence_marker | evidence=0"
    )
    assert "[INSUFFICIENT_EVIDENCE]" in report
    assert "Source: Finviz Smart Money Scanner" in report
    assert "insufficient evidence" in caplog.text
