# Codebase Analysis & Design Report: gemini_agent Structure and Data Fetching

## 1. Analysis of Current Market Data Fetching Mechanisms

Based on the codebase review of `advanced_agent.py` and the `tradingagents/` package, market data and benchmarks are retrieved and managed through the following mechanisms:

### Data Vendors and Routing Layer
- The system is multi-vendor capable, supporting **Yahoo Finance (`yfinance`)** and **Alpha Vantage**.
- A centralized interface routing layer is located at `tradingagents/dataflows/interface.py`. This layer maps method calls to vendor-specific implementations based on configuration files or environment variables.
- The core stock pricing data (OHLCV) is retrieved via `route_to_vendor("get_stock_data", symbol, start_date, end_date)`.
- The vendor implementations reside in `tradingagents/dataflows/y_finance.py` (which directly invokes `yfinance`) and `tradingagents/dataflows/alpha_vantage_stock.py` (which calls Alpha Vantage).

### Caching and Look-Ahead Bias Prevention
- In the file `tradingagents/dataflows/stockstats_utils.py`, the helper function `load_ohlcv(symbol, curr_date)` is used to retrieve historical OHLCV data.
- **Caching Mechanism**: `load_ohlcv` checks a local cache directory (`DEFAULT_CONFIG["data_cache_dir"]`) for cached CSV files named according to the pattern `{safe_symbol}-YFin-data-{start_date}-{end_date}.csv`. If a cache miss occurs, it uses `yfinance` to download 5 years of historical data to today and stores it as a CSV.
- **Look-Ahead Bias Prevention**: Crucially, `load_ohlcv` filters out rows where the `Date` is greater than the provided `curr_date` parameter: `data = data[data["Date"] <= curr_date_dt]`. This ensures that backtesting runs cannot inspect future price data. It also validates that the data is not excessively stale compared to `curr_date`.

### Benchmark Resolution
- The benchmark (defaulting to **SPY** for US-listed tickers) is resolved dynamically in `TradingAgentsGraph._resolve_benchmark` (located in `tradingagents/graph/trading_graph.py`).
- Suffixes of tickers are matched against a benchmark map configuration (e.g., matching `.T` for Tokyo listings to `^N225`).
- The benchmark price data is fetched via `yfinance` in `_fetch_returns` as a baseline index to calculate alpha returns.

---

## 2. Proposed Module Structure for `gemini_agent`

The proposed `gemini_agent/` folder will adapt the orchestrator logic from `advanced_agent.py` into a modular package structure, with the files laid out as follows:

```
gemini_agent/
├── __init__.py
├── agent.py
└── watcher.py
```

### 2.1. `gemini_agent/__init__.py`
This initialization file exposes the core `AdvancedTradingAgent` class to ensure clean imports when packaging or running tests.

```python
from gemini_agent.agent import AdvancedTradingAgent

__all__ = ["AdvancedTradingAgent"]
```

### 2.2. `gemini_agent/watcher.py`
This module contains `MarketWatcher` for fetching daily OHLCV snapshots and the skeleton for `OpportunityScanner` (Milestone 3) for scoring candidates. 
It uses the existing caching layer `load_ohlcv` to keep data fetches efficient and prevent look-ahead bias.

