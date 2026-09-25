# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development commands

```bash
pip install .                    # install the package in editable dev mode
pytest                          # run all tests (no API keys needed)
pytest -m unit                  # unit tests only
pytest -m integration           # integration tests only
pytest tests/test_memory_log.py # single test file
tradingagents                   # launch interactive CLI from source
python -m cli.main              # alternative CLI entrypoint
python main.py                  # quick single-analysis script
```

There are no lint or type-check commands configured. Tests use `pytest` with markers `unit`, `integration`, and `smoke`. API keys are auto-mocked via `conftest.py`.

## Architecture

**TradingAgents** is a LangGraph-based multi-agent financial trading framework. It simulates a trading firm: specialist analysts research a ticker, bull/bear researchers debate the findings, a trader proposes an action, risk debaters challenge it, and a portfolio manager makes the final decision.

### Entry point

`TradingAgentsGraph` (`tradingagents/graph/trading_graph.py`) is the main class. Instantiate with a config dict (see `default_config.py`), call `.propagate(ticker, date)` → `(final_state, decision)`. The graph is compiled from a LangGraph `StateGraph`; each agent node is a LangChain runnable that receives the shared `AgentState`.

### Pipeline stages (in order)

1. **Analyst Team** — market, sentiment/social, news, fundamentals. Each analyst has its own tool node (`ToolNode` with data-fetching functions). Analysts run sequentially, using `quick_thinking_llm`.
2. **Bull & Bear Researchers** — debate the analyst findings. Controlled by `max_debate_rounds` config. Uses `quick_thinking_llm`.
3. **Research Manager** — synthesizes the debate into a structured decision. Uses `deep_thinking_llm` with `with_structured_output(ResearchManagerOutput)`.
4. **Trader** — creates a concrete investment plan. Uses `quick_thinking_llm` with `with_structured_output(TraderOutput)`.
5. **Risk Debators** — Aggressive, Conservative, Neutral analysts debate the plan. Controlled by `max_risk_discuss_rounds`.
6. **Portfolio Manager** — final approve/reject decision. Uses `deep_thinking_llm` with `with_structured_output(PortfolioManagerOutput)`. This is the only agent that reads the persistent memory log.

The graph flow is defined in `GraphSetup.setup_graph()` (`tradingagents/graph/setup.py`). Node wiring and conditional edge logic lives in `ConditionalLogic` (`tradingagents/graph/conditional_logic.py`).

### LLM provider layer

All LLM access goes through a factory pattern in `tradingagents/llm_clients/`:

- `create_llm_client(provider, model, base_url, **kwargs)` → `BaseLLMClient`
- Each client wraps a LangChain chat model and normalizes content to plain strings
- Providers: `openai` (and all OpenAI-compatible: `xai`, `deepseek`, `qwen`, `glm`, `ollama`, `openrouter`), `anthropic`, `google`, `azure`
- Provider-specific kwargs (thinking/reasoning effort, Google key rotation) are threaded from config through `_get_provider_kwargs()`
- Two LLM tiers: `deep_think_llm` (complex reasoning — Research Manager, Portfolio Manager) and `quick_think_llm` (all other agents)

### Data vendor abstraction

`tradingagents/dataflows/interface.py` defines a vendor routing system. Each tool method (e.g. `get_stock_data`, `get_indicators`) is mapped to vendor-specific implementations. The config's `data_vendors` dict selects the primary vendor per category; `tool_vendors` overrides per-tool. Vendors include `yfinance`, `alpha_vantage`, `binance` (crypto), `crypto` (news/sentiment), and `fred` (macro).

### Crypto subsystem

The crypto modules add Binance-backed trading for digital assets, designed as **research-first, trade-second**:

