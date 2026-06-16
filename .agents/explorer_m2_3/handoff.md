# Handoff Report: Continuous Watch Loop Analysis

## 1. Observation

We directly observed and analyzed the following files in the repository `/home/patryk/Dokumenty/trading_ai/TradingAgents/`:
*   **`advanced_agent.py`**: The original agent implementation. Line 9 defines `class AdvancedTradingAgent`. Lines 45-120 define the `run(self, portfolio: dict, trade_date: str = None)` function, which executes a synchronous selection and propagation loop for stock analysis.
*   **`tradingagents/default_config.py`**: The default configuration definition. Line 45 defines `DEFAULT_CONFIG = _apply_env_overrides({...})`. Line 10 defines `_ENV_OVERRIDES` which maps environment variables to configuration keys.
*   **`tradingagents/graph/trading_graph.py`**: The main langgraph orchestrator class `TradingAgentsGraph` is defined on line 46, and its `propagate` method is defined on lines 321-360.
*   **`cli/main.py`**: A Typer-based CLI. Lines 1317-1335 define the `analyze` command.
*   **`PROJECT.md`**: Defines the package architecture. It references `gemini_agent/agent.py` as containing `AdvancedTradingAgent` with `--watch` loop.

We confirmed that the module directory `gemini_agent/` and its sub-modules do not yet exist, which matches the decomposition strategy where Milestone 2 (CLI & Core Watcher) has not been implemented.

---

## 2. Logic Chain

1. **Orchestrator Role of `agent.py`**: According to the system layout in `PROJECT.md:13-30` and `PROJECT.md:65`, the `AdvancedTradingAgent` in `gemini_agent/agent.py` is the top-level class that drives the continuous watch loop (`run_watch_loop`).
2. **Loop Resilience**: Because LLM reasoning latency is high (typically 1-5 minutes per stock in the `TradingAgentsGraph`), standard fixed-interval sleeps would cause progressive loop drift. Therefore, we calculated that dynamic sleep (the difference between the target interval and the elapsed execution time) is required to keep cycle times consistent.
3. **Graceful CLI Interrupts**: Standard `time.sleep(X)` for long intervals (e.g., 60 minutes) blocks terminal interrupt handling. By implementing a loop that sleeps in short increments (e.g., 1 second) and checks a loop condition, we ensure the agent reacts instantly to `KeyboardInterrupt` / `SIGINT`.
4. **Resiliency to Failures**: Real-time APIs and LLM services are prone to rate limits, network outages, and parse errors. Thus, we concluded that a two-tier try-except structure is necessary: a ticker-level try-except (to isolate failures to a single asset and proceed with the remaining candidates) and a cycle-level try-except (to log general API failures and continue to the next scheduled interval).
5. **Config & Env-Var Mapping**: The configuration module `tradingagents/default_config.py` overrides default dictionary keys using matching `TRADINGAGENTS_*` prefix variables. Extending this mapping ensures configuration parameters for watch mode can be set globally in the environment or overridden at the CLI.
6. **E2E CLI Testability**: Infinite loops are notoriously difficult to test using automated runner tools. Introducing a `--once` / `--dry-run` flag allows tests to invoke `run_watch_loop`, execute exactly one full cycle of data fetching, scanning, and graph propagation, and then exit immediately with status codes.

---

## 3. Caveats

*   **Mock Dependencies**: The modular components (`MarketWatcher`, `OpportunityScanner`, `PortfolioMemory`, `RiskGuard`, and `ReportWriter`) are planned under separate Milestone tasks (M2, M3, M4). When testing `run_watch_loop` before those milestones are implemented, developers must mock these dependencies.
*   **API Rate Limits**: Frequent runs with short intervals (e.g. `--interval-minutes 1`) risk triggering IP bans or rate limit blocks from data providers (e.g., yfinance) and LLM endpoints. It is assumed the user will run testing modes with minimal mock datasets.

---

## 4. Conclusion

The design of `run_watch_loop` must be placed in `gemini_agent/agent.py` inside the `AdvancedTradingAgent` class. It should implement an anti-drift, KeyboardInterrupt-responsive `while` loop that calls modular methods sequentially:
1. `MarketWatcher.fetch_snapshots`
2. `OpportunityScanner.score_candidates`
3. Ticker-level isolated iteration of `ta_graph.propagate` and `RiskGuard.assess_risk`
4. `PortfolioMemory.update_portfolio` and `PortfolioMemory.review_performance`
5. `ReportWriter.generate_daily_summary`

The CLI in `gemini_agent/agent.py` must support `--watch`, `--interval-minutes`, `--watchlist`, `--max-candidates`, and `--once` to satisfy all testing and runtime specifications.

---

## 5. Verification Method

To independently verify the loop design and structure:
1. Inspect the written analysis report at:
   `/home/patryk/Dokumenty/trading_ai/TradingAgents/.agents/explorer_m2_3/analysis.md`
2. Inspect the proposed CLI arguments parser and class logic.
3. Validate that standard configuration integration guidelines in `analysis.md` match the interface structure in `tradingagents/default_config.py`.
4. The invalidation condition for this design would be if `TradingAgentsGraph` requires asynchronous propagation, which is not the case as verified in `tradingagents/graph/trading_graph.py` (it exposes a synchronous `propagate` method).
