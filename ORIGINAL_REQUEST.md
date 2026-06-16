# Original User Request

## Initial Request — 2026-06-16T12:17:56+02:00

Create an autonomous, continuous trading analyst MVP based on the provided plan. The new agent should be created by copying and modifying the logic of `advanced_agent.py` into a new script located in the `gemini_agent` directory. The agent will run in an async loop, fetch market data, score tickers, and log results to JSONL/Markdown without executing actual trades.

Working directory: /home/patryk/Dokumenty/trading_ai/TradingAgents/gemini_agent
Integrity mode: development

## Verification Resources
Reference plan: `/home/patryk/Dokumenty/trading_ai/TradingAgents/plan_wykonani_gemini.txt`
Base file: `/home/patryk/Dokumenty/trading_ai/TradingAgents/advanced_agent.py`

## Requirements

### R1. Core CLI & Event Loop
Implement an async continuous loop (`run_watch_loop`) in the main agent class, supporting new CLI parameters: `--watch`, `--interval-minutes`, `--watchlist`, and `--max-candidates`.

### R2. Market Scanning
Implement a `MarketWatcher` to fetch data/snapshots, and an `OpportunityScanner` to score candidates (e.g. by price dynamics, volume, and SPY relative strength) to pick the top 3-5 candidates for analysis.

### R3. Memory & Risk Tracking
Create a `PortfolioMemory` to save JSON/JSONL snapshots and decisions, along with a Performance Review module to check past recommendations. Implement a `RiskGuard` to flag risks (safe, watch, risky) without blocking real trades. The portfolio tracking must simulate a theoretical paper trading portfolio starting with a capital of $10,000 USD.

### R4. Reporting System
Implement a `ReportWriter` that generates structural JSONL logs (e.g. `watch_log.jsonl`, `opportunities.jsonl`, `decisions.jsonl`) into a reports folder and produces a readable `daily_summary.md`.

## Acceptance Criteria

### Execution & Output
- [ ] Running the script with `--watch` and a small `--interval-minutes` in dry-run mode completes at least 2 cycles without crashing.
- [ ] The `reports/continuous` folder is populated with valid JSONL log files containing market snapshots and decisions.
- [ ] A `daily_summary.md` file is successfully generated reflecting the scanned tickers and risk flags.
- [ ] The `OpportunityScanner` demonstrably assigns scores to candidates before selecting the top ones.
- [ ] The system accurately tracks hypothetical trades against the theoretical $10,000 starting balance in its JSONL outputs or memory states.
