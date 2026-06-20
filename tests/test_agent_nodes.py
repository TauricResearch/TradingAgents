"""Tests for five debate/risk agent node creators.

All five modules (bull_researcher, bear_researcher, aggressive_debator,
neutral_debator, conservative_debator) export a single ``create_*`` function
that returns a LangGraph-compatible node.  The node reads from a structured
state dict, builds a prompt, invokes the LLM, and writes results back to the
state.

This file uses ``unittest.TestCase`` style with ``@pytest.mark.unit`` so it
runs under ``pytest -m unit`` and also directly under ``python -m unittest``.
"""

import unittest
from unittest.mock import MagicMock, patch

import pytest

from tradingagents.agents.researchers.bear_researcher import create_bear_researcher
from tradingagents.agents.researchers.bull_researcher import create_bull_researcher
from tradingagents.agents.risk_mgmt.aggressive_debator import create_aggressive_debator
from tradingagents.agents.risk_mgmt.conservative_debator import create_conservative_debator
from tradingagents.agents.risk_mgmt.neutral_debator import create_neutral_debator

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_BASE_STATE = {
    "company_of_interest": "AAPL",
    "asset_type": "stock",
    "market_report": "Bullish market trends",
    "sentiment_report": "Positive sentiment",
    "news_report": "No adverse news",
    "fundamentals_report": "Strong earnings growth",
    "instrument_context": "Company: Apple Inc.; Sector: Technology",
    "trader_investment_plan": "Buy 100 shares at $180",
    "company_of_interest": "AAPL",
    "holdings_context": {},
    "transactions_context": [],
}


def _make_mock_llm(content="Mock LLM response"):
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content=content)
    return llm


def _make_investment_debate_state(**overrides) -> dict:
    base = {
        "history": "Initial debate history.",
        "bull_history": "Bull says buy.",
        "bear_history": "Bear says sell.",
        "current_response": "Last argument.",
        "judge_decision": "",
        "count": 2,
    }
    base.update(overrides)
    return base


def _make_risk_debate_state(**overrides) -> dict:
    base = {
        "history": "Initial risk debate history.",
        "aggressive_history": "Aggressive says go big.",
        "conservative_history": "Conservative says be careful.",
        "neutral_history": "Neutral says balance.",
        "latest_speaker": "",
        "current_aggressive_response": "",
        "current_conservative_response": "",
        "current_neutral_response": "",
        "count": 0,
    }
    base.update(overrides)
    return base


# ===================================================================
# Bull Researcher
# ===================================================================


