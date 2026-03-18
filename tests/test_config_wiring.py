"""Tests for config wiring — new tools in ToolNodes, new state fields, etc."""

import pytest


class TestAgentStateFields:
    def test_macro_regime_report_field_exists(self):
        """AgentState should have macro_regime_report field."""
        from tradingagents.agents.utils.agent_states import AgentState
        # TypedDict fields are accessible via __annotations__
        assert "macro_regime_report" in AgentState.__annotations__

    def test_all_original_fields_still_present(self):
        from tradingagents.agents.utils.agent_states import AgentState
        expected_fields = [
            "company_of_interest", "trade_date", "sender",
            "market_report", "sentiment_report", "news_report", "fundamentals_report",
            "investment_debate_state", "investment_plan", "trader_investment_plan",
            "risk_debate_state", "final_trade_decision",
        ]
        for field in expected_fields:
            assert field in AgentState.__annotations__, f"Missing field: {field}"


class TestNewToolsExported:
    def test_get_ttm_analysis_exported(self):
        from tradingagents.agents.utils.agent_utils import get_ttm_analysis
        # @tool returns a LangChain StructuredTool — callable() is False on it.
        # hasattr(..., "invoke") is the correct check for LangChain tools.
        assert hasattr(get_ttm_analysis, "invoke")

    def test_get_peer_comparison_exported(self):
        from tradingagents.agents.utils.agent_utils import get_peer_comparison
        assert hasattr(get_peer_comparison, "invoke")

    def test_get_sector_relative_exported(self):
        from tradingagents.agents.utils.agent_utils import get_sector_relative
        assert hasattr(get_sector_relative, "invoke")

    def test_get_macro_regime_exported(self):
        from tradingagents.agents.utils.agent_utils import get_macro_regime
        assert hasattr(get_macro_regime, "invoke")

    def test_tools_are_langchain_tools(self):
        """All new tools should be LangChain @tool decorated (have .name attribute)."""
        from tradingagents.agents.utils.agent_utils import (
            get_ttm_analysis, get_peer_comparison, get_sector_relative, get_macro_regime
        )
        for tool in [get_ttm_analysis, get_peer_comparison, get_sector_relative, get_macro_regime]:
            assert hasattr(tool, "name"), f"{tool} is not a LangChain tool"


class TestTTMToolInCategory:
    def test_ttm_in_fundamental_data_category(self):
        from tradingagents.dataflows.interface import TOOLS_CATEGORIES
        assert "get_ttm_analysis" in TOOLS_CATEGORIES["fundamental_data"]["tools"]


class TestConditionalLogicWiring:
    def test_default_config_debate_rounds(self):
        from tradingagents.default_config import DEFAULT_CONFIG
        assert DEFAULT_CONFIG["max_debate_rounds"] == 2
        assert DEFAULT_CONFIG["max_risk_discuss_rounds"] == 2

    def test_conditional_logic_accepts_config_values(self):
        from tradingagents.graph.conditional_logic import ConditionalLogic
        cl = ConditionalLogic(max_debate_rounds=3, max_risk_discuss_rounds=3)
        assert cl.max_debate_rounds == 3
        assert cl.max_risk_discuss_rounds == 3

    def test_debate_threshold_calculation(self):
        """Threshold = 2 * max_debate_rounds."""
        from tradingagents.graph.conditional_logic import ConditionalLogic
        from tradingagents.agents.utils.agent_states import InvestDebateState
        cl = ConditionalLogic(max_debate_rounds=2)
        # At count=4, should route to Research Manager
        state = {
            "investment_debate_state": InvestDebateState(
                bull_history="", bear_history="", history="",
                current_response="Bull: argument", judge_decision="", count=4,
            )
        }
        result = cl.should_continue_debate(state)
        assert result == "Research Manager"

    def test_risk_threshold_calculation(self):
        """Threshold = 3 * max_risk_discuss_rounds."""
        from tradingagents.graph.conditional_logic import ConditionalLogic
        from tradingagents.agents.utils.agent_states import RiskDebateState
        cl = ConditionalLogic(max_risk_discuss_rounds=2)
        state = {
            "risk_debate_state": RiskDebateState(
                aggressive_history="", conservative_history="", neutral_history="",
                history="", latest_speaker="Aggressive",
                current_aggressive_response="", current_conservative_response="",
                current_neutral_response="", judge_decision="", count=6,
            )
        }
        result = cl.should_continue_risk_analysis(state)
        assert result == "Risk Judge"


class TestNewModulesImportable:
    def test_ttm_analysis_importable(self):
        from tradingagents.dataflows.ttm_analysis import compute_ttm_metrics, format_ttm_report
        assert callable(compute_ttm_metrics)
        assert callable(format_ttm_report)

    def test_peer_comparison_importable(self):
        from tradingagents.dataflows.peer_comparison import (
            get_sector_peers, compute_relative_performance,
            get_peer_comparison_report, get_sector_relative_report,
        )
        assert callable(get_sector_peers)
        assert callable(compute_relative_performance)

    def test_macro_regime_importable(self):
        from tradingagents.dataflows.macro_regime import classify_macro_regime, format_macro_report
        assert callable(classify_macro_regime)
        assert callable(format_macro_report)
