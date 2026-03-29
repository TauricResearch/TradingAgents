<!-- GSD:project-start source:PROJECT.md -->
## Project

**TradingAgents — Options Trading Module**

An options trading analysis module for TradingAgents — a multi-agent AI system that uses LLM-powered agent teams to analyze financial markets. The new module adds a parallel options analysis team that evaluates options chains, Greeks, volatility surfaces, dealer positioning, and options flow to recommend specific multi-leg options strategies with transparent reasoning.

**Core Value:** Agents produce actionable multi-leg options recommendations (with specific contracts AND alternative ranges) backed by transparent, educational reasoning that helps the user both trade and learn.

### Constraints

- **Data providers**: Tradier (REST, 120 req/min, Greeks hourly) and Tastyworks (REST + WebSocket streaming) as primary options data sources
- **No 2nd-order Greeks from API**: Charm, Vanna, Volga must be calculated from 1st-order Greeks + Black-Scholes
- **Architecture**: Must follow existing patterns — agent factory functions, vendor routing, LangGraph StateGraph
- **Python**: >=3.11, consistent with `pyproject.toml` and options-module / tastytrade SDK baseline
- **LLM provider agnostic**: Options agents must work with any supported LLM provider via the client factory
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Languages
- Python >=3.11 - Entire codebase (agents, dataflows, CLI, graph orchestration)
## Runtime
- Python 3.11+ (compatible up to 3.13+ per `uv.lock` resolution markers)
- uv (primary - `uv.lock` present at project root)
- pip/setuptools (build backend, `pyproject.toml` uses `setuptools>=61.0`)
- Lockfile: `uv.lock` present
## Frameworks
- LangGraph >=0.4.8 - Multi-agent workflow orchestration via `StateGraph` (`tradingagents/graph/setup.py`)
- LangChain Core >=0.3.81 - Base abstractions for LLM agents, callbacks, messages
- langchain-openai >=0.3.23 - OpenAI, Ollama, OpenRouter, xAI via `ChatOpenAI` (`tradingagents/llm_clients/openai_client.py`)
- langchain-anthropic >=0.3.15 - Anthropic Claude via `ChatAnthropic` (`tradingagents/llm_clients/anthropic_client.py`)
- langchain-google-genai >=2.1.5 - Google Gemini via `ChatGoogleGenerativeAI` (`tradingagents/llm_clients/google_client.py`)
- langchain-experimental >=0.3.4 - Experimental LangChain features
- Typer >=0.21.0 - CLI framework (`cli/main.py`)
- Rich >=14.0.0 - Terminal UI, panels, spinners, tables (`cli/main.py`)
- Questionary >=2.1.0 - Interactive prompts
- No test framework declared in `pyproject.toml`. One test file exists: `tests/test_ticker_symbol_handling.py`
- setuptools >=80.9.0 - Build backend
- uv - Package/dependency management
## Key Dependencies
- `langgraph >=0.4.8` - Core orchestration engine; all agent workflows are LangGraph `StateGraph` instances compiled and executed via `.stream()` / `.invoke()`
- `langchain-core >=0.3.81` - Provides `BaseCallbackHandler`, message types (`AIMessage`), and tool abstractions used throughout
- `yfinance >=0.2.63` - Default financial data vendor for stock prices, fundamentals, news, insider transactions
- `backtrader >=1.9.78.123` - Backtesting engine (imported but usage not prominent in core flow)
- `pandas >=2.3.0` - DataFrame operations for financial data manipulation (`tradingagents/dataflows/`)
- `stockstats >=0.6.5` - Technical indicator calculations on stock data (`tradingagents/dataflows/stockstats_utils.py`)
- `rank-bm25 >=0.2.2` - BM25 lexical similarity for agent memory retrieval (`tradingagents/agents/utils/memory.py`)
- `parsel >=1.10.0` - HTML/XML parsing (likely for web scraping)
- `requests >=2.32.4` - HTTP client for Alpha Vantage API calls (`tradingagents/dataflows/alpha_vantage_common.py`)
- `redis >=6.2.0` - Redis client (declared as dependency, usage not prominent in core flow)
- `python-dotenv` - Environment variable loading from `.env` files (`main.py`, `cli/main.py`)
- `tqdm >=4.67.1` - Progress bars
- `pytz >=2025.2` - Timezone handling
## Configuration
- `.env` file present - loaded via `python-dotenv` at startup
- `.env.example` documents required API keys: `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`, `XAI_API_KEY`, `OPENROUTER_API_KEY`
- `ALPHA_VANTAGE_API_KEY` - Required when using Alpha Vantage data vendor
- `TRADINGAGENTS_RESULTS_DIR` - Optional, defaults to `./results`
- `tradingagents/default_config.py` - Central config dict (`DEFAULT_CONFIG`) controlling:
- `pyproject.toml` - Project metadata, dependencies, entry points, package discovery
## Data Storage
- `tradingagents/dataflows/data_cache/` - Cached financial data
- `eval_results/{ticker}/` - Logged trading states as JSON
- `results/` - Trade results output directory
- `redis >=6.2.0` declared as dependency. Connection details would come via environment config.
## CLI Entry Point
- Maps to `cli.main:app` (Typer application)
- Fetches announcements from `https://api.tauric.ai/v1/announcements` (`cli/config.py`)
## Platform Requirements
- Python 3.11+
- uv package manager (recommended) or pip
- At least one LLM provider API key (OpenAI, Anthropic, Google, xAI, or OpenRouter)
- Redis server (if redis-based features are used)
- Same as development; runs as a Python CLI application
- No containerization or deployment configs detected
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Naming Patterns
- Use `snake_case.py` for all Python modules: `bull_researcher.py`, `agent_states.py`, `y_finance.py`
- No hyphens in file names; underscores only
- Module names describe the single responsibility: `signal_processing.py`, `conditional_logic.py`
- Use `snake_case` for all functions: `create_bull_researcher()`, `get_stock_data()`, `process_signal()`
- Factory functions use `create_` prefix: `create_fundamentals_analyst()`, `create_llm_client()`, `create_trader()`
- Getter functions use `get_` prefix: `get_config()`, `get_memories()`, `get_vendor()`
- Private/internal methods use `_` prefix: `_get_provider_kwargs()`, `_log_state()`, `_rebuild_index()`
- Use `snake_case` for all variables: `curr_situation`, `past_memory_str`, `trade_date`
- Abbreviations are common and accepted: `llm`, `curr_date`, `curr_date_dt`
- Config keys use `snake_case` strings: `"deep_think_llm"`, `"max_debate_rounds"`, `"data_vendors"`
- Use `PascalCase`: `TradingAgentsGraph`, `FinancialSituationMemory`, `BaseLLMClient`, `SignalProcessor`
- State types use `TypedDict` with `PascalCase`: `AgentState`, `InvestDebateState`, `RiskDebateState`
- Enums use `PascalCase` with `UPPER_CASE` members: `AnalystType.MARKET`, `AnalystType.SOCIAL`
- Use `UPPER_SNAKE_CASE`: `DEFAULT_CONFIG`, `TOOLS_CATEGORIES`, `VENDOR_METHODS`, `VENDOR_LIST`
- Module-level private constants use `_UPPER_SNAKE_CASE`: `_PASSTHROUGH_KWARGS`, `_PROVIDER_CONFIG`
## Code Style
- No automated formatter configured (no black, ruff, or yapf config files detected)
- Indentation: 4 spaces (standard Python)
- Line length varies; no enforced limit. Some lines exceed 120 characters, especially LLM prompt strings
- Trailing commas used inconsistently
- No linter configured (no flake8, pylint, ruff, or mypy config detected)
- No pre-commit hooks
- No CI/CD pipeline detected
- Used selectively, not comprehensively
- Present on class methods and factory function signatures: `def create_llm_client(provider: str, model: str, ...) -> BaseLLMClient`
- `Annotated` types used extensively for LangChain tool parameters: `Annotated[str, "ticker symbol"]`
- `TypedDict` used for agent state definitions in `tradingagents/agents/utils/agent_states.py`
- Missing from most inner function closures and callback signatures
## Import Organization
- Wildcard imports used in some places: `from tradingagents.agents import *` in `tradingagents/graph/setup.py` and `tradingagents/agents/utils/agent_states.py`
- Relative imports within packages: `from .base_client import BaseLLMClient` in `tradingagents/llm_clients/`
- Absolute imports across packages: `from tradingagents.dataflows.interface import route_to_vendor`
- `__all__` lists defined in key `__init__.py` files: `tradingagents/agents/__init__.py`, `tradingagents/llm_clients/__init__.py`
- None. All imports use full dotted paths.
## Error Handling
- Broad `try/except Exception as e` is the dominant pattern throughout the codebase
- Error returns as formatted strings rather than raising exceptions: `return f"Error retrieving fundamentals for {ticker}: {str(e)}"` in `tradingagents/dataflows/y_finance.py`
- This is intentional for LLM tool functions: errors become text the LLM can interpret
- `ValueError` raised for invalid configuration: `raise ValueError(f"Unsupported LLM provider: {provider}")` in `tradingagents/llm_clients/factory.py`
- Custom exception class: `AlphaVantageRateLimitError` in `tradingagents/dataflows/alpha_vantage_common.py` for vendor fallback logic
- Fallback pattern in `tradingagents/dataflows/interface.py`: `route_to_vendor()` tries primary vendor, catches rate limit errors, falls back to alternatives
- Silent error swallowing with `print()` in `tradingagents/dataflows/y_finance.py`: `print(f"Error getting bulk stockstats data: {e}")` followed by fallback logic
- Raise `ValueError` for programming errors (bad config, invalid arguments)
- Return error strings from data-fetching tool functions (these become LLM context)
- Raise `RuntimeError` when all vendor fallbacks exhausted
## Logging
- Debug output via `print()`: `print(f"Error getting stockstats indicator data...")` in `tradingagents/dataflows/y_finance.py`
- Rich console for CLI user-facing output: `console = Console()` with `console.print()` in `cli/main.py` and `cli/utils.py`
- No log levels, no log files, no structured log format
## Agent/Node Design Pattern
- Analyst nodes: `create_*_analyst(llm)` - take only LLM, use tool-calling
- Researcher/manager nodes: `create_*(llm, memory)` - take LLM + memory for reflection
- Trader node: uses `functools.partial` to bind name: `return functools.partial(trader_node, name="Trader")`
- All nodes return a dict updating parts of `AgentState`
- Analyst nodes return `{"messages": [result], "<type>_report": report}`
- Debate nodes return `{"investment_debate_state": {...}}` or `{"risk_debate_state": {...}}`
## LLM Prompt Construction

