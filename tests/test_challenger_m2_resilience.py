import pytest
from unittest.mock import patch, MagicMock
import os
import json
import pandas as pd

from tradingagents.dataflows.symbol_utils import NoMarketDataError
from gemini_agent.watcher import MarketWatcher
from gemini_agent.agent import AdvancedTradingAgent


@pytest.mark.unit
def test_market_watcher_empty_watchlist():
    """Verify that MarketWatcher fetches the benchmark ticker snapshot when the watchlist is empty."""
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
        snapshots = watcher.fetch_snapshots([])
        
        # Verify only SPY benchmark is fetched
        assert "SPY" in snapshots
        assert len(snapshots) == 1
        assert snapshots["SPY"]["close"] == 102.0
        assert snapshots["SPY"]["date"] == "2026-06-15"
        mock_load.assert_called_once_with("SPY", "2026-06-15")


@pytest.mark.unit
def test_market_watcher_error_resilience():
    """Verify MarketWatcher behavior when some tickers throw NoMarketDataError or generic Exception.
    It should still fetch snapshots for other tickers and the benchmark.
    """
    mock_df_aapl = pd.DataFrame({
        "Date": [pd.Timestamp("2026-06-15")],
        "Open": [150.0],
        "High": [155.0],
        "Low": [148.0],
        "Close": [152.0],
        "Volume": [2000000.0]
    })
    mock_df_spy = pd.DataFrame({
        "Date": [pd.Timestamp("2026-06-15")],
        "Open": [400.0],
        "High": [405.0],
        "Low": [398.0],
        "Close": [402.0],
        "Volume": [5000000.0]
    })
    
    def side_effect(ticker, date):
        if ticker == "AAPL":
            return mock_df_aapl
        elif ticker == "SPY":
            return mock_df_spy
        elif ticker == "MSFT":
            raise NoMarketDataError("No market data for MSFT")
        else:
            raise ValueError("Unexpected error for TSLA")
            
    with patch("gemini_agent.watcher.load_ohlcv", side_effect=side_effect) as mock_load:
        watcher = MarketWatcher(curr_date="2026-06-15")
        snapshots = watcher.fetch_snapshots(["AAPL", "MSFT", "TSLA"])
        
        # Verify AAPL and SPY snapshots are returned
        assert "AAPL" in snapshots
        assert "SPY" in snapshots
        # Verify failing tickers are not in snapshots
        assert "MSFT" not in snapshots
        assert "TSLA" not in snapshots
        
        assert snapshots["AAPL"]["close"] == 152.0
        assert snapshots["SPY"]["close"] == 402.0
        assert len(snapshots) == 2


@pytest.mark.unit
def test_event_loop_ticker_propagation_exception(tmp_path):
    """Verify event loop behavior when one ticker's graph propagation throws a severe exception.
    It should isolate the error, log the failure, update portfolio memory for other tickers, and proceed.
    """
    config = {
        "project_dir": str(tmp_path),
        "results_dir": str(tmp_path / "logs"),
        "llm_provider": "mock",
        "deep_think_llm": "mock-think",
        "watchlist": ["AAPL", "MSFT"],
        "max_candidates": 2,
        "interval_minutes": 1,
        "benchmark_ticker": "SPY"
    }
    
    mock_df = pd.DataFrame({
        "Date": [pd.Timestamp("2026-06-15")],
        "Open": [100.0],
        "High": [105.0],
        "Low": [95.0],
        "Close": [102.0],
        "Volume": [1000000.0]
    })
    
    # We will mock the opportunity scanner to return AAPL and MSFT
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = MagicMock(content='["AAPL"]')
    
    # Propagate mock: AAPL throws a severe exception, MSFT succeeds
    mock_graph_instance = MagicMock()
    def propagate_side_effect(ticker, date):
        if ticker == "AAPL":
            raise RuntimeError("Severe Graph Error for AAPL")
        return ({"final_trade_decision": "BUY"}, "BUY")
    mock_graph_instance.propagate.side_effect = propagate_side_effect

    with patch("gemini_agent.agent.create_llm_client") as mock_client, \
         patch("gemini_agent.agent.TradingAgentsGraph", return_value=mock_graph_instance), \
         patch("gemini_agent.watcher.load_ohlcv", return_value=mock_df):
         
        mock_client.return_value.get_llm.return_value = mock_llm
        
        agent = AdvancedTradingAgent(config=config)
        
        # Run loop once
        agent.run_watch_loop(once=True)
        
        # Verify that AAPL threw an error but MSFT succeeded and updated portfolio memory
        portfolio_state = agent.portfolio_memory.load_memory()
        
        # AAPL decision should NOT be in past_decisions, MSFT should be
        decisions = portfolio_state["past_decisions"]
        assert len(decisions) == 1
        assert decisions[0]["ticker"] == "MSFT"
        assert decisions[0]["decision"] == "BUY"
        
        # Check event logs for failure on AAPL and success on MSFT
        event_logs_path = os.path.join(agent.report_writer.reports_dir, "event_logs.jsonl")
        assert os.path.exists(event_logs_path)
        
        with open(event_logs_path, "r") as f:
            logs = [json.loads(line) for line in f if line.strip()]
            
        # We expect a "ticker_analysis_failed" event for AAPL
        failed_events = [e for e in logs if e["event_type"] == "ticker_analysis_failed"]
        assert len(failed_events) == 1
        assert failed_events[0]["data"]["ticker"] == "AAPL"
        assert "Severe Graph Error for AAPL" in failed_events[0]["data"]["error"]
        
        # We expect a "ticker_analysis_success" event for MSFT
        success_events = [e for e in logs if e["event_type"] == "ticker_analysis_success"]
        assert len(success_events) == 1
        assert success_events[0]["data"]["ticker"] == "MSFT"
        assert success_events[0]["data"]["decision"] == "BUY"


