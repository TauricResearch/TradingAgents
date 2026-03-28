from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import Runnable

from tradingagents.agents.scanners.drift_scanner import create_drift_scanner
from tradingagents.agents.scanners.factor_alignment_scanner import (
    create_factor_alignment_scanner,
)


class MockRunnable(Runnable):
    def __init__(self, invoke_responses):
        self.invoke_responses = invoke_responses
        self.call_count = 0

    def invoke(self, input, config=None, **kwargs):
        response = self.invoke_responses[self.call_count]
        self.call_count += 1
        return response


class MockLLM(Runnable):
    def __init__(self, invoke_responses):
        self.runnable = MockRunnable(invoke_responses)
        self.tools_bound = None

    def invoke(self, input, config=None, **kwargs):
        return self.runnable.invoke(input, config=config, **kwargs)

    def bind_tools(self, tools):
        self.tools_bound = tools
        return self.runnable


def _base_state():
    return {
        "messages": [HumanMessage(content="Run the market scan.")],
        "scan_date": "2026-03-27",
        "sector_performance_report": "| Sector | 1-Month % |\n| Technology | +5.0% |",
        "market_movers_report": "| Symbol | Change % |\n| NVDA | +4.0% |",
    }


def test_factor_alignment_scanner_end_to_end():
    llm = MockLLM(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "get_topic_news", "args": {"topic": "analyst upgrades downgrades", "limit": 3}, "id": "tc1"},
                    {"name": "get_topic_news", "args": {"topic": "earnings estimate revisions", "limit": 3}, "id": "tc2"},
                    {"name": "get_earnings_calendar", "args": {"from_date": "2026-03-27", "to_date": "2026-04-17"}, "id": "tc3"},
                ],
            ),
            AIMessage(content="Factor alignment report with globally surfaced tickers."),
        ]
    )

    topic_tool = SimpleNamespace(
        name="get_topic_news",
        invoke=lambda args: "analyst news" if "analyst" in args["topic"] else "revision news",
    )
    earnings_tool = SimpleNamespace(
        name="get_earnings_calendar",
        invoke=lambda args: "earnings calendar",
    )

    with patch(
        "tradingagents.agents.scanners.factor_alignment_scanner.get_topic_news",
        topic_tool,
    ), patch(
        "tradingagents.agents.scanners.factor_alignment_scanner.get_earnings_calendar",
        earnings_tool,
    ):
        node = create_factor_alignment_scanner(llm)
        result = node(_base_state())

    assert "Factor alignment report" in result["factor_alignment_report"]
    assert result["sender"] == "factor_alignment_scanner"
    assert [tool.name for tool in llm.tools_bound] == ["get_topic_news", "get_earnings_calendar"]


def test_drift_scanner_end_to_end():
    llm = MockLLM(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "get_gap_candidates", "args": {}, "id": "tc1"},
                    {"name": "get_topic_news", "args": {"topic": "earnings beats raised guidance", "limit": 3}, "id": "tc2"},
                    {"name": "get_earnings_calendar", "args": {"from_date": "2026-03-27", "to_date": "2026-04-10"}, "id": "tc3"},
                ],
            ),
            AIMessage(content="Drift opportunities report with continuation setups."),
        ]
    )

    gap_tool = SimpleNamespace(
        name="get_gap_candidates",
        invoke=lambda args: "gap candidates table",
    )
    topic_tool = SimpleNamespace(
        name="get_topic_news",
        invoke=lambda args: "continuation news",
    )
    earnings_tool = SimpleNamespace(
        name="get_earnings_calendar",
        invoke=lambda args: "earnings calendar",
    )

    with patch(
        "tradingagents.agents.scanners.drift_scanner.get_gap_candidates",
        gap_tool,
    ), patch(
        "tradingagents.agents.scanners.drift_scanner.get_topic_news",
        topic_tool,
    ), patch(
        "tradingagents.agents.scanners.drift_scanner.get_earnings_calendar",
        earnings_tool,
    ):
        node = create_drift_scanner(llm)
        result = node(_base_state())

    assert "Drift opportunities report" in result["drift_opportunities_report"]
    assert result["sender"] == "drift_scanner"
    assert [tool.name for tool in llm.tools_bound] == [
        "get_gap_candidates",
        "get_topic_news",
        "get_earnings_calendar",
    ]
