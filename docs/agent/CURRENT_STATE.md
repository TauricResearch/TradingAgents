# Current Milestone

Pre-existing test failures fixed (12 across 5 files). PR #16 (Finnhub) merged. Next: opt-in vendor fallback (ADR 011), Macro Synthesis JSON robustness, `pipeline` CLI command.

# Recent Progress

- End-to-end scanner pipeline operational (`python -m cli.main scan --date YYYY-MM-DD`)
- All 53 tests passing (14 original + 9 scanner fallback + 15 env override + 15 industry deep dive)
- Environment variable config overrides merged (PR #9)
- Thread-safe rate limiter for Alpha Vantage implemented
- Vendor fallback (AV -> yfinance) broadened to catch `AlphaVantageError`, `ConnectionError`, `TimeoutError`
- **PR #13 merged**: Industry Deep Dive quality fixed — enriched industry data (price returns), explicit sector routing via `_extract_top_sectors()`, tool-call nudge in `run_tool_loop`
- Finnhub integrated as third vendor: insider transactions (primary), earnings calendar (new), economic calendar (new)
- ADR 010 written documenting Finnhub vendor decision and paid-tier constraints
- Technical indicators confirmed local-only (stockstats via yfinance OHLCV) — no AV dependency, zero effort to switch
- Finnhub free-tier evaluation complete: 27/41 live tests pass, paid-tier endpoints identified and skipped
- **12 pre-existing test failures fixed** across 5 files: `test_config_wiring.py`, `test_env_override.py`, `test_scanner_comprehensive.py`, `test_scanner_fallback.py`, `test_scanner_graph.py` — root causes: `callable()` wrong for LangChain tools, env var leak via `load_dotenv()` on reload, missing `@pytest.mark.integration` on LLM tests, stale output-file assertions. Full offline suite: 388 passed, 0 failures.

# Planned Next

- **Opt-in vendor fallback (ADR 011)** — fail-fast by default, fallback only for fungible data (OHLCV, indices, sector/industry perf, market movers). Plan: `docs/agent/plans/011-opt-in-vendor-fallback.md`
- Macro Synthesis JSON parsing fragile — DeepSeek R1 sometimes wraps output in markdown code blocks; `json.loads()` in CLI may fail (branch `feat/macro-json-robust-parsing` exists with `extract_json()` utility)
- `pipeline` CLI command (scan -> filter -> per-ticker deep dive) not yet implemented

# Active Blockers

- Macro Synthesis JSON parsing fragile — DeepSeek R1 sometimes wraps output in markdown code blocks; `json.loads()` in CLI may fail
- `pipeline` CLI command (scan -> filter -> per-ticker deep dive) not yet implemented
