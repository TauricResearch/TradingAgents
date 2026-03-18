<!-- Last verified: 2026-03-18 -->

# Conventions

## Configuration

- Env var override pattern: `TRADINGAGENTS_<UPPERCASE_KEY>=value` — empty/unset preserves default. (`default_config.py`)
- Per-tier overrides: each tier has `{tier}_llm_provider` and `{tier}_backend_url`, falling back to top-level `llm_provider` and `backend_url`. (`default_config.py`)
- `load_dotenv()` runs at module level in `default_config.py` — import-order-independent. Check actual env var values when debugging auth. (`default_config.py`)
- `llm_provider` and `backend_url` must always exist at top level — `scanner_graph.py` and `trading_graph.py` use them as fallbacks. (ADR 006)
- `mid_think_llm` defaults to `None`, meaning mid-tier falls back to `quick_think_llm`. (`default_config.py`)

## Agent Creation

- Factory pattern: `create_X(llm)` returns a closure `_node(state)`. Some factories take extra params: `create_bull_researcher(llm, memory)`, `create_trader(llm, memory)`. (`tradingagents/agents/`)
- When `bind_tools()` is used, there MUST be a tool execution path — either `ToolNode` in graph or `run_tool_loop()` inline. (ADR 004)

## Tool Execution

- Trading graph: analysts use `ToolNode` in the LangGraph graph with conditional routing (`should_continue_X`). (`graph/setup.py`)
- Scanner agents: use `run_tool_loop()` inline — no `ToolNode`, tools execute inside the agent node. (`agents/utils/tool_runner.py`)
- `MAX_TOOL_ROUNDS = 5` — max iterations of tool calling before returning. (`tool_runner.py`)
- `MIN_REPORT_LENGTH = 2000` — if first response is shorter and has no tool calls, a nudge message is appended asking the LLM to call tools. Fires at most once. (`tool_runner.py`)

## Vendor Routing

- Fail-fast by default (ADR 011). Only methods in `FALLBACK_ALLOWED` get cross-vendor fallback:
  - `get_stock_data`
  - `get_market_indices`
  - `get_sector_performance`
  - `get_market_movers`
  - `get_industry_performance`
- Never add news, indicator, or financial-statement tools to `FALLBACK_ALLOWED` — data contracts differ across vendors. (ADR 011)
- Functions inside `route_to_vendor` must RAISE on failure, not embed errors in return values. (`interface.py`)
- Catch `(AlphaVantageError, FinnhubError, ConnectionError, TimeoutError)`, not just `RateLimitError`. (`interface.py`)
- Exception chaining required: `raise RuntimeError(...) from last_error`. (ADR 011)
- 2-level routing: category-level (`data_vendors` config dict) + tool-level override (`tool_vendors` config dict). (`interface.py`)

## yfinance Gotchas

- `top_companies` has ticker as the DataFrame INDEX, not a column. Access via `.index`, not a column name. (ADR 003)
- `Sector.overview` has NO performance data. Use ETF proxies (SPDR sector ETFs) for sector performance. (ADR 003)
- Always use `.head(10)` for both download and display in industry performance. (ADR 009)

## LangGraph State

- Any state field written by parallel nodes MUST have a reducer (`Annotated[str, reducer_fn]`). (ADR 005)
- `ScannerState` uses `_last_value` reducer (keeps newest value) for all report fields. (`scanner_states.py`)
- State classes: `AgentState` (trading), `InvestDebateState` (debate sub-state), `RiskDebateState` (risk sub-state), `ScannerState` (scanner). (`agent_states.py`, `scanner_states.py`)

## Threading & Rate Limiting

- Never hold a lock during `sleep()` or IO. Pattern: release lock, sleep outside, re-acquire. (ADR 007)
- Alpha Vantage: 75 calls/min (premium). (`alpha_vantage_common.py`)
- Finnhub: 60 calls/min (free tier). (`finnhub_common.py`)
- Finnhub paid-tier endpoints (`/stock/candle`, `/financials-reported`, `/indicator`) must never be called on free key. (ADR 010)

## Ollama

- Never hardcode `localhost:11434`. Use configured `base_url` from config. (ADR 001)

## CLI Patterns

- Typer for command definitions, Rich for live UI. (`cli/main.py`)
- `MessageBuffer` — deque-based singleton tracking agent statuses, reports, tool calls. Fixed agents grouped by team (`FIXED_AGENTS`), analysts selectable. (`cli/main.py`)
- `StatsCallbackHandler` — token and timing statistics for display. (`cli/stats_handler.py`)
- Scan results saved as `{key}.md` files to `results/macro_scan/{scan_date}/`. (`cli/main.py`)

## Pipeline Patterns

- `MacroBridge` is the facade class for scan → filter → per-ticker analysis. (`pipeline/macro_bridge.py`)
- `ConvictionLevel = Literal["high", "medium", "low"]`; `CONVICTION_RANK = {"high": 3, "medium": 2, "low": 1}`. (`macro_bridge.py`)
- `extract_json()` handles DeepSeek R1 `<think>` blocks, markdown fences, and raw JSON. (`json_utils.py`)

## Testing

- Run tests: `conda activate tradingagents && pytest tests/ -v`
- Skip integration tests: `pytest tests/ -v -m "not integration"`
- Skip paid-tier tests: `pytest tests/ -v -m "not paid_tier"`
- Mocking vendor methods: patch `VENDOR_METHODS` dict entries directly (it stores function refs), not module attributes. (`interface.py`)
- Env isolation: always mock env vars before `importlib.reload()` — `load_dotenv()` leaks real `.env` values otherwise.
- `callable()` returns False on LangChain `@tool` objects — use `hasattr(x, "invoke")` instead.

## Error Handling

- Fail-fast by default — no silent fallback unless method is in `FALLBACK_ALLOWED`. (ADR 011)
- Alpha Vantage hierarchy: `AlphaVantageError` → `APIKeyInvalidError`, `RateLimitError`, `ThirdPartyError`, `ThirdPartyTimeoutError`, `ThirdPartyParseError`. (`alpha_vantage_common.py`)
- Finnhub hierarchy: `FinnhubError` → `APIKeyInvalidError`, `RateLimitError`, `ThirdPartyError`, `ThirdPartyTimeoutError`, `ThirdPartyParseError`. (`finnhub_common.py`)
