# Current Milestone

Scanner pipeline is feature-complete and quality-improved. Focus shifts to Macro Synthesis JSON robustness and the `pipeline` CLI command.

# Recent Progress

- End-to-end scanner pipeline operational (`python -m cli.main scan --date YYYY-MM-DD`)
- All 53 tests passing (14 original + 9 scanner fallback + 15 env override + 15 industry deep dive)
- Environment variable config overrides merged (PR #9)
- Thread-safe rate limiter for Alpha Vantage implemented
- Vendor fallback (AV -> yfinance) broadened to catch `AlphaVantageError`, `ConnectionError`, `TimeoutError`
- **PR #13 merged**: Industry Deep Dive quality fixed — enriched industry data (price returns), explicit sector routing via `_extract_top_sectors()`, tool-call nudge in `run_tool_loop`
- Finnhub integrated as third vendor: insider transactions (primary), earnings calendar (new), economic calendar (new)
- ADR 010 written documenting Finnhub vendor decision and paid-tier constraints

# Active Blockers

- Macro Synthesis JSON parsing fragile — DeepSeek R1 sometimes wraps output in markdown code blocks; `json.loads()` in CLI may fail
- `pipeline` CLI command (scan -> filter -> per-ticker deep dive) not yet implemented
