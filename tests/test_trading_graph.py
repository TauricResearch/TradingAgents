"""Tests for tradingagents.graph.trading_graph — broker initialization & portfolio injection."""

from unittest.mock import patch, MagicMock, PropertyMock

from tradingagents.execution.models import OrderResult, OrderStatus


class TestBrokerInitialization:
    """Test that TradingAgentsGraph conditionally initializes the execution layer."""

    @patch("tradingagents.graph.trading_graph.GraphSetup")
    @patch("tradingagents.graph.trading_graph.Reflector")
    @patch("tradingagents.graph.trading_graph.SignalProcessor")
    @patch("tradingagents.graph.trading_graph.Propagator")
    @patch("tradingagents.graph.trading_graph.ConditionalLogic")
    @patch("tradingagents.graph.trading_graph.FinancialSituationMemory")
    @patch("tradingagents.graph.trading_graph.create_llm_client")
    @patch("tradingagents.graph.trading_graph.set_config")
    @patch("tradingagents.graph.trading_graph.os.makedirs")
    def test_broker_disabled_by_default(
        self, mock_makedirs, mock_set_config, mock_llm,
        mock_memory, mock_cond, mock_prop, mock_sp, mock_refl, mock_gs
    ):
        """When broker.enabled is False, execution_engine should be None."""
        mock_client = MagicMock()
        mock_client.get_llm.return_value = MagicMock()
        mock_llm.return_value = mock_client
        mock_gs.return_value.setup_graph.return_value = MagicMock()

        from tradingagents.graph.trading_graph import TradingAgentsGraph

        config = {
            "llm_provider": "openai",
            "deep_think_llm": "gpt-4",
            "quick_think_llm": "gpt-4",
            "project_dir": "/tmp/test",
            "broker": {"enabled": False},
        }
        graph = TradingAgentsGraph(config=config)
        assert graph.execution_engine is None

    @patch("tradingagents.graph.trading_graph.GraphSetup")
    @patch("tradingagents.graph.trading_graph.Reflector")
    @patch("tradingagents.graph.trading_graph.SignalProcessor")
    @patch("tradingagents.graph.trading_graph.Propagator")
    @patch("tradingagents.graph.trading_graph.ConditionalLogic")
    @patch("tradingagents.graph.trading_graph.FinancialSituationMemory")
    @patch("tradingagents.graph.trading_graph.create_llm_client")
    @patch("tradingagents.graph.trading_graph.set_config")
    @patch("tradingagents.graph.trading_graph.os.makedirs")
    def test_broker_enabled_creates_engine(
        self, mock_makedirs, mock_set_config, mock_llm,
        mock_memory, mock_cond, mock_prop, mock_sp, mock_refl, mock_gs
    ):
        """When broker.enabled is True, execution_engine should be initialized."""
        mock_client = MagicMock()
        mock_client.get_llm.return_value = MagicMock()
        mock_llm.return_value = mock_client
        mock_gs.return_value.setup_graph.return_value = MagicMock()

        mock_broker = MagicMock()
        mock_engine = MagicMock()

        with patch(
            "tradingagents.execution.create_broker",
            return_value=mock_broker,
        ) as mock_create_broker, patch(
            "tradingagents.execution.ExecutionEngine",
            return_value=mock_engine,
        ) as mock_engine_cls:
            from tradingagents.graph.trading_graph import TradingAgentsGraph

            config = {
                "llm_provider": "openai",
                "deep_think_llm": "gpt-4",
                "quick_think_llm": "gpt-4",
                "project_dir": "/tmp/test",
                "broker": {
                    "enabled": True,
                    "mode": "paper",
                    "kis_app_key": "key",
                    "kis_app_secret": "secret",
                    "kis_account_no": "12345678-01",
                },
            }
            graph = TradingAgentsGraph(config=config)

        mock_create_broker.assert_called_once()
        mock_broker.connect.assert_called_once()
        assert graph.execution_engine is mock_engine


