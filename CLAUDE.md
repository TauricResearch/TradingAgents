# TradingAgents Framework - Project Knowledge

## Project Overview

Multi-agent LLM trading framework using LangGraph for financial analysis and decision making.

## Development Environment

**Conda Environment**: `trasingagetns`

Before starting any development work, activate the conda environment:

```bash
conda activate trasingagetns
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

- Agent creation: `tradingagents/agents/analysts/news_analyst.py`
- Tools: `tradingagents/agents/utils/news_data_tools.py`
- Graph setup: `tradingagents/graph/setup.py`
