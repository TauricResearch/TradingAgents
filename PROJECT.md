# Project: Autonomous Continuous Trading Analyst MVP

## Architecture
The system is built by copying and adapting the logic of `advanced_agent.py` into a new package/module structure in `gemini_agent`.
The primary class `AdvancedTradingAgent` in `gemini_agent` will implement:
- CLI parameters parsing and the continuous event loop (`run_watch_loop`).
- Integration with `MarketWatcher` to fetch ticker/benchmark market snapshots.
- Integration with `OpportunityScanner` to rank and score watchlist candidates.
- Context injection from `PortfolioMemory` and execution of deep analysis using the existing `TradingAgentsGraph`.
- Safety and risk checks via `RiskGuard`.
- Performance reporting and paper portfolio value logging using `ReportWriter`.

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

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | E2E Testing Track | Design and implement the complete E2E test suite covering Tiers 1-4. Generate `TEST_READY.md`. | None | DONE |
| 2 | CLI & Core Watcher | Implement the CLI options (`--watch`, etc.) and the basic `MarketWatcher` loop fetching market data. | None | DONE |
| 3 | Opportunity Scanner | Implement the scoring logic in `OpportunityScanner` to score and pick the top 3-5 candidates. | M2 | IN_PROGRESS (Conv: 922682f0-f85a-41cc-8bfc-8535e7eedf52) |
| 4 | Memory & Risk Guard | Implement `PortfolioMemory`, paper trading simulator ($10k), `RiskGuard` flags, and Performance Review. | M2 | PLANNED |
| 5 | Loop Integration & E2E | Integrate all modules into `run_watch_loop`, wire reports, and pass 100% of the E2E tests (Tiers 1-4). | M1, M3, M4 | PLANNED |
| 6 | Adversarial Hardening | Phase 2: Run Challengers to find gaps and write Tier 5 adversarial tests, fixing any discovered issues. | M5 | PLANNED |

## Interface Contracts
### `MarketWatcher`
- `fetch_snapshots(watchlist: list[str]) -> dict`: Fetches market data for tickers and benchmark SPY. Returns snapshots including daily open/close/volume/high/low.

### `OpportunityScanner`
- `score_candidates(snapshots: dict) -> list[dict]`: Scores each ticker based on price dynamics, volume, and relative strength vs SPY. Returns a sorted list of candidates with their assigned score.

### `PortfolioMemory`
- `load_memory() -> dict`: Returns the state of the simulated portfolio (cash, positions, past decisions).
- `save_snapshot(snapshot: dict)`: Saves a JSON snapshot of the portfolio and market state.
- `update_portfolio(decision: dict)`: Simulates trade execution and tracks positions against the theoretical $10,000 USD starting balance.
- `review_performance() -> dict`: Calculates the ROI of previous decisions.

### `RiskGuard`
- `assess_risk(ticker: str, portfolio: dict) -> str`: Evaluates exposure, volatility, and rules. Returns one of `safe`, `watch`, `risky`.

### `ReportWriter`
- `log_event(event_type: str, data: dict)`: Appends an event log to the specific JSONL file in `reports/continuous/`.
- `generate_daily_summary() -> str`: Generates the Markdown summary `daily_summary.md`.

## Code Layout
- `gemini_agent/` - New agent folder.
  - `__init__.py` - Exports the main agent class.
  - `agent.py` - Contains the `AdvancedTradingAgent` with `--watch` loop.
  - `watcher.py` - Contains `MarketWatcher` and `OpportunityScanner`.
  - `memory.py` - Contains `PortfolioMemory` and `RiskGuard`.
  - `reporter.py` - Contains `ReportWriter` and log path configurations.