**Patterns:** Analysts often use LangChain `ChatPromptTemplate.from_messages()` with `MessagesPlaceholder` and `.partial()` for tool-calling flows (`tradingagents/agents/analysts/`). Researchers, managers, and the trader frequently use plain f-strings or string prompts with `llm.invoke(...)`. Prefer **ChatPromptTemplate + bind_tools** when tools are required; otherwise f-string prompts are acceptable for simpler nodes. Keep system vs human roles explicit and keep prompts close to the node factory that uses them.

## Configuration Pattern
- `tradingagents/dataflows/config.py` holds a module-level `_config` dict
- `set_config()` and `get_config()` provide access
- `DEFAULT_CONFIG` in `tradingagents/default_config.py` provides defaults
- Config is a plain `dict`, not a dataclass or Pydantic model
## Module Design
- Key `__init__.py` files define `__all__` lists for controlled exports
- `tradingagents/agents/__init__.py` re-exports all agent factory functions
- `tradingagents/llm_clients/__init__.py` exports `BaseLLMClient` and `create_llm_client`
- `tradingagents/agents/__init__.py` serves as a barrel file aggregating all agent creators
- `tradingagents/dataflows/interface.py` acts as the routing interface for all data operations
## Docstrings
- Present on classes and public methods, especially in `tradingagents/graph/` and `tradingagents/llm_clients/`
- Google-style docstrings with `Args:` and `Returns:` sections: see `tradingagents/llm_clients/factory.py`, `tradingagents/graph/trading_graph.py`
- Missing from most inner closure functions and some utility functions
- Tool functions use docstrings as LLM-readable descriptions (LangChain `@tool` convention)
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## Pattern Overview
- Stateful DAG execution via LangGraph `StateGraph` with a single shared `AgentState`
- Factory-function pattern: every agent is created by a `create_*()` function that returns a closure
- Two debate loops (investment + risk) with configurable round limits
- Vendor-abstracted data layer with pluggable providers (yfinance, Alpha Vantage)
- BM25-based memory system for reflection/learning across runs
- Two LLM tiers: "quick think" (analysts, researchers, debators) and "deep think" (managers)
## Layers
- Purpose: Interactive terminal interface for configuring and running analyses
- Location: `cli/`
- Contains: Typer app, Rich UI rendering, interactive prompts, stats tracking
- Depends on: `tradingagents.graph.trading_graph`, `tradingagents.default_config`
- Used by: End users via `tradingagents` CLI command
- Purpose: Constructs, configures, and executes the LangGraph agent workflow
- Location: `tradingagents/graph/`
- Contains: Graph setup, state propagation, conditional routing, reflection, signal processing
- Depends on: Agents layer, LLM clients layer, dataflows config
- Used by: CLI layer, `main.py` script, any Python consumer
- Purpose: Implements all LLM-powered agent behaviors as node functions
- Location: `tradingagents/agents/`
- Contains: Analyst nodes, researcher debate nodes, trader node, manager nodes, risk debator nodes
- Depends on: LangChain prompts/tools, dataflows (via tool functions), memory system
- Used by: Graph orchestration layer
- Purpose: Retrieves and routes financial data from external providers
- Location: `tradingagents/dataflows/`
- Contains: Vendor-specific implementations (yfinance, Alpha Vantage), routing interface, caching
- Depends on: External APIs (yfinance, Alpha Vantage), local filesystem cache
- Used by: Agent tool functions in `tradingagents/agents/utils/`
- Purpose: Abstracts LLM provider creation behind a factory pattern
- Location: `tradingagents/llm_clients/`
- Contains: Base client ABC, provider-specific clients (OpenAI, Anthropic, Google), factory
- Depends on: LangChain provider packages (langchain-openai, langchain-anthropic, langchain-google-genai)
- Used by: Graph orchestration layer (`TradingAgentsGraph.__init__`)
## Data Flow
- Single `AgentState` (extends LangGraph `MessagesState`) flows through the entire graph
- `AgentState` contains: messages, company/date, 4 analyst reports, `InvestDebateState`, `RiskDebateState`, trader plan, final decision
- `InvestDebateState` tracks bull/bear debate history and round count
- `RiskDebateState` tracks aggressive/conservative/neutral debate history and round count
- State is immutable within LangGraph; nodes return partial state dicts that get merged
## Key Abstractions
- Purpose: Create agent node callables with captured LLM and memory references
- Examples: `tradingagents/agents/analysts/market_analyst.py::create_market_analyst`, `tradingagents/agents/researchers/bull_researcher.py::create_bull_researcher`, `tradingagents/agents/trader/trader.py::create_trader`
- Pattern: Each `create_*()` function returns an inner function (closure) that takes `state` and returns a partial state dict
- Purpose: Decouple agents from specific data providers
- Examples: `tradingagents/dataflows/interface.py::route_to_vendor`, `tradingagents/agents/utils/core_stock_tools.py::get_stock_data`
- Pattern: Tool functions (decorated with `@tool`) call `route_to_vendor(method_name, *args)`, which resolves the configured vendor and calls the appropriate implementation. Supports automatic fallback on rate-limit errors.
- Purpose: Create LLM instances for any supported provider via a single entry point
- Examples: `tradingagents/llm_clients/factory.py::create_llm_client`
- Pattern: Factory function maps provider string to client class; each client implements `BaseLLMClient` ABC with `get_llm()` and `validate_model()`
- Purpose: Store and retrieve past trading reflections for agent learning
- Examples: `tradingagents/agents/utils/memory.py::FinancialSituationMemory`
- Pattern: BM25-based lexical similarity search over stored situation-recommendation pairs. No external API or embedding model required.
## Entry Points
- Location: `main.py`
- Triggers: Direct script execution (`python main.py`)
- Responsibilities: Creates `TradingAgentsGraph` with custom config, calls `propagate()`, prints decision
- Location: `cli/main.py`
- Triggers: `tradingagents` shell command (registered via `pyproject.toml` `[project.scripts]`)
- Responsibilities: Interactive wizard for selecting provider, models, analysts, depth; runs analysis with Rich live UI; displays progress and final report
- Location: `tradingagents/graph/trading_graph.py`
- Triggers: `from tradingagents.graph.trading_graph import TradingAgentsGraph`
- Responsibilities: Programmatic usage as a Python library
## Error Handling
- Data vendor fallback: `route_to_vendor()` catches `AlphaVantageRateLimitError` and falls through to next vendor in chain (`tradingagents/dataflows/interface.py`)
- Analyst validation: `GraphSetup.setup_graph()` raises `ValueError` if no analysts selected (`tradingagents/graph/setup.py`)
- LLM provider validation: `create_llm_client()` raises `ValueError` for unsupported providers (`tradingagents/llm_clients/factory.py`)
- No structured error handling within agent nodes; LLM failures propagate as exceptions
## Cross-Cutting Concerns

- **Logging:** Mostly `print()` and Rich `console.print()`; no centralized log levels yet — see `.planning/codebase/INTEGRATIONS.md` for recommended structured logging path.
- **Security:** Secrets only via environment / `.env` (gitignored); never commit API keys.
- **Observability:** `StatsCallbackHandler` tracks LLM/tool/token counts in CLI runs; no external APM.
- **Caching:** File cache under `tradingagents/dataflows/data_cache/`; Redis dependency declared but unused in code today.
- **Reliability:** Vendor fallback in `route_to_vendor()` for rate limits; LLM calls generally lack retries (see `.planning/codebase/CONCERNS.md`).

<!-- GSD:architecture-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
