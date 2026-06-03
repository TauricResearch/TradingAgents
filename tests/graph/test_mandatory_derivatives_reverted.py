import pytest
from unittest.mock import patch, MagicMock

@pytest.mark.unit
def test_selected_analysts_not_forced_to_include_derivatives(tmp_path):
    """When the caller omits derivatives, it stays omitted."""
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.default_config import DEFAULT_CONFIG

    config = dict(DEFAULT_CONFIG)
    config.update({
        "iic_db_path": str(tmp_path / "iic.db"),
        "iic_data_dir": str(tmp_path / "data"),
        "results_dir": str(tmp_path / "results"),
        "data_cache_dir": str(tmp_path / "cache"),
        "memory_log_path": str(tmp_path / "memory" / "trading_memory.md"),
    })

    # Stub heavy dependencies: we only want to verify selected_analysts
    # is not mutated by the constructor.
    with patch("tradingagents.graph.trading_graph.create_llm_client", return_value=MagicMock()), \
         patch("tradingagents.graph.trading_graph.GraphSetup") as mock_setup:
        mock_setup.return_value.setup_graph.return_value = MagicMock()
        g = TradingAgentsGraph(selected_analysts=["market"], config=config)
        # The constructor should call GraphSetup.setup_graph with the ORIGINAL list.
        called_with = mock_setup.return_value.setup_graph.call_args
        assert "derivatives" not in called_with.kwargs.get("selected_analysts", called_with.args[0])
