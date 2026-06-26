# Task 1 Report: Track `last_check_at` in Indicator Schedule

## Status: DONE

## Commits
- `4a256b7` feat: track last_check_at in indicator schedule

## Files Modified
- `web/server/storage.py` — Extended `read_indicator_schedule` to return `last_check_at` (default `None`), extended `write_indicator_schedule` to persist `last_check_at` when non-`None`
- `web/server/app.py` — Added `_update_last_check_at()` helper; called from `_indicator_background_loop` in the `else` block after a successful `_run_indicator_check()`

## Test Summary
```
tests/test_fred.py::FredResolutionTests::test_get_macro_data_returns_guidance_on_bad_indicator PASSED
tests/test_stockstats_date_column.py::TestCleanDataframeAcrossVersions::test_indicators_compute_after_index_rename PASSED
```
2 passed, 572 deselected — no regressions.

## Notes
- `last_check_at` is written only when `interval_ms > 0` (i.e., auto-run is configured)
- Timestamps are UTC ISO-8601 with `Z` suffix, consistent with the rest of the codebase
- The `_update_last_check_at` function was extracted into its own helper for clarity
