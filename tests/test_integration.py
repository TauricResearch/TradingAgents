"""End-to-end integration tests for Polymarket agent."""
from unittest.mock import MagicMock, patch


def test_graph_compiles_with_all_analysts():
    """Verify the graph compiles without errors."""
    with patch("tradingagents.graph.trading_graph.create_llm_client") as mock_client:
        mock_llm = MagicMock()
        mock_client.return_value = MagicMock(get_llm=lambda: mock_llm)

        from tradingagents.graph.trading_graph import TradingAgentsGraph
        graph = TradingAgentsGraph(
            selected_analysts=["odds", "social", "news", "event"],
            debug=False,
        )
        assert graph.graph is not None


def test_graph_compiles_with_single_analyst():
    """Verify the graph works with a single analyst."""
    with patch("tradingagents.graph.trading_graph.create_llm_client") as mock_client:
        mock_llm = MagicMock()
        mock_client.return_value = MagicMock(get_llm=lambda: mock_llm)

        from tradingagents.graph.trading_graph import TradingAgentsGraph
        graph = TradingAgentsGraph(
            selected_analysts=["odds"],
            debug=False,
        )
        assert graph.graph is not None


def test_initial_state_has_correct_fields():
    """Verify initial state matches AgentState schema."""
    from tradingagents.graph.propagation import Propagator
    prop = Propagator()
    state = prop.create_initial_state("test-event-id", "Will X happen?", "2026-03-21")

    assert state["event_id"] == "test-event-id"
    assert state["event_question"] == "Will X happen?"
    assert state["odds_report"] == ""
    assert state["event_report"] == ""
    assert state["trader_plan"] == ""
    assert state["final_decision"] == ""
    assert "timing_history" in state["investment_debate_state"]
    assert "latest_speaker" in state["investment_debate_state"]
    assert state["investment_debate_state"]["count"] == 0


def test_initial_state_has_no_old_fields():
    """Verify old stock-related fields are absent."""
    from tradingagents.graph.propagation import Propagator
    prop = Propagator()
    state = prop.create_initial_state("evt", "Q?", "2026-01-01")

    assert "company_of_interest" not in state
    assert "market_report" not in state
    assert "fundamentals_report" not in state
    assert "trader_investment_plan" not in state
    assert "final_trade_decision" not in state


def test_signal_processor_json_output():
    """Verify signal processor returns valid JSON."""
    import json
    from tradingagents.graph.signal_processing import SignalProcessor

    mock_llm = MagicMock()
    mock_llm.invoke.return_value = MagicMock(
        content='{"action": "YES", "confidence": 0.8, "edge": 0.15, "position_size": 0.05, "reasoning": "Strong evidence", "time_horizon": "2 weeks"}'
    )

    processor = SignalProcessor(mock_llm)
    result = processor.process_signal("Analysis text")
    parsed = json.loads(result)
    assert parsed["action"] == "YES"
    assert parsed["confidence"] == 0.8
    assert "edge" in parsed
