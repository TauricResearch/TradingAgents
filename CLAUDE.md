# TradingAgents Framework - Project Knowledge

## Project Overview

Multi-agent LLM trading framework using LangGraph for financial analysis and decision making.

## Development Environment

**Conda Environment**: `tradingagents`

Before starting any development work, activate the conda environment:

```bash
conda activate tradingagents
```

## Architecture

- **Agent Factory Pattern**: `create_X(llm)` → closure pattern
- **3-Tier LLM System**:
  - Quick thinking (fast responses)
  - Mid thinking (balanced analysis)
  - Deep thinking (complex reasoning)
- **Data Vendor Routing**: yfinance (primary), Alpha Vantage (fallback)
- **Graph-Based Workflows**: LangGraph for agent coordination

## Key Directories

- `tradingagents/agents/` - Agent implementations
- `tradingagents/graph/` - Workflow graphs and setup
- `tradingagents/dataflows/` - Data access layer
- `cli/` - Command-line interface

## Agent Flow (Existing Trading Analysis)

1. Analysts (parallel): Fundamentals, Market, News, Social Media
2. Bull/Bear Debate
3. Research Manager
4. Trader
5. Risk Debate
6. Risk Judge

## Scanner Flow (New Market-Wide Analysis)

```
START ──┬── Geopolitical Scanner (quick_think) ──┐
        ├── Market Movers Scanner (quick_think) ──┼── Industry Deep Dive (mid_think) ── Macro Synthesis (deep_think) ── END
        └── Sector Scanner (quick_think) ─────────┘
```

- Phase 1: Parallel execution of 3 scanners
- Phase 2: Industry Deep Dive cross-references all outputs
- Phase 3: Macro Synthesis produces top-10 watchlist

## Data Vendors

- **yfinance** (primary, free): Screener(), Sector(), Industry(), index tickers
- **Alpha Vantage** (alternative, API key required): TOP_GAINERS_LOSERS endpoint only (fallback for market movers)

## LLM Providers

OpenAI, Anthropic, Google, xAI, OpenRouter, Ollama

## CLI Entry Point

`cli/main.py` with Typer:

- `analyze` (per-ticker analysis)
- `scan` (new, market-wide scan)

## Configuration

`tradingagents/default_config.py`:

- LLM tiers configuration
- Vendor routing
- Debate rounds settings
- All values overridable via `TRADINGAGENTS_<KEY>` env vars (see `.env.example`)

## Patterns to Follow

- Agent creation (trading): `tradingagents/agents/analysts/news_analyst.py`
- Agent creation (scanner): `tradingagents/agents/scanners/geopolitical_scanner.py`
- Tools: `tradingagents/agents/utils/news_data_tools.py`
- Scanner tools: `tradingagents/agents/utils/scanner_tools.py`
- Graph setup (trading): `tradingagents/graph/setup.py`
- Graph setup (scanner): `tradingagents/graph/scanner_setup.py`
- Inline tool loop: `tradingagents/agents/utils/tool_runner.py`

## Critical Patterns (see `docs/agent/decisions/008-lessons-learned.md` for full details)

- **Tool execution**: Trading graph uses `ToolNode` in graph. Scanner agents use `run_tool_loop()` inline. If `bind_tools()` is used, there MUST be a tool execution path.
- **yfinance DataFrames**: `top_companies` has ticker as INDEX, not column. Always check `.index` and `.columns`.
- **yfinance Sector/Industry**: `Sector.overview` has NO performance data. Use ETF proxies for performance.
- **Vendor fallback**: Functions inside `route_to_vendor` must RAISE on failure, not embed errors in return values. Catch `(AlphaVantageError, ConnectionError, TimeoutError)`, not just `RateLimitError`.
- **LangGraph parallel writes**: Any state field written by parallel nodes MUST have a reducer (`Annotated[str, reducer_fn]`).
- **Ollama remote host**: Never hardcode `localhost:11434`. Use configured `base_url`.
- **.env loading**: `load_dotenv()` runs at module level in `default_config.py` — import-order-independent. Check actual env var values when debugging auth.
- **Rate limiter locks**: Never hold a lock during `sleep()` or IO. Release, sleep, re-acquire.
- **LLM policy errors**: `_is_policy_error(exc)` detects 404 from any provider (checks `status_code` attribute or message content). `_build_fallback_config(config)` substitutes per-tier fallback models. Both live in `agent_os/backend/services/langgraph_engine.py`.
- **Config fallback keys**: `llm_provider` and `backend_url` must always exist at top level — `scanner_graph.py` and `trading_graph.py` use them as fallbacks.

## Agentic Memory (docs/agent/)

Agent workflows use the `docs/agent/` scaffold for structured memory:

- `docs/agent/CURRENT_STATE.md` — Live state tracker (milestone, progress, blockers). Read at session start.
- `docs/agent/decisions/` — Architecture decision records (ADR-style, numbered `001-...`)
- `docs/agent/plans/` — Implementation plans with checkbox progress tracking
- `docs/agent/logs/` — Agent run logs
- `docs/agent/templates/` — Commit, PR, and decision templates

Before starting work, always read `docs/agent/CURRENT_STATE.md`. Before committing, update it.

## LLM Configuration

Per-tier provider overrides in `tradingagents/default_config.py`:
- Each tier (`quick_think`, `mid_think`, `deep_think`) can have its own `_llm_provider` and `_backend_url`
- Falls back to top-level `llm_provider` and `backend_url` when per-tier values are None
- All config values overridable via `TRADINGAGENTS_<KEY>` env vars
- Keys for LLM providers: `.env` file (e.g., `OPENROUTER_API_KEY`, `ALPHA_VANTAGE_API_KEY`)

### Env Var Override Convention

```env
# Pattern: TRADINGAGENTS_<UPPERCASE_KEY>=value
TRADINGAGENTS_LLM_PROVIDER=openrouter
TRADINGAGENTS_DEEP_THINK_LLM=deepseek/deepseek-r1-0528
TRADINGAGENTS_MAX_DEBATE_ROUNDS=3
TRADINGAGENTS_VENDOR_SCANNER_DATA=alpha_vantage
```

Empty or unset vars preserve the hardcoded default. `None`-default fields (like `mid_think_llm`) stay `None` when unset, preserving fallback semantics.

### Per-Tier Fallback LLM

When a model returns HTTP 404 (blocked by provider guardrail/policy), the engine
auto-detects it via `_is_policy_error()` and retries with a per-tier fallback:

```env
TRADINGAGENTS_QUICK_THINK_FALLBACK_LLM=gpt-5-mini
TRADINGAGENTS_QUICK_THINK_FALLBACK_LLM_PROVIDER=openai
TRADINGAGENTS_MID_THINK_FALLBACK_LLM=gpt-5-mini
TRADINGAGENTS_MID_THINK_FALLBACK_LLM_PROVIDER=openai
TRADINGAGENTS_DEEP_THINK_FALLBACK_LLM=gpt-5.2
TRADINGAGENTS_DEEP_THINK_FALLBACK_LLM_PROVIDER=openai
```

Leave unset to disable auto-retry (pipeline emits a clear actionable error instead).

## Running the Scanner

```bash
conda activate tradingagents
python -m cli.main scan --date 2026-03-17
```

## Running Tests

```bash
conda activate tradingagents
pytest tests/ -v
```
