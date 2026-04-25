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
        "scanner_graph_context_text": SCANNER_PACKET,
        "market_report": "market data here",
        "sentiment_report": "sentiment data here",
        "news_report": "news data here",
        "fundamentals_report": "fundamentals data here",
        "macro_regime_report": "TRANSITION",
        "market_report_structured": {"current_price": "$150.00"},
        "research_packet_summary": "",
        "messages": [("human", "AAPL")],
        "investment_plan": "Buy AAPL at $150",
        "trader_investment_plan": "Buy AAPL at $150",
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


def _mock_llm(response_text: str = "mock response") -> MagicMock:
    """Build a MagicMock LLM compatible with llm_guard.invoke_with_timeout."""
    response = SimpleNamespace(content=response_text)
    mock_llm = MagicMock()

    # This is what invoke_with_timeout uses: llm.bind(...).invoke(...)
    bound = MagicMock()
    bound.invoke.return_value = response
    mock_llm.bind.return_value = bound

    # Support direct .invoke calls
    mock_llm.invoke.return_value = response

    return mock_llm


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
        assert "## Scanner Graph Context" in packet
        assert "$103.28" in packet

    def test_scanner_context_first_in_packet(self):
        """Scanner Context appears before analyst reports in the research packet."""
        state = _base_state(research_packet_summary="")
        packet = build_research_packet(state)
        scanner_pos = packet.index("## Scanner Graph Context")
        market_pos = packet.index("## Market Report")
        assert scanner_pos < market_pos

    def test_raw_reports_take_precedence_over_summary(self):
        """When raw analyst reports exist, they remain canonical even if summary is present."""
        state = _base_state(research_packet_summary="compressed summary with Scanner Context")
        packet = build_research_packet(state)
        assert "## Scanner Graph Context" in packet
        assert "## Market Report" in packet
        assert packet != "compressed summary with Scanner Context"

    def test_summary_used_only_when_raw_reports_missing(self):
        """No legacy-summary fallback remains once summary generation is disabled."""
        state = _base_state(
            scanner_graph_context_text="",
            market_report="",
            sentiment_report="",
            news_report="",
            fundamentals_report="",
            macro_regime_report="",
            research_packet_summary="compressed summary with Scanner Context",
        )
        packet = build_research_packet(state)
        assert packet == ""


# ---------------------------------------------------------------------------
# Research Manager — ground-truth constraint
# ---------------------------------------------------------------------------


class TestResearchManagerGroundTruth:
    def test_ground_truth_in_prompt(self):
        from tradingagents.agents.managers.research_manager import create_research_manager

        llm = _mock_llm("Buy AAPL")
        node = create_research_manager(llm, _mock_memory())
        node(_base_state())

        # Extract prompt from either bind().invoke or plain invoke
        call_args = llm.bind.return_value.invoke.call_args or llm.invoke.call_args
        prompt = call_args.args[0]
        assert "GROUND TRUTH" in prompt
        assert "Scanner Graph Context" in prompt
        assert "Do NOT invent" in prompt

    def test_scratchpad_output_triggers_fallback(self):
        """When LLM outputs scratchpad phrases, we use the deterministic fallback."""
        from tradingagents.agents.managers.research_manager import create_research_manager

        # Trigger phrase: "we need to"
        llm = _mock_llm("We need to follow instruction.\nWe can create bull arguments.")
        node = create_research_manager(llm, _mock_memory())

        result = node(
            _base_state(
                news_report_structured={
                    "status": "completed",
                    "claims": [
                        {
                            "claim": "AAPL secured a $4.10B financing package.",
                            "source": "Reuters",
                            "published_at": "2026-03-30",
                        }
                    ],
                },
                fundamentals_report_structured={
                    "status": "timeout_fallback",
                    "macro_regime": "unknown",
                    "key_metrics": {"numeric_mentions": 0},
                },
            )
        )

        # Should use fallback because scratchpad was detected
        final_out = result.get("investment_plan") or result.get("trader_investment_plan") or ""
        assert "We need to follow instruction" not in final_out
        assert (
            "Market Evidence" in final_out
            or "Macro Regime" in final_out
            or "Price Levels" in final_out
            or "Strategic Action" in final_out
        )


