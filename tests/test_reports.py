# tests/test_reports.py
import pytest


class TestExtractReports:
    def test_extracts_basic_string_fields(self):
        from backend import _extract_reports
        state = {
            "market_report": "Market analysis here",
            "sentiment_report": "Sentiment text",
            "news_report": "News text",
            "fundamentals_report": "Fundamentals text",
            "trader_investment_plan": "Trader plan",
            "final_trade_decision": "**Rating**: Buy",
        }
        r = _extract_reports(state)
        assert r["market"] == "Market analysis here"
        assert r["sentiment"] == "Sentiment text"
        assert r["news"] == "News text"
        assert r["fundamentals"] == "Fundamentals text"
        assert r["trader"] == "Trader plan"
        assert r["final_decision"] == "**Rating**: Buy"

    def test_joins_bull_history_list_with_double_newline(self):
        from backend import _extract_reports
        state = {
            "investment_debate_state": {
                "bull_history": ["Message 1", "Message 2", "Message 3"],
                "bear_history": ["Bear msg"],
                "judge_decision": "Research manager decision",
            }
        }
        r = _extract_reports(state)
        assert r["bull"] == "Message 1\n\nMessage 2\n\nMessage 3"
        assert r["bear"] == "Bear msg"
        assert r["research_manager"] == "Research manager decision"

    def test_joins_risk_history_list(self):
        from backend import _extract_reports
        state = {
            "risk_debate_state": {
                "history": ["Risk msg A", "Risk msg B"],
            }
        }
        r = _extract_reports(state)
        assert r["risk"] == "Risk msg A\n\nRisk msg B"

    def test_missing_fields_return_empty_string(self):
        from backend import _extract_reports
        r = _extract_reports({})
        assert r["market"] == ""
        assert r["bull"] == ""
        assert r["risk"] == ""
        assert r["research_manager"] == ""
        assert r["final_decision"] == ""

    def test_none_values_return_empty_string(self):
        from backend import _extract_reports
        state = {
            "market_report": None,
            "final_trade_decision": None,
            "investment_debate_state": {"bull_history": None, "bear_history": None},
        }
        r = _extract_reports(state)
        assert r["market"] == ""
        assert r["final_decision"] == ""
        assert r["bull"] == ""

    def test_returns_all_ten_keys(self):
        from backend import _extract_reports
        r = _extract_reports({})
        expected_keys = {
            "market", "sentiment", "news", "fundamentals",
            "bull", "bear", "research_manager", "trader", "risk", "final_decision"
        }
        assert set(r.keys()) == expected_keys