- **`scanner/`** — `FastScanner` detects setups via technical patterns (RSI reversal, breakout, EMA crossover, etc.) with configurable filters
- **`analyzer/`** — `DeepAnalyzer` runs full LLM analysis on triggered setups, producing structured signals
- **`execution/`** — `BinanceExecutor` (live) and `PaperTrading` (simulated) for order execution
- **`memory/`** — three-tier memory: raw logs → lesson drafts → global validated rules. `MemoryProcessor` handles raw→lesson, `LessonValidator` manages promotion to global. Trade mode only reads global memory.
- **`dataflows/crypto_*.py`** — CCXT/Binance data, CryptoPanic news, Alternative.me Fear & Greed
- **`crypto/train_runner.py`** — training loop that ties scanner → analyzer → memory together
- **`notifications/telegram_bot.py`** — signal delivery and human confirmation via Telegram
- **`storage/sqlite_store.py`** — persistent storage for raw trades

The crypto config preset is `CRYPTO_TRAIN_CONFIG` in `default_config.py`.

### Memory & persistence

Two persistence systems:

1. **Decision log** (always on) — `TradingMemoryLog` appends each completed decision to `~/.tradingagents/memory/trading_memory.md`. On the next same-ticker run, pending entries are resolved with realised returns, alpha vs benchmark, and a reflection. The Portfolio Manager sees recent same-ticker decisions plus cross-ticker lessons.

2. **Checkpoint resume** (opt-in via `config["checkpoint_enabled"] = True`) — LangGraph `SqliteSaver` checkpoints save state after each node. Crashed runs resume from the last successful step. Per-ticker SQLite databases at `~/.tradingagents/cache/checkpoints/<TICKER>.db`.

For crypto, `CryptoTrainingMemory` provides the two-tier raw+lesson store (global tier is optional).

### Structured output agents

Research Manager, Trader, and Portfolio Manager use LangChain's `with_structured_output()` returning Pydantic models (defined in `tradingagents/agents/schemas.py`). Each provider maps this to its native mode: `json_schema` for OpenAI/xAI, `response_schema` for Gemini, `tool_use` for Anthropic, `function_calling` for OpenAI-compatible providers.

### Key configuration fields

See `tradingagents/default_config.py` for all options. Important ones:

- `llm_provider`, `deep_think_llm`, `quick_think_llm` — model selection
- `max_debate_rounds`, `max_risk_discuss_rounds` — debate depth
- `data_vendors`, `tool_vendors` — data source routing
- `output_language` — analyst report/decision language (debate stays English)
- `market_type` — `"stock"` or `"crypto"`
- `checkpoint_enabled` — enable LangGraph resume
- `memory_log_max_entries` — cap resolved entries (pending never pruned)

### Module layout

```
tradingagents/
├── agents/          # Agent node factories + shared utils (states, tools, schemas, memory)
│   ├── analysts/    # Market, news, sentiment, social, fundamentals
│   ├── researchers/ # Bull, bear debaters
│   ├── risk_mgmt/   # Aggressive, conservative, neutral debaters
│   ├── managers/    # Research manager, portfolio manager
│   ├── trader/      # Trader agent
│   └── utils/       # States, tool wrappers, memory, structured output helpers
├── graph/           # LangGraph orchestration (setup, conditional logic, propagation, reflection, signal processing)
├── llm_clients/     # Provider factory + per-provider clients (base, openai, anthropic, google, azure, key rotator, validators, model catalog)
├── dataflows/       # Data vendor implementations + interface routing
├── scanner/         # Crypto: fast technical scanner
├── analyzer/        # Crypto: deep LLM analysis
├── memory/          # Crypto: memory processor, lesson validator, trade memory
├── execution/       # Crypto: Binance executor, paper trading
├── notifications/   # Crypto: Telegram bot
├── storage/         # Crypto: SQLite store
├── crypto/          # Crypto: training loop runner
└── default_config.py
cli/                 # Interactive CLI (Typer-based)
scripts/             # Standalone scripts (crypto backtests, dashboard, training, view_runs)
tests/               # Pytest suite with auto-mocked API keys
```