```python
import logging
import pandas as pd
from tradingagents.dataflows.stockstats_utils import load_ohlcv
from tradingagents.dataflows.errors import NoMarketDataError

logger = logging.getLogger(__name__)

class MarketWatcher:
    """
    MarketWatcher fetches current or historical market data snapshots
    for a watchlist of tickers and the benchmark (SPY).
    It leverages load_ohlcv for caching and look-ahead bias protection.
    """
    def __init__(self, config: dict = None):
        self.config = config or {}

    def fetch_snapshots(self, watchlist: list[str], current_date: str = None) -> dict:
        """
        Fetches market data snapshots for tickers in the watchlist and the benchmark (SPY).
        Returns a dictionary mapping ticker symbol to daily OHLCV snapshot data.
        
        Args:
            watchlist (list[str]): List of ticker symbols to watch.
            current_date (str, optional): The reference trading date in YYYY-MM-DD format.
                                          Defaults to today's date if not specified.
        Returns:
            dict: Market data snapshots. Example:
                  {
                      "AAPL": {"date": "2026-06-16", "open": 180.0, "high": 182.0, "low": 179.0, "close": 181.0, "volume": 50000000},
                      "SPY": ...
                  }
        """
        if current_date is None:
            current_date = pd.Timestamp.today().strftime("%Y-%m-%d")

        snapshots = {}
        
        # We always fetch benchmark SPY alongside the watchlist
        symbols_to_fetch = set(watchlist)
        symbols_to_fetch.add("SPY")

        for symbol in symbols_to_fetch:
            try:
                # Use load_ohlcv to leverage the cache and symbol normalization
                df = load_ohlcv(symbol, current_date)
                
                if df.empty:
                    logger.warning(f"No market data available for {symbol} up to {current_date}")
                    continue
                
                # Retrieve the last row representing the current trading day
                last_row = df.iloc[-1]
                
                snapshots[symbol] = {
                    "date": str(last_row["Date"]),
                    "open": float(last_row["Open"]),
                    "high": float(last_row["High"]),
                    "low": float(last_row["Low"]),
                    "close": float(last_row["Close"]),
                    "volume": int(last_row["Volume"])
                }
            except NoMarketDataError as e:
                logger.warning(f"Market data not available for symbol '{symbol}': {e.detail}")
            except Exception as e:
                logger.error(f"Error fetching snapshot for {symbol}: {e}")

        return snapshots


class OpportunityScanner:
    """
    OpportunityScanner filters and ranks watchlist candidates based on
    price dynamics and relative strength vs SPY (implemented in Milestone 3).
    """
    def __init__(self, config: dict = None):
        self.config = config or {}

    def score_candidates(self, snapshots: dict) -> list[dict]:
        """
        Scores each ticker and returns a sorted list of candidates.
        """
        scored = []
        for ticker, snap in snapshots.items():
            if ticker == "SPY":
                continue
            # Scoring stub to be expanded in Milestone 3
            score = 0.0
            scored.append({
                "ticker": ticker,
                "score": score,
                "snapshot": snap
            })
        return sorted(scored, key=lambda x: x["score"], reverse=True)
```

### 2.3. `gemini_agent/agent.py`
This module acts as the orchestrator. It parses CLI parameters and runs a continuous watch loop (`run_watch_loop`) that executes the analysis flow.

```python
import time
import argparse
import logging
from datetime import datetime
from typing import Optional, List
import pandas as pd

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.llm_clients import create_llm_client

from gemini_agent.watcher import MarketWatcher, OpportunityScanner

logger = logging.getLogger(__name__)

class AdvancedTradingAgent:
    """
    AdvancedTradingAgent coordinates the continuous watch loop, opportunity selection,
    deep analysis execution via TradingAgentsGraph, and logging/reporting.
    """
    def __init__(self, config: dict = None):
        self.config = config or DEFAULT_CONFIG.copy()
        
        # Initialize LLM client for custom orchestration
        deep_client = create_llm_client(
            provider=self.config["llm_provider"],
            model=self.config["deep_think_llm"],
            base_url=self.config.get("backend_url"),
        )
        self.llm = deep_client.get_llm()
        
        # Core sub-modules
        self.ta_graph = TradingAgentsGraph(debug=False, config=self.config)
        self.watcher = MarketWatcher(config=self.config)
        self.scanner = OpportunityScanner(config=self.config)

    def analyze_ticker(self, ticker: str, trade_date: str) -> dict:
        """
        Runs deep analysis on a single ticker using the TradingAgentsGraph.
        """
        try:
            final_state, decision = self.ta_graph.propagate(ticker, trade_date)
            return {
                "ticker": ticker,
                "status": "success",
                "decision": final_state.get("final_trade_decision", str(decision)),
                "state": final_state
            }
        except Exception as e:
            logger.error(f"Error analyzing {ticker}: {e}")
            return {
                "ticker": ticker,
                "status": "error",
                "error": str(e)
            }

    def run_single_iteration(self, watchlist: List[str], max_candidates: int, current_date: str = None) -> None:
        """
        Executes a single cycle of the analysis loop:
        1. Fetch market snapshots for watchlist and SPY.
        2. Score candidates.
        3. Select top candidates up to max_candidates.
        4. Execute deep analysis for selected candidates.
        """
        if current_date is None:
            current_date = pd.Timestamp.today().strftime("%Y-%m-%d")

        logger.info(f"=== Starting Cycle on {current_date} ===")
        
        # Step 1: Fetch market snapshots
        snapshots = self.watcher.fetch_snapshots(watchlist, current_date)
        
        # Step 2: Score candidates
        scored_candidates = self.scanner.score_candidates(snapshots)
        
        # Step 3: Select top candidates
        top_candidates = [c["ticker"] for c in scored_candidates[:max_candidates]]
        logger.info(f"Top selected candidates: {top_candidates}")
        
        # Step 4: Perform deep analysis
        results = {}
        for ticker in top_candidates:
            logger.info(f"Running deep analysis for {ticker}...")
            result = self.analyze_ticker(ticker, current_date)
            results[ticker] = result

    def run_watch_loop(self, watchlist: List[str], interval_minutes: int, max_candidates: int, watch: bool = True, current_date: str = None) -> None:
        """
        Orchestrates the execution of the agent, either in a continuous loop (watch=True)
        or as a single run (watch=False).
        """
        if not watch:
            self.run_single_iteration(watchlist, max_candidates, current_date)
            return

        logger.info(f"Starting continuous watch loop. Interval: {interval_minutes} minutes.")
        while True:
            try:
                self.run_single_iteration(watchlist, max_candidates, current_date)
            except Exception as e:
                logger.error(f"Error in watch loop cycle: {e}")
            
            logger.info(f"Sleeping for {interval_minutes} minutes...")
            time.sleep(interval_minutes * 60)
```

