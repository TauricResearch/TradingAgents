# Data-Source Decision Table (Phase 2)

Policy: **free-first**. Everything marked *implemented* below is free and
(except FRED) keyless, wired behind injectable-transport adapters in
`tradingagents/pro/ingestion/`. Nothing paid is integrated; paid rows are
**pending sign-off** — approve a row and it becomes a new adapter behind
the same interface.

## Gold (XAU/USD)

| Feed | Source | Cost | Rate limit | Status |
|---|---|---|---|---|
| Futures OHLCV (daily) | yfinance `GC=F` via existing cached loader | free, keyless | yf soft-429, retry built in | **implemented** (`YFinanceDailyBarsFeed`) |
| Spot XAU/USD (true spot + intraday) | OANDA v20 practice API (free demo acct) or Metals-API (~$10+/mo) | free-demo / paid | OANDA: generous | **pending sign-off** — decide broker-demo vs API vendor |
| Silver correlation | derived from `GC=F` + `SI=F` closes | free | — | **implemented** (`GoldCrossAssetFeed`, computed in code) |
| DXY | yfinance `DX-Y.NYB` (daily) + FRED `DTWEXBGS` (broad index) | free | FRED 120 req/min | **implemented** (both) |
| US10Y nominal / real | yfinance `^TNX` + FRED `DGS10`, `DFII10` | free (FRED key) | 120/min | **implemented** |
| Fed funds, CPI YoY, PPI YoY, NFP | FRED `DFF`, `CPIAUCSL` (pc1), `PPIACO` (pc1), `PAYEMS` (chg) — transforms server-side | free (key) | 120/min | **implemented** (`FredMacroFeed`) |
| Gold ETF flows | World Gold Council (free, weekly/monthly files) or GLD volume proxy via yfinance | free | low-frequency | **planned** — WGC file format is manual-ish; propose deferring to Phase 2.1 |
| Central-bank purchases | World Gold Council central-bank stats (free, monthly/quarterly) | free | monthly | **planned** — same WGC adapter |
| COT positioning (managed money) | CFTC public weekly CSV | free | weekly | **planned** — cheap adapter, weekly cadence |
| Session awareness | deterministic code (UTC boundaries, ADR-0012) | — | — | **implemented** (`sessions.py`) |
| Microstructure (ticks, book) | Databento (~$/GB) or Polygon ($199/mo indices+futures) | **paid** | n/a | **pending sign-off** — only needed if we trade sub-hour timeframes |

## Bitcoin (BTC/USD)

| Feed | Source | Cost | Rate limit | Status |
|---|---|---|---|---|
| Spot OHLCV (1m–1w) | Binance `/api/v3/klines` | free, keyless | 6000 weight/min | **implemented** (`BinanceSpotFeed`) |
| Top-of-book quote | Binance `bookTicker` + `ticker/price` | free | same | **implemented** |
| Order-book imbalance | Binance `/api/v3/depth`, imbalance computed in code | free | same | **implemented** |
| Perp funding rate + mark | Binance `fapi/v1/premiumIndex` | free | 2400/min | **implemented** (`BinanceDerivativesFeed`) |
| Open interest | Binance `fapi/v1/openInterest` (+history endpoint available) | free | same | **implemented** |
| Liquidations | Coinglass API ($29+/mo) — Binance removed the public REST endpoint (WS only) | **paid** (or WS collector) | — | **pending sign-off**; free alternative = run a `forceOrder` websocket collector |
| MVRV, realized cap, active addresses | CoinMetrics Community API | free, keyless | ~10 req/6 s | **implemented** (`CoinMetricsFeed`) |
| SOPR, exchange reserves, whale flows | Glassnode ($39+/mo) or CryptoQuant ($39+/mo) | **paid** | — | **pending sign-off** — CoinMetrics community does not carry these |
| Miner hash rate / revenue | blockchain.com charts API | free, keyless | lenient | **implemented** (`BlockchainComFeed`) |
| Stablecoin flows | DefiLlama stablecoins API | free, keyless | lenient | **planned** — easy follow-up adapter |
| Whale wallet alerts | Whale Alert / Arkham | **paid** | — | **pending sign-off** — lowest priority; noisy signal |
| BTC ETF flows | Farside Investors (free page, needs scraping) or SoSoValue API | free-scrape / paid | daily | **pending decision** — scraping is brittle; recommend deferring |
| Fear & Greed index | alternative.me | free, keyless | lenient | **implemented** (`FearGreedFeed`) |

## Recommendations needing your sign-off

1. **On-chain depth (SOPR/reserves/whales):** Glassnode Standard (~$39/mo)
   is the cleanest single buy; CryptoQuant similar. If we stay free, we
   have MVRV + miner + funding/OI — adequate for Phase 3-4 development.
   *Recommendation: defer purchase until backtests (Phase 7) show the
   missing metrics matter.*
2. **Liquidations:** run our own free Binance `forceOrder` websocket
   collector (Phase 2.1, small daemon) instead of Coinglass.
3. **Gold intraday/microstructure:** skip paid tick data until a strategy
   explicitly needs sub-hour bars; OANDA free practice account is the
   cheapest intraday XAU/USD source when we get there and doubles as the
   Phase 9 paper-trading adapter.
4. **Keys you should set:** `FRED_API_KEY` (free) is the only key the
   implemented feeds use. `ALPHA_VANTAGE_API_KEY` remains optional for the
   base framework's fallback chain.

## Mockability / backtest support

Every adapter takes an injectable transport (`HttpTransport`) or loader
callable; tests run fully offline against canned payloads
(`tests/pro_fakes.py`). Backtests will inject replay transports/loaders
over recorded data — same adapters, zero code change (Phase 7).


## Delta Exchange (India) — added for live BTC/gold

Public market-data endpoints (candles 1m–1w, tickers with funding/OI/
mark) for BTCUSD perp and PAXGUSD (tokenized gold ≈ spot, small basis —
disclosed in /api/symbols). No signing required; DELTA_API_KEY/SECRET
stay in .env for potential future signed endpoints, never used for
trading from the dashboard. Vendor preference is probe-gated with
Binance/yfinance fallbacks; PRO_DISABLE_LIVE_VENDORS=1 forces fallbacks
(hermetic tests).
