# Data Provider Wrapper

PR-2 starts with a compatibility adapter instead of rewriting vendor calls in
one pass.

## Current Adapter

Use `LegacyDataflowProvider` from:

```python
from tradingagents.research_platform.legacy_provider import LegacyDataflowProvider
```

The adapter calls the existing `tradingagents.dataflows.interface.route_to_vendor`
path by default and converts legacy string reports into normalized contracts:

- `PriceBar`
- `FundamentalSnapshot`
- `NewsItem`

This gives new research, backtest, risk, and report code typed records while
the current TradingAgents graph continues to run unchanged.

## Lookahead Rules

The wrapper accepts `as_of_date` on every method:

- Price bars after `as_of_date` are filtered out.
- Fundamentals are tagged with the requested `as_of_date`.
- Legacy news strings do not preserve publication timestamps, so parsed
  `NewsItem.published_at` is conservatively set to midnight on `as_of_date`.

The next migration step should call richer vendor functions directly where
possible so publication timestamps and provider ids are preserved before legacy
formatting.

## Error Rules

Explicit legacy sentinels such as `NO_DATA_AVAILABLE`, `DATA_UNAVAILABLE`, and
`Error fetching...` raise `DataUnavailableError` from:

```python
from tradingagents.research_platform.legacy_provider import DataUnavailableError
```

`No news found...` returns an empty list because no-news is a valid research
state, not a provider failure.

## Next Steps

1. Add direct yfinance adapters that bypass markdown string formatting.
2. Add cache interfaces for normalized artifacts.
3. Replace agent tools gradually so LLM prompts receive compact snapshots plus
   provenance ids instead of raw CSV prose.
4. Feed `TradeSignal` backtests only from normalized records.