---

## 3. Design of CLI Parameter Parsing

To make `gemini_agent/agent.py` executable directly, CLI parameter parsing will support options for running a single analysis or starting a continuous loop.

### 3.1. CLI Specifications
1. `--watch` (boolean): Flag to enable the continuous watch loop. If omitted, the agent will perform a single iteration and exit (which is useful for integration/E2E testing).
2. `--interval-minutes` (integer): Specifies the delay between consecutive iterations of the watch loop (default: `60`).
3. `--watchlist` (string): Comma-separated list of symbols to monitor (e.g. `AAPL,MSFT,TSLA`). Defaults to a core list of tech tickers.
4. `--max-candidates` (integer): Maximum number of top-scored candidates to submit for detailed agent debate/analysis (default: `3`).
5. `--current-date` (string): Standard format date `YYYY-MM-DD` to override the real current date. Highly useful for testing or backtesting.

### 3.2. CLI Parsing Options
We present two implementation strategies matching current codebase styles:

#### Option A: `argparse` Standard Library Implementation (Recommended for standalone execution)
This avoids extra dependencies and is robust for standalone script execution:

```python
def main():
    parser = argparse.ArgumentParser(description="Continuous Trading Analyst MVP")
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Run continuously at specified intervals."
    )
    parser.add_argument(
        "--interval-minutes",
        type=int,
        default=60,
        help="Interval in minutes between watch iterations (default: 60)."
    )
    parser.add_argument(
        "--watchlist",
        type=str,
        default="AAPL,MSFT,TSLA,NVDA,SPY",
        help="Comma-separated list of ticker symbols to monitor."
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=3,
        help="Maximum candidates to analyze per cycle (default: 3)."
    )
    parser.add_argument(
        "--current-date",
        type=str,
        default=None,
        help="Override reference trading date (YYYY-MM-DD) for simulation/backtesting."
    )

    args = parser.parse_args()
    watchlist_list = [t.strip().upper() for t in args.watchlist.split(",") if t.strip()]

    agent = AdvancedTradingAgent()
    agent.run_watch_loop(
        watchlist=watchlist_list,
        interval_minutes=args.interval_minutes,
        max_candidates=args.max_candidates,
        watch=args.watch,
        current_date=args.current_date
    )

if __name__ == "__main__":
    main()
```

#### Option B: `typer` Implementation (Aligning with existing `cli/main.py`)
Since `typer` is already a dependency and is used for the framework's main CLI, registering a command with `typer` is a natural fit:

```python
import typer

app = typer.Typer(help="Continuous Trading Analyst MVP CLI")

@app.command()
def start(
    watch: bool = typer.Option(False, "--watch", help="Run continuously at specified intervals."),
    interval_minutes: int = typer.Option(60, "--interval-minutes", help="Interval in minutes between watch iterations."),
    watchlist: str = typer.Option("AAPL,MSFT,TSLA,NVDA,SPY", "--watchlist", help="Comma-separated list of symbols to monitor."),
    max_candidates: int = typer.Option(3, "--max-candidates", help="Maximum candidates to analyze per cycle."),
    current_date: str = typer.Option(None, "--current-date", help="Override reference trading date (YYYY-MM-DD) for simulation/backtesting.")
):
    watchlist_list = [t.strip().upper() for t in watchlist.split(",") if t.strip()]
    agent = AdvancedTradingAgent()
    agent.run_watch_loop(
        watchlist=watchlist_list,
        interval_minutes=interval_minutes,
        max_candidates=max_candidates,
        watch=watch,
        current_date=current_date
    )

if __name__ == "__main__":
    app()
```
