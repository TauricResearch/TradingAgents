# PR13: Watchlist Research Board

PR13 adds a compact, local-only watchlist board to the research cockpit. It
extends `tradingagents/research_platform` without modifying the upstream
TradingAgents agent graph or calling an external vendor.

## Board contents

For every explicit watchlist symbol, the board shows:

- latest cached closing price and price date;
- a summarized cache-health state;
- latest archived research timestamp;
- the latest manual decision and risk decision, when present.

Rows are derived from local JSONL artifacts and immutable research archives.
Selecting a symbol on the board changes the existing single-ticker cockpit
view; it does not create a research run or mutate the watchlist.

## Data semantics

`missing` or `lagging` is a cache-availability observation, not an investment
recommendation. A symbol can have a complete archived report while its current
mutable cache is missing data, so the board deliberately surfaces the two
states separately.
