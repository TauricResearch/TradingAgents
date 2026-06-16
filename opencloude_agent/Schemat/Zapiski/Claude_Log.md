---
type: log
tags:
  - opencloude-agent
  - claude-log
---

# Claude Log

## 2026-06-16

### Fixed yfinance MultiIndex market parsing

- Root cause: `yf.download(..., group_by="ticker")` returns MultiIndex columns like `(Ticker, Price)`, so the old `MarketWatcher` looked for flat `"Close"` and `"Volume"` columns and produced `null` values in `results/continuous/watch_log.jsonl`.
- Fix: added `MarketWatcher.snapshot_from_dataframe(...)` with MultiIndex handling, corrected `_latest_close(...)` to operate on an already-selected ticker frame, and changed `benchmark_return_20d` to mean the benchmark ticker's 20d return.
- Added `relative_strength_20d = return_20d - benchmark_return_20d` to the market snapshot.
- Updated `OpportunityScanner._score(...)` to use `relative_strength_20d` directly.
- Added regression test: `test_market_watcher_parser_handles_yfinance_multiindex_columns`.
- Verification: `python -m unittest opencloude_agent.tests.test_opencloude_agent` passes.
- Runtime smoke test: one cycle now produces non-null market data and opportunities, though current market scores are below buy threshold, so decisions are still `hold`.

- Zmapowałem projekt `opencloude_agent` do pełnego szkieletu notatek w sejfie Obsidian `Schemat`.
- Dodałem notatki dla projektu, kodu, architektury, runtime, testów, wyników i indeksu.
- Zachowano konwencję wikilinków i frontmatter YAML zgodnie z [[../CLAUDE.md]].
