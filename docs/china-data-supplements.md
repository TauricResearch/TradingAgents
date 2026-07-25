# China A-share supplemental research data

These tools add source-labelled research inputs. They are not substitutes for
OHLCV, do not calculate a recommendation, and can safely degrade without
blocking core price or financial-statement analysis.

| Capability | Tool method | Provider boundary | Failure behaviour |
| --- | --- | --- | --- |
| Capital flow | `get_a_share_capital_flow` | EastMoney direct HTTP | Optional unavailable result |
| Northbound aggregate flow | `get_a_share_northbound_flow` | AKShare `stock_hsgt_hist_em` | Optional unavailable result |
| Northbound ticker holding/ranking | `get_a_share_northbound_holdings` | AKShare `stock_hsgt_hold_stock_em` | Filters market-wide rows by requested security; no match fails closed |
| Disclosed management/shareholder changes | `get_a_share_insider_trades` | AKShare `stock_ggcg_em` | Filters market-wide rows by requested security; identity and timing still require filing verification |
| China macro / cycle inputs | `get_china_macro_indicators` | AKShare public macro adapters | Uses only explicit series: `gdp`, `cpi`, `pmi`, `money_supply`, `lpr`, `industrial_production`, `fx_reserves` |

`get_china_macro_indicators` accepts a comma-separated allowlist, for example
`gdp,cpi,pmi`. Each returned series keeps its provider columns, units, release
calendar, and revision behaviour. It intentionally does not infer an economic
cycle stage. If a requested AKShare adapter is unavailable, the returned
report labels the missing series; if no requested series is available, the
router returns the normal source-unavailable result.

The vendor router applies its normal capability-scoped health tracking:
rate-limit failures cool down for 60 seconds and network/5xx failures for 20
seconds. These capabilities are configured independently under
`china_macro_data` or `a_share_market_data`, so an optional public endpoint
cannot poison core OHLCV routing.
