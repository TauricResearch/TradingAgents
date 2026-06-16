# Analysis: Continuous Watch Loop Structure in gemini_agent/agent.py

## Summary of Core Findings
The continuous watch loop (`run_watch_loop`) in `gemini_agent/agent.py` should be designed as a robust, synchronous event loop that fetches market data via `MarketWatcher`, ranks opportunities via `OpportunityScanner`, performs deep analyses via `TradingAgentsGraph`, and evaluates risk via `RiskGuard`. The loop must feature anti-drift sleeping, granular ticker-level exception isolation, and integration with `DEFAULT_CONFIG` and environment overrides alongside a `--once` CLI testing flag to enable automated dry-runs.

---

## 1. Context & Architecture Overview

Based on `PROJECT.md` and the modularization scope, the proposed `gemini_agent/agent.py` will encapsulate the `AdvancedTradingAgent` class. This class is designed to run continuous or single-cycle market observation runs, acting as the orchestrator for all other agent modules.

```
                    +--------------------------------+
                    |      AdvancedTradingAgent      |
                    |       (run_watch_loop)         |
                    +---------------+----------------+
                                    |
           +------------------------+------------------------+
           |                        |                        |
           v                        v                        v
  +-----------------+      +-----------------+      +-----------------+
  |  MarketWatcher  |      | PortfolioMemory |      |  ReportWriter   |
  +--------+--------+      +--------+--------+      +--------+--------+
           |                        |                        |
           v                        v                        v
  +-----------------+      +-----------------+      +-----------------+
  | OpportunityScan |      |    RiskGuard    |      |  daily_summary  |
  +-----------------+      +-----------------+      +-----------------+
```

### Key Modular Dependencies

| Dependency | Module | Responsibilities | Source Reference / Contract |
|---|---|---|---|
| `TradingAgentsGraph` | `tradingagents.graph` | Deep analysis graph engine | `tradingagents/graph/trading_graph.py:46` |
| `MarketWatcher` | `gemini_agent.watcher` | Fetch daily OHLCV & volume for watchlist and SPY | `PROJECT.md:43` |
| `OpportunityScanner` | `gemini_agent.watcher` | Score candidates relative to SPY | `PROJECT.md:46` |
| `PortfolioMemory` | `gemini_agent.memory` | Read/Write portfolio snapshots, track paper trades ($10K) | `PROJECT.md:49` |
| `RiskGuard` | `gemini_agent.memory` | Enforce risk rules (assess risk status: `safe`, `risky`, etc.) | `PROJECT.md:55` |
| `ReportWriter` | `gemini_agent.reporter` | Write log events (.jsonl) and update `daily_summary.md` | `PROJECT.md:58` |

---

## 2. Deep Dive: `run_watch_loop` Design

The continuous watch loop is the central orchestration engine. It must satisfy strict production constraints: liveness, exception tolerance, minimal drift, and graceful shut down.

### A. Anti-Drift Sleep Architecture
Trading analysis tasks using deep LLM reasoning graphs (like `TradingAgentsGraph`) are computationally heavy and high-latency, often taking 1 to 5 minutes to propagate for a single ticker. If the loop slept for a fixed duration (`time.sleep(interval)`), the actual execution time would drift significantly (e.g. if analysis takes 4 minutes and interval is 60 minutes, the next cycle runs after 64 minutes).

To address this:
1. **Dynamic Sleep Calculation**: Calculate the remaining interval based on the iteration start time:
   $$\text{sleep\_time} = \max(0, \text{interval\_seconds} - (\text{time.time()} - \text{start\_time}))$$
2. **KeyboardInterrupt Liveness**: Instead of sleeping for the entire duration in a single `time.sleep()` call (which makes the CLI unresponsive to `Ctrl+C`), sleep in small increments (e.g., $1.0$ second) inside a loop check.

### B. Two-Tier Exception Handling
We propose a nested `try...except` structure to prevent loop crashes:
1. **Ticker-Level Exception Handling (Inner)**: If a specific stock fails during propagation in `ta_graph.propagate(...)` or during `RiskGuard` analysis, this failure must be caught, logged, and reported via `ReportWriter`, and the loop must move on to the next ticker candidate. One failed ticker must not halt the cycle.
2. **Cycle-Level Exception Handling (Outer)**: If data fetching or opportunity scanning fails entirely (e.g., due to an API breakdown or internet disconnect), the exception must be logged, and the loop must proceed to wait for the next scheduled interval.

