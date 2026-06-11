"""Tests for the cache-friendly prompt shape of the debate/risk agents.

Each agent must send a two-part prompt: a system message holding everything
that is constant across rounds (role instructions, reports, trader plan) and
a human message holding only the per-round tail (history, last responses).
The system part being byte-identical across rounds is what makes the
provider-side prompt cache hit — these tests pin that invariant.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from tradingagents.agents.researchers.bear_researcher import create_bear_researcher
from tradingagents.agents.researchers.bull_researcher import create_bull_researcher
from tradingagents.agents.risk_mgmt.aggressive_debator import create_aggressive_debator
from tradingagents.agents.risk_mgmt.conservative_debator import create_conservative_debator
from tradingagents.agents.risk_mgmt.neutral_debator import create_neutral_debator


def _mock_llm():
    llm = MagicMock()
    llm.invoke.return_value = SimpleNamespace(content="the-argument")
    return llm


def _base_state(**extra):
    state = {
        "company_of_interest": "NVDA",
        "instrument_context": "INSTRUMENT-CONTEXT",
        "asset_type": "stock",
        "market_report": "MARKET-REPORT",
        "sentiment_report": "SENTIMENT-REPORT",
        "news_report": "NEWS-REPORT",
        "fundamentals_report": "FUNDAMENTALS-REPORT",
    }
    state.update(extra)
    return state


def _invoked_messages(llm):
    (messages,), _ = llm.invoke.call_args
    return messages


def _research_state(history="", current_response="", count=0):
    return _base_state(
        investment_debate_state={
            "history": history,
            "bull_history": "",
            "bear_history": "",
            "current_response": current_response,
            "count": count,
        }
    )


def _risk_state(history="", count=0, **responses):
    debate = {
        "history": history,
        "aggressive_history": "",
        "conservative_history": "",
        "neutral_history": "",
        "latest_speaker": "",
        "current_aggressive_response": "",
        "current_conservative_response": "",
        "current_neutral_response": "",
        "count": count,
    }
    debate.update(responses)
    return _base_state(trader_investment_plan="TRADER-PLAN", risk_debate_state=debate)


REPORT_TOKENS = (
    "INSTRUMENT-CONTEXT", "MARKET-REPORT", "SENTIMENT-REPORT",
    "NEWS-REPORT", "FUNDAMENTALS-REPORT",
)


@pytest.mark.unit
class TestResearcherPromptShape:
    @pytest.mark.parametrize("factory", [create_bull_researcher, create_bear_researcher])
    def test_reports_in_system_history_in_human(self, factory):
        llm = _mock_llm()
        factory(llm)(_research_state(history="ROUND-1-HISTORY", current_response="LAST-ARG"))

        (system_role, system), (human_role, human) = _invoked_messages(llm)
        assert (system_role, human_role) == ("system", "human")
        for token in REPORT_TOKENS:
            assert token in system
            assert token not in human
        assert "ROUND-1-HISTORY" in human and "ROUND-1-HISTORY" not in system
        assert "LAST-ARG" in human and "LAST-ARG" not in system

    @pytest.mark.parametrize("factory", [create_bull_researcher, create_bear_researcher])
    def test_system_is_byte_identical_across_rounds(self, factory):
        llm = _mock_llm()
        node = factory(llm)
        node(_research_state())
        node(_research_state(history="\nBull: a\nBear: b", current_response="Bear: b", count=2))

        (first, _), (second, _) = (call.args[0] for call in llm.invoke.call_args_list)
        assert first == second  # ("system", <text>) tuples must match exactly

    @pytest.mark.parametrize("factory", [create_bull_researcher, create_bear_researcher])
    def test_round_one_human_message_is_not_empty(self, factory):
        llm = _mock_llm()
        factory(llm)(_research_state())
        _, (_, human) = _invoked_messages(llm)
        assert human.strip()  # Anthropic rejects empty message content

    def test_state_contract_unchanged(self):
        llm = _mock_llm()
        out = create_bull_researcher(llm)(
            _research_state(history="H", current_response="R", count=3)
        )
        debate = out["investment_debate_state"]
        assert debate["history"] == "H\nBull Analyst: the-argument"
        assert debate["bull_history"] == "\nBull Analyst: the-argument"
        assert debate["bear_history"] == ""
        assert debate["current_response"] == "Bull Analyst: the-argument"
        assert debate["count"] == 4


RISK_FACTORIES = [
    (create_aggressive_debator, "Aggressive"),
    (create_conservative_debator, "Conservative"),
    (create_neutral_debator, "Neutral"),
]


@pytest.mark.unit
class TestRiskDebatorPromptShape:
    @pytest.mark.parametrize("factory,_", RISK_FACTORIES)
    def test_plan_and_reports_in_system_history_in_human(self, factory, _):
        llm = _mock_llm()
        factory(llm)(_risk_state(history="RISK-HISTORY"))

        (system_role, system), (human_role, human) = _invoked_messages(llm)
        assert (system_role, human_role) == ("system", "human")
        for token in REPORT_TOKENS + ("TRADER-PLAN",):
            assert token in system
            assert token not in human
        assert "RISK-HISTORY" in human and "RISK-HISTORY" not in system

    @pytest.mark.parametrize("factory,_", RISK_FACTORIES)
    def test_system_is_byte_identical_across_rounds(self, factory, _):
        llm = _mock_llm()
        node = factory(llm)
        node(_risk_state())
        node(
            _risk_state(
                history="\nAggressive Analyst: x",
                count=1,
                current_aggressive_response="Aggressive Analyst: x",
            )
        )

        (first, _), (second, _) = (call.args[0] for call in llm.invoke.call_args_list)
        assert first == second

    @pytest.mark.parametrize("factory,speaker", RISK_FACTORIES)
    def test_state_contract_unchanged(self, factory, speaker):
        llm = _mock_llm()
        out = factory(llm)(_risk_state(history="H", count=2))
        debate = out["risk_debate_state"]
        argument = f"{speaker} Analyst: the-argument"
        assert debate["history"] == f"H\n{argument}"
        assert debate[f"{speaker.lower()}_history"] == f"\n{argument}"
        assert debate["latest_speaker"] == speaker
        assert debate[f"current_{speaker.lower()}_response"] == argument
        assert debate["count"] == 3
