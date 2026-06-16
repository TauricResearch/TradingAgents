## 2026-06-16T10:38:37Z
You are a worker agent. Your task is to re-implement the code for Milestone 2 (CLI & Core Watcher) in `gemini_agent/` to restore the full, functional implementation and overwrite the stubs that were written by the testing track.

Please perform the following steps:
1. Re-implement `gemini_agent/__init__.py` to export `AdvancedTradingAgent`.
2. Re-implement `gemini_agent/watcher.py` containing:
   - `MarketWatcher`: fetches market data for watchlist and benchmark SPY using `load_ohlcv` from `tradingagents.dataflows.stockstats_utils`, returning snapshots with open/close/volume/high/low/date.
   - `OpportunityScanner` (skeleton stub for now): returns candidate dictionaries with score stub, sorted by score descending, excluding SPY.
3. Re-implement `gemini_agent/memory.py` containing skeletal stubs for `PortfolioMemory` and `RiskGuard`.
4. Re-implement `gemini_agent/reporter.py` containing skeletal stubs for `ReportWriter`.
5. Re-implement `gemini_agent/agent.py` containing:
   - `AdvancedTradingAgent`: adapted from `advanced_agent.py`, containing `run_watch_loop` using anti-drift dynamic sleeping, ticker-level exception isolation, and CLI options.
   - CLI execution (`if __name__ == "__main__":`) that parses `--watch`, `--interval-minutes`, `--watchlist`, `--max-candidates`, `--once`, and `--date`, calling `run_watch_loop` or the legacy `run` flow as appropriate.
6. Verify that `tests/test_gemini_milestone2.py` exists and is intact (re-create it if needed).
7. Run the unit tests via pytest on the system:
   pytest tests/test_gemini_milestone2.py
8. Write a summary of your changes and test execution results in `/home/patryk/Dokumenty/trading_ai/TradingAgents/.agents/worker_m2_retry/changes.md` and a handoff report in `/home/patryk/Dokumenty/trading_ai/TradingAgents/.agents/worker_m2_retry/handoff.md`.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A Forensic Auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Report back when done by sending a message to parent (conversation ID: 2c384fc7-083c-413b-ae5c-b1feb94a0a30) with the path to your handoff.md.
