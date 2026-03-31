<!-- Last verified: 2026-03-31 -->

# Architecture

This file is the concise internal architecture context for agent work.
For the public docs index, see `docs/README.md`.
For exact runtime execution, prefer `docs/graph_execution_reference.md`.

## System Overview

TradingAgents is a multi-agent LangGraph system with four main runtime surfaces:

1. scanner graph
2. per-ticker trading graph
3. portfolio graph
4. auto orchestration

It also has two operator surfaces:

- terminal CLI (`cli/`)
- AgentOS web observability (`agent_os/`)

## LLM Configuration Model

Three reasoning tiers are used throughout the repo:

| Tier | Default model | Typical use |
| --- | --- | --- |
| Quick | `gpt-5-mini` | analysts, scanners, risk debaters |
| Mid | `None` -> falls back to quick | researchers, trader, holding reviewer, summary agents |
| Deep | `gpt-5.2` | research manager, macro synthesis, PM decision |

Each tier may override provider and backend URL. Top-level `llm_provider` and `backend_url` remain required fallbacks.

## Data Routing

Primary vendor surfaces:

- `yfinance`
- `Alpha Vantage`
- `Finnhub`
- `Finviz`

Routing lives in `tradingagents/dataflows/interface.py`.
Fallback is fail-fast by default and only enabled for methods explicitly listed in `FALLBACK_ALLOWED`.

## Runtime Graphs

### Scanner

`START` fans out to:

- `gatekeeper_scanner`
- `geopolitical_scanner`
- `market_movers_scanner`
- `sector_scanner`

Then:

- `factor_alignment_scanner`
- `smart_money_scanner`
- `drift_scanner`
- `industry_deep_dive`
- `macro_synthesis`

### Per-Ticker Trading

The compiled graph currently runs analysts sequentially, then debate and risk loops:

- `Market Analyst`
- `Social Analyst`
- `News Analyst`
- `Fundamentals Analyst`
- bull/bear loop
- `Research Manager`
- `Trader`
- aggressive/conservative/neutral loop
- `Portfolio Manager`

### Portfolio

Current flow:

- `load_portfolio`
- `compute_risk`
- `review_holdings`
- `prioritize_candidates`
- `macro_summary` and `micro_summary` in parallel
- `make_pm_decision`
- `cash_sweep`
- `execute_trades`

### Auto

`run_auto()` is imperative orchestration in `LangGraphEngine`, not a standalone DAG.

## Execution Patterns

The runtime uses four patterns:

- prefetch before LLM call
- inline tool loop inside the node
- pure reasoning node
- plain Python closure node

Do not assume the whole codebase uses one universal tool pattern.

## Persistence and Identity

The canonical identifier is `run_id`.

Run-scoped artifacts live under:

```text
reports/daily/{date}/{run_id}/
  market/report/
  {TICKER}/report/
  portfolio/report/
  run_meta.json
  run_events.jsonl
```

`daily_digest.md` is shared per date and lives at `reports/daily/{date}/daily_digest.md`.

## AgentOS Runtime Model

Current AgentOS behavior:

- REST run endpoints create a new `run_id`, initialize in-memory run state, persist initial metadata, and start a background task.
- The background task drives `LangGraphEngine` and appends streamed events into `runs[run_id]["events"]`.
- The WebSocket endpoint streams cached events, polls for new ones, and lazy-loads history from disk when needed.
- Startup hydration rebuilds run metadata from persisted `run_meta.json` files.

This means WebSocket is the event stream transport, not the sole executor.

## Portfolio Data Layer

Portfolio persistence uses:

- direct PostgreSQL access via `psycopg2`
- `SupabaseClient` as the low-level CRUD layer
- `PortfolioRepository` as the business-logic facade
- `ReportStore` for run-scoped artifacts and checkpoints

## Where to Read Next

- `docs/graph_flows.md`
- `docs/graph_execution_reference.md`
- `docs/agent_dataflow.md`
- `docs/portfolio/00_overview.md`
- `docs/architecture_learnings.md`
