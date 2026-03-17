---
type: decision
status: active
date: 2026-03-17
agent_author: "claude"
tags: [data, yfinance, sector-performance]
related_files: [tradingagents/dataflows/yfinance_scanner.py]
---

## Context

`yfinance.Sector("technology").overview` returns only metadata (companies_count, market_cap, etc.) — no performance data (oneDay, oneWeek, etc.).

## The Decision

Use SPDR sector ETFs as proxies:
```python
sector_etfs = {
    "Technology": "XLK", "Healthcare": "XLV", "Financials": "XLF",
    "Energy": "XLE", "Consumer Discretionary": "XLY", ...
}
```
Download 6 months of history via `yf.download()` and compute 1-day, 1-week, 1-month, YTD percentage changes from closing prices.

## Constraints

- `yfinance.Sector.overview` has NO performance data — do not attempt to use it.
- `top_companies` has ticker as INDEX, not column. Always use `.iterrows()`.

## Actionable Rules

- Always test yfinance APIs interactively before writing agent code.
- Always inspect DataFrame structure with `.head()`, `.columns`, and `.index`.
