# Alpaca Market-Data Integration Report

## Scope

- Added the environment-backed `use_alpaca_market_data` switch with a false default.
- When enabled, daily OHLCV for exactly AAPL, MSFT, NVDA, AMZN, META, GOOG, and TSLA uses Alpaca's IEX feed first and Yahoo Finance only when Alpaca is unavailable, empty, malformed, stale, or outside the requested range.
- When disabled, Yahoo remains the sole data path; Yahoo errors and typed stale-data failures are not replaced by an unexpected Alpaca call or credential requirement.
- Every symbol outside that seven-symbol allowlist remains on Yahoo even when Alpaca equity market data is enabled.
- Preserved inclusive end dates, UTC-to-naive date normalization, the canonical OHLCV column shape, provider-separated caching, and look-ahead filtering.
- Alpaca fallback logs omit upstream exception details, and configuration errors never include credential values.

## Initial Integration Evidence (Historical)

The evidence in this section records the initial implementation cycle. The later formal-fix sections describe the final behavior.

- RED: the strict-opt-in, non-equity routing, injectable-client, and malformed-response tests initially produced five failures. A separate missing-frame test then reproduced an untyped `AttributeError`.
- GREEN: `.venv/bin/pytest -q tests/test_alpaca_ohlcv_fallback.py` passed with 11 tests.
- Integrated: the market-data, date-boundary, environment, cache, stale-data, no-data, symbol, and vendor-routing slice passed with 81 tests.
- Staged-only: the same 81-test slice and owned-file Ruff check passed from a temporary archive of `git write-tree`, independently of concurrent unstaged cash-policy edits.
- Static: Ruff passed for every owned Python file, and `git diff --check` reported no whitespace errors.
- Full: `.venv/bin/pytest -q` passed with 1,034 tests and 69 subtests; one optional `langchain_aws` test was skipped, with only known model and pytest temporary-directory warnings.

## Review Conclusions

- The original unconditional Alpaca fallback while `use_alpaca_market_data=false` was a defect because ordinary Yahoo-only runs could unexpectedly require an optional dependency and broker credentials.
- Alpaca eligibility is the exact AAPL, MSFT, NVDA, AMZN, META, GOOG, and TSLA allowlist; all other symbols bypass Alpaca.
- No real network or broker call was made; request behavior was verified with injected clients and fetchers.

## Formal Fix Round 1

- Separated cache namespaces into `YFin` and `Alpaca-IEX`. An enabled approved-symbol run uses Yahoo's namespace only after a typed Alpaca failure, never as Alpaca provenance or as a reason to skip the next Alpaca attempt; disabled runs never read the Alpaca namespace.
- Replaced unconditional `reset_index()` handling with one strict canonicalizer that returns exactly Date/Open/High/Low/Close/Volume, normalizes timestamps, requires finite positive prices and nonnegative volume, and enforces coherent highs and lows before caching or return.
- Added `AlpacaMarketDataError`. Missing credentials/dependencies, Alpaca API errors, request timeouts/errors, OS/network failures, empty frames, malformed frames, and stale frames use this sanitized typed boundary. Routing catches only this type; unexpected `RuntimeError` and `TypeError` propagate without invoking Yahoo.
- Restricted Alpaca IEX routing to AAPL, MSFT, NVDA, AMZN, META, GOOG, and TSLA. Every other symbol stays on Yahoo.
- Updated two cache-freshness test fixtures, with coordinator authorization, so they exercise coherent canonical OHLCV rather than the now-invalid Date/Close-only shape.
- RED: the new review tests initially produced 14 behavioral failures across cache contamination, broad fallback, universe overreach, unsanitized network errors, and invalid OHLCV acceptance. One additional failure was isolated to an invalid integer/`inf` test fixture and corrected before implementation assessment.
- RED sanitization follow-up: API, timeout, and OS-error cases proved the original exception cause still retained secret-bearing upstream text; the typed translation now suppresses those causes.
- GREEN: the focused market-data file passed with 35 tests before the final exception matrix was added; the expanded market-data/cache/vendor integration slice then passed with 125 tests. Ruff and `git diff --check` passed.
- Full: `.venv/bin/pytest -q --ignore='tests/test_alpaca_ohlcv_fallback 2.py'` passed with 1,074 tests and 69 subtests; one optional `langchain_aws` test was skipped, with only known model and pytest temporary-directory warnings.
- Staged-only: the 125-test integration slice and owned-file Ruff check passed from a temporary archive of `git write-tree`, independently of the preserved untracked duplicate.
- Preserved user artifact: the untracked `tests/test_alpaca_ohlcv_fallback 2.py` was not modified or deleted. Run alone, it had two passes and two expected failures because it asserts the rejected unconditional false-mode fallback and monkeypatches the superseded no-argument routing helper.

