import pytest
import pandas as pd
from unittest.mock import patch, MagicMock

from gemini_agent import AdvancedTradingAgent
from gemini_agent.watcher import MarketWatcher
from gemini_agent.agent import main

@pytest.mark.unit
def test_import_advanced_trading_agent():
    """Verify that AdvancedTradingAgent can be successfully imported."""
    assert AdvancedTradingAgent is not None

@pytest.mark.unit
def test_market_watcher_fetch_snapshots():
    """Verify that MarketWatcher works correctly and fetches formatted snapshots."""
    mock_df = pd.DataFrame({
        "Date": [pd.Timestamp("2026-06-15")],
        "Open": [100.0],
        "High": [105.0],
        "Low": [95.0],
        "Close": [102.0],
        "Volume": [1000000.0]
    })
    
    with patch("gemini_agent.watcher.load_ohlcv") as mock_load:
        mock_load.return_value = mock_df
        
        watcher = MarketWatcher(curr_date="2026-06-15")
        snapshots = watcher.fetch_snapshots(["AAPL"])
        
        # Verify that both the target ticker and benchmark are included
        assert "AAPL" in snapshots
        assert "SPY" in snapshots
        
        # Verify structure and values
        for ticker in ["AAPL", "SPY"]:
            assert snapshots[ticker]["open"] == 100.0
            assert snapshots[ticker]["high"] == 105.0
            assert snapshots[ticker]["low"] == 95.0
            assert snapshots[ticker]["close"] == 102.0
            assert snapshots[ticker]["volume"] == 1000000.0
            assert snapshots[ticker]["date"] == "2026-06-15"

@pytest.mark.unit
def test_cli_once_execution():
    """Verify that the CLI runs successfully with the --once flag under standard mocks."""
    mock_df = pd.DataFrame({
        "Date": [pd.Timestamp("2026-06-15")],
        "Open": [100.0],
        "High": [105.0],
        "Low": [95.0],
        "Close": [102.0],
        "Volume": [1000000.0]
    })
    
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = MagicMock(content='["AAPL"]')
    
    mock_graph_instance = MagicMock()
    mock_graph_instance.propagate.return_value = ({"final_trade_decision": "BUY"}, "BUY")
    
    with patch("gemini_agent.agent.create_llm_client") as mock_client, \
         patch("gemini_agent.agent.TradingAgentsGraph") as mock_graph, \
         patch("gemini_agent.watcher.load_ohlcv") as mock_load:
         
        mock_client.return_value.get_llm.return_value = mock_llm
        mock_graph.return_value = mock_graph_instance
        mock_load.return_value = mock_df
        
        # Execute the main entrypoint with `--once` flag
        main(["--once", "--watchlist", "AAPL", "--date", "2026-06-15", "--max-candidates", "1"])
        
        # Verify component interaction
        mock_load.assert_any_call("AAPL", "2026-06-15")
        mock_load.assert_any_call("SPY", "2026-06-15")
        mock_graph_instance.propagate.assert_called_once_with("AAPL", "2026-06-15")
