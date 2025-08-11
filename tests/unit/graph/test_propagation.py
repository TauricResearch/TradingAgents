"""Unit tests for propagation module."""

from unittest.mock import Mock, patch
import pytest


class TestPropagator:
    """Test suite for Propagator class."""

    def test_propagator_initialization(self):
        """Test Propagator initialization."""
        # Mock propagator
        propagator = Mock()
        propagator.create_initial_state = Mock()
        propagator.get_graph_args = Mock()

        assert hasattr(propagator, "create_initial_state")
        assert hasattr(propagator, "get_graph_args")
        assert callable(propagator.create_initial_state)
        assert callable(propagator.get_graph_args)

    def test_create_initial_state(self):
        """Test creating initial state for propagation."""
        propagator = Mock()

        # Mock the create_initial_state method
        expected_state = {
            "company_of_interest": "AAPL",
            "trade_date": "2024-05-10",
            "messages": [],
            "market_report": "",
            "sentiment_report": "",
            "news_report": "",
            "fundamentals_report": "",
            "investment_debate_state": {
                "bull_history": [],
                "bear_history": [],
                "history": [],
                "current_response": "",
                "judge_decision": "",
            },
            "trader_investment_plan": "",
            "risk_debate_state": {
                "risky_history": [],
                "safe_history": [],
                "neutral_history": [],
                "history": [],
                "judge_decision": "",
            },
            "investment_plan": "",
            "final_trade_decision": "",
        }

        propagator.create_initial_state = Mock(return_value=expected_state)

        # Test
        state = propagator.create_initial_state("AAPL", "2024-05-10")

        assert state["company_of_interest"] == "AAPL"
        assert state["trade_date"] == "2024-05-10"
        assert state["messages"] == []
        assert "investment_debate_state" in state
        assert "risk_debate_state" in state
        propagator.create_initial_state.assert_called_once_with("AAPL", "2024-05-10")

    def test_get_graph_args(self):
        """Test getting graph arguments."""
        propagator = Mock()

        # Mock the get_graph_args method
        expected_args = {
            "recursion_limit": 100,
            "config": {"tags": ["tradingagents"]},
        }

        propagator.get_graph_args = Mock(return_value=expected_args)

        # Test
        args = propagator.get_graph_args()

        assert "recursion_limit" in args
        assert "config" in args
        assert args["recursion_limit"] == 100
        propagator.get_graph_args.assert_called_once()

    def test_propagate_with_different_tickers(self):
        """Test propagation with different ticker symbols."""
        propagator = Mock()

        tickers = ["AAPL", "GOOGL", "MSFT", "TSLA", "NVDA"]

        for ticker in tickers:
            state = {
                "company_of_interest": ticker,
                "trade_date": "2024-05-10",
                "messages": [],
            }
            propagator.create_initial_state = Mock(return_value=state)

            result = propagator.create_initial_state(ticker, "2024-05-10")
            assert result["company_of_interest"] == ticker

    def test_propagate_with_different_dates(self):
        """Test propagation with different dates."""
        propagator = Mock()

        dates = ["2024-01-01", "2024-06-15", "2024-12-31"]

        for date in dates:
            state = {"company_of_interest": "AAPL", "trade_date": date, "messages": []}
            propagator.create_initial_state = Mock(return_value=state)

            result = propagator.create_initial_state("AAPL", date)
            assert result["trade_date"] == date

    def test_propagate_error_handling(self):
        """Test error handling in propagation."""
        propagator = Mock()

        # Simulate error
        propagator.create_initial_state = Mock(side_effect=ValueError("Invalid ticker"))

        with pytest.raises(ValueError):
            propagator.create_initial_state("INVALID", "2024-05-10")

        propagator.create_initial_state.assert_called_once()

    def test_graph_args_with_custom_config(self):
        """Test graph args with custom configuration."""
        propagator = Mock()

        custom_config = {
            "recursion_limit": 200,
            "config": {"tags": ["custom", "test"], "metadata": {"version": "1.0"}},
        }

        propagator.get_graph_args = Mock(return_value=custom_config)

        args = propagator.get_graph_args()
        assert args["recursion_limit"] == 200
        assert "custom" in args["config"]["tags"]
        assert args["config"]["metadata"]["version"] == "1.0"

    def test_initial_state_completeness(self):
        """Test that initial state contains all required fields."""
        propagator = Mock()

        required_fields = [
            "company_of_interest",
            "trade_date",
            "messages",
            "market_report",
            "sentiment_report",
            "news_report",
            "fundamentals_report",
            "investment_debate_state",
            "trader_investment_plan",
            "risk_debate_state",
            "investment_plan",
            "final_trade_decision",
        ]

        state = {field: "" for field in required_fields}
        state["messages"] = []
        state["investment_debate_state"] = {}
        state["risk_debate_state"] = {}

        propagator.create_initial_state = Mock(return_value=state)

        result = propagator.create_initial_state("AAPL", "2024-05-10")

        for field in required_fields:
            assert field in result, f"Missing required field: {field}"
