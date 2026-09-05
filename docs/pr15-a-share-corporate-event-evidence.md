# PR15: A-share Corporate Event Evidence

PR15 extends the local Tushare Pro adapter with company-specific A-share
disclosures.  It remains inside `tradingagents.research_platform` and does not
modify the upstream TradingAgents dataflow.

## Evidence scope

For A-share symbols, `get_news` now reads these Tushare endpoints:

- `forecast`: performance forecasts.
- `express`: performance express reports.

Each returned record is normalized into the existing `NewsItem` contract with:

- the exact disclosure date as `published_at` at UTC midnight because Tushare
  exposes a date, not a time of day;
- the requesting run's `as_of_date` for point-in-time filtering;
- a stable source identifier containing endpoint, Tushare ticker, announcement
  date, report period, and update flag;
- only vendor fields present in the response, without inferred sentiment or
  synthetic links.

The provider filters records to the requested date window and excludes any
announcement later than the run's `as_of_date`.

## Coverage boundary

Tushare's generic news feeds are not symbol-specific, so they are not matched
to tickers using title text.  Hong Kong tickers continue to return an empty
company-event evidence set until a source that supplies reliable issuer-level
identifiers and publication timestamps is added.

Tushare account permissions remain authoritative.  An unavailable `forecast`
or `express` endpoint becomes a clear local research-job failure rather than a
silently incomplete event record.
