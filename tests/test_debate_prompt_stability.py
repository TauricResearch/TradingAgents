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

    def invoke(self, prompt):
        if hasattr(prompt, "to_messages"):
            prompt = prompt.to_messages()
        elif hasattr(prompt, "messages"):
            prompt = prompt.messages
        self.calls.append(list(prompt))
        return AIMessage(content="captured argument")


def _state(suffix="one"):
    return {
        "asset_type": "stock",
        "company_of_interest": f"ticker {suffix}",
        "instrument_context": f"instrument context {suffix}",
        "market_report": f"market report {suffix}",
        "sentiment_report": f"sentiment report {suffix}",
        "news_report": f"news report {suffix}",
        "fundamentals_report": f"fundamentals report {suffix}",
        "trader_investment_plan": f"trader plan {suffix}",
        "investment_debate_state": {
            "history": f"history {suffix}",
            "bull_history": f"bull history {suffix}",
            "bear_history": f"bear history {suffix}",
            "current_response": f"current response {suffix}",
            "judge_decision": "",
            "count": 0,
        },
        "risk_debate_state": {
            "history": f"risk history {suffix}",
            "aggressive_history": f"aggressive history {suffix}",
            "conservative_history": f"conservative history {suffix}",
            "neutral_history": f"neutral history {suffix}",
            "latest_speaker": "",
            "current_aggressive_response": f"aggressive response {suffix}",
            "current_conservative_response": f"conservative response {suffix}",
            "current_neutral_response": f"neutral response {suffix}",
            "judge_decision": "",
            "count": 0,
        },
    }


def _system_message(messages):
    return next(message.content for message in messages if isinstance(message, SystemMessage))


def _human_message(messages):
    return next(message.content for message in messages if isinstance(message, HumanMessage))


class DebatePromptStabilityTests(unittest.TestCase):
    factories = (
        create_bull_researcher,
        create_bear_researcher,
        create_aggressive_debator,
        create_neutral_debator,
        create_conservative_debator,
    )

    def test_all_debate_system_prompts_are_stable_and_context_is_dynamic(self):
        dynamic_values = (
            "instrument context",
            "market report",
            "sentiment report",
            "news report",
            "fundamentals report",
            "history",
            "current response",
            "trader plan",
            "aggressive response",
            "conservative response",
            "neutral response",
        )
        for factory in self.factories:
            with self.subTest(factory=factory.__name__):
                llm = CapturingLlm()
                node = factory(llm)
                node(_state("one"))
                node(_state("two"))
                first_system = _system_message(llm.calls[-2])
                second_system = _system_message(llm.calls[-1])
                first_human = _human_message(llm.calls[-2])
                second_human = _human_message(llm.calls[-1])

                self.assertEqual(first_system, second_system)
                for value in dynamic_values:
                    self.assertNotIn(value, first_system.lower())
                self.assertIn("one", first_human)
                self.assertIn("two", second_human)

    def test_risk_system_prompts_preserve_debate_behavior(self):
        for factory in (
            create_aggressive_debator,
            create_neutral_debator,
            create_conservative_debator,
        ):
            with self.subTest(factory=factory.__name__):
                llm = CapturingLlm()
                factory(llm)(_state())
                system_prompt = _system_message(llm.calls[-1]).lower()
                self.assertIn("no responses", system_prompt)
                self.assertIn("present your own argument", system_prompt)
                self.assertIn("debating", system_prompt)
                self.assertIn("not just presenting data", system_prompt)
                self.assertIn("output conversationally", system_prompt)
                self.assertIn("without any special formatting", system_prompt)

    def test_dynamic_json_braces_are_passed_as_literal_content(self):
        json_evidence = '{"score": 7}'
        state = _state(json_evidence)

        for factory in self.factories:
            with self.subTest(factory=factory.__name__):
                llm = CapturingLlm()
                factory(llm)(state)
                self.assertIn(json_evidence, _human_message(llm.calls[-1]))

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