### C. MarketWatcher and Execution Flow
The watch loop cycle logic runs as follows:
1. **Fetch**: `MarketWatcher.fetch_snapshots(watchlist)` obtains daily market prices.
2. **Filter & Score**: `OpportunityScanner.score_candidates(snapshots)` evaluates candidate tickers against benchmarks. The top $N$ candidates (limited by `max_candidates` configuration) are selected.
3. **Analyze**: For each candidate:
   - Load the portfolio simulation memory from `PortfolioMemory.load_memory()`.
   - Run the graph: `TradingAgentsGraph.propagate(ticker, trade_date)`.
   - Perform safety screenings: `RiskGuard.assess_risk(ticker, portfolio)`.
   - Execute paper transactions in the simulator: `PortfolioMemory.update_portfolio(decision)`.
   - Log the outcome: `ReportWriter.log_event("analysis_completed", data)`.
4. **Evaluate & Summarize**: Run `PortfolioMemory.review_performance()` on older decisions and write the consolidated daily report `daily_summary.md` using `ReportWriter`.

---

## 3. Configuration & Environment Integration

The watch loop requires new configuration parameters added to the framework's configuration pipeline. 

### Proposed Config Changes in `tradingagents/default_config.py`
We should extend `DEFAULT_CONFIG` and `_ENV_OVERRIDES` to support watch mode seamlessly.

#### 1. Configuration Keys (Defaults)
```python
# To be added to default dictionary (tradingagents/default_config.py:45)
"watch": False,                # Enable/disable watch loop
"interval_minutes": 60,        # Sleep interval between runs
"watchlist": ["AAPL", "MSFT", "NVDA", "TSLA", "SPY"],  # Default watch list
"max_candidates": 3,           # Max candidates to run deep analysis on per cycle
```

#### 2. Environment Overrides
To expose these parameters to `.env` file configurations without modifying the execution code:
```python
# Add to _ENV_OVERRIDES (tradingagents/default_config.py:10)
"TRADINGAGENTS_WATCH": "watch",
"TRADINGAGENTS_INTERVAL_MINUTES": "interval_minutes",
"TRADINGAGENTS_WATCHLIST": "watchlist",
"TRADINGAGENTS_MAX_CANDIDATES": "max_candidates",
```

#### 3. Watchlist Coercion
Since environment variables provide watchlist as a comma-separated string, the class constructor must normalize the config value:
```python
watchlist = self.config.get("watchlist", [])
if isinstance(watchlist, str):
    self.watchlist = [t.strip().upper() for t in watchlist.split(",") if t.strip()]
else:
    self.watchlist = [t.upper() for t in watchlist]
```

---

## 4. CLI Execution & Testability

### CLI Flags & Arguments
The entrypoint script `gemini_agent/agent.py` must support the following arguments to make it easily runnable:

*   `--watch` / `-w` (flag): Run in continuous loop mode.
*   `--interval-minutes` / `-i` (int, default: 60): Frequency of loop iterations.
*   `--watchlist` / `-l` (str): Comma-separated list of symbols (overrides config).
*   `--max-candidates` / `-c` (int, default: 3): Cap on candidates evaluated per run.
*   `--once` / `--dry-run` (flag): **Crucial for CLI Testing**. Run the loop exactly once and exit immediately without sleeping.
*   `--portfolio` / `-p` (str): Path to JSON file defining initial custom portfolio (starting balance, risk tolerance, etc.).
*   `--date` / `-d` (str): Backtest date override (defaults to current date).

### Standard CLI Invocation Examples

1. **Continuous Watch Execution**:
   ```bash
   python -m gemini_agent.agent --watch --interval-minutes 30 --watchlist AAPL,TSLA,NVDA,SPY
   ```
2. **Testing / E2E Verification Run (Single Cycle)**:
   ```bash
   python -m gemini_agent.agent --watchlist AAPL,SPY --max-candidates 1 --once
   ```

---

## 5. Proposed Design Sketch (Pseudo-Code)

Below is the proposed implementation logic for `gemini_agent/agent.py`. It is styled as a complete implementation outline for the developer:

