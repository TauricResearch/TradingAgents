# Alpaca Market-Data Integration Report

## Scope

- Added the environment-backed `use_alpaca_market_data` switch with a false default.
- When enabled for an equity-shaped symbol, daily OHLCV uses Alpaca's IEX feed first and Yahoo Finance only when Alpaca is unavailable, empty, malformed, or stale.
- When disabled, Yahoo remains the sole data path; Yahoo errors and typed stale-data failures are not replaced by an unexpected Alpaca call or credential requirement.
- Yahoo-native crypto, futures, forex, and index symbols remain on Yahoo even when Alpaca equity market data is enabled.
- Preserved inclusive end dates, UTC-to-naive date normalization, the existing OHLCV column/cache shape, and look-ahead filtering.
- Alpaca fallback logs omit upstream exception details, and configuration errors never include credential values.

## TDD and Review Evidence

- RED: the strict-opt-in, non-equity routing, injectable-client, and malformed-response tests initially produced five failures. A separate missing-frame test then reproduced an untyped `AttributeError`.
- GREEN: `.venv/bin/pytest -q tests/test_alpaca_ohlcv_fallback.py` passed with 11 tests.
- Integrated: the market-data, date-boundary, environment, cache, stale-data, no-data, symbol, and vendor-routing slice passed with 81 tests.
- Staged-only: the same 81-test slice and owned-file Ruff check passed from a temporary archive of `git write-tree`, independently of concurrent unstaged cash-policy edits.
- Static: Ruff passed for every owned Python file, and `git diff --check` reported no whitespace errors.
- Full: `.venv/bin/pytest -q` passed with 1,034 tests and 69 subtests; one optional `langchain_aws` test was skipped, with only known model and pytest temporary-directory warnings.

## Review Conclusions

- The original unconditional Alpaca fallback while `use_alpaca_market_data=false` was a defect because ordinary Yahoo-only runs could unexpectedly require an optional dependency and broker credentials.
- Alpaca eligibility is intentionally conservative and syntactic: symbols containing Yahoo-specific separators such as `-`, `=`, or `^` bypass Alpaca. If Alpaca later supports additional symbol forms, eligibility can be widened with explicit fixtures.
- No real network or broker call was made; request behavior was verified with injected clients and fetchers.
