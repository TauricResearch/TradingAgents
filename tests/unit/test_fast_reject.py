"""Unit tests for structured critical-abort routing."""

from unittest.mock import MagicMock

from tradingagents.agents.managers.critical_abort_terminal import create_critical_abort_terminal
from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
from tradingagents.agents.utils.critical_abort import has_abort, raise_abort
from tradingagents.graph.conditional_logic import CRITICAL_ABORT_NODE, ConditionalLogic

normal_market_report = "Market analysis shows strong bullish trend with positive momentum."
normal_fundamentals_report = "Company fundamentals are strong with healthy margins."
strong_sell_market_report = (
    "Market view: strong sell due to weak momentum, but no hard-stop event detected."
)
macro_regime_report = "Current macro environment shows stable interest rates."

nvda_false_positive_market_report = """# NVDA Technical Analysis Report

Risk is elevated and a cautious approach is warranted.

[CRITICAL ABORT] No catastrophic conditions detected in the pre-loaded data.

Final recommendation: HOLD / CAUTIOUS DEFENSIVE
"""


def _abort_signal(
    *,
    source: str = "market_analyst",
    reason: str = "market_data_unavailable",
    detail: str = "Trading halted pending SEC investigation.",
) -> dict:
    return raise_abort(source=source, reason=reason, detail=detail, recoverable=True)[
        "abort_signal"
    ]


class TestConditionalLogicAbortDetection:
    def test_has_abort_detects_structured_signal(self):
        assert has_abort({"abort_signal": _abort_signal()}) is True

    def test_report_marker_text_does_not_trigger_abort(self):
        state = {
            "market_report": " \n\t[CRITICAL ABORT] Reason: legacy text marker",
            "fundamentals_report": normal_fundamentals_report,
        }

        assert has_abort(state) is False

    def test_nvda_market_report_does_not_bypass_debate_flow(self):
        cl = ConditionalLogic()
        state = {
            "market_report": nvda_false_positive_market_report,
            "investment_debate_state": {"current_response": "", "count": 0},
        }

        assert cl.should_continue_debate(state) == "Bull Researcher"

    def test_strong_sell_language_does_not_trigger_abort(self):
        state = {"market_report": strong_sell_market_report}

        assert has_abort(state) is False


class TestConditionalLogicFlowControl:
    def test_should_continue_debate_with_structured_abort(self):
        cl = ConditionalLogic()
        state = {
            "abort_signal": _abort_signal(
                source="fundamentals_analyst", reason="fundamentals_empty_ttm"
            ),
            "investment_debate_state": {"current_response": "", "count": 0},
        }

        assert cl.should_continue_debate(state) == CRITICAL_ABORT_NODE

    def test_normal_debate_flow_without_abort(self):
        cl = ConditionalLogic()
        state = {
            "market_report": normal_market_report,
            "fundamentals_report": normal_fundamentals_report,
            "investment_debate_state": {"current_response": "", "count": 0},
        }

        assert cl.should_continue_debate(state) == "Bull Researcher"


class TestCriticalAbortTerminal:
    def test_holding_abort_returns_sell_terminal_action(self):
        node = create_critical_abort_terminal()

        result = node(
            {
                "company_of_interest": "AAPL",
                "portfolio_context": "holding",
                "abort_signal": _abort_signal(),
                "risk_debate_state": {},
            }
        )

        assert result["analysis_status"] == "aborted"
        assert result["terminal_action"] == "SELL"
        assert result["abort_signal"]["reason"] == "market_data_unavailable"
        assert "Terminal Action: SELL" in result["final_trade_decision"]

    def test_candidate_abort_returns_avoid_terminal_action(self):
        node = create_critical_abort_terminal()

        result = node(
            {
                "company_of_interest": "AAPL",
                "portfolio_context": "candidate",
                "abort_signal": _abort_signal(
                    source="fundamentals_analyst",
                    reason="fundamentals_empty_ttm",
                    detail="No TTM fundamentals were available.",
                ),
                "risk_debate_state": {},
            }
        )

        assert result["analysis_status"] == "aborted"
        assert result["terminal_action"] == "AVOID"
        assert result["abort_signal"]["reason"] == "fundamentals_empty_ttm"
        assert "Terminal Action: AVOID" in result["final_trade_decision"]

    def test_news_abort_is_rendered_by_terminal(self):
        node = create_critical_abort_terminal()

        result = node(
            {
                "company_of_interest": "AAPL",
                "portfolio_context": "candidate",
                "abort_signal": _abort_signal(
                    source="news_analyst",
                    reason="news_schema_invalid",
                    detail="Source validation failed twice.",
                ),
                "risk_debate_state": {},
            }
        )

        assert "news_analyst" in result["final_trade_decision"]
        assert "news_schema_invalid" in result["final_trade_decision"]
        assert "Source validation failed twice." in result["final_trade_decision"]


