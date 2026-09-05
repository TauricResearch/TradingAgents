# PR16: A-share Financial Quality Snapshots

PR16 adds a point-in-time financial-quality snapshot for A-share research. It
extends only `tradingagents.research_platform`; the upstream TradingAgents
dataflow remains unchanged.

## Source records

The Tushare Pro adapter retrieves four issuer-specific statement endpoints:

- `income`
- `balancesheet`
- `cashflow`
- `fina_indicator`

The adapter retains the existing daily valuation snapshot and appends a
separate `financial_report_YYYY-MM-DD` snapshot when records are available.

## Point-in-time rule

A report period is eligible only when the source record's `ann_date` is on or
before the research run's `as_of_date`. For each endpoint, the latest available
revision for the selected report period is used. A future-announced report is
never substituted for the last disclosed period.

## Metrics

The financial-quality snapshot preserves vendor-reported values for revenue,
net income, operating profit, operating cash flow, free cash flow, assets,
liabilities, equity, ROE, ROA, margins, leverage, liquidity, and selected
growth ratios. It also derives only two transparent ratios when the necessary
source values are present:

- operating cash flow / net income
- liabilities / total assets

Announcement dates are included as metrics so that the underlying availability
cutoff can be inspected in the Cockpit and archived Markdown report.

Hong Kong remains on the prior Tushare daily snapshot coverage until a
comparable issuer-level financial-statement source is configured.
