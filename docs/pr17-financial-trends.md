# PR17: Financial Quality History and Trends

PR17 extends the PR16 financial-quality snapshot into a bounded A-share report
history. The change stays inside `tradingagents.research_platform`.

## History policy

The Tushare financial statement rows already fetched for one research run are
normalized into up to eight financial-report snapshots. A report period enters
the history only when its source record has `ann_date <= as_of_date`.

Each period keeps the latest available revision for every statement endpoint.
The resulting snapshots are stored alongside the existing daily valuation
snapshot without changing the artifact-store schema.

## Views

- The Cockpit retains the latest Financial Quality panel.
- A Financial Trend table shows the disclosed report periods with revenue, net
  income, operating cash flow, and ROE.
- The archived Markdown report adds a matching Financial Trend table when at
  least two disclosed periods are available.

Hong Kong retains its prior daily-data scope until a compatible issuer-level
financial statement source is configured.