class TestPortfolioManagerAbortDetection:
    @staticmethod
    def _make_mock_llm(content: str) -> MagicMock:
        response = MagicMock(content=content)
        mock_llm = MagicMock()
        bound = MagicMock()
        bound.invoke.return_value = response
        mock_llm.bind.return_value = bound
        mock_llm.invoke.return_value = response
        return mock_llm

    def _make_state(self, *, abort_signal=None):
        return {
            "company_of_interest": "AAPL",
            "market_report": normal_market_report,
            "news_report": "",
            "fundamentals_report": normal_fundamentals_report,
            "macro_regime_report": macro_regime_report,
            "risk_debate_state": {
                "history": [],
                "aggressive_history": [],
                "conservative_history": [],
                "neutral_history": [],
                "current_aggressive_response": "",
                "current_conservative_response": "",
                "current_neutral_response": "",
                "count": 0,
            },
            "sentiment_report": "",
            "investment_plan": "RESEARCH PLAN: SHOULD NOT APPEAR",
            "trader_investment_plan": "TRADER PLAN: USE THIS",
            "abort_signal": abort_signal,
        }

    def test_portfolio_manager_uses_structured_abort_in_abort_prompt(self):
        mock_llm = self._make_mock_llm("RECOMMENDATION: SELL - market data unavailable")
        portfolio_manager = create_portfolio_manager(mock_llm, MagicMock())
        state = self._make_state(abort_signal=_abort_signal())

        result = portfolio_manager(state)

        assert "SELL" in result.get("final_trade_decision", "").upper()
        call_args = mock_llm.bind.return_value.invoke.call_args or mock_llm.invoke.call_args
        prompt = call_args.args[0]
        assert "market_data_unavailable" in prompt
        assert "Trading halted pending SEC investigation." in prompt
        assert "TRADER PLAN: USE THIS" in prompt
        assert "RESEARCH PLAN: SHOULD NOT APPEAR" not in prompt

    def test_portfolio_manager_normal_flow_without_abort(self):
        mock_llm = self._make_mock_llm("RECOMMENDATION: BUY - positive momentum")
        portfolio_manager = create_portfolio_manager(mock_llm, MagicMock())

        result = portfolio_manager(self._make_state())

        assert "BUY" in result.get("final_trade_decision", "").upper()


class TestFastRejectFullFlow:
    def test_structured_abort_terminal_short_circuits_follow_on_routes(self):
        state = {
            "company_of_interest": "AAPL",
            "portfolio_context": "candidate",
            "market_report": normal_market_report,
            "fundamentals_report": normal_fundamentals_report,
            "investment_debate_state": {"current_response": "", "count": 0},
            "risk_debate_state": {"latest_speaker": "Aggressive", "count": 0},
            "abort_signal": _abort_signal(),
        }

        abort_terminal = create_critical_abort_terminal()
        state = {**state, **abort_terminal(state)}

        assert "AVOID" in state.get("final_trade_decision", "").upper()
        assert state.get("analysis_status") == "aborted"

        cl = ConditionalLogic()
        assert cl.should_continue_debate(state) == CRITICAL_ABORT_NODE

    def test_normal_flow_does_not_short_circuit(self):
        state = {
            "market_report": normal_market_report,
            "fundamentals_report": normal_fundamentals_report,
            "investment_debate_state": {"current_response": "", "count": 0},
        }

        cl = ConditionalLogic()

        assert cl.should_continue_debate(state) == "Bull Researcher"
