# Artifact Store

`JsonArtifactStore` is a local-first cache for normalized research records:

```python
from tradingagents.research_platform.artifact_store import JsonArtifactStore
```

It persists JSONL files grouped by artifact type and symbol:

```text
cache/
  prices/NVDA.jsonl
  fundamentals/NVDA.jsonl
  news/NVDA.jsonl
```

Supported records:

- `PriceBar`
- `FundamentalSnapshot`
- `NewsItem`

## Why JSONL First

JSONL is deliberately simple for the first data-layer cut:

- Easy to inspect by hand.
- Works without extra services.
- Round-trips Pydantic models directly.
- Gives backtests, reports, and the future cockpit a shared artifact boundary.

Once the access patterns settle, this interface can gain SQLite, DuckDB, or
Parquet implementations without changing higher layers.

## Lookahead Behavior

Load methods accept `as_of_date` and filter records by availability:

- Prices use `record.provenance.as_of_date`.
- Fundamentals use `record.provenance.as_of_date`.
- News uses `record.as_of_date`.

This keeps historical research and backtests from reading records that were not
available yet.
