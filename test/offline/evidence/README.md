# Offline evidence — time filtering

Test scaffold for time filtering of evidence items. No test functions yet.

## Running

The repo's pytest config sets `testpaths = ["tests"]`, so run this suite by
path:

```sh
pytest test/offline/evidence -m "not integration"
```

## Red / green

- **Red**: `src/egta/evidence/time_policy.py` does not exist, so
  `_target.py` records `MISSING_REASON` and re-raises the `ModuleNotFoundError`,
  which fails collection. This is the expected starting state.
- **Green**: once `egta.evidence.time_policy` provides `is_admissible` and
  `TimeVerdict`, the import succeeds and `TARGET_AVAILABLE` is `True`.

Fixtures are `test/offline/evidence/fixtures/E-01.json` … `E-30.json`
(read-only). `conftest.py` also provides `frozen_now`,
`load_case(case_id)` and `iter_items(case)`.