# ---------------------------------------------------------------------------
# Trader — ground-truth constraint
# ---------------------------------------------------------------------------


class TestTraderGroundTruth:
    def test_scanner_context_in_user_message(self):
        from tradingagents.agents.trader.trader import create_trader

        llm = _mock_llm("Buy AAPL at $150")
        node = create_trader(llm, _mock_memory())
        node(_base_state())

        call_args = llm.invoke.call_args.args[0]
        # call_args is a list of messages
        user_msg = next(m for m in call_args if m["role"] == "user")
        assert "## Scanner Graph Context" in user_msg["content"]
        assert "$103.28" in user_msg["content"]

    def test_ground_truth_instruction_in_system_prompt(self):
        from tradingagents.agents.trader.trader import create_trader

        llm = _mock_llm("Buy AAPL at $150")
        node = create_trader(llm, _mock_memory())
        node(_base_state())

        call_args = llm.invoke.call_args.args[0]
        system_msg = next(m for m in call_args if m["role"] == "system")
        assert "ground-truth calendar data ONLY" in system_msg["content"]
        assert "Do NOT estimate or invent" in system_msg["content"]

    def test_scratchpad_output_triggers_fallback(self):
        """When LLM outputs scratchpad phrases, we use the deterministic fallback."""
        from tradingagents.agents.trader.trader import create_trader

        # Contains trigger phrases like "Let's craft" and "produce final answer"
        llm = _mock_llm("Let's craft the final answer.\nNow produce final answer. Buy AAPL.")
        node = create_trader(llm, _mock_memory())

        result = node(_base_state())

        # Should NOT contain the scratchpad text, but rather the fallback
        assert "Let's craft" not in result["trader_investment_plan"]
        assert (
            "Market Evidence" in result["trader_investment_plan"]
            or "Price Levels" in result["trader_investment_plan"]
            or "Research Manager" in result["trader_investment_plan"]
        )

    def test_empty_upstream_plan_raises_runtime_error(self):
        from tradingagents.agents.trader.trader import create_trader

        llm = _mock_llm("- FINAL TRANSACTION PROPOSAL: **BUY**")
        node = create_trader(llm, _mock_memory())
        with pytest.raises(RuntimeError) as exc:
            node(
                _base_state(
                    investment_plan="",
                    investment_plan_structured={"status": "empty"},
                )
            )

        assert "upstream Research Manager plan was empty" in str(exc.value)
        assert llm.invoke.call_count == 0

    def test_price_anchor_mismatch_raises_runtime_error(self):
        from tradingagents.agents.trader.trader import create_trader

        llm = _mock_llm(
            "- Entry Setup: $28.50 breakout\n"
            "- Risk Parameters: Stop-loss $24.23, take-profit $37.05\n"
            "- FINAL TRANSACTION PROPOSAL: **BUY**"
        )
        node = create_trader(llm, _mock_memory())
        with pytest.raises(RuntimeError) as exc:
            node(
                _base_state(
                    investment_plan="- Recommendation: BUY",
                    investment_plan_structured={"status": "completed"},
                    market_report_structured={
                        "current_price": "$130.49",
                        "key_levels": ["$130.49", "$128.47"],
                    },
                )
            )

        assert "entry $28.50 deviates from validated current price $130.49" in str(exc.value)


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


# ---------------------------------------------------------------------------
# Structured contract emission — every downstream node
# ---------------------------------------------------------------------------


