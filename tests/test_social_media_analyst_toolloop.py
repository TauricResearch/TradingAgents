"""Tests for social_media_analyst and news_analyst tool-call loop.

MIX-16531: social_media_analyst was single-shot — if the LLM made tool calls,
tool results were discarded and sentiment_report was left empty. This test
verifies the multi-turn ToolNode loop pattern handles tool calls correctly.

Strategy: patch langgraph.prebuilt.ToolNode before importing the analyst
module. This is the canonical import site for the ToolNode that the node
function uses at runtime (via `from langgraph.prebuilt import ToolNode`).
"""
import unittest
from unittest.mock import MagicMock, patch
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableLambda


def _msg_with_tools(content, tool_calls):
    msg = AIMessage(content=content)
    msg.tool_calls = list(tool_calls)
    return msg


class SocialMediaAnalystToolLoopTests(unittest.TestCase):
    """Verify social_media_analyst handles tool calls correctly."""

    def test_sentiment_report_populated_after_tool_loop(self):
        """Core regression: before the fix, sentiment_report was '' when
        tool_calls > 0 because tool results were never fed back to the LLM."""
        call_count = [0]

        def chain_logic(messages):
            call_count[0] += 1
            if call_count[0] == 1:
                return _msg_with_tools(
                    "Let me search for NVDA news.",
                    [{"name": "get_news", "args": {"query": "NVDA"}, "id": "call1"}],
                )
            else:
                return AIMessage(
                    content="NVDA sentiment is **bullish**.\n\n| Day | Sentiment |\n|-----|----------|\n| Mon | +0.7 |"
                )

        fake_tool_msg = HumanMessage(
            content="[NVDA] Social sentiment: +0.8 on Monday, +0.6 on Tuesday."
        )

        # Patch langgraph.prebuilt.ToolNode before the module imports it.
        # The node function uses `from langgraph.prebuilt import ToolNode`.
        mock_tn_instance = MagicMock()
        mock_tn_instance.invoke.return_value = {"messages": [fake_tool_msg]}
        with patch("langgraph.prebuilt.ToolNode", return_value=mock_tn_instance):
            from tradingagents.agents.analysts.social_media_analyst import (
                create_social_media_analyst,
            )

            mock_llm = MagicMock()
            mock_llm.bind_tools.return_value = RunnableLambda(chain_logic)
            mock_llm.invoke = chain_logic

            analyst_node = create_social_media_analyst(mock_llm)(
                {
                    "trade_date": "2026-05-08",
                    "company_of_interest": "NVDA",
                    "messages": [HumanMessage(content="Analyze NVDA sentiment")],
                }
            )

        self.assertGreater(len(analyst_node["sentiment_report"]), 0)
        self.assertIn("bullish", analyst_node["sentiment_report"])
        self.assertEqual(call_count[0], 2, "LLM should be called twice (tool loop)")

    def test_direct_response_no_tool_calls(self):
        """When LLM responds without tool calls, report is the content on first call."""
        call_count = [0]

        def chain_logic(messages):
            call_count[0] += 1
            return AIMessage(content="Direct report — no tools needed.")

        with patch("langgraph.prebuilt.ToolNode", return_value=MagicMock()):
            from tradingagents.agents.analysts.social_media_analyst import (
                create_social_media_analyst,
            )

            mock_llm = MagicMock()
            mock_llm.bind_tools.return_value = RunnableLambda(chain_logic)

            result = create_social_media_analyst(mock_llm)(
                {
                    "trade_date": "2026-05-08",
                    "company_of_interest": "TSLA",
                    "messages": [HumanMessage(content="Quick TSLA check")],
                }
            )

        self.assertGreater(len(result["sentiment_report"]), 0)
        self.assertIn("Direct report", result["sentiment_report"])
        self.assertEqual(call_count[0], 1, "No tool calls — LLM called exactly once")


class NewsAnalystToolLoopTests(unittest.TestCase):
    """Verify news_analyst handles tool calls correctly."""

    def test_news_report_populated_after_tool_loop(self):
        """Same regression as MIX-16531 but for news_analyst."""
        call_count = [0]

        def chain_logic(messages):
            call_count[0] += 1
            if call_count[0] == 1:
                return _msg_with_tools(
                    "Let me get the latest news.",
                    [{"name": "get_global_news", "args": {}, "id": "call1"}],
                )
            else:
                return AIMessage(
                    content="Macro outlook is **neutral**.\n\n| Factor | Reading |\n|--------|---------|\n| Inflation | Moderate |"
                )

        fake_tool_msg = HumanMessage(content="Global markets: S&P500 flat, yields rising.")
        mock_tn_instance = MagicMock()
        mock_tn_instance.invoke.return_value = {"messages": [fake_tool_msg]}
        with patch("langgraph.prebuilt.ToolNode", return_value=mock_tn_instance):
            from tradingagents.agents.analysts.news_analyst import create_news_analyst

            mock_llm = MagicMock()
            mock_llm.bind_tools.return_value = RunnableLambda(chain_logic)

            analyst_node = create_news_analyst(mock_llm)(
                {
                    "trade_date": "2026-05-08",
                    "company_of_interest": "SPY",
                    "messages": [HumanMessage(content="Macro check for SPY")],
                }
            )

        self.assertGreater(len(analyst_node["news_report"]), 0)
        self.assertIn("Macro outlook", analyst_node["news_report"])
        self.assertEqual(call_count[0], 2)

    def test_messages_accumulate_across_turns(self):
        """The returned messages array should grow with each turn."""
        call_count = [0]

        def chain_logic(messages):
            call_count[0] += 1
            if call_count[0] == 1:
                return _msg_with_tools(
                    "Fetching news.",
                    [{"name": "get_news", "args": {}, "id": "call1"}],
                )
            else:
                return AIMessage(content="Market news report complete.")

        fake_tool_msg = HumanMessage(content="News results here.")
        mock_tn_instance = MagicMock()
        mock_tn_instance.invoke.return_value = {"messages": [fake_tool_msg]}
        with patch("langgraph.prebuilt.ToolNode", return_value=mock_tn_instance):
            from tradingagents.agents.analysts.news_analyst import create_news_analyst

            mock_llm = MagicMock()
            mock_llm.bind_tools.return_value = RunnableLambda(chain_logic)

            result = create_news_analyst(mock_llm)(
                {
                    "trade_date": "2026-05-08",
                    "company_of_interest": "QQQ",
                    "messages": [HumanMessage(content="QQQ analysis")],
                }
            )

        self.assertGreaterEqual(len(result["messages"]), 3)


if __name__ == "__main__":
    unittest.main()