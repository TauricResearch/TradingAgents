"""Unit tests for reflection module."""

from unittest.mock import Mock, patch
import pytest


class TestReflector:
    """Test suite for Reflector class."""

    @pytest.fixture
    def mock_llm(self):
        """Mock LLM for testing."""
        mock = Mock()
        mock.invoke = Mock(return_value=Mock(content="Reflection result"))
        return mock

    @pytest.fixture
    def mock_memory(self):
        """Mock memory for testing."""
        memory = Mock()
        memory.add_memory = Mock()
        memory.get_memory = Mock(return_value="Previous reflections")
        memory.clear_memory = Mock()
        return memory

    @pytest.fixture
    def sample_state(self):
        """Sample state for reflection."""
        return {
            "company_of_interest": "AAPL",
            "trade_date": "2024-05-10",
            "investment_debate_state": {
                "bull_history": ["Bull argument 1"],
                "bear_history": ["Bear argument 1"],
                "judge_decision": "BUY",
            },
            "trader_investment_plan": "Buy 100 shares",
            "risk_debate_state": {
                "risky_history": ["High risk tolerance"],
                "safe_history": ["Conservative approach"],
                "judge_decision": "MODERATE_RISK",
            },
            "final_trade_decision": "BUY",
        }

    def test_reflector_initialization(self, mock_llm):
        """Test Reflector initialization."""
        reflector = Mock()
        reflector.llm = mock_llm

        assert reflector.llm == mock_llm

    def test_reflect_bull_researcher(self, mock_llm, mock_memory, sample_state):
        """Test reflection for bull researcher."""
        reflector = Mock()
        reflector.reflect_bull_researcher = Mock()

        returns_losses = {"return": 0.05, "loss": -0.02}

        reflector.reflect_bull_researcher(sample_state, returns_losses, mock_memory)

        reflector.reflect_bull_researcher.assert_called_once_with(
            sample_state, returns_losses, mock_memory
        )

    def test_reflect_bear_researcher(self, mock_llm, mock_memory, sample_state):
        """Test reflection for bear researcher."""
        reflector = Mock()
        reflector.reflect_bear_researcher = Mock()

        returns_losses = {"return": -0.03, "loss": -0.05}

        reflector.reflect_bear_researcher(sample_state, returns_losses, mock_memory)

        reflector.reflect_bear_researcher.assert_called_once()

    def test_reflect_trader(self, mock_llm, mock_memory, sample_state):
        """Test reflection for trader."""
        reflector = Mock()
        reflector.reflect_trader = Mock()

        returns_losses = {"return": 0.10, "loss": 0.0}

        reflector.reflect_trader(sample_state, returns_losses, mock_memory)

        reflector.reflect_trader.assert_called_once()

    def test_reflect_invest_judge(self, mock_llm, mock_memory, sample_state):
        """Test reflection for investment judge."""
        reflector = Mock()
        reflector.reflect_invest_judge = Mock()

        returns_losses = {"return": 0.02, "loss": -0.01}

        reflector.reflect_invest_judge(sample_state, returns_losses, mock_memory)

        reflector.reflect_invest_judge.assert_called_once()

    def test_reflect_risk_manager(self, mock_llm, mock_memory, sample_state):
        """Test reflection for risk manager."""
        reflector = Mock()
        reflector.reflect_risk_manager = Mock()

        returns_losses = {"return": -0.05, "loss": -0.10}

        reflector.reflect_risk_manager(sample_state, returns_losses, mock_memory)

        reflector.reflect_risk_manager.assert_called_once()

    def test_reflection_with_positive_returns(
        self, mock_llm, mock_memory, sample_state
    ):
        """Test reflection with positive returns."""
        reflector = Mock()

        # Mock all reflection methods
        reflector.reflect_bull_researcher = Mock(return_value="Positive reflection")
        reflector.reflect_bear_researcher = Mock(return_value="Positive reflection")
        reflector.reflect_trader = Mock(return_value="Positive reflection")

        returns_losses = {"return": 0.15, "loss": 0.0}

        # Call all reflections
        reflector.reflect_bull_researcher(sample_state, returns_losses, mock_memory)
        reflector.reflect_bear_researcher(sample_state, returns_losses, mock_memory)
        reflector.reflect_trader(sample_state, returns_losses, mock_memory)

        # Verify all were called
        assert reflector.reflect_bull_researcher.called
        assert reflector.reflect_bear_researcher.called
        assert reflector.reflect_trader.called

    def test_reflection_with_negative_returns(
        self, mock_llm, mock_memory, sample_state
    ):
        """Test reflection with negative returns."""
        reflector = Mock()

        # Mock reflection methods
        reflector.reflect_bull_researcher = Mock(return_value="Negative reflection")
        reflector.reflect_bear_researcher = Mock(return_value="Negative reflection")
        reflector.reflect_risk_manager = Mock(return_value="Risk reflection")

        returns_losses = {"return": -0.08, "loss": -0.15}

        # Call reflections
        reflector.reflect_bull_researcher(sample_state, returns_losses, mock_memory)
        reflector.reflect_bear_researcher(sample_state, returns_losses, mock_memory)
        reflector.reflect_risk_manager(sample_state, returns_losses, mock_memory)

        # Verify all were called
        assert reflector.reflect_bull_researcher.call_count == 1
        assert reflector.reflect_bear_researcher.call_count == 1
        assert reflector.reflect_risk_manager.call_count == 1

    def test_reflection_memory_update(self, mock_llm, mock_memory):
        """Test that reflection updates memory correctly."""
        reflector = Mock()

        def mock_reflect(state, returns, memory):
            reflection = f"Reflection for {state['company_of_interest']}"
            memory.add_memory(reflection)
            return reflection

        reflector.reflect_trader = Mock(side_effect=mock_reflect)

        state = {"company_of_interest": "TSLA"}
        returns_losses = {"return": 0.05, "loss": 0.0}

        reflector.reflect_trader(state, returns_losses, mock_memory)

        mock_memory.add_memory.assert_called_once()

    def test_reflection_with_different_decisions(self, mock_llm, mock_memory):
        """Test reflection with different trading decisions."""
        reflector = Mock()
        reflector.reflect_trader = Mock()

        decisions = ["BUY", "SELL", "HOLD"]

        for decision in decisions:
            state = {"final_trade_decision": decision, "company_of_interest": "AAPL"}
            returns_losses = {"return": 0.03, "loss": -0.01}

            reflector.reflect_trader(state, returns_losses, mock_memory)

        assert reflector.reflect_trader.call_count == 3

    def test_reflection_error_handling(self, mock_llm, mock_memory, sample_state):
        """Test error handling in reflection."""
        reflector = Mock()

        # Simulate error in reflection
        reflector.reflect_bull_researcher = Mock(
            side_effect=Exception("Reflection error")
        )

        with pytest.raises(Exception):
            reflector.reflect_bull_researcher(sample_state, {}, mock_memory)

        reflector.reflect_bull_researcher.assert_called_once()
