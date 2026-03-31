<!-- Last verified: 2026-03-31 -->

# Components

This is the current component map for navigating the codebase.
It is intentionally shorter than a raw directory dump and focuses on where important responsibilities live.

## Core Runtime Packages

### `tradingagents/`

- `default_config.py`: shared config model and env overrides
- `report_paths.py`: canonical `run_id` and report path helpers
- `observability.py`: `RunLogger` and callback-based event logging
- `daily_digest.py`: shared per-date digest writing
- `notebook_sync.py`: optional NotebookLM sync

### `tradingagents/agents/`

Agent factories grouped by role:

- `analysts/`: market, social, news, fundamentals
- `researchers/`: bull and bear
- `managers/`: research manager, portfolio manager, context helpers
- `risk_mgmt/`: aggressive, conservative, neutral
- `scanners/`: gatekeeper, geopolitical, market movers, sector, factor alignment, smart money, drift, industry deep dive, macro synthesis
- `portfolio/`: holding reviewer, macro summary, micro summary, PM decision
- `utils/`: tool runners, state models, memory helpers, data-tool wrappers, JSON parsing

### `tradingagents/dataflows/`

Vendor and derived data layers:

- `interface.py`: routing and fallback policy
- `y_finance.py`, `alpha_vantage_*`, `finnhub_*`, `finviz_*`-style helpers
- derived analysis modules such as `macro_regime.py`, `peer_comparison.py`, `ttm_analysis.py`

### `tradingagents/graph/`

Graph assembly and orchestration:

- `setup.py`: per-ticker trading graph builder
- `scanner_setup.py`: scanner graph builder
- `portfolio_setup.py`: portfolio graph builder
- `trading_graph.py`, `scanner_graph.py`, `portfolio_graph.py`: orchestrator classes
- `conditional_logic.py`: debate/risk routing
- `propagation.py`: pipeline state bootstrapping
- `reflection.py`: reflexion update helpers

### `tradingagents/portfolio/`

Portfolio storage and execution layer:

- `models.py`: portfolio, holding, trade, snapshot models
- `config.py`: portfolio-specific config
- `supabase_client.py`: direct PostgreSQL CRUD client
- `repository.py`: business-logic facade
- `report_store.py`: run-scoped artifact persistence
- `store_factory.py`: store selection and `run_id` wiring
- `risk_evaluator.py`, `risk_metrics.py`: deterministic portfolio analytics
- `candidate_prioritizer.py`: candidate ranking
- `trade_executor.py`: execution and constraint enforcement
- `lesson_store.py`, `memory_loader.py`: selection-memory support

### `tradingagents/memory/`

- `reflexion.py`: per-ticker reflexion memory
- `macro_memory.py`: regime-level memory

## User Interfaces

### CLI

- `cli/main.py`: Typer entrypoints and interactive flows
- `cli/stats_handler.py`: runtime stats display
- `cli/config.py`, `cli/models.py`, `cli/utils.py`: CLI support code

### AgentOS

- `agent_os/backend/main.py`: FastAPI app
- `agent_os/backend/routes/runs.py`: run creation, history, and rerun endpoints
- `agent_os/backend/routes/websocket.py`: run event stream endpoint
- `agent_os/backend/routes/portfolios.py`: portfolio API
- `agent_os/backend/services/langgraph_engine.py`: run orchestration and event mapping
- `agent_os/backend/store.py`: in-memory run cache
- `agent_os/backend/run_metadata.py`: persisted run metadata normalization
- `agent_os/frontend/src/Dashboard.tsx`: main dashboard
- `agent_os/frontend/src/hooks/useAgentStream.ts`: WebSocket client hook
- `agent_os/frontend/src/components/AgentGraph.tsx`: live graph renderer
- `agent_os/frontend/src/components/PortfolioViewer.tsx`: portfolio views

## Entry-Point Guide

If you need to work on:

- graph topology: start in `tradingagents/graph/`
- vendor routing or fallback: start in `tradingagents/dataflows/interface.py`
- agent prompts and tool loops: start in `tradingagents/agents/`
- run persistence or reruns: start in `agent_os/backend/routes/runs.py` and `tradingagents/portfolio/report_store.py`
- event streaming or frontend graph behavior: start in `agent_os/backend/services/langgraph_engine.py` and `agent_os/frontend/src/`
- portfolio execution: start in `tradingagents/portfolio/` and `tradingagents/agents/portfolio/`

## Related Docs

- `docs/README.md`
- `docs/graph_execution_reference.md`
- `docs/agent_dataflow.md`
- `docs/portfolio/00_overview.md`
