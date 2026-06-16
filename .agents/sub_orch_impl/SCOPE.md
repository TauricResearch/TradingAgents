# Scope: Implementation Track

## Architecture
We are adapting the existing single-file agent `advanced_agent.py` into a modular package structure under `gemini_agent/` as follows:
- `gemini_agent/`
  - `__init__.py` - Exports `AdvancedTradingAgent`
  - `agent.py` - Core CLI parser, continuous watch loop (`run_watch_loop`)
  - `watcher.py` - `MarketWatcher` (market data fetching) & `OpportunityScanner` (candidate ranking/scoring)
  - `memory.py` - `PortfolioMemory` (paper simulator, performance) & `RiskGuard` (risk screening)
  - `reporter.py` - `ReportWriter` (event logging and daily summaries)

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 2 | CLI & Core Watcher | Implement CLI parameters (`--watch`, `--interval-minutes`, `--watchlist`) and the basic `MarketWatcher` loop. | None | DONE |
| 3 | Opportunity Scanner | Implement the scoring logic in `OpportunityScanner` to rank and pick top candidates. | M2 | IN_PROGRESS (Conv: 922682f0-f85a-41cc-8bfc-8535e7eedf52) |
| 4 | Memory & Risk Guard | Implement `PortfolioMemory`, paper trading simulator ($10k), `RiskGuard` rules, and performance review. | M2 | PLANNED |
| 5 | Loop Integration & E2E | Integrate modules, wire continuous loop logging, and pass 100% of E2E tests (Tiers 1-4). | M3, M4 | PLANNED |
| 6 | Adversarial Hardening | Run challengers to identify gaps, write Tier 5 adversarial tests, and harden coverage. | M5 | PLANNED |

## Interface Contracts
- See `PROJECT.md` at root for specifications of `MarketWatcher`, `OpportunityScanner`, `PortfolioMemory`, `RiskGuard`, and `ReportWriter`.
