# Mistakes & Lessons Learned

Documenting bugs and wrong assumptions to avoid repeating them.

---

## Mistake 1: Scanner agents had no tool execution

**What happened**: All 4 scanner agents (geopolitical, market movers, sector, industry) used `llm.bind_tools(tools)` but only checked `if len(result.tool_calls) == 0: report = result.content`. When the LLM chose to call tools (which it always does when tools are available), nobody executed them. Reports were always empty strings.

**Root cause**: Copied the pattern from existing analysts (`news_analyst.py`) without realizing that the trading graph has separate `ToolNode` graph nodes that handle tool execution in a routing loop. The scanner graph has no such nodes.

**Fix**: Created `tool_runner.py` with `run_tool_loop()` that executes tools inline within the agent node.

**Lesson**: When an LLM has `bind_tools`, there MUST be a tool execution mechanism — either graph-level `ToolNode` routing or inline execution. Always verify the tool execution path exists.

---

## Mistake 2: Assumed yfinance `Sector.overview` has performance data

**What happened**: Wrote `get_sector_performance_yfinance` using `yf.Sector("technology").overview["oneDay"]` etc. This field doesn't exist — `overview` only returns metadata (companies_count, market_cap, industries_count).

**Root cause**: Assumed the yfinance Sector API mirrors the Yahoo Finance website which shows performance data. It doesn't.

**Fix**: Switched to SPDR ETF proxy approach — download ETF prices and compute percentage changes.

**Lesson**: Always test data source APIs interactively before writing agent code. Run `python -c "import yfinance as yf; print(yf.Sector('technology').overview)"` to see actual data shape.

---

## Mistake 3: yfinance `top_companies` — ticker is the index, not a column

**What happened**: Used `row.get('symbol')` to get ticker from `top_companies` DataFrame. Always returned N/A.

**Root cause**: The DataFrame has `index.name = 'symbol'` — tickers are the index, not a column. The actual columns are `['name', 'rating', 'market weight']`.

**Fix**: Changed to `for symbol, row in top_companies.iterrows()`.

**Lesson**: Always inspect DataFrame structure with `.head()`, `.columns`, and `.index` before writing access code.

---

## Mistake 4: Hardcoded Ollama localhost URL

**What happened**: `openai_client.py` had `base_url = "http://localhost:11434/v1"` hardcoded for Ollama provider, ignoring the `self.base_url` config. User's Ollama runs on `192.168.50.76:11434`.

**Fix**: Changed to `host = self.base_url or "http://localhost:11434"` with `/v1` suffix appended.

**Lesson**: Never hardcode URLs. Always use the configured value with a sensible default.

---

## Mistake 5: Only caught `RateLimitError` in vendor fallback

**What happened**: `route_to_vendor()` only caught `RateLimitError`. Alpha Vantage demo key returns "Information" responses (not rate limit errors) and other `AlphaVantageError` subtypes. Fallback to yfinance never triggered.

**Fix**: Broadened catch to `AlphaVantageError` (base class).

**Lesson**: Fallback mechanisms should catch the broadest reasonable error class, not just specific subtypes.

---

## Mistake 6: AV scanner functions silently caught errors

**What happened**: `get_sector_performance_alpha_vantage` and `get_industry_performance_alpha_vantage` caught exceptions internally and embedded error strings in the output (e.g., `"Error: ..."` in the result dict). `route_to_vendor` never saw an exception, so it never fell back to yfinance.

**Fix**: Made both functions raise `AlphaVantageError` when ALL queries fail, while still tolerating partial failures.

**Lesson**: Functions used inside `route_to_vendor` MUST raise exceptions on total failure — embedding errors in return values defeats the fallback mechanism.

---

## Mistake 7: LangGraph concurrent write without reducer

**What happened**: Phase 1 runs 3 scanners in parallel. All write to `sender` (and other shared fields). LangGraph raised `INVALID_CONCURRENT_GRAPH_UPDATE` because `ScannerState` had no reducer for concurrent writes.

**Fix**: Added `_last_value` reducer via `Annotated[str, _last_value]` to all ScannerState fields.

**Lesson**: Any LangGraph state field written by parallel nodes MUST have a reducer. Use `Annotated[type, reducer_fn]`.

---

## Mistake 8: .env file had placeholder values in worktree

**What happened**: Created `.env` in worktree with template values (`your_openrouter_key_here`). User's real keys were only in main repo's `.env`. `load_dotenv()` loaded the worktree placeholder, so OpenRouter returned 401.

**Root cause**: Created `.env` template during setup without copying real keys. `load_dotenv()` with `override=False` (default) keeps the first value found.

**Fix**: Updated worktree `.env` with real keys. Also added fallback `load_dotenv()` call for project root.

**Lesson**: When creating `.env` files, always verify they have real values, not placeholders. When debugging auth errors, first check `os.environ.get('KEY')` to see what value is actually loaded.

---

## Mistake 9: Removed top-level `llm_provider` but code still references it

**What happened**: Removed `llm_provider` from `default_config.py` (since we have per-tier providers). But `scanner_graph.py` line 78 does `self.config.get(f"{tier}_llm_provider") or self.config["llm_provider"]` — would crash if per-tier provider is ever None.

**Status**: Works currently because per-tier providers are always set. But it's a latent bug.

**TODO**: Add a safe fallback or remove the dead code path.
