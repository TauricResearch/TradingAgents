# v2 Tavily News: Budgeted Multi-Source News Curator

## Status

Implemented as a data-layer curator in this workspace. A separate graph node can be added later if the workflow needs more agent-visible control.

## Changes

- Added Tavily as the default primary news source.
- Kept yfinance and Alpha Vantage as auxiliary news sources for cross-checking and fallback.
- Added conservative Tavily defaults:
  - `search_depth=basic`
  - `max_results=5`
  - `topic=finance`
  - `include_raw_content=False`
  - `include_answer=False`
  - `include_images=False`
  - `auto_parameters=False`
- Added fallback from Tavily `topic=finance` to `topic=news` when the API rejects the finance topic.
- Added raw Tavily response logging under:
  `~/.tradingagents/logs/<TICKER>/<DATE>/data/`
  - The saved audit file always includes `request_id` and a stable `usage.credits` key, even when Tavily omits usage in the response.
- Added a lightweight News Curator equivalent in the dataflow layer:
  - source labeling
  - deduplication by URL/title
  - max item limiting
  - compact Markdown package for downstream News and Social analysts

## Verification

- Mock Tavily tests should assert default budget parameters, raw response logging, and max result behavior.
- News aggregation tests should assert Tavily + yfinance deduplication and source failure fallback.
