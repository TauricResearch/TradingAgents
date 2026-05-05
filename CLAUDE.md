# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install (using uv is preferred, pip also works)
uv pip install -e .
pip install -e .

# Run the CLI (interactive: prompts for ticker, date, provider, analysts)
tradingagents analyze

# Run with checkpoint/resume support
tradingagents analyze --checkpoint

# Clear saved checkpoints before running
tradingagents analyze --clear-checkpoints

# Run all tests
pytest tests/

# Run a single test file
pytest tests/test_structured_agents.py -v

# Run tests by marker
pytest tests/ -m unit
pytest tests/ -m smoke

# Run the smoke test for structured-output agents across providers
python scripts/smoke_structured_output.py
```

## Architecture

TradingAgents is a LangGraph-based multi-agent framework where specialized LLM agents collaborate on a trading decision. The pipeline flows:

**Analysts (sequential)** → **Researchers (Bull/Bear debate)** → **Research Manager** → **Trader** → **Risk Mgmt (3-way debate)** → **Portfolio Manager** → final 5-tier rating signal

The main entry point is `TradingAgentsGraph` in `tradingagents/graph/trading_graph.py`. Call `.propagate(company_name, trade_date)` to run a full analysis; use `.process_signal(full_signal)` to extract the rating from the output. The graph is assembled dynamically in `graph/setup.py` based on which analyst types are enabled in config.

### Key subsystems

**`tradingagents/graph/`** — LangGraph orchestration
- `trading_graph.py`: `TradingAgentsGraph` class — key public methods: `propagate(company_name, trade_date)` and `process_signal(full_signal)`
- `setup.py`: Constructs the StateGraph with nodes/edges per analyst selection
- `conditional_logic.py`: Routing between debate rounds (configurable rounds per debate)
- `checkpointer.py`: SQLite-backed resume via `langgraph-checkpoint-sqlite`; checkpoints stored at `~/.tradingagents/cache/checkpoints/<TICKER>.db`
- `reflection.py`: Post-trade LLM reflection injected into memory on next run

**`tradingagents/agents/`** — All agent implementations
- `analysts/`: One file per analyst type (market, social_media, news, fundamentals) — each wraps LLM calls with tool nodes
- `managers/`: `research_manager.py` and `portfolio_manager.py` use **structured output** (Pydantic schemas in `agents/schemas.py`)
- `traders/trader.py`: Also structured output
- `risk_mgmt/`: Three debators (aggressive/neutral/conservative) in a round-robin loop
- `utils/memory.py`: Reads the persistent `trading_memory.md` log; injects prior decisions into agent context

**`tradingagents/llm_clients/`** — Multi-provider LLM abstraction
- `factory.py`: `create_llm_client(provider, model, **kwargs)` → `BaseLLMClient`
- Provider clients (`openai_client.py`, `anthropic_client.py`, `google_client.py`, `azure_client.py`) each expose `.get_llm()` returning a LangChain chat model
- `openai_client.py` also handles xAI, DeepSeek, Qwen, GLM, OpenRouter (all OpenAI-compatible APIs)
- `model_catalog.py`: Canonical model name lists per provider

**`tradingagents/dataflows/`** — Market data
- `interface.py`: Vendor-agnostic routing (yfinance or Alpha Vantage) via `TOOLS_CATEGORIES` dispatch
- Data is cached under `~/.tradingagents/cache/`

**`tradingagents/default_config.py`** — All tuneable defaults: provider, models, debate rounds, data vendor, checkpoint on/off, output language

**`cli/main.py`** — Typer app; wraps `TradingAgentsGraph` with rich terminal UI, interactive provider/model selection, and a `StatsCallbackHandler` that tracks token usage

### Persistent state

| Path | Purpose |
|------|---------|
| `~/.tradingagents/memory/trading_memory.md` | Append-only decision log; past entries are injected into analyst context |
| `~/.tradingagents/cache/checkpoints/<TICKER>.db` | LangGraph SQLite checkpoint for mid-run resume |
| `~/.tradingagents/logs/` | Saved full analysis reports |

### Structured output pattern

Decision agents (Research Manager, Trader, Portfolio Manager) use `with_structured_output(Schema)` on the LangChain model. Schemas are Pydantic models in `tradingagents/agents/schemas.py`:
- `PortfolioRating` (5-tier): Buy / Overweight / Hold / Underweight / Sell — used by Research Manager and Portfolio Manager
- `TraderAction` (3-tier): Buy / Hold / Sell — used by the Trader
- `ResearchPlan`, `TraderProposal` — wrapping types that include the rating/action plus reasoning

The `utils/agent_utils.py` helpers handle provider-specific quirks (e.g., DeepSeek reasoning stripping).

### Adding a new LLM provider

1. Add a client class in `tradingagents/llm_clients/` implementing `BaseLLMClient`
2. Register it in `factory.py`
3. Add model names to `model_catalog.py`
4. Add the API key var to `.env.example`

### Environment

Copy `.env.example` to `.env` and populate whichever provider keys you need. Azure OpenAI uses `.env.enterprise.example` instead. The framework raises an early error if a required key is missing for the chosen provider.
