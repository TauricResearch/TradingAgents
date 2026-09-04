# Task 7 Report — Earnings Cache Refresh

## Status

Implemented and verified in isolation. Options remain disabled by default. No
LaunchAgent was loaded, and no real network or broker call was made.

## Implementation

- Added `refresh_earnings(symbols, fetch, now)`, which accepts only unique
  supported symbols, requires one explicit `CONFIRMED` future date per symbol,
  and emits the approved Wall Street Horizon cache shape with an aware ISO
  retrieval timestamp.
- Added the fixed seven-symbol Wall Street Horizon page map and a production
  fetcher that uses `urllib.request.Request`, a fixed user agent, and a 30-second
  timeout.
- Added `write_earnings_cache(path, symbols, fetch, now)`, which completes the
  entire refresh before creating a sibling temporary file, flushes and `fsync`s
  it, then atomically replaces the configured cache. Failed refreshes leave an
  existing cache and directory contents unchanged.
- Added a CLI that reads the existing env-backed `watchlist` and
  `options_earnings_path`, requires exactly seven unique configured symbols,
  writes the cache, and logs only symbols, dates, and timestamps.
- Added focused tests with injected fetchers/openers; no test performs a real
  network request.

## TDD Evidence

### RED

Command:

```text
.venv/bin/python -m pytest -q tests/test_refresh_earnings.py
```

Observed before production code: collection failed with `ImportError: cannot
import name 'refresh_earnings' from 'scripts'` because the script was absent.

### GREEN

The same focused command after implementation: `10 passed` with six unrelated
pytest temporary-directory cleanup warnings.

## Verification Results

- Focused Task 7 suite: `10 passed`.
- Integrated options/configuration/automation/earnings run: `134 passed, 8
  failed`; all eight failures are in the pre-existing modified
  `tests/test_automation_cycle.py` work and concern covered-share suppression,
  live cancellation acknowledgements, profit exits, and submission error labels.
- Full repository suite: `905 passed, 1 skipped, 11 failed, 24 warnings, 69
  subtests passed` in 284.82 seconds. The 11 failures are confined to pre-existing
  modified `tests/test_alpaca_execution.py` and `tests/test_automation_cycle.py`;
  none exercises or imports Task 7 files. The skip is the existing optional
  `langchain_aws` dependency.
- `python -m compileall -q` on both owned Python files: exit 0.
- Ruff on both owned Python files: `All checks passed!`.
- Owned-file `git diff --check`: exit 0.
- `launchctl list` contains no TradingAgents or earnings service.

## Self-review

- Confirmed the CLI is the cardinality boundary: it must refresh exactly seven
  unique configured symbols. The reusable function accepts a supported subset
  so callers can receive the required confirmed-date error for one symbol, as
  specified by the plan tests.
- Confirmed duplicate symbols and unsupported symbols fail before any fetch.
- Confirmed ambiguous, malformed, unconfirmed, current-date, and past dates fail
  closed and cannot replace the cache.
- Confirmed New York local date is used for the future-date boundary, matching
  the existing cache reader.
- Confirmed every configured symbol is fetched once and output once, and no
  environment values or credentials are logged.
- Confirmed temporary files are created beside the target and removed if writing
  or replacement fails.

## Preserved External Work

The repository had unrelated modified and untracked files before Task 7 began.
They were neither edited nor staged by this task. The broader-suite failures
listed above remain outside Task 7 ownership.
