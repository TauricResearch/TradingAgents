# Current Milestone

Portfolio Manager Phases 2-5 complete. All 93 tests passing (4 integration skipped).

# Recent Progress

- **PR #32 merged**: Portfolio Manager data foundation — models, SQL schema, module scaffolding
  - `tradingagents/portfolio/` — full module: models, config, exceptions, supabase_client (psycopg2), report_store, repository
  - `migrations/001_initial_schema.sql` — 4 tables (portfolios, holdings, trades, snapshots) with constraints, indexes, triggers
  - `tests/portfolio/` — 51 tests: 20 model, 15 report_store, 12 repository unit, 4 integration
  - Uses `psycopg2` direct PostgreSQL via Supabase pooler (`aws-1-eu-west-1.pooler.supabase.com:6543`)
  - Business logic: avg cost basis, cash accounting, trade recording, snapshots
- **PR #22 merged**: Unified report paths, structured observability logging, memory system update
- **feat/daily-digest-notebooklm** (shipped): Daily digest consolidation + NotebookLM source sync
- **Portfolio Manager Phases 2-6** (current branch):
  - `tradingagents/portfolio/risk_evaluator.py` — pure-Python risk metrics (log returns, Sharpe, Sortino, VaR, max drawdown, beta, sector concentration, constraint checking)
  - `tradingagents/portfolio/candidate_prioritizer.py` — conviction × thesis × diversification × held_penalty scoring
  - `tradingagents/portfolio/trade_executor.py` — executes BUY/SELL (SELLs first), constraint pre-flight, EOD snapshot
  - `tradingagents/agents/portfolio/holding_reviewer.py` — LLM holding review agent (run_tool_loop pattern)
  - `tradingagents/agents/portfolio/pm_decision_agent.py` — pure-reasoning PM decision agent (no tools)
  - `tradingagents/portfolio/portfolio_states.py` — PortfolioManagerState (MessagesState + reducers)
  - `tradingagents/graph/portfolio_setup.py` — PortfolioGraphSetup (sequential 6-node workflow)
  - `tradingagents/graph/portfolio_graph.py` — PortfolioGraph (mirrors ScannerGraph pattern)
  - 48 new tests (28 risk_evaluator + 10 candidate_prioritizer + 10 trade_executor)
  - `cli/main.py` CLI integration end-to-end wiring via `portfolio`, `check-portfolio`, and `auto` commands

# In Progress

- Refinement of macro scan synthesis prompts (ongoing)

# Active Blockers

- None currently
