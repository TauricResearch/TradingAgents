# Koral Equities: £10,000 GBP forward paper portfolio (v1)

This addition is **paper-only**, and is fully isolated from Trading 212, your ISA, and any brokerage API. No real money can be traded by this code. It uses TradingAgents' existing multi-agent ratings and a separate, deterministic trading ledger. It is a forward trading experiment, not proof of an edge.

## Installation

From this repository's root (Python 3.11+):

```sh
pip install -e .
koral-equities-paper init
koral-equities-paper status
```

To perform an after-close batch (requires the configured AI provider and its credentials, and Yahoo Finance connectivity):

```sh
koral-equities-paper run --tickers AAPL MSFT NVDA AMZN GOOGL META JPM COST
koral-equities-paper status
```

If you want a different state directory, pass `--state /path/to/portfolio.json` **before** `init`, `run`, or `status`. Default: `~/.tradingagents/paper/portfolio.json`. Each invocation checks against the New York clock and does **not** process a US session until 5:30pm New York time (market close + forex candle buffer). Running again that night does not duplicate a completed agent decision or an executed order. If the data provider or model fails, the affected symbol is not given a synthetic recommendation.

When the US market is closed, `run` loads each completed daily session since the last update, fills **orders queued after the previous close** at the next observed session's open, applies stop orders (including gap/slippage modelling), and marks portfolio equity. It then asks the multi-agent framework for new ratings for the watchlist. `Buy`/`Overweight` can queue a long; `Sell`/`Underweight` can queue an exit for an existing paper position; `Hold`/`REVIEW` does nothing. Decisions are queued for the **next** session — never the decision day's close. Portfolio context includes current stock positions, but never misrepresents GBP cash as USD cash. Agent reports and memory are saved alongside the paper ledger.

### Fixed research configuration

| Parameter | Setting |
|---|---|
| Starting capital | £10,000 GBP, simulated |
| Trade stop-based risk budget | 2% of current equity, approximate (includes simulated trading costs) |
| Aggregate initial stop risk | 6% of equity |
| Number of positions | 5 maximum |
| Maximum allocation per symbol | 30% of equity |
| Gross exposure | 100% maximum, long-only, whole shares |
| Equity drawdown guard | 10% of the historical high-water mark; sticky halt on **new** buys |
| Position time exit | Queue sale after 20 sessions, fill at following open |
| Default initial stop | 8% below the signal close; modify with `--stop-pct` |
| Simulated slippage | 0.10% per side |
| Simulated conversion fee | 0.15% each purchase/sale |
| Benchmark | SPY share price converted to GBP (price return only) |

Risk is a **budget, not a loss guarantee**: opening gaps, slippage and FX movements can exceed 2%; stop decisions use the worst of the day's opening price and the stop level. Positions are marked in GBP using USD/GBP exchange-rate history; realised P&L includes simulated conversion fees. All inputs must be valid — missing bars fail closed. A 10% drawdown halts **new** positions; existing positions retain stops/time exits and are not automatically liquidated.

### Boundaries of this version

- This is a **daily manually invoked command**, not an always-on broker simulator or hosted scheduler. The strategy only advances when run. No API connection to Trading 212 is included; no live orders or funds are accessed.
- Yahoo daily OHLCV and FX are proxies. A daily-bar engine cannot establish the true intraday bid/ask, price path, auction fill, trading halt or available liquidity. Corporate actions such as stock splits/dividends need to be handled before this is used to draw firm performance conclusions.
- Stop placement is a baseline 8% rule, **not a strategy-derived stop**, and costs are approximate. The stock watchlist is a starting sample, not an unbiased historical S&P 500 membership snapshot.
- Because model calls depend on changing LLMs and text feeds, store and review reports; they are not automatically reproducible, and no strategy alpha is established merely by a rating or successful unit test.
- `koral-equities-paper init` refuses to overwrite an existing ledger. JSON is written atomically. A `.lock` file prevents parallel CLI runs. After a confirmed crashed run (and only then), remove its stale `.lock` manually.

## Validation

```sh
pip install -e '.[dev]'
pytest -q tests/test_paper_engine.py
```

Before even considering real money: longer out-of-sample testing; total-return benchmarks (SPY dividends included); robust price/FX feeds and corporate-action handling; review of spreads, gaps, fills, market calendars, taxes, ISA/API restrictions; independent reconciliation; and a real kill switch. Keep existing personal ISA holdings entirely outside this ledger.

## When one stock has malformed price data

The feed validates daily OHLC. If an unheld candidate such as JPM has an invalid
bar or vendor outage, the scan now logs `SKIPPED TICKER`, saves a
`MARKET_DATA_ERROR` event and continues analysing the other candidates. It
does not invent prices, backfill with yesterday's bar or queue an order for
the missing symbol. **If the data is required for a current holding, a pending
order, SPY, or GBP/USD conversion, the entire run still aborts without
writing the portfolio**, because processing with missing risk data would be
unsafe. Any market-data incident is logged for follow-up.


## GBP/USD daily high/low mismatches

Yahoo's daily FX candle may show a positive close a few pips outside its own
high/low interval due to inconsistent FX session windows. FX is only used for
GBP conversion, not price stops or fills. The FX validator therefore requires
finite, positive, broadly plausible GBPUSD open/close/high/low values and halts
on gross discrepancies (>5% from the day's opening quote) or inverted high/low.
It **does not demand that FX O/C be inside the vendor's high/low**, unlike
stocks and SPY. The original FX opening/closing rates are used unchanged,
and any out-of-range OHLC window is logged as `DATA_QUALITY_WARNING` with the
quote date. Negative, zero, nonfinite, wildly outlying, or unavailable FX quotes
still halt the entire simulation without modifying the saved ledger. The
candle shown on 20 Oct 2026 (O=1.33103, H=1.34084, L=1.33103, C=1.33085)
is the reproducing regression case; it is not a licence to repair bad
stock candles or use stale forex rates.

## Manual cancellation of pending paper orders

If a research report has **conditional** instructions that are not supported by the label-based paper execution bridge, use the explicit operator command below **before the next daily run**:

```powershell
.\\.venv\\Scripts\\koral-equities-paper.exe status
.\\.venv\\Scripts\\koral-equities-paper.exe cancel-pending
.\\.venv\\Scripts\\koral-equities-paper.exe status
```

`cancel-pending` cancels every **pending simulated order**, records an `ORDER_CANCELLED` audit event for each, and does not erase prior AI decisions, positions, returns or reports. If no order is queued, it is a no-op. It does not change real brokerage assets or orders. It must be invoked explicitly; installing updated code alone does not cancel any orders.

**Caution:** The original `run` command still translates simple `Buy`/`Overweight` ratings into market-at-next-open orders without enforcing the report's conditions. Do not reactivate the strategy without an approved structured execution bridge. This cancellation command is a manual safety tool, not that bridge.

**Backwards compatibility:** The original `tradingagents` and `tradingagents-paper` console commands remain installed as internal compatibility aliases, but new user-facing commands use Koral Equities names.
