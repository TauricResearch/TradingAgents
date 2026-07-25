"""Tests for Anthropic cache-control annotations on static system prompts."""

import unittest
from unittest.mock import MagicMock

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableLambda

from tradingagents.agents.analysts.market_analyst import create_market_analyst
from tradingagents.agents.managers.research_manager import create_research_manager
from tradingagents.agents.researchers.bull_researcher import create_bull_researcher
from tradingagents.agents.risk_mgmt.aggressive_debator import create_aggressive_debator
from tradingagents.agents.utils.agent_utils import build_cacheable_system_content


def _debate_state():
    return {
        "company_of_interest": "NVDA",
        "market_report": "market",
        "sentiment_report": "sentiment",
        "news_report": "news",
        "fundamentals_report": "fundamentals",
        "trader_investment_plan": "trader plan",
        "investment_debate_state": {
            "history": "history",
            "bull_history": "bull",
            "bear_history": "bear",
            "current_response": "response",
            "count": 0,
        },
        "risk_debate_state": {
            "history": "risk history",
            "aggressive_history": "aggressive",
            "conservative_history": "conservative",
            "neutral_history": "neutral",
            "current_aggressive_response": "aggressive response",
            "current_conservative_response": "conservative response",
            "current_neutral_response": "neutral response",
            "count": 0,
        },
    }


class FakeAnthropicLLM:
    __module__ = "langchain_anthropic.chat_models"

    def __init__(self):
        self.calls = []

    def bind_tools(self, tools):
        return RunnableLambda(self._invoke)

    def with_structured_output(self, schema):
        raise NotImplementedError

    def invoke(self, prompt):
        return self._invoke(prompt)

    def __call__(self, prompt):
        return self._invoke(prompt)

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
        self.assertEqual(content[0]["cache_control"]["ttl"], "5m")

    def test_cacheable_system_content_wraps_native_anthropic_subclasses(self):
        class ProjectAnthropicLLM(FakeAnthropicLLM):
            __module__ = "tradingagents.llm_clients.anthropic_client"

        content = build_cacheable_system_content("hello", ProjectAnthropicLLM())
        self.assertIsInstance(content, list)
        self.assertEqual(content[0]["cache_control"]["type"], "ephemeral")

    def test_cacheable_system_content_leaves_non_anthropic_text_plain(self):
        content = build_cacheable_system_content("hello", object())
        self.assertEqual(content, "hello")

    def test_bedrock_claude_model_id_is_not_marked(self):
        class BedrockLLM:
            model_id = "anthropic.claude-3-5-sonnet-20241022-v2:0"

        content = build_cacheable_system_content("hello", BedrockLLM())
        self.assertEqual(content, "hello")

    def test_magic_mock_claude_model_id_is_not_marked(self):
        claude = MagicMock()
        claude.model_id = "anthropic.claude-3-haiku"
        self.assertEqual(build_cacheable_system_content("hello", claude), "hello")

    def test_openai_compatible_claude_model_is_not_marked(self):
        class ChatOpenAI:
            __module__ = "langchain_openai.chat_models.base"
            model = "claude-3-5-sonnet"

        self.assertEqual(build_cacheable_system_content("hello", ChatOpenAI()), "hello")

    def test_claude_like_class_name_without_provider_or_model_is_not_marked(self):
        class ClaudeHelper:
            __module__ = "example.helpers"

        self.assertEqual(build_cacheable_system_content("hello", ClaudeHelper()), "hello")

    def test_market_prompt_uses_system_message_block(self):
        llm = FakeAnthropicLLM()
        node = create_market_analyst(llm)
        node(
            {
                "company_of_interest": "NVDA",
                "trade_date": "2026-05-20",
                "asset_type": "stock",
                "messages": [HumanMessage(content="Analyze NVDA")],
            }
        )

        messages = llm.calls[-1]
        self.assertIsInstance(messages[0], SystemMessage)
        self.assertIsInstance(messages[0].content, list)
        self.assertEqual(messages[0].content[0]["cache_control"]["type"], "ephemeral")

    def test_researcher_risk_and_structured_agents_cache_system_content(self):
        cases = (
            (create_bull_researcher, _debate_state()),
            (create_aggressive_debator, _debate_state()),
            (
                create_research_manager,
                {
                    "company_of_interest": "NVDA",
                    "investment_debate_state": {
                        "history": "debate",
                        "bull_history": "bull",
                        "bear_history": "bear",
                        "count": 1,
                    },
                },
            ),
        )
        for factory, state in cases:
            with self.subTest(factory=factory.__name__):
                llm = FakeAnthropicLLM()
                factory(llm)(state)
                system = next(
                    message
                    for message in llm.calls[-1]
                    if isinstance(message, SystemMessage)
                    or (isinstance(message, dict) and message.get("role") == "system")
                )
                content = system.content if isinstance(system, SystemMessage) else system["content"]
                self.assertIsInstance(content, list)
                self.assertEqual(content[0]["cache_control"]["type"], "ephemeral")


if __name__ == "__main__":
    unittest.main()
