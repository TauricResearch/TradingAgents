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

## Patterns to Follow

- Agent creation (trading): `tradingagents/agents/analysts/news_analyst.py`
- Agent creation (scanner): `tradingagents/agents/scanners/geopolitical_scanner.py`
- Tools: `tradingagents/agents/utils/news_data_tools.py`
- Scanner tools: `tradingagents/agents/utils/scanner_tools.py`
- Graph setup (trading): `tradingagents/graph/setup.py`
- Graph setup (scanner): `tradingagents/graph/scanner_setup.py`
- Inline tool loop: `tradingagents/agents/utils/tool_runner.py`

## Critical Patterns (from past mistakes)

- **Tool execution**: Trading graph uses `ToolNode` in graph. Scanner agents use `run_tool_loop()` inline. If `bind_tools()` is used, there MUST be a tool execution path.
- **yfinance DataFrames**: `top_companies` has ticker as INDEX, not column. Always check `.index` and `.columns`.
- **yfinance Sector/Industry**: `Sector.overview` has NO performance data. Use ETF proxies for performance.
- **Vendor fallback**: Functions inside `route_to_vendor` must RAISE on failure, not embed errors in return values. Catch `AlphaVantageError` (base class), not just `RateLimitError`.
- **LangGraph parallel writes**: Any state field written by parallel nodes MUST have a reducer (`Annotated[str, reducer_fn]`).
- **Ollama remote host**: Never hardcode `localhost:11434`. Use configured `base_url`.
- **.env loading**: Check actual env var values when debugging auth. Worktree and main repo may have different `.env` files.

## Project Tracking (Memory System)

Do NOT write to `DECISIONS.md`, `MISTAKES.md`, or `PROGRESS.md`. Use the memory system instead:

- **Decisions**: Use `/remember` to record architecture decisions (vendor strategy, LLM setup, tool execution)
- **Progress**: Use `/remember` to record feature progress, what works, TODOs
- **Mistakes**: Use `/remember` to record bugs and lessons learned

A `PreToolUse` hook enforces this — writes to those files are automatically blocked.

## Current LLM Configuration (Hybrid)

```
quick_think: qwen3.5:27b via Ollama (http://192.168.50.76:11434)
mid_think:   qwen3.5:27b via Ollama (http://192.168.50.76:11434)
deep_think:  deepseek/deepseek-r1-0528 via OpenRouter
```

Config: `tradingagents/default_config.py` (per-tier `_llm_provider` keys)
Keys: `.env` file (`OPENROUTER_API_KEY`, `ALPHA_VANTAGE_API_KEY`)

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
