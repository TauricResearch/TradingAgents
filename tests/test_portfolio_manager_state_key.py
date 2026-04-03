"""Tests for Portfolio Manager reading the correct state key.

The Portfolio Manager must use state["trader_investment_plan"] (the Trader's
memory-refined output), not state["investment_plan"] (the Research Manager's
raw output). Using the wrong key means the Trader agent's entire contribution
— including lessons from past trades — is silently bypassed.
"""

import types
import unittest
from unittest.mock import MagicMock


class TestPortfolioManagerStateKey(unittest.TestCase):
    """Verify Portfolio Manager reads trader_investment_plan, not investment_plan."""

    def _make_state(self, trader_plan="TRADER PLAN: BUY AAPL", research_plan="RESEARCH PLAN: HOLD AAPL"):
        """Build a minimal AgentState-like dict for testing."""
        return {
            "company_of_interest": "AAPL",
            "trade_date": "2025-01-15",
            "market_report": "Market is bullish with strong momentum.",
            "sentiment_report": "Social sentiment is positive.",
            "news_report": "No significant negative news.",
            "fundamentals_report": "Strong earnings, low P/E ratio.",
            "investment_plan": research_plan,          # Research Manager's output
            "trader_investment_plan": trader_plan,      # Trader's refined output
            "risk_debate_state": {
                "history": "Aggressive: Go all in. Conservative: Be careful.",
                "aggressive_history": "Aggressive: Go all in.",
                "conservative_history": "Conservative: Be careful.",
                "neutral_history": "Neutral: Balance risk.",
                "latest_speaker": "Neutral",
                "current_aggressive_response": "Aggressive: Go all in.",
                "current_conservative_response": "Conservative: Be careful.",
                "current_neutral_response": "Neutral: Balance risk.",
                "judge_decision": "",
                "count": 3,
            },
        }

    def test_portfolio_manager_uses_trader_plan_not_research_plan(self):
        """The prompt sent to the LLM must contain the Trader's plan, not the Research Manager's."""
        from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Rating: Buy. The trader's analysis is compelling."
        mock_llm.invoke.return_value = mock_response

        mock_memory = MagicMock()
        mock_memory.get_memories.return_value = []

        node = create_portfolio_manager(mock_llm, mock_memory)

        state = self._make_state(
            trader_plan="UNIQUE_TRADER_MARKER: BUY with 60% position",
            research_plan="UNIQUE_RESEARCH_MARKER: HOLD with caution",
        )

        node(state)

        # The LLM should have been called with the Trader's plan
        call_args = mock_llm.invoke.call_args
        prompt_text = call_args[0][0] if call_args[0] else str(call_args)

        self.assertIn("UNIQUE_TRADER_MARKER", prompt_text,
                       "Portfolio Manager must use trader_investment_plan (Trader's output), "
                       "not investment_plan (Research Manager's output)")
        self.assertNotIn("UNIQUE_RESEARCH_MARKER", prompt_text,
                         "Portfolio Manager should NOT contain Research Manager's raw plan")

    def test_portfolio_manager_returns_final_trade_decision(self):
        """Portfolio Manager must return final_trade_decision in its output."""
        from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Final decision: BUY AAPL at market open."
        mock_llm.invoke.return_value = mock_response

        mock_memory = MagicMock()
        mock_memory.get_memories.return_value = []

        node = create_portfolio_manager(mock_llm, mock_memory)
        state = self._make_state()
        result = node(state)

        self.assertIn("final_trade_decision", result)
        self.assertEqual(result["final_trade_decision"], "Final decision: BUY AAPL at market open.")

    def test_portfolio_manager_preserves_risk_debate_state(self):
        """Portfolio Manager must preserve all risk_debate_state fields."""
        from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Decision rendered."
        mock_llm.invoke.return_value = mock_response

        mock_memory = MagicMock()
        mock_memory.get_memories.return_value = []

        node = create_portfolio_manager(mock_llm, mock_memory)
        state = self._make_state()
        result = node(state)

        rds = result["risk_debate_state"]
        self.assertEqual(rds["judge_decision"], "Decision rendered.")
        self.assertEqual(rds["latest_speaker"], "Judge")
        # Original histories must be preserved
        self.assertEqual(rds["aggressive_history"], "Aggressive: Go all in.")
        self.assertEqual(rds["conservative_history"], "Conservative: Be careful.")
        self.assertEqual(rds["neutral_history"], "Neutral: Balance risk.")
        self.assertEqual(rds["count"], 3)

    def test_distinct_trader_and_research_plans_both_present_in_state(self):
        """Ensure the test state correctly models both plan types as distinct values."""
        state = self._make_state(
            trader_plan="Trader says BUY aggressively",
            research_plan="Research says HOLD cautiously",
        )
        self.assertNotEqual(state["investment_plan"], state["trader_investment_plan"],
                           "Test setup: plans must be distinct to catch the wrong-key bug")

    def test_portfolio_manager_with_memory_recommendations(self):
        """Past memory recommendations should appear in the prompt."""
        from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Decision with memory context."
        mock_llm.invoke.return_value = mock_response

        mock_memory = MagicMock()
        mock_memory.get_memories.return_value = [
            {"recommendation": "PAST_LESSON_ALPHA: avoid overleveraging", "similarity_score": 0.9},
            {"recommendation": "PAST_LESSON_BETA: check earnings date", "similarity_score": 0.7},
        ]

        node = create_portfolio_manager(mock_llm, mock_memory)
        state = self._make_state()
        node(state)

        prompt_text = mock_llm.invoke.call_args[0][0]
        self.assertIn("PAST_LESSON_ALPHA", prompt_text)
        self.assertIn("PAST_LESSON_BETA", prompt_text)


class TestStockStatsBulkImport(unittest.TestCase):
    """Verify _get_stock_stats_bulk has access to pandas."""

    def test_pandas_imported_in_y_finance(self):
        """y_finance.py must import pandas for _get_stock_stats_bulk to work."""
        import importlib
        import tradingagents.dataflows.y_finance as yf_module

        # pd must be accessible in the module namespace
        self.assertTrue(
            hasattr(yf_module, 'pd'),
            "_get_stock_stats_bulk uses pd.isna() but pandas is not imported as 'pd' "
            "in y_finance.py, causing NameError on every call"
        )

    def test_pd_isna_callable(self):
        """pd.isna must be callable from y_finance module scope."""
        import tradingagents.dataflows.y_finance as yf_module
        pd_ref = getattr(yf_module, 'pd', None)
        self.assertIsNotNone(pd_ref, "pd not found in y_finance module")
        self.assertTrue(callable(getattr(pd_ref, 'isna', None)),
                       "pd.isna must be callable")


if __name__ == "__main__":
    unittest.main()
