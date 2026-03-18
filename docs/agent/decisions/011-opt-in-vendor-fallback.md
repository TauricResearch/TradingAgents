---
type: decision
status: active
date: 2026-03-18
agent_author: "claude"
tags: [data, vendor, fallback, fail-fast]
related_files: [tradingagents/dataflows/interface.py, tests/test_vendor_failfast.py]
---

## Context

The previous `route_to_vendor()` silently tried every available vendor when the primary failed. This is dangerous for trading software — different vendors return different data contracts (e.g., AV news has sentiment scores, yfinance doesn't; stockstats indicator names are incompatible with AV API names). Silent fallback corrupts signal quality without leaving a trace.

## The Decision

- Default to fail-fast: only methods in `FALLBACK_ALLOWED` get cross-vendor fallback.
- `FALLBACK_ALLOWED` contains only methods where data contracts are vendor-agnostic: `get_stock_data`, `get_market_indices`, `get_sector_performance`, `get_market_movers`, `get_industry_performance`.
- All other methods raise `RuntimeError` immediately when the primary vendor fails.
- Error messages include method name and vendors tried for debuggability.
- Exception chaining (`from last_error`) preserves the original cause.

Supersedes: ADR 002 (which assumed universal fallback was safe).

## Constraints

- Adding a method to `FALLBACK_ALLOWED` requires verifying that all vendor implementations return compatible data contracts.
- Never add news tools (`get_news`, `get_global_news`, `get_topic_news`) — AV has sentiment scores that yfinance lacks.
- Never add `get_indicators` — stockstats names (`close_50_sma`) differ from AV API names (`SMA`).
- Never add financial statement tools — different fiscal period alignment across vendors.

## Actionable Rules

- When adding a new data method, it is fail-fast by default. Only add to `FALLBACK_ALLOWED` after verifying data contract compatibility across all vendor implementations.
- Functions inside `route_to_vendor` must RAISE on failure, not embed errors in return values (unchanged from ADR 002).
- Test both fail-fast and fallback paths when modifying vendor routing.
