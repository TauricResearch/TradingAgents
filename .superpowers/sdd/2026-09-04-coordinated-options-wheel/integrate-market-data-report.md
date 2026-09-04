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

## Formal Fix Round 1

- Separated cache namespaces into `YFin` and `Alpaca-IEX`; enabled approved-symbol runs cannot read or write the Yahoo-mode path, and disabled runs cannot read the Alpaca-mode path.
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