```python
# gemini_agent/agent.py
import time
import argparse
import json
import logging
from datetime import datetime

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

# These imports will be implemented in their respective modules
from gemini_agent.watcher import MarketWatcher, OpportunityScanner
from gemini_agent.memory import PortfolioMemory, RiskGuard
from gemini_agent.reporter import ReportWriter

logger = logging.getLogger("AdvancedTradingAgent")

class AdvancedTradingAgent:
    def __init__(self, config=None):
        self.config = config or DEFAULT_CONFIG.copy()
        
        # Initialize Core Graph Engine
        self.ta_graph = TradingAgentsGraph(debug=False, config=self.config)
        
        # Initialize Modular Components (defined in Milestone Contracts)
        self.market_watcher = MarketWatcher(config=self.config)
        self.opportunity_scanner = OpportunityScanner(config=self.config)
        self.portfolio_memory = PortfolioMemory(config=self.config)
        self.risk_guard = RiskGuard(config=self.config)
        self.report_writer = ReportWriter(config=self.config)
        
        # Normalize watchlist
        watchlist_raw = self.config.get("watchlist", [])
        if isinstance(watchlist_raw, str):
            self.watchlist = [t.strip().upper() for t in watchlist_raw.split(",") if t.strip()]
        else:
            self.watchlist = [str(t).upper() for t in watchlist_raw]

    def run(self, portfolio: dict, trade_date: str = None):
        """
        Original single-run execution logic matching advanced_agent.py:45.
        Included for full backward compatibility.
        """
        if trade_date is None:
            trade_date = datetime.now().strftime("%Y-%m-%d")
        # Logic follows advanced_agent.py (select_top_stocks, propagate, etc.)
        # ...
        pass

    def run_watch_loop(self, once: bool = False):
        """
        Continuous Watch Loop. 
        Fetches market snapshot -> Scores opportunities -> Runs Deep Analysis -> Enforces RiskGuard -> Logs events.
        """
        interval_seconds = int(self.config.get("interval_minutes", 60)) * 60
        max_candidates = int(self.config.get("max_candidates", 3))
        
        print(f"Starting Watch Loop. Interval: {self.config.get('interval_minutes')} min. Watchlist: {self.watchlist}")
        self.report_writer.log_event("loop_started", {"watchlist": self.watchlist, "interval_minutes": self.config.get("interval_minutes")})
        
        while True:
            start_time = time.time()
            trade_date = datetime.now().strftime("%Y-%m-%d")
            
            try:
                print(f"[{datetime.now().isoformat()}] Fetching market snapshots...")
                # 1. Fetch market data
                snapshots = self.market_watcher.fetch_snapshots(self.watchlist)
                
                # 2. Score candidates
                scored_candidates = self.opportunity_scanner.score_candidates(snapshots)
                top_candidates = [item["ticker"] for item in scored_candidates[:max_candidates]]
                
                print(f"Selected candidates for analysis: {top_candidates}")
                self.report_writer.log_event("opportunities_scanned", {"candidates": scored_candidates, "top": top_candidates})
                
                # 3. Analyze each candidate
                for ticker in top_candidates:
                    try:
                        print(f"Analyzing {ticker}...")
                        portfolio = self.portfolio_memory.load_memory()
                        
                        # Execute graph
                        final_state, decision = self.ta_graph.propagate(ticker, trade_date)
                        
                        # Assess risk
                        risk_status = self.risk_guard.assess_risk(ticker, portfolio)
                        
                        # Commit to memory and process portfolio changes
                        decision_record = {
                            "ticker": ticker,
                            "date": trade_date,
                            "decision": str(decision),
                            "risk_status": risk_status,
                            "price": snapshots.get(ticker, {}).get("close")
                        }
                        self.portfolio_memory.update_portfolio(decision_record)
                        
                        self.report_writer.log_event("ticker_analysis_success", decision_record)
                        print(f"Analysis for {ticker} complete: Decision = {decision_record['decision']} ({risk_status})")
                        
                    except Exception as ticker_err:
                        # Fail-safe: Ticker failure does not crash the loop
                        error_msg = f"Failed to analyze {ticker}: {ticker_err}"
                        logger.error(error_msg, exc_info=True)
                        self.report_writer.log_event("ticker_analysis_failed", {"ticker": ticker, "error": str(ticker_err)})
                
                # 4. Perform Performance Review and generate Daily Summary
                performance_metrics = self.portfolio_memory.review_performance()
                self.report_writer.log_event("performance_reviewed", performance_metrics)
                
                summary_path = self.report_writer.generate_daily_summary()
                print(f"Cycle finished. Summary report updated at {summary_path}")
                
            except Exception as cycle_err:
                # Fail-safe: Cycle/network failure does not crash the loop
                error_msg = f"Watch loop cycle error: {cycle_err}"
                logger.error(error_msg, exc_info=True)
                self.report_writer.log_event("cycle_failed", {"error": str(cycle_err)})
            
            if once:
                print("Once/Dry-Run flag detected. Exiting loop.")
                break
                
            # Sleep calculation (anti-drift)
            elapsed = time.time() - start_time
            sleep_time = max(0.0, interval_seconds - elapsed)
            print(f"Cycle execution time: {elapsed:.2f}s. Sleeping for {sleep_time:.2f}s...")
            
            # Sub-second increment sleep for KeyboardInterrupt responsiveness
            try:
                sleep_remaining = sleep_time
                while sleep_remaining > 0:
                    time.sleep(min(1.0, sleep_remaining))
                    sleep_remaining -= 1.0
            except KeyboardInterrupt:
                print("\nKeyboardInterrupt detected. Shutting down gracefully...")
                self.report_writer.log_event("loop_terminated", {"reason": "KeyboardInterrupt"})
                break

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Autonomous Continuous Trading Analyst CLI")
    parser.add_argument("--watch", "-w", action="store_true", help="Run in continuous market watching mode")
    parser.add_argument("--interval-minutes", "-i", type=int, help="Override interval between market checks (minutes)")
    parser.add_argument("--watchlist", "-l", type=str, help="Override watchlist tickers (comma-separated)")
    parser.add_argument("--max-candidates", "-c", type=int, help="Override maximum candidates to analyze per cycle")
    parser.add_argument("--once", action="store_true", help="Run the watch loop exactly once and exit (for testing)")
    parser.add_argument("--portfolio", "-p", type=str, help="Path to portfolio JSON state file")
    parser.add_argument("--date", "-d", type=str, help="Historical date override for backtesting (YYYY-MM-DD)")
    
    args = parser.parse_args()
    
    # Load config and override values based on CLI inputs
    config = DEFAULT_CONFIG.copy()
    if args.interval_minutes:
        config["interval_minutes"] = args.interval_minutes
    if args.watchlist:
        config["watchlist"] = args.watchlist
    if args.max_candidates:
        config["max_candidates"] = args.max_candidates
        
    agent = AdvancedTradingAgent(config=config)
    
    if args.watch or args.once:
        agent.run_watch_loop(once=args.once)
    else:
        # Fallback path (runs standard portfolio-selection mode)
        # Load portfolio configuration
        if args.portfolio:
            with open(args.portfolio, "r") as f:
                portfolio = json.load(f)
        else:
            # Sample fallback portfolio from advanced_agent.py
            portfolio = {
                "cash_usd": 50000,
                "positions": {"AAPL": 100, "TSLA": 50, "GOOGL": 20},
                "risk_tolerance": "moderate"
            }
        agent.run(portfolio, trade_date=args.date)
```

