# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TradingAgents is a multi-agent LLM financial trading framework built with LangGraph. It simulates a trading firm with specialized agents: analysts (market, social, news, fundamentals), researchers (bull/bear), trader, and risk management teams. The system supports multiple LLM providers (OpenAI, Anthropic, Google, xAI, OpenRouter, Ollama) and data vendors (Yahoo Finance, Alpha Vantage).

## Essential Commands

### Installation (requires Python >=3.10)
```bash
pip install -r requirements.txt
# OR for editable install with CLI entry point
pip install -e .
```

### CLI Usage
```bash
python -m cli.main
# or if installed via pip install -e .
tradingagents
```

### Python API Usage
```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

ta = TradingAgentsGraph(debug=True, config=DEFAULT_CONFIG.copy())
_, decision = ta.propagate("NVDA", "2026-01-15")
print(decision)

# After observing actual returns, memorize mistakes for future runs
# ta.reflect_and_remember(returns)  # parameter is the position returns (e.g. 1000)
```

### Testing and Linting
No formal test suite or linting configuration exists. `test.py` at root is a manual smoke test for Yahoo Finance data functions.

### Environment Variables
Set via `.env` file (loaded with `python-dotenv`) or shell exports. Only the provider you use is required:
```bash
OPENAI_API_KEY=...          # OpenAI (GPT)
GOOGLE_API_KEY=...          # Google (Gemini)
ANTHROPIC_API_KEY=...       # Anthropic (Claude)
XAI_API_KEY=...             # xAI (Grok)
OPENROUTER_API_KEY=...      # OpenRouter
ZHIPU_API_KEY=...           # Zhipu AI
ALPHA_VANTAGE_API_KEY=...   # Alpha Vantage (optional, for non-yfinance data)
TRADINGAGENTS_RESULTS_DIR=... # Optional results directory override
```

## Architecture

### Core Workflow (LangGraph State Machine)
The trading graph follows a sequential multi-phase workflow:

1. **Analyst Phase** - Each selected analyst runs sequentially, uses tools to gather data, clears messages after completion
2. **Research Phase** - Bull/Bear researchers debate with analyst reports as context; Research Manager finalizes after `max_debate_rounds`
3. **Trading Phase** - Trader synthesizes research into investment plan
4. **Risk Phase** - Aggressive/Conservative/Neutral agents debate; Risk Judge finalizes after `max_risk_discuss_rounds`

Key files:
- `tradingagents/graph/trading_graph.py` - Main TradingAgentsGraph class
- `tradingagents/graph/setup.py` - GraphSetup for building workflow
- `tradingagents/graph/conditional_logic.py` - Routing logic
- `tradingagents/graph/propagation.py` - State initialization

### Directory Structure
```
cli/                    # Command-line interface (Typer-based)
tradingagents/
  agents/
    analysts/           # Initial analysis agents
    researchers/        # Bull/bear researchers + manager
    managers/           # Research and risk managers
    trader/            # Trading decision agent
    risk_mgmt/         # Risk assessment agents
    utils/             # Agent states, tools, memory (BM25)
  graph/               # LangGraph workflow orchestration
  dataflows/           # Data source abstraction (vendor routing)
  llm_clients/         # Multi-provider LLM factory
```

### LLM Client Factory
`tradingagents/llm_clients/factory.py` implements the factory pattern for creating LLM clients. Base client class in `base_client.py` with provider-specific implementations (OpenAI, Anthropic, Google). Provider-specific thinking configuration:
- Google: `google_thinking_level` ("high", "minimal")
- OpenAI: `openai_reasoning_effort` ("medium", "high", "low")

### Data Vendor Routing
`tradingagents/dataflows/interface.py` routes tool calls to vendor implementations. Configuration via `default_config.py`:
- Category-level: `data_vendors["core_stock_apis"] = "yfinance"`
- Tool-level override: `tool_vendors["get_stock_data"] = "alpha_vantage"`

Supported vendors: Yahoo Finance (free, default), Alpha Vantage (requires API key).

### Agent State Management
Agent states are TypedDict classes in `agents/utils/agent_states.py`:
- `AgentState` - Base state for analyst agents
- `InvestDebateState` - Research team debate state
- `RiskDebateState` - Risk management debate state

Each agent function takes `state` and returns state updates. Messages are cleared between phases to manage context window.

### Tool Definition
All data tools use `@tool` decorator from `langchain_core.tools` and are defined in `agents/utils/`. Tools route via `dataflows.interface.route_to_vendor()` to vendor implementations.

## Configuration

`tradingagents/default_config.py` defines the default configuration:
- `llm_provider` - "openai", "google", "anthropic", "xai", "openrouter", "ollama"
- `deep_think_llm` - Model for complex reasoning (default: "gpt-5.2")
- `quick_think_llm` - Model for quick tasks (default: "gpt-5-mini")
- `backend_url` - Custom API endpoint (default: OpenAI's endpoint)
- `max_debate_rounds` - Research team debate iterations (default: 1)
- `max_risk_discuss_rounds` - Risk team debate iterations (default: 1)
- `max_recur_limit` - LangGraph recursion limit (default: 100)
- `data_vendors` - Per-category vendor selection (categories: core_stock_apis, technical_indicators, fundamental_data, news_data)
- `tool_vendors` - Per-tool vendor overrides (takes precedence over category-level)

Copy and modify `DEFAULT_CONFIG` to customize. Always use `.copy()` to avoid mutating the shared default.

## Important Patterns

1. **Agent Functions** - Each agent is a function `agent(state) -> dict` returning state updates
2. **Message Clearing** - Analysts clear messages after completion to prevent context bloat
3. **Tool Decorators** - Use `@tool` from `langchain_core.tools` for all data tools
4. **Factory Pattern** - LLM clients via `create_llm_client()` in `llm_clients/factory.py`
5. **Memory** - BM25-based lexical matching in `agents/utils/memory.py` (no API calls, offline-capable)
6. **Caching** - Data cached in `tradingagents/dataflows/data_cache/`

## Results and Output

Analysis logs and reports are saved to `results/` directory (configurable via `TRADINGAGENTS_RESULTS_DIR` env var). The CLI provides real-time progress display using Rich library.

## Key Entry Points

- CLI: `cli/main.py` (Typer app)
- Trading Graph: `tradingagents/graph/trading_graph.py` - `TradingAgentsGraph.propagate()`
- LLM Factory: `tradingagents/llm_clients/factory.py` - `create_llm_client()`
- Data Interface: `tradingagents/dataflows/interface.py` - `route_to_vendor()`