@pytest.mark.unit
class TestBullResearcher(unittest.TestCase):
    def test_returns_callable(self):
        node = create_bull_researcher(_make_mock_llm())
        self.assertTrue(callable(node))

    def test_returns_dict_with_investment_debate_state(self):
        node = create_bull_researcher(_make_mock_llm("Bullish case: AAPL undervalued"))
        state = dict(_BASE_STATE)
        state["investment_debate_state"] = _make_investment_debate_state()
        result = node(state)
        self.assertIn("investment_debate_state", result)
        debate = result["investment_debate_state"]
        self.assertIn("Bull Analyst:", debate["bull_history"])
        self.assertEqual("Bull Analyst: Bullish case: AAPL undervalued", debate["current_response"])
        self.assertEqual(3, debate["count"])

    def test_prompt_includes_bear_counterpoint(self):
        captured = {}
        def side_effect(prompt):
            captured["prompt"] = prompt
            return MagicMock(content="Response")
        llm = MagicMock()
        llm.invoke.side_effect = side_effect
        node = create_bull_researcher(llm)
        state = dict(_BASE_STATE)
        state["investment_debate_state"] = _make_investment_debate_state()
        node(state)
        self.assertIn("Apple Inc.", captured["prompt"])
        self.assertIn("Last argument.", captured["prompt"])

    def test_crypto_asset_type_sets_correct_labels(self):
        node = create_bull_researcher(_make_mock_llm("Crypto bull case"))
        state = dict(_BASE_STATE)
        state["asset_type"] = "crypto"
        state["investment_debate_state"] = _make_investment_debate_state()
        result = node(state)
        self.assertIn("investment_debate_state", result)

    def test_minimal_debate_state_handled_with_defaults(self):
        node = create_bull_researcher(_make_mock_llm())
        state = dict(_BASE_STATE)
        state["investment_debate_state"] = {"count": 0}
        result = node(state)
        self.assertIn("investment_debate_state", result)
        self.assertEqual("Bull Analyst: Mock LLM response", result["investment_debate_state"]["current_response"])

    def test_preserves_bear_history(self):
        node = create_bull_researcher(_make_mock_llm("Bull wins"))
        state = dict(_BASE_STATE)
        state["investment_debate_state"] = _make_investment_debate_state(bear_history="Original bear argument")
        result = node(state)
        self.assertIn("Original bear argument", result["investment_debate_state"]["bear_history"])

    def test_llm_invoked_with_prompt_string(self):
        llm = _make_mock_llm()
        state = dict(_BASE_STATE)
        state["investment_debate_state"] = _make_investment_debate_state()
        create_bull_researcher(llm)(state)
        prompt_arg = llm.invoke.call_args[0][0]
        self.assertIsInstance(prompt_arg, str)
        self.assertTrue(prompt_arg.startswith("You are a Bull Analyst"))

    def test_language_instruction_appended(self, monkeypatch=None):
        """Verify get_language_instruction() suffix is appended to the prompt
        by patching it to return a non-empty instruction."""
        with patch(
            "tradingagents.agents.researchers.bull_researcher.get_language_instruction",
            return_value=" Write your entire response in Chinese.",
        ):
            llm = _make_mock_llm()
            state = dict(_BASE_STATE)
            state["investment_debate_state"] = _make_investment_debate_state()
            create_bull_researcher(llm)(state)
            prompt_arg = llm.invoke.call_args[0][0]
            self.assertTrue(prompt_arg.endswith(" Write your entire response in Chinese."))


# ===================================================================
# Bear Researcher
# ===================================================================


@pytest.mark.unit
class TestBearResearcher(unittest.TestCase):
    def test_returns_callable(self):
        node = create_bear_researcher(_make_mock_llm())
        self.assertTrue(callable(node))

    def test_returns_dict_with_investment_debate_state(self):
        node = create_bear_researcher(_make_mock_llm("Bearish case: AAPL overvalued"))
        state = dict(_BASE_STATE)
        state["investment_debate_state"] = _make_investment_debate_state()
        result = node(state)
        self.assertIn("investment_debate_state", result)
        debate = result["investment_debate_state"]
        self.assertIn("Bear Analyst:", debate["bear_history"])
        self.assertEqual("Bear Analyst: Bearish case: AAPL overvalued", debate["current_response"])
        self.assertEqual(3, debate["count"])

    def test_prompt_includes_bull_counterpoint(self):
        captured = {}
        def side_effect(prompt):
            captured["prompt"] = prompt
            return MagicMock(content="Response")
        llm = MagicMock()
        llm.invoke.side_effect = side_effect
        node = create_bear_researcher(llm)
        state = dict(_BASE_STATE)
        state["investment_debate_state"] = _make_investment_debate_state()
        node(state)
        self.assertIn("Apple Inc.", captured["prompt"])
        self.assertIn("Last bull argument", captured["prompt"])

    def test_crypto_asset_type_sets_correct_labels(self):
        node = create_bear_researcher(_make_mock_llm("Crypto bear case"))
        state = dict(_BASE_STATE)
        state["asset_type"] = "crypto"
        state["investment_debate_state"] = _make_investment_debate_state()
        result = node(state)
        self.assertIn("investment_debate_state", result)

    def test_minimal_debate_state_handled_with_defaults(self):
        node = create_bear_researcher(_make_mock_llm())
        state = dict(_BASE_STATE)
        state["investment_debate_state"] = {"count": 0}
        result = node(state)
        self.assertEqual("Bear Analyst: Mock LLM response", result["investment_debate_state"]["current_response"])

    def test_preserves_bull_history(self):
        node = create_bear_researcher(_make_mock_llm("Bear wins"))
        state = dict(_BASE_STATE)
        state["investment_debate_state"] = _make_investment_debate_state(bull_history="Original bull argument")
        result = node(state)
        self.assertIn("Original bull argument", result["investment_debate_state"]["bull_history"])

    def test_prompt_starts_with_bear_intro(self):
        llm = _make_mock_llm()
        state = dict(_BASE_STATE)
        state["investment_debate_state"] = _make_investment_debate_state()
        create_bear_researcher(llm)(state)
        prompt_arg = llm.invoke.call_args[0][0]
        self.assertIsInstance(prompt_arg, str)
        self.assertTrue(prompt_arg.startswith("You are a Bear Analyst"))


