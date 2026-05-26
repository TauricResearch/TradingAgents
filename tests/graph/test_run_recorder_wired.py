import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.unit
def test_trading_agents_graph_constructs_a_run_recorder():
    """The constructor must create a RunRecorder for the run and wire its node."""
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    with patch("tradingagents.graph.trading_graph.create_llm_client", return_value=MagicMock()), \
         patch("tradingagents.graph.trading_graph.GraphSetup") as mock_setup:
        mock_setup.return_value.setup_graph.return_value = MagicMock()
        g = TradingAgentsGraph(selected_analysts=["market"])
        # The graph must hold a run_id and a recorder.
        assert hasattr(g, "run_id") and g.run_id
        assert hasattr(g, "run_recorder")


@pytest.mark.unit
def test_setup_graph_receives_run_recorder_node():
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    with patch("tradingagents.graph.trading_graph.create_llm_client", return_value=MagicMock()), \
         patch("tradingagents.graph.trading_graph.GraphSetup") as mock_setup:
        mock_setup.return_value.setup_graph.return_value = MagicMock()
        TradingAgentsGraph(selected_analysts=["market"])
        call = mock_setup.return_value.setup_graph.call_args
        # run_recorder_node is a kwarg now
        assert "run_recorder_node" in call.kwargs
        assert callable(call.kwargs["run_recorder_node"])
