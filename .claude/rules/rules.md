# Coding Rules

## General
- Write clear, readable code over clever code.
- Keep functions small and focused — one responsibility per function.
- Avoid deep nesting; prefer early returns.
- Delete dead code; don't comment it out.
- No magic numbers — use named constants.

## Python
- Target Python 3.11+; use modern syntax (match/case, `X | Y` unions, etc.).
- Use type hints on all public functions and methods.
- Prefer `pathlib.Path` over `os.path`.
- Use f-strings for string formatting.
- Use `dataclasses` or `pydantic` for structured data, not plain dicts.
- Raise specific exceptions, never bare `except:` or `except Exception:` silently.
- Use `logging` instead of `print` for anything that isn't direct user output.

## Naming
- `snake_case` for variables, functions, modules.
- `PascalCase` for classes.
- `UPPER_SNAKE_CASE` for module-level constants.
- Prefix private helpers with `_`.
- Boolean variables/functions should read as predicates: `is_ready`, `has_error`.

## Project Layout (Modular by Responsibility)
Organize code by responsibility area. Each package groups related functionality together.

```
cli/                             # CLI entry point and user interaction
├── main.py                      # Typer app, run_analysis(), display logic
├── utils.py                     # CLI helpers: prompts, selections, user input
├── models.py                    # CLI enums (AnalystType, etc.)
├── stats_handler.py             # Callback handler for LLM/tool call stats
├── announcements.py             # Fetch and display announcements
├── notion_publisher.py          # Publish analysis to Notion API
└── config.py                    # CLI-specific config

tradingagents/                   # Core library
├── default_config.py            # DEFAULT_CONFIG dict
├── agents/                      # LLM agent nodes (one file per agent role)
│   ├── analysts/                # market, social, news, fundamentals analysts
│   ├── researchers/             # bull_researcher, bear_researcher
│   ├── managers/                # research_manager, portfolio_manager
│   ├── risk_mgmt/               # aggressive, conservative, neutral debators
│   ├── trader/                  # trader node
│   ├── schemas.py               # Structured output schemas (Pydantic)
│   └── utils/                   # Shared agent utilities
│       ├── agent_states.py      # TypedDict state definitions (AgentState, etc.)
│       ├── agent_utils.py       # Re-exports all @tool functions
│       ├── memory.py            # TradingMemoryLog (past context, reflection)
│       ├── *_tools.py           # @tool functions grouped by data domain
│       ├── structured.py        # Structured output helpers
│       └── rating.py            # Rating utilities
│
├── dataflows/                   # Data fetching + vendor routing (no LLM logic)
│   ├── interface.py             # route_to_vendor(), VENDOR_METHODS registry
│   ├── config.py                # set_config(), get_vendor()
│   ├── yfinance_client.py       # yfinance implementations
│   ├── alpha_vantage*.py        # Alpha Vantage implementations (stock, news, etc.)
│   ├── binance.py               # Binance kline implementations
│   ├── binance_models.py        # Binance data models (KlineInterval, etc.)
│   └── stockstats_utils.py      # Technical indicator calculations
│
├── graph/                       # LangGraph orchestration
│   ├── trading_graph.py         # TradingAgentsGraph class (main entry)
│   ├── setup.py                 # GraphSetup: build StateGraph, wire nodes + edges
│   ├── conditional_logic.py     # should_continue_* branching functions
│   ├── propagation.py           # Propagator: create initial state
│   ├── reflection.py            # Reflector: post-trade reflection
│   ├── signal_processing.py     # Extract BUY/HOLD/SELL from PM output
│   └── checkpointer.py          # SqliteSaver checkpoint for crash recovery
│
└── llm_clients/                 # LLM provider abstraction
    ├── base_client.py           # Abstract base class
    ├── openai_client.py         # OpenAI-compatible client
    ├── anthropic_client.py      # Anthropic client
    ├── azure_client.py          # Azure OpenAI client
    ├── factory.py               # create_llm_client() factory
    ├── model_catalog.py         # MODEL_OPTIONS for CLI selection
    └── validators.py            # VALID_MODELS whitelist

tests/                           # Flat test directory
├── conftest.py
└── test_*.py                    # One test file per concern

docs/                            # Design documents and flow diagrams
scripts/                         # One-off utility scripts
```

**Rules:**
- `cli/` depends on `tradingagents/` — never the reverse.
- `dataflows/` is pure data I/O — no LLM calls, no agent logic.
- `agents/` contains LLM node functions + `@tool` definitions — delegates data fetching to `dataflows/`.
- `graph/` orchestrates agents via LangGraph — no direct data fetching or LLM prompt construction.
- `llm_clients/` is provider abstraction only — no business logic.
- New features go into the existing package that matches their responsibility. Only create a new top-level package if no existing one fits.
- When adding a new data source: add implementation in `dataflows/`, register in `interface.py`, expose via `agents/utils/*_tools.py`.
- When adding a new agent role: add to `agents/<category>/`, wire into `graph/setup.py`.
- When adding a new CLI feature: add to `cli/`, import from `tradingagents/` as needed.
- When adding a new LLM provider: add client in `llm_clients/`, register in `factory.py`, update `model_catalog.py` and `validators.py`.

## Testing
- Every public function should have at least one test.
- Test file naming: `tests/test_<module>.py` (flat directory, no subdirectories).
- Use `pytest` fixtures for shared setup; avoid global state in tests.
- Prefer real behavior over mocks; only mock at I/O boundaries (network, disk, time).
- Run tests before committing: `pytest --tb=short`.

## Git
- Commit messages use imperative mood: "Add feature" not "Added feature".
- One logical change per commit.
- Never commit secrets, `.env` files, or credentials.
- Branch names: `feat/`, `fix/`, `chore/` prefixes.

## Dependencies
- Pin direct dependencies with minimum versions (`>=`), not exact pins, in `pyproject.toml`.
- Add new dependencies to `[project.dependencies]` (runtime) or `[project.optional-dependencies] dev` (dev-only).
- Keep `environment.yml` in sync when adding conda-managed packages.

## Security
- Never log or print sensitive data (tokens, passwords, PII).
- Validate all external input at the boundary (API responses, user input, file content).
- Use `secrets` module for generating tokens, not `random`.
