# Current Milestone

FE improvements: configurable max_auto_tickers + run persistence with phase-level node re-run. PR pending review on `feat/fe-max-tickers-load-run`.

# Recent Progress

- **feat/fe-max-tickers-load-run**: Two features implemented:
  - Feature 1: `max_auto_tickers` config key + macro synthesis prompt injection + frontend number input + backend safety cap
  - Feature 2: Run persistence (run_meta.json + run_events.jsonl), intermediate phase checkpoints (analysts/trader), phase subgraphs (debate + risk), POST /api/run/rerun-node endpoint, frontend history panel + modified node re-run
- **PR#108 merged**: Per-tier LLM fallback for 404/policy errors
- **PR#107 merged**: `save_holding_review` per-ticker fix, `RunLogger` threading.local to contextvars.ContextVar
- **PR#106 merged**: MongoDB report store, RunLogger observability, reflexion memory, run-ID namespaced reports
- **Smart Money Scanner**: Finviz integration with Golden Overlap strategy (ADR 014)
- **AgentOS**: Full-stack visual observability layer (FastAPI + React + ReactFlow)
- **Portfolio Manager**: Phases 1-10 complete (models, agents, CLI, stop-loss/take-profit)

# In Progress

- feat/fe-max-tickers-load-run PR under review

# Active Blockers

- None