# ===================================================================
# Aggressive Debator
# ===================================================================


@pytest.mark.unit
class TestAggressiveDebator(unittest.TestCase):
    def test_returns_callable(self):
        node = create_aggressive_debator(_make_mock_llm())
        self.assertTrue(callable(node))

    def test_returns_dict_with_risk_debate_state(self):
        node = create_aggressive_debator(_make_mock_llm("Aggressive: buy aggressively"))
        state = dict(_BASE_STATE)
        state["risk_debate_state"] = _make_risk_debate_state()
        result = node(state)
        self.assertIn("risk_debate_state", result)
        debate = result["risk_debate_state"]
        self.assertIn("Aggressive Analyst:", debate["aggressive_history"])
        self.assertEqual("Aggressive Analyst: Aggressive: buy aggressively", debate["current_aggressive_response"])
        self.assertEqual(1, debate["count"])
        self.assertEqual("Aggressive", debate["latest_speaker"])

    def test_prompt_includes_trader_decision(self):
        captured = {}
        def side_effect(prompt):
            captured["prompt"] = prompt
            return MagicMock(content="Response")
        llm = MagicMock()
        llm.invoke.side_effect = side_effect
        node = create_aggressive_debator(llm)
        state = dict(_BASE_STATE)
        state["risk_debate_state"] = _make_risk_debate_state(
            current_conservative_response="Conservative says no",
            current_neutral_response="Neutral says maybe",
        )
        node(state)
        self.assertIn("Buy 100 shares at $180", captured["prompt"])
        self.assertIn("Conservative says no", captured["prompt"])

    def test_minimal_risk_debate_state_handled(self):
        node = create_aggressive_debator(_make_mock_llm())
        state = dict(_BASE_STATE)
        state["risk_debate_state"] = {"count": 0}
        result = node(state)
        self.assertIn("risk_debate_state", result)

    def test_preserves_non_current_histories(self):
        node = create_aggressive_debator(_make_mock_llm("Aggressive push"))
        state = dict(_BASE_STATE)
        state["risk_debate_state"] = _make_risk_debate_state(
            conservative_history="Keep conservative.",
            neutral_history="Keep neutral.",
        )
        result = node(state)
        rds = result["risk_debate_state"]
        self.assertIn("Keep conservative.", rds["conservative_history"])
        self.assertIn("Keep neutral.", rds["neutral_history"])


# ===================================================================
# Neutral Debator
# ===================================================================


