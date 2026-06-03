import pytest
from unittest.mock import patch, MagicMock


def _temp_config(tmp_path):
    from tradingagents.default_config import DEFAULT_CONFIG

    config = dict(DEFAULT_CONFIG)
    config.update({
        "iic_db_path": str(tmp_path / "iic.db"),
        "iic_data_dir": str(tmp_path / "data"),
        "results_dir": str(tmp_path / "results"),
        "data_cache_dir": str(tmp_path / "cache"),
        "memory_log_path": str(tmp_path / "memory" / "trading_memory.md"),
    })
    return config


@pytest.mark.unit
def test_trading_agents_graph_constructs_a_run_recorder(tmp_path):
    """The constructor must create a RunRecorder for the run and wire its node."""
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    with patch("tradingagents.graph.trading_graph.create_llm_client", return_value=MagicMock()), \
         patch("tradingagents.graph.trading_graph.GraphSetup") as mock_setup:
        mock_setup.return_value.setup_graph.return_value = MagicMock()
        g = TradingAgentsGraph(selected_analysts=["market"], config=_temp_config(tmp_path))
        # The graph must hold a run_id and a recorder.
        assert hasattr(g, "run_id") and g.run_id
        assert hasattr(g, "run_recorder")


@pytest.mark.unit
def test_setup_graph_receives_run_recorder_node(tmp_path):
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    with patch("tradingagents.graph.trading_graph.create_llm_client", return_value=MagicMock()), \
         patch("tradingagents.graph.trading_graph.GraphSetup") as mock_setup:
        mock_setup.return_value.setup_graph.return_value = MagicMock()
        TradingAgentsGraph(selected_analysts=["market"], config=_temp_config(tmp_path))
        call = mock_setup.return_value.setup_graph.call_args
        # run_recorder_node is a kwarg now
        assert "run_recorder_node" in call.kwargs
        assert callable(call.kwargs["run_recorder_node"])