## Formal Fix Round 2

- Kept Alpaca-IEX and Yahoo cache ownership tied to the response provider. A typed Alpaca failure can reuse or populate only the Yahoo cache for that call; it never creates an Alpaca cache entry, so the next enabled call retries Alpaca and can recover.
- Enforced the requested Alpaca date interval as an inclusive normalized range before stale checks, caching, or return. Out-of-range rows, including future look-ahead rows, are discarded; a response with no usable in-range rows raises `AlpacaMarketDataError` and follows the typed Yahoo fallback.
- RED: five focused tests failed against the prior implementation, reproducing Yahoo fallback cached as Alpaca, failure to retry after a transient outage, acceptance of out-of-range rows, and future rows reaching cache handling.
- GREEN: the same five focused tests passed, followed by all 47 market-data fallback tests.
- Integrated: the market-data, date-boundary, environment, cache, stale-data, no-data, symbol, and vendor-routing slice passed with 130 tests.
- Full: `.venv/bin/pytest -q --ignore='tests/test_alpaca_ohlcv_fallback 2.py'` passed with 1,079 tests and 69 subtests; one optional `langchain_aws` test was skipped. The preserved untracked duplicate remained excluded as directed.
- Staged-only/static: the same 130-test integration slice and owned-file Ruff check passed from an archive of `git write-tree`; `git diff --check` also passed.

## Formal Fix Round 3

- Alpaca cache entries and downloads are filtered and validated against the actual consumer `curr_date` before acceptance or cache writes. Rows exclusively after that date are typed unavailable and use Yahoo fallback without creating an Alpaca cache entry.
- A structurally valid but consumer-stale Alpaca cache is treated as a cache miss before the generic final guard. The run retries Alpaca; a typed failure can populate Yahoo's cache without deleting or relabeling the stale Alpaca entry, and a later validated Alpaca response replaces only the Alpaca entry.
- RED: both consumer-date regressions failed against the prior implementation: future-only data reached the final generic no-data error, while a stale Alpaca cache reached the final generic stale error without attempting either provider.
- GREEN: both focused regressions passed, followed by all 49 market-data fallback tests.
- Integrated: the market-data, date-boundary, environment, cache, stale-data, no-data, symbol, and vendor-routing slice passed with 132 tests.
- Full: `.venv/bin/pytest -q --ignore='tests/test_alpaca_ohlcv_fallback 2.py'` passed with 1,081 tests and 69 subtests; one optional `langchain_aws` test was skipped, with the preserved duplicate excluded as directed.
- Staged-only/static: the same 132-test integration slice and owned-file Ruff check passed from an archive of `git write-tree`; `git diff --check` also passed.

## Formal Fix Round 4

- Added the normalized consumer `curr_date` to Alpaca cache filenames while retaining the existing symbol, provider, and download-window components. Yahoo cache naming and behavior are unchanged.
- Consumer-date scoping prevents an Alpaca snapshot truncated for an earlier historical request from satisfying a later historical request. Repeating the same consumer date still reuses its cache, and the existing current-day TTL applies to that date-specific path.
- RED: a sequential 2026-08-25 then 2026-08-27 request reused the first truncated cache and omitted the valid 2026-08-27 bar.
- GREEN: the regression passed with two date-specific cache entries, two Alpaca fetches across distinct dates, and no additional fetch for the repeated 2026-08-27 request; all 50 focused market-data tests then passed.
- Integrated: the market-data, date-boundary, environment, cache, stale-data, no-data, symbol, and vendor-routing slice passed with 133 tests.
- Full: `.venv/bin/pytest -q --ignore='tests/test_alpaca_ohlcv_fallback 2.py'` passed with 1,082 tests and 69 subtests; one optional `langchain_aws` test was skipped, with the preserved duplicate excluded as directed.
- Staged-only/static: the same 133-test integration slice and owned-file Ruff check passed from an archive of `git write-tree`; `git diff --check` also passed.
