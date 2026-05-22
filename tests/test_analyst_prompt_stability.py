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
    return next(
        message.content
        for message in messages
        if isinstance(message, SystemMessage)
    )


def _context_message(messages):
    return next(
        message.content
        for message in messages
        if isinstance(message, HumanMessage)
        and "Analysis context" in message.content
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
            _base_state("AAPL", "2026-05-20"),
        )

    def test_fundamentals_system_prompt_excludes_dynamic_context(self):
        self._assert_tool_analyst_context_is_outside_system(
            create_fundamentals_analyst,
            _base_state("MSFT", "2026-05-20"),
        )

    def test_sentiment_system_prompt_excludes_prefetched_dynamic_context(self):
        state = _base_state("NVDA", "2026-05-20")

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
            messages = _invoke_and_capture(create_sentiment_analyst, state)

        system_prompt = _system_message(messages)
        context_prompt = _context_message(messages)

        self.assertNotIn(state["trade_date"], system_prompt)
        self.assertNotIn(state["company_of_interest"], system_prompt)
        self.assertNotIn("news block for NVDA", system_prompt)
        self.assertNotIn("stocktwits block for NVDA", system_prompt)
        self.assertNotIn("reddit block for NVDA", system_prompt)
        self.assertIn(state["trade_date"], context_prompt)
        self.assertIn(state["company_of_interest"], context_prompt)
        self.assertIn("news block for NVDA", context_prompt)
        self.assertIn("stocktwits block for NVDA", context_prompt)
        self.assertIn("reddit block for NVDA", context_prompt)

    def _assert_tool_analyst_context_is_outside_system(self, node_factory, state):
        messages = _invoke_and_capture(node_factory, state)

        system_prompt = _system_message(messages)
        context_prompt = _context_message(messages)

        self.assertNotIn(state["trade_date"], system_prompt)
        self.assertNotIn(state["company_of_interest"], system_prompt)
        self.assertNotIn("Analysis context", system_prompt)
        self.assertIn(state["trade_date"], context_prompt)
        self.assertIn(state["company_of_interest"], context_prompt)


if __name__ == "__main__":
    unittest.main()
