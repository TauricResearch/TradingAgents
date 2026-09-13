import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableLambda

from tradingagents.agents.analysts.fundamentals_analyst import (
    create_fundamentals_analyst,
)
from tradingagents.agents.analysts.market_analyst import create_market_analyst
from tradingagents.agents.analysts.news_analyst import create_news_analyst
from tradingagents.agents.analysts.sentiment_analyst import create_sentiment_analyst


class CapturingLlm:
    def __init__(self):
        self.calls = []

    def bind_tools(self, tools):
        self.bound_tools = tools
        return RunnableLambda(self._invoke)

    def __call__(self, messages):
        return self._invoke(messages)

    def invoke(self, messages):
        return self._invoke(messages)

    def _invoke(self, messages):
        if hasattr(messages, "to_messages"):
            messages = messages.to_messages()
        elif hasattr(messages, "messages"):
            messages = messages.messages
        self.calls.append(list(messages))
        return AIMessage(content="captured report")


def _base_state(ticker="NVDA", trade_date="2026-05-20"):
    return {
        "company_of_interest": ticker,
        "trade_date": trade_date,
        "messages": [HumanMessage(content="Analyze the target.")],
    }


def _invoke_and_capture(node_factory, state):
    llm = CapturingLlm()
    node = node_factory(llm)
    node(state)
    return llm.calls[-1]


def _system_message(messages):
    return next(message.content for message in messages if isinstance(message, SystemMessage))


def _context_message(messages):
    return next(
        message.content
        for message in messages
        if isinstance(message, HumanMessage) and "Analysis context" in message.content
    )


class AnalystPromptStabilityTests(unittest.TestCase):
    def test_market_system_prompt_excludes_dynamic_context(self):
        self._assert_tool_analyst_context_is_outside_system(
            create_market_analyst,
            {
                **_base_state("BTC-USD", "2026-05-20"),
                "asset_type": "crypto",
            },
        )

    def test_news_system_prompt_excludes_dynamic_context(self):
        self._assert_tool_analyst_context_is_outside_system(
            create_news_analyst,
            {**_base_state("AAPL", "2026-05-20"), "asset_type": "stock"},
            other_asset_type="crypto",
        )

    def test_fundamentals_system_prompt_excludes_dynamic_context(self):
        self._assert_tool_analyst_context_is_outside_system(
            create_fundamentals_analyst,
            _base_state("MSFT", "2026-05-20"),
        )

    def test_sentiment_system_prompt_excludes_prefetched_dynamic_context(self):
        state = _base_state("NVDA", "2026-05-20")
        other_state = _base_state("AAPL", "2027-06-21")

        with (
            patch(
                "tradingagents.agents.analysts.sentiment_analyst.get_news.func",
                return_value="news block for NVDA",
            ),
            patch(
                "tradingagents.agents.analysts.sentiment_analyst.fetch_stocktwits_messages",
                return_value="stocktwits block for NVDA",
            ),
            patch(
                "tradingagents.agents.analysts.sentiment_analyst.fetch_reddit_posts",
                return_value="reddit block for NVDA",
            ),
        ):
            llm = CapturingLlm()
            node = create_sentiment_analyst(llm)
            node(state)
            node(other_state)
            messages = llm.calls[-2]
            other_messages = llm.calls[-1]

        system_prompt = _system_message(messages)
        other_system_prompt = _system_message(other_messages)
        context_prompt = _context_message(messages)
        other_context_prompt = _context_message(other_messages)

        self.assertEqual(system_prompt, other_system_prompt)
        self.assertNotIn(state["trade_date"], system_prompt)
        self.assertNotIn(state["company_of_interest"], system_prompt)
        self.assertNotIn("news block for NVDA", system_prompt)
        self.assertNotIn("stocktwits block for NVDA", system_prompt)
        self.assertNotIn("reddit block for NVDA", system_prompt)
        self.assertIn("collaborating with other assistants", system_prompt)
        self.assertIn("FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**", system_prompt)
        self.assertIn("so the team knows to stop", system_prompt)
        self.assertIn(state["trade_date"], context_prompt)
        self.assertIn("2026-05-13 to 2026-05-20", context_prompt)
        self.assertIn(state["company_of_interest"], context_prompt)
        self.assertIn("news block for NVDA", context_prompt)
        self.assertIn("stocktwits block for NVDA", context_prompt)
        self.assertIn("reddit block for NVDA", context_prompt)
        self.assertIn(other_state["trade_date"], other_context_prompt)
        self.assertIn("2027-06-14 to 2027-06-21", other_context_prompt)
        self.assertIn(other_state["company_of_interest"], other_context_prompt)

    def _assert_tool_analyst_context_is_outside_system(
        self, node_factory, state, other_asset_type=None
    ):
        other_state = {
            **state,
            "company_of_interest": "OTHER-TICKER",
            "trade_date": "2027-06-21",
        }
        if other_asset_type is not None:
            other_state["asset_type"] = other_asset_type
        llm = CapturingLlm()
        node = node_factory(llm)
        node(state)
        node(other_state)
        messages = llm.calls[-2]
        other_messages = llm.calls[-1]

        system_prompt = _system_message(messages)
        other_system_prompt = _system_message(other_messages)
        context_prompt = _context_message(messages)
        other_context_prompt = _context_message(other_messages)

        self.assertEqual(system_prompt, other_system_prompt)
        self.assertNotIn(state["trade_date"], system_prompt)
        self.assertNotIn(state["company_of_interest"], system_prompt)
        self.assertNotIn(other_state["trade_date"], other_system_prompt)
        self.assertNotIn(other_state["company_of_interest"], other_system_prompt)
        self.assertNotIn("Analysis context", system_prompt)
        self.assertIn(state["trade_date"], context_prompt)
        self.assertIn(state["company_of_interest"], context_prompt)
        self.assertIn(other_state["trade_date"], other_context_prompt)
        self.assertIn(other_state["company_of_interest"], other_context_prompt)


if __name__ == "__main__":
    unittest.main()
