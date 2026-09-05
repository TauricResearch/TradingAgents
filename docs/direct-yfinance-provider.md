# Direct YFinance Provider

`YFinanceProvider` is the next data-layer step after the legacy wrapper.

Import it directly:

```python
from tradingagents.research_platform.yfinance_provider import YFinanceProvider
```

It returns normalized platform contracts without first rendering data as
markdown or CSV:

- `get_price_bars(...) -> list[PriceBar]`
- `get_fundamentals(...) -> list[FundamentalSnapshot]`
- `get_news(...) -> list[NewsItem]`

## Why This Exists

The legacy `dataflows` path is optimized for LLM prompts. It formats prices,
fundamentals, and news into strings. That is fine for the current graph, but it
is fragile for a personal research platform because downstream systems need
machine-readable records.

The direct provider keeps these concerns separate:

- Data adapters produce typed records.
- Agents consume compact snapshots and evidence ids.
- Backtests read bars and signals, not prose.
- Risk reviews consume structured signals and portfolio state.

## Testing Pattern

`YFinanceProvider` accepts a `ticker_factory` so tests can inject fake ticker
objects and stay offline:

```python
provider = YFinanceProvider(ticker_factory=lambda symbol: fake_ticker)
```

This keeps normalization logic covered without depending on live Yahoo Finance
responses.

## Remaining Work

1. Add cache storage for normalized yfinance artifacts.
2. Add fixture-based integration tests for representative yfinance responses.
3. Replace selected analyst tools so they can cite normalized artifact ids.
4. Move common provider errors into a shared data-layer error module when the
   package exports are updated.
