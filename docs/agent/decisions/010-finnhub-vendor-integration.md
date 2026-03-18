---
type: decision
status: active
date: 2026-03-18
agent_author: "claude"
tags: [data, finnhub, vendor, calendar, insider]
related_files: [tradingagents/dataflows/interface.py, tradingagents/dataflows/finnhub_scanner.py, tradingagents/agents/utils/scanner_tools.py]
---

## Context

Live integration testing of the Finnhub API (2026-03-18) confirmed free-tier availability
of 6 endpoints. Evaluation identified two high-value unique capabilities (earnings calendar,
economic calendar) and two equivalent-quality replacements (insider transactions, company profile).

## The Decision

- Add Finnhub as a third vendor alongside yfinance and Alpha Vantage.
- `get_insider_transactions` → Finnhub primary (free, same data + MSPR aggregate bonus signal)
- `get_earnings_calendar` → Finnhub only (new capability, not in AV at any tier)
- `get_economic_calendar` → Finnhub only (new capability, FOMC/CPI/NFP dates)
- AV remains primary for news (per-article sentiment scores irreplaceable), market movers (TOP_GAINERS_LOSERS full-market coverage), and financial statements (Finnhub requires paid)

## Paid-Tier Endpoints (do NOT use on free key)

- `/stock/candle` → HTTP 403 on free tier (use yfinance for OHLCV)
- `/financials-reported` → HTTP 403 on free tier (use AV for statements)
- `/indicator` → HTTP 403 on free tier (yfinance/stockstats already primary)

## Constraints

- `FINNHUB_API_KEY` env var required — `APIKeyInvalidError` raised if missing
- Free tier rate limit: 60 calls/min — enforced by `_rate_limited_request` in `finnhub_common.py`
- Calendar endpoints return empty list (not error) when no events exist in range — return formatted "no events" message, do NOT raise

## Actionable Rules

- Finnhub functions in `route_to_vendor` must raise `FinnhubError` (not return error strings) on total failure
- `route_to_vendor` fallback catch must include `FinnhubError` alongside `AlphaVantageError`
- Calendar functions return graceful empty-state strings (not raise) when API returns empty list — this is normal behaviour, not an error
- Never add Finnhub paid-tier endpoints (`/stock/candle`, `/financials-reported`, `/indicator`) to free-tier routing
- `get_insider_transactions` is excluded from `FALLBACK_ALLOWED` — Finnhub MSPR aggregate data has no equivalent in other vendors (ADR 011)
