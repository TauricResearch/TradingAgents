# PR12: Cache Data Health

PR12 adds a point-in-time health summary for the mutable local cache used by
the research cockpit. It remains isolated to `tradingagents/research_platform`
and does not change the upstream TradingAgents agent graph or add a vendor API.

## Reference date

When an archived run is selected, cache health compares each source's latest
availability date with that run's `as_of` date. This avoids treating an older
historical research run as stale simply because the workstation date is newer.
Without a selected run, the cockpit reports cached availability without making
a freshness claim.

## States

- `aligned`: the source is available as of the selected research date or later.
- `lagging`: cached availability predates the selected research date.
- `missing`: no record of that source is cached.
- `available`: cache exists but no archived research date is selected.

The panel covers normalized market bars, fundamentals, and news. It surfaces
the data layer's declared availability metadata; it does not infer market
truth, trigger external refreshes, or alter historical research artifacts.
