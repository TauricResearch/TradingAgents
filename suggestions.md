# Refactor Suggestions & Observations

Items noticed during the architecture refactor that are worth future attention.

---

## P1 — Correctness / Data Integrity

### 1. ✅ Memory log entries for non-running tickers never get resolved
~~`_resolve_pending_entries()` in `trading_graph.py` only resolves entries whose ticker matches the current run.~~
**Fixed** (`refactor/suggestions-cleanup`): `_resolve_pending_entries()` now takes no ticker argument and resolves ALL pending entries on every `propagate()` call. Tests updated accordingly.

### 2. ✅ Signal extraction is fragile for multi-word sentiments
~~`signal_processing.py` uses keyword search over free text.~~
**Mitigated** by the structured-output refactor: the Portfolio Manager now always emits a Pydantic-validated `PortfolioDecision` whose rendered markdown always starts with `**Rating**: X`. The `parse_rating` heuristic anchors to the `Rating:` label first (pass 1) and only falls back to a word scan (pass 2) for legacy or freetext inputs. A "not a buy" phrase in body text is harmless because the label pass fires first.

### 3. No idempotency on checkpoint clear
`clear_checkpoint()` is called after a successful run. If the process crashes between `_log_state()` and `clear_checkpoint()`, the next run will replay from the checkpoint into a state where the log file already exists.
**Partially mitigated**: `_log_state()` opens with `"w"` mode (idempotent overwrite) and `store_decision()` is idempotent (skips if same ticker/date already present). The window still exists but consequences are benign — an atomic rename + checkpoint-clear transaction would close it fully.

---

## P2 — Performance

### 4. ✅ yfinance history calls are not cached between runs on the same date
~~`_fetch_returns()` in `trading_graph.py` calls `yf.Ticker(ticker).history(...)` every run.~~
**Fixed** (`refactor/suggestions-cleanup`): `_fetch_returns()` now maintains a `_returns_cache` dict keyed by `(ticker, trade_date)`. Successful fetches are cached for the lifetime of the session; failed fetches (data not yet available) are retried next call.

### 5. ✅ Data fetcher tools lack concurrency within a single analyst
~~The fundamentals analyst calls `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement` sequentially.~~
**Fixed** (`refactor/suggestions-cleanup`): A new `tradingagents/agents/utils/tool_utils.py` module provides `dispatch_tool_calls()`. When the LLM returns multiple tool calls in a single step, they are dispatched concurrently via `ThreadPoolExecutor`. Applied to all four analysts.

### 6. ✅ Redundant news fetches across analysts
~~Both social media analyst and news analyst call `get_news()` with overlapping queries.~~
**Fixed** (`refactor/suggestions-cleanup-2`): `route_to_vendor()` in `interface.py` now maintains a thread-safe `_session_cache` dict keyed by `(method, *args)`. Identical calls within a single run are served from cache. `clear_session_cache()` is called at the top of every `propagate()` call so stale data never leaks between runs.

---

## P3 — Maintainability

### 7. ✅ Prompts are inlined in analyst factory functions
~~Analyst system prompts are long string literals inside `create_*_analyst()` functions.~~
**Fixed** (`refactor/suggestions-cleanup-2`): Prompts moved to `tradingagents/agents/prompts/` YAML files (one per analyst type: `market_analyst.yaml`, `social_media_analyst.yaml`, `news_analyst.yaml`, `fundamentals_analyst.yaml`). A `load_prompt(analyst_type)` helper in `prompts/__init__.py` loads them at runtime. Analysts call `load_prompt("...")` + `get_language_instruction()` instead of inline strings. YAML files included in the wheel via `pyproject.toml` package-data.

### 8. ✅ Agent names are duplicated between setup.py and conditional_logic.py
~~Node name strings appear in both `setup.py` (as `add_node` keys) and `conditional_logic.py` (as router return values).~~
**Fixed** (`refactor/suggestions-cleanup`): New `tradingagents/graph/node_names.py` module provides a `NodeNames` class (all node names as class attributes) and an `ANALYST_NODE_NAMES` dict. Both `setup.py` and `conditional_logic.py` now import and use these constants. A rename in one place now propagates everywhere.

### 9. ✅ `_log_state` in trading_graph.py is tightly coupled to analyst field names
~~`_log_state` constructs the JSON manually field-by-field.~~
**Fixed** (`refactor/suggestions-cleanup-2`): `RunSnapshot`, `_InvestDebateSnapshot`, and `_RiskDebateSnapshot` Pydantic models added to `schemas.py`. A `build_run_snapshot(trade_date, final_state)` helper constructs the snapshot with safe `.get()` defaults. `_log_state` is now a 4-liner: build snapshot, call `model_dump()`, store in dict, write JSON. Adding or renaming a field means touching `schemas.py` in one place.

### 10. ✅ No version field in the logged JSON state file
~~`full_states_log_<date>.json` has no schema version.~~
**Fixed** (previous refactor): `_log_state()` now writes `"schema_version": 1` at the top level.

### 11. ✅ `selected_analysts` parameter accepts plain strings with no validation
~~If a caller passes `["markt", "social"]`, `setup_graph` silently skips the typo.~~
**Fixed** (previous refactor): `setup_graph()` raises `ValueError` with a clear message listing valid options when an unknown analyst key is passed.

### 12. ✅ Docker image rebuilds fully on any source change
~~The `Dockerfile` copies source code before `pip install`.~~
**Fixed** (`refactor/suggestions-cleanup`): Builder stage now copies `pyproject.toml` + `README.md` + minimal stubs first, installs all dependencies, then copies source and does a `--no-deps` reinstall. The dependency layer is now cache-friendly.

---

## P4 — Developer Experience

### 13. ✅ No Makefile / task runner
~~Common operations require knowing the exact commands.~~
**Fixed** (`refactor/suggestions-cleanup`): `Makefile` added at project root with `install`, `test`, `test-unit`, `test-smoke`, `lint`, `run`, `docker-build`, and `clean` targets.

### 14. ✅ Type stubs missing for dataflows module
~~`dataflows/interface.py` uses `Any` for return types throughout.~~
**Fixed** (`refactor/suggestions-cleanup`): `interface.py` now imports `Any` and a `_DataFrame` alias, and `route_to_vendor` has a `-> str | _DataFrame` return type. `get_vendor` uses `str | None` for its optional parameter.

### 15. ✅ No integration test for the full propagate() path
~~All existing tests cover isolated units; there is no smoke test that exercises the full `TradingAgentsGraph.propagate()` path with a mock LLM.~~
**Fixed** (`refactor/suggestions-cleanup`): `tests/test_graph_integration.py` added with 8 smoke-marked tests. A `_MockLLM` handles `bind_tools()`, `invoke()`, and `with_structured_output()` for all three decision-making schemas. Tests verify: graph compiles, `propagate()` returns a valid tuple, final state contains all required keys, signal is a valid 5-tier rating, memory log receives an entry, and all 4 analysts populate `analyst_reports`.
