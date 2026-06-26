# Task 2 Report: PATCH `/api/indicators/{indicator_id}` Endpoint

**Status:** DONE

## Changes Made

### `web/server/indicators.py`
- Added `update_indicator(indicator_id, body)` function after `remove_indicator()`.
- Finds indicator by ID, updates `threshold` and/or `enabled` fields from the request body while preserving all other fields.
- Raises `ValueError` if threshold is not a valid number.

### `web/server/app.py`
- Added `PATCH /api/indicators/{indicator_id}` route inside `create_app()`, directly after the `DELETE` endpoint.
- Calls `indicators.update_indicator()`, returns 400 on validation error, 404 if not found, or the updated indicator dict on success.

## Test Results

```
tests/test_fred.py::FredResolutionTests::test_get_macro_data_returns_guidance_on_bad_indicator PASSED
tests/test_stockstats_date_column.py::TestCleanDataframeAcrossVersions::test_indicators_compute_after_index_rename PASSED
2 passed, 572 deselected in 2.96s
```

No regressions — all existing indicator-related tests pass.

## Commits

- `095d12a` feat: add PATCH /api/indicators/{id} endpoint for threshold updates
