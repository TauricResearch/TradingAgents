"""Tests that scanner context ground-truth instructions propagate to all downstream agents.

These tests verify that every agent in the pipeline that receives the scanner
context packet also has explicit ground-truth anchoring instructions, addressing:

- P0 #1: Data integrity — prevents fabricated commodity prices (e.g. $82.30 oil)
- P0 #2: Data integrity — prevents contradicting analyst data (e.g. margin compression)
- P0 #3: Data integrity — prevents wrong-year catalyst dates
- P2 #8: Precision — prevents sector numbers mutating across agents
- P2 #9: Precision — prevents hallucinated statistics
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from tradingagents.agents.utils.summary_context import build_research_packet


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

SCANNER_PACKET = (
    "## STRUCTURED LIVE DATA (GROUND TRUTH)\n"
    "### Commodity Prices\n"
    "Gold: $2,341.50/oz\n"
    "Oil (WTI): $103.28/bbl\n"
    "Bitcoin: $67,890.12\n"
    "### FX Rates\n"
    "EUR/USD: 1.0812\n"
    "### Earnings Calendar\n"
    "AAPL: 2026-04-24\n"
    "### Economic Calendar\n"
    "FOMC: 2026-05-06\n"
    "CPI: 2026-04-10\n"
)


def _base_state(**overrides):
    """Build a minimal pipeline state dict for testing."""
    state = {
        "company_of_interest": "AAPL",
        "trade_date": "2026-03-31",
        "scanner_context_packet": SCANNER_PACKET,
        "market_report": "market data here",
        "sentiment_report": "sentiment data here",
        "news_report": "news data here",
        "fundamentals_report": "fundamentals data here",
        "macro_regime_report": "TRANSITION",
        "research_packet_summary": "",
        "messages": [("human", "AAPL")],
        "investment_plan": "Buy AAPL at $190",
        "trader_investment_plan": "Buy AAPL at $190",
        "investment_debate_state": {
            "bull_history": "bull argument",
            "bear_history": "bear argument",
            "history": "full history",
            "summary": "debate summary",
            "current_response": "Bull Analyst: some argument",
            "current_bull_summary": "Strong fundamentals",
            "current_bear_summary": "Valuation risk",
            "judge_decision": "",
            "count": 2,
        },
        "risk_debate_state": {
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "history": "",
            "summary": "",
            "latest_speaker": "Aggressive",
            "current_aggressive_response": "",
            "current_conservative_response": "",
            "current_neutral_response": "",
            "judge_decision": "",
            "count": 0,
        },
        "risk_r1_aggressive": "Aggressive Round 1 position",
        "risk_r1_conservative": "Conservative Round 1 position",
        "risk_r1_neutral": "Neutral Round 1 position",
    }
    state.update(overrides)
    return state


def _mock_llm(response_text="mock response"):
    llm = MagicMock()
    llm.invoke.return_value = SimpleNamespace(content=response_text)
    return llm


def _mock_memory():
    mem = MagicMock()
    mem.get_memories.return_value = []
    return mem


# ---------------------------------------------------------------------------
# build_research_packet includes scanner context
# ---------------------------------------------------------------------------

class TestBuildResearchPacketIncludesScanner:
    def test_scanner_context_included_when_no_summary(self):
        """When research_packet_summary is empty, raw reports include scanner context."""
        state = _base_state(research_packet_summary="")
        packet = build_research_packet(state)
        assert "Scanner Context (Phase 1)" in packet
        assert "$103.28" in packet

    def test_scanner_context_first_in_packet(self):
        """Scanner Context appears before analyst reports in the research packet."""
        state = _base_state(research_packet_summary="")
        packet = build_research_packet(state)
        scanner_pos = packet.index("Scanner Context (Phase 1)")
        market_pos = packet.index("Market Research Report")
        assert scanner_pos < market_pos

    def test_summary_takes_precedence(self):
        """When research_packet_summary exists, it is used instead of raw reports."""
        state = _base_state(research_packet_summary="compressed summary with Scanner Context")
        packet = build_research_packet(state)
        assert packet == "compressed summary with Scanner Context"


# ---------------------------------------------------------------------------
# Research Manager — ground-truth constraint
# ---------------------------------------------------------------------------

class TestResearchManagerGroundTruth:
    def test_ground_truth_in_prompt(self):
        from tradingagents.agents.managers.research_manager import create_research_manager

        llm = _mock_llm("Buy AAPL")
        node = create_research_manager(llm, _mock_memory())
        node(_base_state())

        prompt = llm.invoke.call_args.args[0]
        assert "GROUND TRUTH" in prompt
        assert "Scanner Context" in prompt
        assert "Do NOT invent" in prompt


# ---------------------------------------------------------------------------
# Trader — ground-truth constraint
# ---------------------------------------------------------------------------

class TestTraderGroundTruth:
    def test_scanner_context_in_user_message(self):
        from tradingagents.agents.trader.trader import create_trader

        llm = _mock_llm("Buy AAPL at $190")
        node = create_trader(llm, _mock_memory())
        node(_base_state())

        call_args = llm.invoke.call_args.args[0]
        # call_args is a list of messages
        user_msg = next(m for m in call_args if m["role"] == "user")
        assert "Scanner Ground-Truth Data" in user_msg["content"]
        assert "$103.28" in user_msg["content"]

    def test_ground_truth_instruction_in_system_prompt(self):
        from tradingagents.agents.trader.trader import create_trader

        llm = _mock_llm("Buy AAPL at $190")
        node = create_trader(llm, _mock_memory())
        node(_base_state())

        call_args = llm.invoke.call_args.args[0]
        system_msg = next(m for m in call_args if m["role"] == "system")
        assert "ground-truth calendar data ONLY" in system_msg["content"]
        assert "Do NOT estimate or invent" in system_msg["content"]


# ---------------------------------------------------------------------------
# Risk Debators — ground-truth constraint (all 3, both rounds)
# ---------------------------------------------------------------------------

class TestRiskDebatorsGroundTruth:
    def test_aggressive_r1_has_ground_truth(self):
        from tradingagents.agents.risk_mgmt.aggressive_debator import create_aggressive_debator

        llm = _mock_llm("aggressive position")
        node = create_aggressive_debator(llm, round_num=1)
        node(_base_state())

        prompt = llm.invoke.call_args.args[0]
        assert "GROUND TRUTH" in prompt
        assert "Scanner Context" in prompt

    def test_aggressive_r2_has_ground_truth(self):
        from tradingagents.agents.risk_mgmt.aggressive_debator import create_aggressive_debator

        llm = _mock_llm("aggressive rebuttal")
        node = create_aggressive_debator(llm, round_num=2)
        node(_base_state())

        prompt = llm.invoke.call_args.args[0]
        assert "GROUND TRUTH" in prompt

    def test_conservative_r1_has_ground_truth(self):
        from tradingagents.agents.risk_mgmt.conservative_debator import create_conservative_debator

        llm = _mock_llm("conservative position")
        node = create_conservative_debator(llm, round_num=1)
        node(_base_state())

        prompt = llm.invoke.call_args.args[0]
        assert "GROUND TRUTH" in prompt
        assert "Scanner Context" in prompt

    def test_conservative_r2_has_ground_truth(self):
        from tradingagents.agents.risk_mgmt.conservative_debator import create_conservative_debator

        llm = _mock_llm("conservative rebuttal")
        node = create_conservative_debator(llm, round_num=2)
        node(_base_state())

        prompt = llm.invoke.call_args.args[0]
        assert "GROUND TRUTH" in prompt

    def test_neutral_r1_has_ground_truth(self):
        from tradingagents.agents.risk_mgmt.neutral_debator import create_neutral_debator

        llm = _mock_llm("neutral position")
        node = create_neutral_debator(llm, round_num=1)
        node(_base_state())

        prompt = llm.invoke.call_args.args[0]
        assert "GROUND TRUTH" in prompt
        assert "Scanner Context" in prompt

    def test_neutral_r2_has_ground_truth(self):
        from tradingagents.agents.risk_mgmt.neutral_debator import create_neutral_debator

        llm = _mock_llm("neutral rebuttal")
        node = create_neutral_debator(llm, round_num=2)
        node(_base_state())

        prompt = llm.invoke.call_args.args[0]
        assert "GROUND TRUTH" in prompt


# ---------------------------------------------------------------------------
# Risk Synthesis — ground-truth constraint
# ---------------------------------------------------------------------------

class TestRiskSynthesisGroundTruth:
    def test_ground_truth_in_synthesis_prompt(self):
        from tradingagents.agents.risk_mgmt.risk_synthesis import create_risk_synthesis

        llm = _mock_llm("synthesis output")
        node = create_risk_synthesis(llm)
        state = _base_state()
        state["risk_r1_aggressive"] = "Aggressive R1"
        state["risk_r1_conservative"] = "Conservative R1"
        state["risk_r1_neutral"] = "Neutral R1"
        state["risk_r2_aggressive"] = "Aggressive R2"
        state["risk_r2_conservative"] = "Conservative R2"
        state["risk_r2_neutral"] = "Neutral R2"

        node(state)

        prompt = llm.invoke.call_args.args[0]
        assert "GROUND TRUTH" in prompt
        assert "Scanner Context" in prompt
        assert "Do NOT introduce statistics" in prompt

    def test_research_packet_included_in_synthesis(self):
        from tradingagents.agents.risk_mgmt.risk_synthesis import create_risk_synthesis

        llm = _mock_llm("synthesis output")
        node = create_risk_synthesis(llm)
        state = _base_state()
        state["risk_r1_aggressive"] = "Aggressive R1"
        state["risk_r1_conservative"] = "Conservative R1"
        state["risk_r1_neutral"] = "Neutral R1"

        node(state)

        prompt = llm.invoke.call_args.args[0]
        assert "Research Packet" in prompt


# ---------------------------------------------------------------------------
# Social Media Analyst — ground-truth constraint
# ---------------------------------------------------------------------------

class TestSocialMediaAnalystGroundTruth:
    def test_ground_truth_in_system_prompt(self):
        """Verify the social media analyst prompt template includes ground-truth instruction."""
        import inspect
        from tradingagents.agents.analysts.social_media_analyst import create_social_media_analyst

        src = inspect.getsource(create_social_media_analyst)
        assert "STRICT GROUND TRUTH" in src
        assert "Scanner Context" in src
        assert "commodity prices" in src.lower() or "ground-truth" in src.lower()


# ---------------------------------------------------------------------------
# Summary rules preserve ground-truth data
# ---------------------------------------------------------------------------

class TestSummaryRulesPreserveGroundTruth:
    def test_research_packet_summary_preserves_prices(self):
        from tradingagents.agents.managers.summary_rules import RESEARCH_PACKET_SUMMARY

        rules_text = " ".join(RESEARCH_PACKET_SUMMARY.rules)
        assert "commodity prices" in rules_text.lower() or "FX rates" in rules_text
        assert "dates" in rules_text.lower()

    def test_scanner_context_is_first_section(self):
        from tradingagents.agents.managers.summary_rules import RESEARCH_PACKET_SUMMARY

        assert RESEARCH_PACKET_SUMMARY.sections[0] == "Scanner Context (Phase 1)"
