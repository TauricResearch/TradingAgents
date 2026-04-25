from unittest.mock import patch

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from tradingagents.agents.scanners.factor_alignment_scanner import (
    create_factor_alignment_scanner,
)


class _FakeLlm:
    def bind_tools(self, _tools):
        return RunnableLambda(lambda _inp: AIMessage(content="ok"))


def test_factor_alignment_uses_sector_tool_and_wider_tool_output_budget():
    node = create_factor_alignment_scanner(_FakeLlm())

    captured: dict = {}

    def _fake_run_tool_loop(
        chain,
        initial_messages,
        tools,
        require_tool_result,
        node_name,
        min_report_length,
        max_tool_output_chars,
    ):
        del chain, initial_messages, require_tool_result, node_name, min_report_length
        captured["tool_names"] = [tool.name for tool in tools]
        captured["max_tool_output_chars"] = max_tool_output_chars
        return AIMessage(content="- Quant summary with % return evidence")

    with (
        patch(
            "tradingagents.agents.scanners.factor_alignment_scanner.run_tool_loop",
            side_effect=_fake_run_tool_loop,
        ),
        patch(
            "tradingagents.agents.scanners.factor_alignment_scanner.save_node_report",
            lambda *_args, **_kwargs: None,
        ),
    ):
        result = node(
            {
                "scan_date": "2026-04-10",
                "run_id": "RUN1",
                "messages": [AIMessage(content="Start factor scan")],
                "sector_performance_report": "Technology +2.1%, Energy -1.3%",
            }
        )

    assert "get_sector_performance" in captured["tool_names"]
    assert captured["max_tool_output_chars"] == 5000
    assert "factor_alignment_report" in result
    assert result["sender"] == "factor_alignment_scanner"
