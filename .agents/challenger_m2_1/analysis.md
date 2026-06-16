# CLI Parameter Parsing & Attribute Merging Analysis

This analysis details the command-line interface (CLI) of the `AdvancedTradingAgent` (located in `gemini_agent/agent.py`), explaining how the parser operates and describing a unit test suite that validates parameter overrides, watchlist normalization, and portfolio fallback logic.

## Overview of CLI Parameter Parsing

The CLI entrypoint is defined in `gemini_agent/agent.py` under the `main(args_list=None)` function. It uses Python's standard `argparse` library to define and parse options.

### Argument Definitions

The parser handles the following options:
*   `--watch`, `-w` (bool): Run in continuous market watching mode.
*   `--interval-minutes`, `-i` (int): Override interval between market checks (minutes).
*   `--watchlist`, `-l` (str): Override watchlist tickers (comma-separated).
*   `--max-candidates`, `-c` (int): Override maximum candidates to analyze per cycle.
*   `--once` (bool): Run the watch loop exactly once and exit (for testing).
*   `--portfolio`, `-p` (str): Path to portfolio JSON state file.
*   `--date`, `-d` (str): Historical date override for backtesting (YYYY-MM-DD).

### Merging Logic

1.  **Configuration Copy**: The `main` function starts by copying `DEFAULT_CONFIG` into a local `config` dictionary.
2.  **CLI Overrides**: It updates this `config` dictionary if options are passed via the command line:
    ```python
    config = DEFAULT_CONFIG.copy()
    if args.interval_minutes is not None:
        config["interval_minutes"] = args.interval_minutes
    if args.watchlist is not None:
        config["watchlist"] = args.watchlist
    if args.max_candidates is not None:
        config["max_candidates"] = args.max_candidates
    if args.date is not None:
        config["date"] = args.date
    ```
3.  **Agent Instantiation**: It instantiates `AdvancedTradingAgent(config=config)`.
4.  **Watchlist Normalization**: Inside `AdvancedTradingAgent.__init__`, the watchlist parameter is normalized to clean up spacing and casing:
    ```python
    watchlist_raw = self.config.get("watchlist", [])
    if isinstance(watchlist_raw, str):
        self.watchlist = [t.strip().upper() for t in watchlist_raw.split(",") if t.strip()]
    else:
        self.watchlist = [str(t).upper() for t in watchlist_raw]
    ```

### Portfolio Fallback Logic

When running in single-date analysis mode (i.e. neither `--watch` nor `--once` is provided), the parser resolves the portfolio state:
1.  **Valid Existing File**: If `--portfolio` is specified and points to a valid, readable JSON file, the JSON is parsed into the `portfolio` dict.
2.  **Invalid or Non-existing File**: If the file does not exist, or if parsing fails (raises a JSONDecodeError / Exception), the CLI prints an error message and falls back to a default hard-coded sample portfolio:
    ```python
    portfolio = {
        "cash_usd": 50000,
        "positions": {"AAPL": 100, "TSLA": 50, "GOOGL": 20},
        "risk_tolerance": "moderate"
    }
    ```

---

## Test Suite Implementation

The test suite is written to `tests/test_challenger_m2_cli.py`. Since we are testing parameter parsing and config merging rather than actual execution, we use `unittest.mock.patch` to stub out external dependencies (API clients, watchers, analyzers, and graph initializations) so that they do not make any network requests or load real files.

### Test Code

