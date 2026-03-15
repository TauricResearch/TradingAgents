"""Tests for tradingagents.graph.setup — Executor node integration."""

from unittest.mock import MagicMock, PropertyMock, patch

from tradingagents.execution.models import OrderResult, OrderStatus


class TestExecutorNodeCreation:
    """Test GraphSetup._create_executor_node and conditional wiring."""

    def _make_mock_setup(self, execution_engine=None):
        """Create a minimal GraphSetup-like object with mocks."""
        setup = MagicMock()
        setup.execution_engine = execution_engine
        setup.quick_thinking_llm = MagicMock()
        return setup

    def test_executor_node_buy_decision(self):
        """Executor node should call engine.execute_decision with extracted signal."""
        from tradingagents.graph.setup import GraphSetup

        engine = MagicMock()
        engine.execute_decision.return_value = OrderResult(
            success=True,
            order_id="ORD001",
            status=OrderStatus.FILLED,
            filled_quantity=10,
            filled_price=70000,
            message="Order filled",
        )
        type(engine.broker).is_paper_trading = PropertyMock(return_value=True)

        # Create a real GraphSetup with all mocks
        setup = GraphSetup(
            quick_thinking_llm=MagicMock(),
            deep_thinking_llm=MagicMock(),
            tool_nodes={},
            bull_memory=MagicMock(),
            bear_memory=MagicMock(),
            trader_memory=MagicMock(),
            invest_judge_memory=MagicMock(),
            risk_manager_memory=MagicMock(),
            conditional_logic=MagicMock(),
            execution_engine=engine,
        )

        # Mock SignalProcessor — imported locally in _create_executor_node
        with patch(
            "tradingagents.graph.signal_processing.SignalProcessor"
        ) as MockSP:
            MockSP.return_value.process_signal.return_value = "BUY"
            node_fn = setup._create_executor_node()

        # Simulate calling the node
        state = {
            "final_trade_decision": "Based on analysis, we recommend BUY.",
            "company_of_interest": "005930",
        }
        result = node_fn(state)

        engine.execute_decision.assert_called_once_with("005930", "BUY")
        assert "Paper" in result["execution_result"]
        assert "Order filled" in result["execution_result"]

    def test_executor_node_sell_decision(self):
        from tradingagents.graph.setup import GraphSetup

        engine = MagicMock()
        engine.execute_decision.return_value = OrderResult(
            success=True,
            order_id="ORD002",
            status=OrderStatus.FILLED,
            filled_quantity=50,
            filled_price=73500,
            message="Sold 50 shares",
        )
        type(engine.broker).is_paper_trading = PropertyMock(return_value=False)

        setup = GraphSetup(
            quick_thinking_llm=MagicMock(),
            deep_thinking_llm=MagicMock(),
            tool_nodes={},
            bull_memory=MagicMock(),
            bear_memory=MagicMock(),
            trader_memory=MagicMock(),
            invest_judge_memory=MagicMock(),
            risk_manager_memory=MagicMock(),
            conditional_logic=MagicMock(),
            execution_engine=engine,
        )

        with patch(
            "tradingagents.graph.signal_processing.SignalProcessor"
        ) as MockSP:
            MockSP.return_value.process_signal.return_value = "SELL"
            node_fn = setup._create_executor_node()

        state = {
            "final_trade_decision": "SELL recommendation",
            "company_of_interest": "005930",
        }
        result = node_fn(state)

        assert "Real" in result["execution_result"]
        assert "Sold 50 shares" in result["execution_result"]

    def test_executor_node_hold_decision(self):
        from tradingagents.graph.setup import GraphSetup

        engine = MagicMock()
        engine.execute_decision.return_value = OrderResult(
            success=True,
            status=OrderStatus.FILLED,
            message="HOLD — no action taken",
        )
        type(engine.broker).is_paper_trading = PropertyMock(return_value=True)

        setup = GraphSetup(
            quick_thinking_llm=MagicMock(),
            deep_thinking_llm=MagicMock(),
            tool_nodes={},
            bull_memory=MagicMock(),
            bear_memory=MagicMock(),
            trader_memory=MagicMock(),
            invest_judge_memory=MagicMock(),
            risk_manager_memory=MagicMock(),
            conditional_logic=MagicMock(),
            execution_engine=engine,
        )

        with patch(
            "tradingagents.graph.signal_processing.SignalProcessor"
        ) as MockSP:
            MockSP.return_value.process_signal.return_value = "HOLD"
            node_fn = setup._create_executor_node()

        state = {
            "final_trade_decision": "Maintain current position — HOLD",
            "company_of_interest": "005930",
        }
        result = node_fn(state)

        engine.execute_decision.assert_called_once_with("005930", "HOLD")
        assert "HOLD" in result["execution_result"]


