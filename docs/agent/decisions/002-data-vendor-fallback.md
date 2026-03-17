---
type: decision
status: active
date: 2026-03-17
agent_author: "claude"
tags: [data, alpha-vantage, yfinance, fallback]
related_files: [tradingagents/dataflows/interface.py, tradingagents/dataflows/alpha_vantage_scanner.py, tradingagents/dataflows/yfinance_scanner.py]
---

## Context

Alpha Vantage free/demo key doesn't support ETF symbols and has strict rate limits. Need reliable data for scanner.

## The Decision

- `route_to_vendor()` catches `AlphaVantageError` (base class) plus `ConnectionError` and `TimeoutError` to trigger fallback.
- AV scanner functions raise `AlphaVantageError` when ALL queries fail (not silently embedding errors in output strings).
- yfinance is the fallback vendor and uses SPDR ETF proxies for sector performance instead of broken `Sector.overview`.

## Constraints

- Functions inside `route_to_vendor` must RAISE on failure, not embed errors in return values.
- Fallback catch must include `(AlphaVantageError, ConnectionError, TimeoutError)`, not just `RateLimitError`.

## Actionable Rules

- Any new data vendor function used with `route_to_vendor` must raise on total failure.
- Test both the primary and fallback paths when adding new vendor functions.