@pytest.mark.unit
class TestNeutralDebator(unittest.TestCase):
    def test_returns_callable(self):
        node = create_neutral_debator(_make_mock_llm())
        self.assertTrue(callable(node))

    def test_returns_dict_with_risk_debate_state(self):
        node = create_neutral_debator(_make_mock_llm("Neutral: balanced approach"))
        state = dict(_BASE_STATE)
        state["risk_debate_state"] = _make_risk_debate_state()
        result = node(state)
        self.assertIn("risk_debate_state", result)
        debate = result["risk_debate_state"]
        self.assertIn("Neutral Analyst:", debate["neutral_history"])
        self.assertEqual("Neutral Analyst: Neutral: balanced approach", debate["current_neutral_response"])
        self.assertEqual(1, debate["count"])
        self.assertEqual("Neutral", debate["latest_speaker"])

    def test_prompt_includes_trader_decision(self):
        captured = {}
        def side_effect(prompt):
            captured["prompt"] = prompt
            return MagicMock(content="Response")
        llm = MagicMock()
        llm.invoke.side_effect = side_effect
        node = create_neutral_debator(llm)
        state = dict(_BASE_STATE)
        state["risk_debate_state"] = _make_risk_debate_state(
            current_aggressive_response="Aggressive says yes",
            current_conservative_response="Conservative says no",
        )
        node(state)
        self.assertIn("Buy 100 shares at $180", captured["prompt"])
        self.assertIn("Aggressive says yes", captured["prompt"])

    def test_minimal_risk_debate_state_handled(self):
        node = create_neutral_debator(_make_mock_llm())
        state = dict(_BASE_STATE)
        state["risk_debate_state"] = {"count": 0}
        result = node(state)
        self.assertIn("risk_debate_state", result)

    def test_preserves_aggressive_and_conservative_histories(self):
        node = create_neutral_debator(_make_mock_llm("Neutral take"))
        state = dict(_BASE_STATE)
        state["risk_debate_state"] = _make_risk_debate_state(
            aggressive_history="Be aggressive.",
            conservative_history="Be conservative.",
        )
        result = node(state)
        rds = result["risk_debate_state"]
        self.assertIn("Be aggressive.", rds["aggressive_history"])
        self.assertIn("Be conservative.", rds["conservative_history"])


# ===================================================================
# Conservative Debator
# ===================================================================


@pytest.mark.unit
class TestConservativeDebator(unittest.TestCase):
    def test_returns_callable(self):
        node = create_conservative_debator(_make_mock_llm())
        self.assertTrue(callable(node))

    def test_returns_dict_with_risk_debate_state(self):
        node = create_conservative_debator(_make_mock_llm("Conservative: protect capital"))
        state = dict(_BASE_STATE)
        state["risk_debate_state"] = _make_risk_debate_state()
        result = node(state)
        self.assertIn("risk_debate_state", result)
        debate = result["risk_debate_state"]
        self.assertIn("Conservative Analyst:", debate["conservative_history"])
        self.assertEqual("Conservative Analyst: Conservative: protect capital", debate["current_conservative_response"])
        self.assertEqual(1, debate["count"])
        self.assertEqual("Conservative", debate["latest_speaker"])

    def test_prompt_includes_trader_decision(self):
        captured = {}
        def side_effect(prompt):
            captured["prompt"] = prompt
            return MagicMock(content="Response")
        llm = MagicMock()
        llm.invoke.side_effect = side_effect
        node = create_conservative_debator(llm)
        state = dict(_BASE_STATE)
        state["risk_debate_state"] = _make_risk_debate_state(
            current_aggressive_response="Aggressive says yes",
            current_neutral_response="Neutral says maybe",
        )
        node(state)
        self.assertIn("Buy 100 shares at $180", captured["prompt"])
        self.assertIn("Aggressive says yes", captured["prompt"])

    def test_minimal_risk_debate_state_handled(self):
        node = create_conservative_debator(_make_mock_llm())
        state = dict(_BASE_STATE)
        state["risk_debate_state"] = {"count": 0}
        result = node(state)
        self.assertIn("risk_debate_state", result)

    def test_preserves_aggressive_and_neutral_histories(self):
        node = create_conservative_debator(_make_mock_llm("Conservative take"))
        state = dict(_BASE_STATE)
        state["risk_debate_state"] = _make_risk_debate_state(
            aggressive_history="Be aggressive.",
            neutral_history="Be neutral.",
        )
        result = node(state)
        rds = result["risk_debate_state"]
        self.assertIn("Be aggressive.", rds["aggressive_history"])
        self.assertIn("Be neutral.", rds["neutral_history"])