class TestPortfolioContextInjection:
    """Test that propagate() injects portfolio_context when broker is active."""

    @patch("tradingagents.graph.trading_graph.GraphSetup")
    @patch("tradingagents.graph.trading_graph.Reflector")
    @patch("tradingagents.graph.trading_graph.SignalProcessor")
    @patch("tradingagents.graph.trading_graph.Propagator")
    @patch("tradingagents.graph.trading_graph.ConditionalLogic")
    @patch("tradingagents.graph.trading_graph.FinancialSituationMemory")
    @patch("tradingagents.graph.trading_graph.create_llm_client")
    @patch("tradingagents.graph.trading_graph.set_config")
    @patch("tradingagents.graph.trading_graph.os.makedirs")
    def test_portfolio_context_injected(
        self, mock_makedirs, mock_set_config, mock_llm,
        mock_memory, mock_cond, mock_prop, mock_sp, mock_refl, mock_gs
    ):
        mock_client = MagicMock()
        mock_client.get_llm.return_value = MagicMock()
        mock_llm.return_value = mock_client

        # Mock graph compile & invoke
        mock_graph = MagicMock()
        mock_final_state = {
            "company_of_interest": "005930",
            "trade_date": "2026-03-15",
            "market_report": "",
            "sentiment_report": "",
            "news_report": "",
            "fundamentals_report": "",
            "investment_debate_state": {
                "bull_history": [], "bear_history": [], "history": [],
                "current_response": "", "judge_decision": "",
            },
            "trader_investment_plan": "",
            "risk_debate_state": {
                "aggressive_history": [], "conservative_history": [],
                "neutral_history": [], "history": [], "judge_decision": "",
            },
            "investment_plan": "",
            "final_trade_decision": "BUY",
            "execution_result": "",
        }
        mock_graph.invoke.return_value = mock_final_state
        mock_gs.return_value.setup_graph.return_value = mock_graph

        # Propagator mock
        mock_prop_inst = mock_prop.return_value
        mock_prop_inst.create_initial_state.return_value = {
            "company_of_interest": "005930",
            "portfolio_context": "",
        }
        mock_prop_inst.get_graph_args.return_value = {}

        # SignalProcessor mock
        mock_sp.return_value.process_signal.return_value = "BUY"

        from tradingagents.graph.trading_graph import TradingAgentsGraph

        config = {
            "llm_provider": "openai",
            "deep_think_llm": "gpt-4",
            "quick_think_llm": "gpt-4",
            "project_dir": "/tmp/test",
            "broker": {"enabled": False},
        }
        graph_obj = TradingAgentsGraph(config=config)

        # Now simulate having an execution engine
        mock_engine = MagicMock()
        mock_engine.get_portfolio_context.return_value = (
            "보유종목: 삼성전자 100주, 예수금: 10,000,000원"
        )
        graph_obj.execution_engine = mock_engine

        graph_obj.propagate("005930", "2026-03-15")

        # Verify portfolio context was injected into initial state
        init_state = mock_prop_inst.create_initial_state.return_value
        assert init_state["portfolio_context"] == (
            "보유종목: 삼성전자 100주, 예수금: 10,000,000원"
        )

    @patch("tradingagents.graph.trading_graph.GraphSetup")
    @patch("tradingagents.graph.trading_graph.Reflector")
    @patch("tradingagents.graph.trading_graph.SignalProcessor")
    @patch("tradingagents.graph.trading_graph.Propagator")
    @patch("tradingagents.graph.trading_graph.ConditionalLogic")
    @patch("tradingagents.graph.trading_graph.FinancialSituationMemory")
    @patch("tradingagents.graph.trading_graph.create_llm_client")
    @patch("tradingagents.graph.trading_graph.set_config")
    @patch("tradingagents.graph.trading_graph.os.makedirs")
    def test_no_injection_without_engine(
        self, mock_makedirs, mock_set_config, mock_llm,
        mock_memory, mock_cond, mock_prop, mock_sp, mock_refl, mock_gs
    ):
        mock_client = MagicMock()
        mock_client.get_llm.return_value = MagicMock()
        mock_llm.return_value = mock_client

        mock_graph = MagicMock()
        mock_final_state = {
            "company_of_interest": "005930",
            "trade_date": "2026-03-15",
            "market_report": "",
            "sentiment_report": "",
            "news_report": "",
            "fundamentals_report": "",
            "investment_debate_state": {
                "bull_history": [], "bear_history": [], "history": [],
                "current_response": "", "judge_decision": "",
            },
            "trader_investment_plan": "",
            "risk_debate_state": {
                "aggressive_history": [], "conservative_history": [],
                "neutral_history": [], "history": [], "judge_decision": "",
            },
            "investment_plan": "",
            "final_trade_decision": "HOLD",
            "execution_result": "",
        }
        mock_graph.invoke.return_value = mock_final_state
        mock_gs.return_value.setup_graph.return_value = mock_graph

        mock_prop_inst = mock_prop.return_value
        mock_prop_inst.create_initial_state.return_value = {
            "company_of_interest": "005930",
            "portfolio_context": "",
        }
        mock_prop_inst.get_graph_args.return_value = {}
        mock_sp.return_value.process_signal.return_value = "HOLD"

        from tradingagents.graph.trading_graph import TradingAgentsGraph

        config = {
            "llm_provider": "openai",
            "deep_think_llm": "gpt-4",
            "quick_think_llm": "gpt-4",
            "project_dir": "/tmp/test",
            "broker": {"enabled": False},
        }
        graph_obj = TradingAgentsGraph(config=config)
        graph_obj.propagate("005930", "2026-03-15")

        # portfolio_context should remain empty
        init_state = mock_prop_inst.create_initial_state.return_value
        assert init_state["portfolio_context"] == ""


