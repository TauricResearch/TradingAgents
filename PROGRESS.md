# Scanner Pipeline — Progress Tracker

## Milestone: End-to-End Scanner ✅ COMPLETE

The 3-phase scanner pipeline runs successfully from `python -m cli.main scan --date 2026-03-17`.

### What Works

| Component | Status | Notes |
|-----------|--------|-------|
| Phase 1: Geopolitical Scanner | ✅ | Ollama/qwen3.5:27b, uses `get_topic_news` |
| Phase 1: Market Movers Scanner | ✅ | Ollama/qwen3.5:27b, uses `get_market_movers` + `get_market_indices` |
| Phase 1: Sector Scanner | ✅ | Ollama/qwen3.5:27b, uses `get_sector_performance` (SPDR ETF proxies) |
| Phase 2: Industry Deep Dive | ✅ | Ollama/qwen3.5:27b, uses `get_industry_performance` + `get_topic_news` |
| Phase 3: Macro Synthesis | ✅ | OpenRouter/DeepSeek R1, pure LLM synthesis (no tools) |
| Parallel fan-out (Phase 1) | ✅ | LangGraph with `_last_value` reducers |
| Tool execution loop | ✅ | `run_tool_loop()` in `tool_runner.py` |
| Data vendor fallback | ✅ | AV → yfinance fallback on `AlphaVantageError` |
| CLI `--date` flag | ✅ | `python -m cli.main scan --date YYYY-MM-DD` |
| .env loading | ✅ | Keys loaded from project root `.env` |
| Tests (23 total) | ✅ | 14 original + 9 scanner fallback tests |

### Output Quality (Sample Run 2026-03-17)

| Report | Size | Content |
|--------|------|---------|
| geopolitical_report | 6,295 chars | Iran conflict, energy risks, central bank signals |
| market_movers_report | 6,211 chars | Top gainers/losers, volume anomalies, index trends |
| sector_performance_report | 8,747 chars | Sector rotation analysis with ranked table |
| industry_deep_dive_report | — | Ran but was sparse (Phase 1 reports were the primary context) |
| macro_scan_summary | 10,309 chars | Full synthesis with stock picks and JSON structure |

### Files Created/Modified

**New files:**
- `tradingagents/agents/utils/tool_runner.py` — inline tool execution loop
- `tradingagents/agents/utils/scanner_states.py` — ScannerState with reducers
- `tradingagents/agents/utils/scanner_tools.py` — LangChain tool wrappers for scanner data
- `tradingagents/agents/scanners/` — all 5 scanner agent modules
- `tradingagents/graph/scanner_graph.py` — ScannerGraph orchestrator
- `tradingagents/graph/scanner_setup.py` — LangGraph workflow setup
- `tradingagents/dataflows/yfinance_scanner.py` — yfinance data for scanner
- `tradingagents/dataflows/alpha_vantage_scanner.py` — Alpha Vantage data for scanner
- `tests/test_scanner_fallback.py` — 9 fallback tests

**Modified files:**
- `tradingagents/default_config.py` — per-tier LLM provider config (hybrid setup)
- `tradingagents/llm_clients/openai_client.py` — Ollama remote host support
- `tradingagents/dataflows/interface.py` — broadened fallback catch to `AlphaVantageError`
- `cli/main.py` — `scan` command with `--date` flag, `.env` loading fix
- `.env` — real API keys

---

## TODOs / Future Work

### High Priority

- [ ] **Industry Deep Dive quality**: Phase 2 report was sparse in test run. The LLM receives Phase 1 reports as context but may not call tools effectively. Consider: pre-fetching industry data and injecting it directly, or tuning the prompt to be more directive about which sectors to drill into.

- [ ] **Macro Synthesis JSON parsing**: The `macro_scan_summary` should be valid JSON but DeepSeek R1 sometimes wraps it in markdown code blocks or adds preamble text. The CLI tries `json.loads(summary)` to build a watchlist table — this may fail. Add robust JSON extraction (strip markdown fences, find first `{`).

- [ ] **`pipeline` command**: `cli/main.py` has a `run_pipeline()` placeholder that chains scan → filter → per-ticker deep dive. Not yet implemented.

### Medium Priority

- [ ] **Scanner report persistence**: Reports are saved to `results/macro_scan/{date}/` as `.md` files. Verify this works and add JSON output option.

- [ ] **Rate limiting for parallel tool calls**: Phase 1 runs 3 agents in parallel, each calling tools. If tools hit the same API (e.g., Google News), they may get rate-limited. Consider adding delays or a shared rate limiter.

- [ ] **Ollama model validation**: Before running the pipeline, validate that the configured model exists on the Ollama server (call `/api/tags` endpoint). Currently a 404 error is only caught at first LLM call.

- [ ] **Test coverage for scanner agents**: Current tests cover data layer (yfinance/AV fallback) but not the agent nodes themselves. Add integration tests that mock the LLM and verify tool loop behavior.

### Low Priority

- [ ] **Configurable MAX_TOOL_ROUNDS**: Currently hardcoded to 5 in `tool_runner.py`. Could be made configurable via `DEFAULT_CONFIG`.

- [ ] **Streaming output**: Scanner currently runs with `Live(Spinner(...))` — no intermediate output. Could stream phase completions to the console.

- [ ] **Remove top-level `llm_provider` references**: `scanner_graph.py` lines 69, 78 still fall back to `self.config["llm_provider"]` which doesn't exist in current config. Works because per-tier providers are always set, but will crash if they're ever `None`.
