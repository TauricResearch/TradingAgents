# PR14: Tushare Pro China and Hong Kong Data

This increment adds a local Tushare Pro adapter under
`tradingagents.research_platform`.  It does not change the upstream
TradingAgents dataflow.

## Configuration

Set `TUSHARE_TOKEN` in the local environment before starting the cockpit.  The
token is read only at provider construction time and is never stored in the
research artifacts, reports, or source tree.

The package now declares `tushare>=1.4.29`.  Install the project dependencies
again when setting up a new environment.

## Symbol routing

The local job form has three data-provider choices:

- `Auto`: Tushare Pro for six-digit A-share tickers and `.SH`, `.SZ`, `.SS`,
  or `.HK` tickers; Yahoo Finance for other symbols.
- `Tushare Pro`: explicitly use the China/Hong Kong adapter.
- `Yahoo Finance`: explicitly use the existing Yahoo adapter.

`600519`, `600519.SH`, `600519.SS`, `000001`, and `0700.HK` are normalized to
the Tushare formats `600519.SH`, `000001.SZ`, and `00700.HK`.

## Initial data scope

- A shares: `daily` bars and `daily_basic` daily valuation snapshots.
- Hong Kong: `hk_daily_adj` bars and its available daily snapshot fields.
- News: this initial provider version left the evidence set empty.  PR15 adds
  date-granular A-share corporate-event evidence; Hong Kong issuer events still
  wait for a source with reliable issuer identifiers and timestamps.

Tushare endpoint permissions and point requirements still apply to the local
account.  A provider permission error is returned as a failed local research
job in the cockpit; it does not crash the server.