class TestGraphSetupExecutionWiring:
    """Test that setup_graph conditionally adds Executor node."""

    def test_no_executor_without_engine(self):
        """Without execution_engine, Risk Judge should connect to END."""
        from tradingagents.graph.setup import GraphSetup

        setup = GraphSetup(
            quick_thinking_llm=MagicMock(),
            deep_thinking_llm=MagicMock(),
            tool_nodes={"market": MagicMock()},
            bull_memory=MagicMock(),
            bear_memory=MagicMock(),
            trader_memory=MagicMock(),
            invest_judge_memory=MagicMock(),
            risk_manager_memory=MagicMock(),
            conditional_logic=MagicMock(),
            execution_engine=None,
        )

        # Mock all the agent creation functions to avoid LLM dependencies
        with patch("tradingagents.graph.setup.create_market_analyst"), \
             patch("tradingagents.graph.setup.create_msg_delete"), \
             patch("tradingagents.graph.setup.create_bull_researcher"), \
             patch("tradingagents.graph.setup.create_bear_researcher"), \
             patch("tradingagents.graph.setup.create_research_manager"), \
             patch("tradingagents.graph.setup.create_trader"), \
             patch("tradingagents.graph.setup.create_aggressive_debator"), \
             patch("tradingagents.graph.setup.create_neutral_debator"), \
             patch("tradingagents.graph.setup.create_conservative_debator"), \
             patch("tradingagents.graph.setup.create_risk_manager"):
            graph = setup.setup_graph(selected_analysts=["market"])

        # The compiled graph should not have an "Executor" node
        node_names = list(graph.nodes.keys())
        assert "Executor" not in node_names

    def test_executor_added_with_engine(self):
        """With execution_engine, Executor node should be present."""
        from tradingagents.graph.setup import GraphSetup

        engine = MagicMock()

        setup = GraphSetup(
            quick_thinking_llm=MagicMock(),
            deep_thinking_llm=MagicMock(),
            tool_nodes={"market": MagicMock()},
            bull_memory=MagicMock(),
            bear_memory=MagicMock(),
            trader_memory=MagicMock(),
            invest_judge_memory=MagicMock(),
            risk_manager_memory=MagicMock(),
            conditional_logic=MagicMock(),
            execution_engine=engine,
        )

        with patch("tradingagents.graph.setup.create_market_analyst"), \
             patch("tradingagents.graph.setup.create_msg_delete"), \
             patch("tradingagents.graph.setup.create_bull_researcher"), \
             patch("tradingagents.graph.setup.create_bear_researcher"), \
             patch("tradingagents.graph.setup.create_research_manager"), \
             patch("tradingagents.graph.setup.create_trader"), \
             patch("tradingagents.graph.setup.create_aggressive_debator"), \
             patch("tradingagents.graph.setup.create_neutral_debator"), \
             patch("tradingagents.graph.setup.create_conservative_debator"), \
             patch("tradingagents.graph.setup.create_risk_manager"), \
             patch("tradingagents.graph.signal_processing.SignalProcessor"):
            graph = setup.setup_graph(selected_analysts=["market"])

        node_names = list(graph.nodes.keys())
        assert "Executor" in node_names