@pytest.mark.unit
def test_event_loop_cycle_level_exception(tmp_path):
    """Verify event loop behavior when a cycle-level exception is thrown.
    It should log the cycle failure and continue to the next cycle.
    """
    config = {
        "project_dir": str(tmp_path),
        "results_dir": str(tmp_path / "logs"),
        "llm_provider": "mock",
        "deep_think_llm": "mock-think",
        "watchlist": ["AAPL"],
        "max_candidates": 1,
        "interval_minutes": 1,
        "benchmark_ticker": "SPY"
    }
    
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
    
    # We will simulate multiple cycles by having once = False.
    # 1st cycle: fetch_snapshots throws a cycle-level ValueError.
    # 2nd cycle: fetch_snapshots succeeds.
    # 3rd cycle: fetch_snapshots raises KeyboardInterrupt to exit the loop gracefully.
    cycle_counter = 0
    def fetch_snapshots_side_effect(watchlist, curr_date=None):
        nonlocal cycle_counter
        cycle_counter += 1
        if cycle_counter == 1:
            raise ValueError("Database cycle failure simulation")
        elif cycle_counter == 2:
            return {
                "AAPL": {"open": 100.0, "high": 105.0, "low": 95.0, "close": 102.0, "volume": 1000000.0, "date": "2026-06-15"},
                "SPY": {"open": 100.0, "high": 105.0, "low": 95.0, "close": 102.0, "volume": 1000000.0, "date": "2026-06-15"}
            }
        else:
            raise KeyboardInterrupt()

    with patch("gemini_agent.agent.create_llm_client") as mock_client, \
         patch("gemini_agent.agent.TradingAgentsGraph", return_value=mock_graph_instance), \
         patch("gemini_agent.watcher.load_ohlcv", return_value=mock_df), \
         patch("time.sleep") as mock_sleep: # mock sleep to avoid waiting
         
        mock_client.return_value.get_llm.return_value = mock_llm
        
        agent = AdvancedTradingAgent(config=config)
        agent.market_watcher.fetch_snapshots = fetch_snapshots_side_effect
        
        # Run loop with once = False
        agent.run_watch_loop(once=False)
        
        # Verify cycle_counter is 3
        assert cycle_counter == 3
        
        # Check event logs
        event_logs_path = os.path.join(agent.report_writer.reports_dir, "event_logs.jsonl")
        assert os.path.exists(event_logs_path)
        
        with open(event_logs_path, "r") as f:
            logs = [json.loads(line) for line in f if line.strip()]
            
        # Cycle 1 failure logged
        cycle_failed_events = [e for e in logs if e["event_type"] == "cycle_failed"]
        assert len(cycle_failed_events) == 1
        assert "Database cycle failure simulation" in cycle_failed_events[0]["data"]["error"]
        
        # Cycle 2 success logged
        success_events = [e for e in logs if e["event_type"] == "ticker_analysis_success"]
        assert len(success_events) == 1
        assert success_events[0]["data"]["ticker"] == "AAPL"
        
        # Loop termination logged
        terminated_events = [e for e in logs if e["event_type"] == "loop_terminated"]
        assert len(terminated_events) == 1
        assert terminated_events[0]["data"]["reason"] == "KeyboardInterrupt"