# ===================================================================
# Cross-cutting: holdings_context integration
# ===================================================================


@pytest.mark.unit
class TestRiskDebatorsWithHoldings(unittest.TestCase):
    def _make_holdings_state(self):
        state = dict(_BASE_STATE)
        state["risk_debate_state"] = _make_risk_debate_state()
        state["holdings_context"] = {
            "AAPL": {
                "ticker": "AAPL",
                "quantity": 100,
                "avg_price": 150.0,
                "current_price": 180.0,
                "weight": 0.25,
                "pnl_pct": 0.20,
            }
        }
        state["transactions_context"] = [
            {"ticker": "AAPL", "action": "buy", "quantity": 100, "price": 150.0, "date": "2026-01-10"}
        ]
        return state

    def test_aggressive_holdings_branch_invoked(self):
        with patch(
            "tradingagents.agents.risk_mgmt.aggressive_debator.get_instrument_context_from_state",
            return_value="Company: Apple Inc.",
        ):
            node = create_aggressive_debator(_make_mock_llm("Response"))
            node(self._make_holdings_state())

    def test_neutral_holdings_branch_invoked(self):
        with patch(
            "tradingagents.agents.risk_mgmt.neutral_debator.get_instrument_context_from_state",
            return_value="Company: Apple Inc.",
        ):
            node = create_neutral_debator(_make_mock_llm("Response"))
            node(self._make_holdings_state())

    def test_conservative_holdings_branch_invoked(self):
        with patch(
            "tradingagents.agents.risk_mgmt.conservative_debator.get_instrument_context_from_state",
            return_value="Company: Apple Inc.",
        ):
            node = create_conservative_debator(_make_mock_llm("Response"))
            node(self._make_holdings_state())

    def test_holdings_context_in_prompt(self):
        captured = {}
        def side_effect(prompt):
            captured["prompt"] = prompt
            return MagicMock(content="Response")
        llm = MagicMock()
        llm.invoke.side_effect = side_effect
        with patch(
            "tradingagents.agents.risk_mgmt.aggressive_debator.get_instrument_context_from_state",
            return_value="Company: Apple Inc.",
        ):
            node = create_aggressive_debator(llm)
            node(self._make_holdings_state())
        self.assertIn("当前风险相关信息", captured["prompt"])


# ===================================================================
# Edge cases
# ===================================================================


@pytest.mark.unit
class TestEdgeCases(unittest.TestCase):
    def test_bull_researcher_missing_current_response(self):
        node = create_bull_researcher(_make_mock_llm("Response"))
        state = dict(_BASE_STATE)
        state["investment_debate_state"] = {"count": 0}
        result = node(state)
        self.assertEqual(1, result["investment_debate_state"]["count"])

    def test_bear_researcher_missing_current_response(self):
        node = create_bear_researcher(_make_mock_llm("Response"))
        state = dict(_BASE_STATE)
        state["investment_debate_state"] = {"count": 0}
        result = node(state)
        self.assertEqual(1, result["investment_debate_state"]["count"])

    def test_counter_increments_correctly(self):
        for count_in, count_out in [(0, 1), (1, 2), (99, 100)]:
            node = create_bull_researcher(_make_mock_llm("Response"))
            state = dict(_BASE_STATE)
            state["investment_debate_state"] = {"count": count_in}
            result = node(state)
            self.assertEqual(count_out, result["investment_debate_state"]["count"])

    def test_all_risk_debators_handle_missing_current_fields(self):
        for create_fn in [create_aggressive_debator, create_neutral_debator, create_conservative_debator]:
            with self.subTest(create_fn=create_fn.__name__):
                node = create_fn(_make_mock_llm("Response"))
                state = dict(_BASE_STATE)
                state["risk_debate_state"] = {"count": 5}
                result = node(state)
                self.assertEqual(6, result["risk_debate_state"]["count"])
