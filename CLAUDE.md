# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install in editable mode
pip install -e .

# Run the CLI
tradingagents                 # interactive analysis
tradingagents analyze         # same, with --checkpoint / --clear-checkpoints flags

# Run directly from source (no install needed)
python -m cli.main

# Tests
pytest                                  # all tests
pytest -m unit                          # unit tests only
pytest -m "not integration"             # skip tests needing external services
pytest tests/test_safe_ticker_component.py -k "test_dot"  # single parametrized case

# Docker
cp .env.example .env
docker compose run --rm tradingagents
```

Tests use `pytest` with three markers: `unit`, `integration`, `smoke`. A `conftest.py` autouse fixture sets dummy API keys so unit tests don't hang waiting for env vars.

## Architecture

TradingAgents is a **LangGraph** multi-agent pipeline that simulates a trading firm. The graph is a linear chain with conditional tool-calling loops and debate cycles:

```
START → [Analysts (up to 4, in sequence)] → Bull/Bear Researcher debate → Research Manager
       → Trader → Aggressive/Conservative/Neutral Risk debate → Portfolio Manager → END
```

- **`tradingagents/graph/`** — Orchestration layer. `TradingAgentsGraph` is the main entry point. It compiles the LangGraph `StateGraph`, manages checkpoint/resume via `SqliteSaver`, and delegates to `GraphSetup` (node/edge wiring), `ConditionalLogic` (debate round counting), `Propagator` (initial state), `Reflector` (post-trade reflection), and `SignalProcessor` (decision parsing).

- **`tradingagents/agents/`** — Each agent is a factory function (e.g. `create_market_analyst`) that returns a LangGraph node — a function binding an LLM + system prompt + tools. Agents communicate through a shared `AgentState` dict. Debate agents (bull/bear researchers, risk debaters) use `InvestDebateState` / `RiskDebateState` sub-structures to track round counts and speaker turns.

- **`tradingagents/dataflows/`** — Data vendor abstraction. `interface.py` is the routing layer: tool calls go through `route_to_vendor(method, *args)` which reads the config's `data_vendors` dict and dispatches to the correct implementation (yfinance or Alpha Vantage). Adding a new data vendor means: implement the tool functions, register them in `VENDOR_METHODS`, and add the vendor name to `VENDOR_LIST`.

- **`tradingagents/llm_clients/`** — LLM provider factory. `factory.py` lazily imports provider modules. OpenAI-compatible providers (OpenAI, xAI, DeepSeek, Qwen, GLM, Ollama, OpenRouter) all share `OpenAIClient`. Anthropic and Google have dedicated clients. Each client wraps `langchain_<provider>` chat models.

- **`tradingagents/dataflows/config.py`** — Module-level singleton config. `set_config()` is called once by `TradingAgentsGraph.__init__()`; `get_config()` is called everywhere else. Defaults come from `tradingagents/default_config.py`.

- **`tradingagents/agents/utils/memory.py`** — `TradingMemoryLog` persists decisions to `~/.tradingagents/memory/trading_memory.md`. Before each run, pending entries for the same ticker are resolved (realized returns fetched, reflections generated) and injected into the Portfolio Manager's prompt.

- **`cli/`** — The CLI is a Typer app. It collects user selections (ticker, date, language, analysts, depth, LLM provider, model) via `questionary` prompts, then streams the graph execution through a Rich `Live` layout. `MessageBuffer` tracks agent status and report sections for the progress UI.

## Key patterns

- **Configuration flows one way**: `DEFAULT_CONFIG` → `set_config()` → `get_config()` everywhere. The data layer, agents, and memory module all read config via `get_config()` — never from env vars or globals directly.
- **Ticker safety**: `safe_ticker_component()` in `dataflows/utils.py` validates tickers before they're interpolated into filesystem paths (cache files, results dirs, checkpoints).
- **Agent creation**: All agents are created by `tradingagents/agents/` factory functions. Each takes an LLM instance and returns a callable node. System prompts live alongside the factory in the same file.
- **Debate mechanics**: Both the research debate (bull/bear) and risk debate (aggressive/conservative/neutral) use a `count`-based termination condition in `ConditionalLogic`. The `latest_speaker` field drives alternating turns.