class TestLogState:
    """Test that _log_state includes execution_result."""

    @patch("tradingagents.graph.trading_graph.GraphSetup")
    @patch("tradingagents.graph.trading_graph.Reflector")
    @patch("tradingagents.graph.trading_graph.SignalProcessor")
    @patch("tradingagents.graph.trading_graph.Propagator")
    @patch("tradingagents.graph.trading_graph.ConditionalLogic")
    @patch("tradingagents.graph.trading_graph.FinancialSituationMemory")
    @patch("tradingagents.graph.trading_graph.create_llm_client")
    @patch("tradingagents.graph.trading_graph.set_config")
    @patch("tradingagents.graph.trading_graph.os.makedirs")
    @patch("builtins.open", new_callable=MagicMock)
    @patch("tradingagents.graph.trading_graph.Path.mkdir")
    def test_execution_result_in_log(
        self, mock_mkdir, mock_open, mock_makedirs, mock_set_config,
        mock_llm, mock_memory, mock_cond, mock_prop, mock_sp, mock_refl, mock_gs
    ):
        mock_client = MagicMock()
        mock_client.get_llm.return_value = MagicMock()
        mock_llm.return_value = mock_client
        mock_gs.return_value.setup_graph.return_value = MagicMock()

        from tradingagents.graph.trading_graph import TradingAgentsGraph

        config = {
            "llm_provider": "openai",
            "deep_think_llm": "gpt-4",
            "quick_think_llm": "gpt-4",
            "project_dir": "/tmp/test",
            "broker": {"enabled": False},
        }
        graph_obj = TradingAgentsGraph(config=config)
        graph_obj.ticker = "005930"

        final_state = {
            "company_of_interest": "005930",
            "trade_date": "2026-03-15",
            "market_report": "market data",
            "sentiment_report": "sentiment data",
            "news_report": "news data",
            "fundamentals_report": "fundamentals data",
            "investment_debate_state": {
                "bull_history": [], "bear_history": [], "history": [],
                "current_response": "", "judge_decision": "",
            },
            "trader_investment_plan": "Buy plan",
            "risk_debate_state": {
                "aggressive_history": [], "conservative_history": [],
                "neutral_history": [], "history": [], "judge_decision": "",
            },
            "investment_plan": "Invest",
            "final_trade_decision": "BUY",
            "execution_result": "[Paper] BUY → Order filled",
        }

        graph_obj._log_state("2026-03-15", final_state)

        logged = graph_obj.log_states_dict["2026-03-15"]
        assert logged["execution_result"] == "[Paper] BUY → Order filled"
        assert logged["final_trade_decision"] == "BUY"
