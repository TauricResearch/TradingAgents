"""Tests for stable debate prompts.

These checks ensure the large instruction blocks stay in the system prompt
while the volatile per-run content moves into the human message, which is the
shape needed for better prefix cache reuse.
"""

import unittest

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from tradingagents.agents.researchers.bear_researcher import create_bear_researcher
from tradingagents.agents.researchers.bull_researcher import create_bull_researcher
from tradingagents.agents.risk_mgmt.aggressive_debator import create_aggressive_debator
from tradingagents.agents.risk_mgmt.conservative_debator import create_conservative_debator
from tradingagents.agents.risk_mgmt.neutral_debator import create_neutral_debator


class CapturingLlm:
    def __init__(self):
        self.calls = []

    def __call__(self, prompt):
        if hasattr(prompt, "to_messages"):
            prompt = prompt.to_messages()
        elif hasattr(prompt, "messages"):
            prompt = prompt.messages
        self.calls.append(list(prompt))
        return AIMessage(content="captured argument")


def _state():
    return {
        "asset_type": "stock",
        "company_of_interest": "NVDA",
        "market_report": "market report",
        "sentiment_report": "sentiment report",
        "news_report": "news report",
        "fundamentals_report": "fundamentals report",
        "trader_investment_plan": "trader plan",
        "investment_debate_state": {
            "history": "history",
            "bull_history": "bull history",
            "bear_history": "bear history",
            "current_response": "current response",
            "judge_decision": "",
            "count": 0,
        },
        "risk_debate_state": {
            "history": "risk history",
            "aggressive_history": "aggressive history",
            "conservative_history": "conservative history",
            "neutral_history": "neutral history",
            "latest_speaker": "",
            "current_aggressive_response": "aggressive response",
            "current_conservative_response": "conservative response",
            "current_neutral_response": "neutral response",
            "judge_decision": "",
            "count": 0,
        },
    }


def _system_message(messages):
    return next(message.content for message in messages if isinstance(message, SystemMessage))


def _human_message(messages):
    return next(message.content for message in messages if isinstance(message, HumanMessage))


class DebatePromptStabilityTests(unittest.TestCase):
    def test_bull_prompt_keeps_static_system_message(self):
        llm = CapturingLlm()
        node = create_bull_researcher(llm)
        node(_state())
        messages = llm.calls[-1]
        system_prompt = _system_message(messages)
        human_prompt = _human_message(messages)
        self.assertNotIn("market report", system_prompt)
        self.assertNotIn("sentiment report", system_prompt)
        self.assertIn("market report", human_prompt)
        self.assertIn("history", human_prompt)

    def test_bear_prompt_keeps_static_system_message(self):
        llm = CapturingLlm()
        node = create_bear_researcher(llm)
        node(_state())
        messages = llm.calls[-1]
        system_prompt = _system_message(messages)
        human_prompt = _human_message(messages)
        self.assertNotIn("market report", system_prompt)
        self.assertNotIn("sentiment report", system_prompt)
        self.assertIn("market report", human_prompt)
        self.assertIn("history", human_prompt)

    def test_aggressive_prompt_keeps_static_system_message(self):
        llm = CapturingLlm()
        node = create_aggressive_debator(llm)
        node(_state())
        messages = llm.calls[-1]
        system_prompt = _system_message(messages)
        human_prompt = _human_message(messages)
        self.assertNotIn("risk history", system_prompt)
        self.assertIn("conservative response", human_prompt)
        self.assertIn("neutral response", human_prompt)
        self.assertIn("trader plan", human_prompt)

    def test_conservative_prompt_keeps_static_system_message(self):
        llm = CapturingLlm()
        node = create_conservative_debator(llm)
        node(_state())
        messages = llm.calls[-1]
        system_prompt = _system_message(messages)
        human_prompt = _human_message(messages)
        self.assertNotIn("risk history", system_prompt)
        self.assertIn("aggressive response", human_prompt)
        self.assertIn("neutral response", human_prompt)
        self.assertIn("trader plan", human_prompt)

    def test_neutral_prompt_keeps_static_system_message(self):
        llm = CapturingLlm()
        node = create_neutral_debator(llm)
        node(_state())
        messages = llm.calls[-1]
        system_prompt = _system_message(messages)
        human_prompt = _human_message(messages)
        self.assertNotIn("risk history", system_prompt)
        self.assertIn("aggressive response", human_prompt)
        self.assertIn("conservative response", human_prompt)
        self.assertIn("trader plan", human_prompt)


if __name__ == "__main__":
    unittest.main()
