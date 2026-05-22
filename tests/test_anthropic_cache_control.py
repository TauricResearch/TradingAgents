"""Tests for Anthropic cache-control annotations on static system prompts."""

import unittest

from langchain_core.messages import SystemMessage
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableLambda

from tradingagents.agents.analysts.market_analyst import create_market_analyst
from tradingagents.agents.utils.agent_utils import build_cacheable_system_content


class FakeAnthropicLLM:
    __module__ = "langchain_anthropic.chat_models"

    def __init__(self):
        self.calls = []

    def bind_tools(self, tools):
        return RunnableLambda(self._invoke)

    def _invoke(self, prompt):
        if hasattr(prompt, "to_messages"):
            prompt = prompt.to_messages()
        elif hasattr(prompt, "messages"):
            prompt = prompt.messages
        self.calls.append(list(prompt))
        return AIMessage(content="ok")


class AnthropicCacheControlTests(unittest.TestCase):
    def test_cacheable_system_content_wraps_anthropic_system_text(self):
        llm = FakeAnthropicLLM()
        content = build_cacheable_system_content("hello", llm)
        self.assertIsInstance(content, list)
        self.assertEqual(content[0]["cache_control"]["type"], "ephemeral")

    def test_cacheable_system_content_leaves_non_anthropic_text_plain(self):
        content = build_cacheable_system_content("hello", object())
        self.assertEqual(content, "hello")

    def test_market_prompt_uses_system_message_block(self):
        llm = FakeAnthropicLLM()
        node = create_market_analyst(llm)
        node({
            "company_of_interest": "NVDA",
            "trade_date": "2026-05-20",
            "asset_type": "stock",
            "messages": [HumanMessage(content="Analyze NVDA")],
        })

        messages = llm.calls[-1]
        self.assertIsInstance(messages[0], SystemMessage)
        self.assertIsInstance(messages[0].content, list)
        self.assertEqual(messages[0].content[0]["cache_control"]["type"], "ephemeral")


if __name__ == "__main__":
    unittest.main()
