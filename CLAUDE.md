# TradingAgents

Short project context for Claude at conversation start. Keep this file practical: commands, architecture truths, workflow rules, and where to find docs.

## What This Repo Is

TradingAgents is a multi-agent trading research system built with:

- Python
- LangGraph
- Typer CLI
- FastAPI backend for AgentOS
- React frontend for AgentOS
- PostgreSQL-backed portfolio persistence

## Bash Commands

Activate env:

```bash
conda activate tradingagents
```

Run tests:

```bash
pytest tests/ -v
```

Skip live/integration tests:

```bash
pytest tests/ -v -m "not integration"
```

Run scanner:

```bash
python -m cli.main scan --date 2026-03-31
```

Run CLI analysis:

```bash
python -m cli.main analyze
```

Run AgentOS backend:

```bash
uvicorn agent_os.backend.main:app --reload --port 8088
```

## Code Style

- Prefer small explicit changes over broad rewrites.
- Keep graph ownership in `tradingagents/graph/`.
- Keep vendor routing rules in `tradingagents/dataflows/interface.py`.
- Keep persistence and path rules in `report_paths.py`, `report_store.py`, and `store_factory.py`.
- If an agent uses `bind_tools()`, it must have a real tool execution path.
- Do not silently add vendor fallback.
- Do not hardcode report paths or provider URLs.
- Check actual vendor output shapes before coding against pandas objects.

## Workflow Rules

- Use `run_id` as the single canonical runtime identifier.
- Report-store writes require `create_report_store(run_id=...)`.
- Re-runs keep the original root `run_id`.
- Analysts in the trading graph run sequentially.
- Scanner agents use inline tool execution with `run_tool_loop()`.
- Portfolio flow includes parallel `macro_summary` and `micro_summary` before PM decision.
- REST endpoints start background execution; WebSocket streams cached and persisted events.
- **Pipeline Failures**: Nodes will hard-crash (raise exceptions) on LLM timeouts or network errors instead of generating silent fallback states. This allows intermediate checkpoints to remain clean for UI resumption.

## Main Architecture

Trading graph:

1. Market Analyst
2. Social Analyst
3. News Analyst
4. Fundamentals Analyst
5. Bull/Bear debate
6. Research Manager
7. Trader
8. Risk loop
9. Portfolio Manager

Scanner graph:

1. gatekeeper, geopolitical, market movers, sector
2. factor alignment, smart money, drift
3. industry deep dive
4. macro synthesis

Portfolio graph:

1. load portfolio
2. compute risk
3. review holdings
4. prioritize candidates
5. macro summary + micro summary
6. PM decision
7. cash sweep
8. execute trades

## Docs Map

Start here:

- `docs/README.md`: index of the docs folder
- `docs/graph_flows.md`: shortest flow overview
- `docs/graph_execution_reference.md`: exact runtime behavior
- `docs/agent_dataflow.md`: agent, tool, and memory summary

Architecture and rules:

- `docs/architecture_learnings.md`: dos, don’ts, avoids
- `docs/agent/context/ARCHITECTURE.md`: internal architecture summary
- `docs/agent/context/CONVENTIONS.md`: implementation conventions
- `docs/agent/context/COMPONENTS.md`: where code lives

Portfolio:

- `docs/portfolio/00_overview.md`: current portfolio architecture
- `docs/portfolio/03_database_schema.md`: DB schema
- `docs/portfolio/04_repository_api.md`: repository and report-store API

Project memory:

- `docs/agent/CURRENT_STATE.md`: active milestone and recent progress
- `docs/agent/decisions/`: ADRs and architectural decisions
- `docs/agent/plans/`: implementation plans

## Important Code Entry Points

- `tradingagents/default_config.py`
- `tradingagents/report_paths.py`
- `tradingagents/dataflows/interface.py`
- `tradingagents/graph/setup.py`
- `tradingagents/graph/scanner_setup.py`
- `tradingagents/graph/portfolio_setup.py`
- `agent_os/backend/services/langgraph_engine.py`
- `agent_os/backend/routes/runs.py`

## Note

`/init` gives Claude a good starting read of the codebase, but this file should hold the persistent project rules and navigation hints that are easy to lose across sessions.