---

## 6. Verification and Testing Plan

To ensure the watcher loop functions correctly, verification should be performed using pytest and manual run triggers:

### E2E Testing using the `--once` CLI option
Since wait times for continuous loops are impractical during standard test runs, test suites should invoke the agent with `--once`. This tests the full execution sequence and returns a status code without stalling.
```python
# Proposed Test Case inside tests/test_watch_loop.py
import pytest
from unittest.mock import MagicMock
from gemini_agent.agent import AdvancedTradingAgent

@pytest.mark.unit
def test_watch_loop_once_execution(monkeypatch):
    # Mock MarketWatcher, OpportunityScanner, PortfolioMemory, RiskGuard, ReportWriter
    mock_watcher = MagicMock()
    mock_watcher.fetch_snapshots.return_value = {
        "AAPL": {"close": 150.0}, "SPY": {"close": 400.0}
    }
    
    mock_scanner = MagicMock()
    mock_scanner.score_candidates.return_value = [{"ticker": "AAPL", "score": 8.0}]
    
    mock_memory = MagicMock()
    mock_memory.load_memory.return_value = {"cash_usd": 10000, "positions": {}}
    
    mock_reporter = MagicMock()
    
    # Instantiate agent with mock configs
    agent = AdvancedTradingAgent(config={
        "watchlist": "AAPL,SPY", "max_candidates": 1, "interval_minutes": 1
    })
    
    # Inject mocks
    agent.market_watcher = mock_watcher
    agent.opportunity_scanner = mock_scanner
    agent.portfolio_memory = mock_memory
    agent.report_writer = mock_reporter
    
    # Mock core graph propagation
    agent.ta_graph = MagicMock()
    agent.ta_graph.propagate.return_value = ({"final_trade_decision": "BUY"}, "BUY")
    
    # Execute loop once
    agent.run_watch_loop(once=True)
    
    # Verify call sequence
    mock_watcher.fetch_snapshots.assert_called_once()
    mock_scanner.score_candidates.assert_called_once()
    agent.ta_graph.propagate.assert_called_once_with("AAPL", pytest.anystr)
    mock_memory.update_portfolio.assert_called_once()
    mock_reporter.generate_daily_summary.assert_called_once()
```
