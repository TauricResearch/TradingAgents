# Refactor Suggestions & Observations

Items noticed during the architecture refactor that are worth future attention.

---

## P1 — Correctness / Data Integrity

### 1. Memory log entries for non-running tickers never get resolved
`_resolve_pending_entries()` in `trading_graph.py` only resolves entries whose ticker matches the current run. Entries for other tickers silently accumulate indefinitely. A background sweep or a periodic batch-resolve on startup could drain the backlog without requiring a dedicated re-run of every ticker.

### 2. Signal extraction is fragile for multi-word sentiments
`signal_processing.py` uses keyword search over free text. If a future LLM uses phrasing like "not a buy" or "avoid buying", the extractor would false-positive to `Buy`. Anchoring regex to the structured output fields (which are already Pydantic-constrained) is cleaner than re-parsing prose.

### 3. No idempotency on checkpoint clear
`clear_checkpoint()` is called after a successful run. If the process crashes between `_log_state()` and `clear_checkpoint()`, the next run will replay from the checkpoint into a state where the log file already exists — potentially writing a duplicate JSON file. Atomic rename + checkpoint clear in one transaction would close this window.

---

## P2 — Performance

### 4. yfinance history calls are not cached between runs on the same date
`_fetch_returns()` in `trading_graph.py` calls `yf.Ticker(ticker).history(...)` every run. On a busy backtest loop this adds significant latency. A simple TTL file cache (similar to what exists in `dataflows/y_finance.py`) would help.

### 5. Data fetcher tools lack concurrency within a single analyst
The fundamentals analyst calls `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement` sequentially. These are independent HTTP calls; running them with `asyncio.gather` or `ThreadPoolExecutor` would halve analyst run time for this node.

### 6. Redundant news fetches across analysts
Both social media analyst and news analyst call `get_news()` with overlapping queries. Deduplicating at the dataflow layer (memoize by query+date range in session) would reduce API call count.

---

## P3 — Maintainability

### 7. Prompts are inlined in analyst factory functions
Analyst system prompts are long string literals inside `create_*_analyst()` functions — impossible to version, translate, or A/B test without touching Python. Moving prompts to YAML files (keyed by analyst type and language) would separate content from code and make prompt iteration far faster.

### 8. Agent names are duplicated between setup.py and conditional_logic.py
Node name strings like `"Bull Researcher"`, `"Bear Researcher"`, `"Portfolio Manager"` appear in both `setup.py` (as `add_node` keys) and `conditional_logic.py` (as router return values). A single `NodeNames` enum or constants module would prevent silent routing bugs when a name changes in one place but not the other.

### 9. `_log_state` in trading_graph.py is tightly coupled to analyst field names
Even after the `analyst_reports` dict refactor, `_log_state` still constructs the JSON manually field-by-field. Using `dataclasses` or Pydantic for `AgentState` snapshot serialization would make the log format self-documenting and easier to extend.

### 10. No version field in the logged JSON state file
`full_states_log_<date>.json` has no schema version. Adding `"schema_version": 1` to the top level would make future migrations mechanical rather than guesswork.

### 11. `selected_analysts` parameter accepts plain strings with no validation
If a caller passes `["markt", "social"]`, `setup_graph` silently skips the typo. Adding a validation step with a clear error message would catch misconfiguration early.

### 12. Docker image rebuilds fully on any source change
The `Dockerfile` copies source code before `pip install`. Reversing the order (install deps first, then copy source) would let Docker cache the dependency layer and rebuild only the app layer on code changes — significantly faster dev iteration.

---

## P4 — Developer Experience

### 13. No Makefile / task runner
Common operations (run tests, run linter, build Docker, run the CLI) require knowing the exact commands. A `Makefile` or `justfile` with `make test`, `make lint`, `make run` would lower the barrier for new contributors.

### 14. Type stubs missing for dataflows module
`dataflows/interface.py` uses `Any` for return types throughout. Adding proper return type annotations (even `str | pd.DataFrame`) would let IDEs and mypy catch misuse at call sites.

### 15. No integration test for the full propagate() path
All existing tests cover isolated units (memory log, signal processing, checkpoint, structured output). There is no smoke test that exercises the full `TradingAgentsGraph.propagate()` path with a mock LLM, which means regressions in graph wiring are only caught by humans running the CLI.