```python
"""Test suite verifying AdvancedTradingAgent CLI argument parsing, configuration merging,
and portfolio loading fallback logic under various parameter combinations.
"""

import os
import json
import pytest
from unittest.mock import patch, MagicMock
from gemini_agent.agent import main, AdvancedTradingAgent

@pytest.fixture
def mock_agent_components():
    """Patches all external components of AdvancedTradingAgent to prevent actual network/API activity."""
    with patch("gemini_agent.agent.create_llm_client") as mock_client, \
         patch("gemini_agent.agent.TradingAgentsGraph") as mock_graph, \
         patch("gemini_agent.agent.MarketWatcher") as mock_watcher, \
         patch("gemini_agent.agent.OpportunityScanner") as mock_scanner, \
         patch("gemini_agent.agent.PortfolioMemory") as mock_memory, \
         patch("gemini_agent.agent.RiskGuard") as mock_guard, \
         patch("gemini_agent.agent.ReportWriter") as mock_writer:
        
        # Setup mock LLM returned by client
        mock_llm = MagicMock()
        mock_client.return_value.get_llm.return_value = mock_llm
        
        yield {
            "mock_client": mock_client,
            "mock_graph": mock_graph,
            "mock_watcher": mock_watcher,
            "mock_scanner": mock_scanner,
            "mock_memory": mock_memory,
            "mock_guard": mock_guard,
            "mock_writer": mock_writer,
        }

@pytest.mark.parametrize("watchlist_input, expected_watchlist", [
    (" aapl, msft , NVDA ", ["AAPL", "MSFT", "NVDA"]),
    ("tsla", ["TSLA"]),
    ("   aapl  ,   NVDA   , msft", ["AAPL", "NVDA", "MSFT"]),
    ("AAPL,MSFT", ["AAPL", "MSFT"]),
])
def test_watchlist_normalization_and_overrides(mock_agent_components, watchlist_input, expected_watchlist):
    """Verify that watchlist overrides with varying spaces and casing are correctly parsed and normalized."""
    args = ["--once", "--watchlist", watchlist_input]
    
    with patch.object(AdvancedTradingAgent, "run_watch_loop") as mock_run_loop:
        main(args)
        
        # Ensure run_watch_loop was called
        mock_run_loop.assert_called_once_with(once=True)
        
        # Inspect the agent instance
        agent_instance = mock_run_loop.call_args[0][0]
        assert agent_instance.watchlist == expected_watchlist
        assert agent_instance.config["watchlist"] == watchlist_input

def test_numeric_and_date_overrides(mock_agent_components):
    """Verify that interval-minutes, max-candidates, and date overrides are merged into config."""
    args = [
        "--once",
        "--interval-minutes", "15",
        "--max-candidates", "5",
        "--date", "2024-06-15"
    ]
    
    with patch.object(AdvancedTradingAgent, "run_watch_loop") as mock_run_loop:
        main(args)
        
        mock_run_loop.assert_called_once_with(once=True)
        agent_instance = mock_run_loop.call_args[0][0]
        
        assert agent_instance.config["interval_minutes"] == 15
        assert agent_instance.config["max_candidates"] == 5
        assert agent_instance.config["date"] == "2024-06-15"

def test_portfolio_existing_file(mock_agent_components, tmp_path):
    """Verify that a valid custom portfolio file is successfully loaded and used."""
    portfolio_data = {
        "cash_usd": 12345,
        "positions": {"MSFT": 10},
        "risk_tolerance": "conservative"
    }
    portfolio_file = tmp_path / "custom_portfolio.json"
    portfolio_file.write_text(json.dumps(portfolio_data))
    
    args = ["--portfolio", str(portfolio_file), "--date", "2024-05-12"]
    
    with patch.object(AdvancedTradingAgent, "run") as mock_run:
        main(args)
        
        mock_run.assert_called_once()
        # Verify self (first arg) is an AdvancedTradingAgent
        agent_instance = mock_run.call_args[0][0]
        assert isinstance(agent_instance, AdvancedTradingAgent)
        
        # Verify portfolio argument (second arg) matches custom portfolio data
        passed_portfolio = mock_run.call_args[0][1]
        assert passed_portfolio == portfolio_data
        
        # Verify trade_date argument (third arg) matches the date argument
        passed_date = mock_run.call_args[0][2]
        assert passed_date == "2024-05-12"

def test_portfolio_non_existing_file(mock_agent_components):
    """Verify that a non-existing portfolio file causes fallback to the sample portfolio."""
    non_existing_file = "non_existent_portfolio_file_xyz.json"
    assert not os.path.exists(non_existing_file)
    
    args = ["--portfolio", non_existing_file, "--date", "2024-05-12"]
    
    expected_fallback = {
        "cash_usd": 50000,
        "positions": {"AAPL": 100, "TSLA": 50, "GOOGL": 20},
        "risk_tolerance": "moderate"
    }
    
    with patch.object(AdvancedTradingAgent, "run") as mock_run:
        main(args)
        
        mock_run.assert_called_once()
        passed_portfolio = mock_run.call_args[0][1]
        assert passed_portfolio == expected_fallback
        
        passed_date = mock_run.call_args[0][2]
        assert passed_date == "2024-05-12"

def test_portfolio_invalid_json_file(mock_agent_components, tmp_path):
    """Verify that an existing portfolio file with invalid JSON falls back to the sample portfolio."""
    portfolio_file = tmp_path / "invalid_portfolio.json"
    portfolio_file.write_text("this is not { valid json } data")
    
    args = ["--portfolio", str(portfolio_file), "--date", "2024-05-12"]
    
    expected_fallback = {
        "cash_usd": 50000,
        "positions": {"AAPL": 100, "TSLA": 50, "GOOGL": 20},
        "risk_tolerance": "moderate"
    }
    
    with patch.object(AdvancedTradingAgent, "run") as mock_run:
        main(args)
        
        mock_run.assert_called_once()
        passed_portfolio = mock_run.call_args[0][1]
        assert passed_portfolio == expected_fallback
        
        passed_date = mock_run.call_args[0][2]
        assert passed_date == "2024-05-12"
```

## Stress / Adversarial Review Findings

### 1. Watchlist String Formatting
If the user passes `--watchlist` as an empty string, i.e., `""` or `"  "`, `split(",")` will return a list containing an empty string. The expression `if t.strip()` filters this out:
```python
self.watchlist = [t.strip().upper() for t in watchlist_raw.split(",") if t.strip()]
```
As a result, `self.watchlist` will evaluate to an empty list `[]`. 
*   **Risk**: An empty watchlist will cause downstream errors in `MarketWatcher.fetch_snapshots` since no tickers will be resolved or fetched.
*   **Mitigation**: The CLI should raise a parsing error if `--watchlist` results in an empty list.

### 2. Portfolio Parsing Exceptions
If `args.portfolio` is provided but parsing fails due to an invalid JSON structure, the CLI prints the exception but continues execution using the fallback portfolio.
*   **Risk**: If this occurs in an automated workflow, the agent will silently default to the mock moderate portfolio, possibly executing unauthorized trades or backtests on incorrect holdings.
*   **Mitigation**: Instead of silently falling back when the user explicitly provides `--portfolio`, the CLI should terminate execution and exit with a non-zero exit status to indicate a configuration failure.