class TestStructuredContractEmission:
    """Each agent must emit its canonical structured field alongside the prose report."""

    def test_research_manager_emits_investment_plan_structured(self):
        from tradingagents.agents.managers.research_manager import create_research_manager

        llm = _mock_llm("- Recommendation: BUY\n- Rationale: strong earnings (HIGH)")
        node = create_research_manager(llm, _mock_memory())
        result = node(_base_state())

        assert "investment_plan_structured" in result
        structured = result["investment_plan_structured"]
        assert structured["ticker"] == "AAPL"
        assert structured["status"] == "completed"
        assert structured["contract_version"] == "investment_plan_v1"
        assert structured["recommendation"] == "BUY"

    def test_research_manager_empty_output_triggers_fallback(self):
        from tradingagents.agents.managers.research_manager import create_research_manager

        llm = _mock_llm("")
        node = create_research_manager(llm, _mock_memory())
        result = node(_base_state())

        final_out = result["investment_plan"]
        assert (
            "Market Evidence" in final_out
            or "Macro Regime" in final_out
            or "Strategic Action" in final_out
        )

    def test_trader_emits_trader_plan_structured(self):
        from tradingagents.agents.trader.trader import create_trader

        llm = _mock_llm(
            "- Entry Setup: $150 breakout\n"
            "- Risk Parameters: Stop-loss $140, take-profit $180\n"
            "- FINAL TRANSACTION PROPOSAL: **BUY**"
        )
        node = create_trader(llm, _mock_memory())
        result = node(_base_state())

        assert "trader_plan_structured" in result
        structured = result["trader_plan_structured"]
        assert structured["ticker"] == "AAPL"
        assert structured["status"] == "completed"
        assert structured["contract_version"] == "trader_plan_v1"
        assert structured["final_action"] == "BUY"
        assert structured["key_metrics"]["stop_loss_present"] is True

    def test_risk_synthesis_emits_risk_synthesis_structured(self):
        from tradingagents.agents.risk_mgmt.risk_synthesis import create_risk_synthesis

        llm = _mock_llm(
            "All three analysts agree on stop-loss discipline.\n"
            "Balanced Assessment: BUY with tight risk controls."
        )
        node = create_risk_synthesis(llm)
        state = _base_state()
        state["risk_r1_aggressive"] = "Aggressive R1"
        state["risk_r1_conservative"] = "Conservative R1"
        state["risk_r1_neutral"] = "Neutral R1"
        state["risk_r2_aggressive"] = "Aggressive R2"
        state["risk_r2_conservative"] = "Conservative R2"
        state["risk_r2_neutral"] = "Neutral R2"

        result = node(state)

        assert "risk_synthesis_structured" in result
        structured = result["risk_synthesis_structured"]
        assert structured["ticker"] == "AAPL"
        assert structured["status"] == "completed"
        assert structured["contract_version"] == "risk_synthesis_v1"
        assert structured["consensus_direction"] == "BUY"

    def test_portfolio_manager_emits_final_trade_decision_structured(self):
        from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager

        llm = _mock_llm("- Action: BUY 200 shares\n- Stop-loss: $183\n- Take-profit: $210")
        node = create_portfolio_manager(llm, _mock_memory())
        state = _base_state()
        # Provide enough risk_debate_state for PM
        state["risk_debate_state"] = {
            "aggressive_history": "agg",
            "conservative_history": "con",
            "neutral_history": "neu",
            "history": "full history",
            "summary": "risk summary",
            "latest_speaker": "Synthesis",
            "current_aggressive_response": "agg",
            "current_conservative_response": "con",
            "current_neutral_response": "neu",
            "judge_decision": "",
            "count": 6,
        }

        result = node(state)

        assert "final_trade_decision_structured" in result
        structured = result["final_trade_decision_structured"]
        assert structured["ticker"] == "AAPL"
        assert structured["status"] == "completed"
        assert structured["contract_version"] == "final_decision_v1"
        assert structured["action"] == "BUY"
        assert structured["key_metrics"]["stop_loss_present"] is True
        assert structured["key_metrics"]["take_profit_present"] is True
