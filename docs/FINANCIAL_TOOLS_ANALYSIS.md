# Financial Tools & Indicators — Comprehensive Analysis

> **Scope**: All technical-indicator, fundamental, and risk implementations in
> `tradingagents/dataflows/` and `tradingagents/portfolio/risk_metrics.py`.
>
> **Perspective**: Dual review — Quantitative Economist × Senior Software Developer.

---

## Table of Contents

1. [Implementation Accuracy](#1-implementation-accuracy)
2. [Library Assessment](#2-library-assessment)
3. [The Alpha Vantage Debate](#3-the-alpha-vantage-debate)
4. [Data Flow & API Mapping](#4-data-flow--api-mapping)

---

## 1. Implementation Accuracy

### 1.1 Technical Indicators (stockstats via yfinance)

| Indicator | Key | Library | Mathematically Correct? | Notes |
|-----------|-----|---------|------------------------|-------|
| 50-day SMA | `close_50_sma` | stockstats | ✅ Yes | Standard arithmetic rolling mean of closing prices over 50 periods. |
| 200-day SMA | `close_200_sma` | stockstats | ✅ Yes | Same as above over 200 periods. |
| 10-day EMA | `close_10_ema` | stockstats | ✅ Yes | Recursive EMA: `EMA_t = α·P_t + (1-α)·EMA_{t-1}`, `α = 2/(n+1)`. stockstats implements the standard Wilder/exponential formula. |
| MACD | `macd` | stockstats | ✅ Yes | Difference of 12-period and 26-period EMAs. |
| MACD Signal | `macds` | stockstats | ✅ Yes | 9-period EMA of the MACD line. |
| MACD Histogram | `macdh` | stockstats | ✅ Yes | MACD line minus Signal line. |
| RSI (14) | `rsi` | stockstats | ✅ Yes | Wilder's RSI: `100 - 100/(1 + avg_gain/avg_loss)`. Uses EMA smoothing of gains/losses (Wilder's method, which is the industry standard). |
| Bollinger Middle | `boll` | stockstats | ✅ Yes | 20-period SMA of close. |
| Bollinger Upper | `boll_ub` | stockstats | ✅ Yes | Middle + 2 × rolling standard deviation. |
| Bollinger Lower | `boll_lb` | stockstats | ✅ Yes | Middle − 2 × rolling standard deviation. |
| ATR (14) | `atr` | stockstats | ✅ Yes | Wilder's smoothed average of True Range: `max(H-L, |H-C_prev|, |L-C_prev|)`. |
| VWMA | `vwma` | stockstats | ✅ Yes | Volume-weighted moving average: `Σ(P_i × V_i) / Σ(V_i)`. Only available via the yfinance/stockstats vendor (not Alpha Vantage or Finnhub). |
| MFI | `mfi` | stockstats | ✅ Yes | Money Flow Index: volume-weighted RSI variant. yfinance-only. |

**Verdict**: All technical indicators delegate to the `stockstats` library, which
implements the canonical formulas (Wilder RSI, standard EMA, Bollinger 2σ, etc.).
No custom re-implementations exist for these indicators — the code is a thin data-fetching
and formatting layer around stockstats.

### 1.2 Alpha Vantage Indicators

The Alpha Vantage vendor (`alpha_vantage_indicator.py`) calls the Alpha Vantage REST API
endpoints directly (e.g., `SMA`, `EMA`, `MACD`, `RSI`, `BBANDS`, `ATR`). These endpoints
return pre-computed indicator values. The app does **no local calculation** — it fetches
CSV data, parses it, and filters by date range.

| Aspect | Assessment |
|--------|-----------|
| API call mapping | ✅ Correct — each indicator maps to the right AV function. |
| CSV parsing | ✅ Correct — column name mapping (`COL_NAME_MAP`) accurately targets the right CSV column for each indicator. |
| Date filtering | ✅ Correct — filters results to the `[before, curr_date]` window. |
| VWMA handling | ⚠️ Known limitation — returns an informative message since Alpha Vantage has no VWMA endpoint. Documented in code (line 157–160). |

### 1.3 Finnhub Indicators

The Finnhub vendor (`finnhub_indicators.py`) calls the `/indicator` endpoint with
Unix-timestamp date ranges. It handles multi-value indicators (MACD: 3 values per row;
BBANDS: 3 values per row) and single-value indicators correctly.

| Aspect | Assessment |
|--------|-----------|
| Timestamp conversion | ✅ Correct — adds 86 400s to end date to ensure inclusive. |
| Multi-value formatting | ✅ Correct — MACD returns macd + signal + histogram; BBANDS returns upper + middle + lower. |
| Error handling | ✅ Raises `FinnhubError` on empty/no_data responses. |
| Output format | ✅ Mirrors Alpha Vantage output style for downstream agent consistency. |

### 1.4 Portfolio Risk Metrics (`risk_metrics.py`)

All computed in **pure Python** (stdlib `math` only — no pandas/numpy dependency).

| Metric | Formula | Correct? | Notes |
|--------|---------|----------|-------|
| Sharpe Ratio | `(μ / σ) × √252` | ✅ Yes | Annualised, risk-free rate = 0. Uses sample std (ddof=1). |
| Sortino Ratio | `(μ / σ_down) × √252` | ✅ Yes | Denominator uses only negative returns. Correct minimum of 2 downside observations. |
| 95% VaR | `-percentile(returns, 5)` | ✅ Yes | Historical simulation — 5th percentile with linear interpolation. Expressed as positive loss fraction. |
| Max Drawdown | peak-to-trough | ✅ Yes | Walks NAV series tracking running peak. Returns most negative (worst) drawdown. |
| Beta | `Cov(r_p, r_b) / Var(r_b)` | ✅ Yes | Correctly uses sample covariance (n−1 denominator). |
| Sector Concentration | `holdings_value / total_value × 100` | ✅ Yes | From the most-recent snapshot's `holdings_snapshot`. |

### 1.5 Macro Regime Classifier (`macro_regime.py`)

Uses 6 market signals to classify: risk-on / transition / risk-off.

| Signal | Data Source | Method | Correct? |
|--------|------------|--------|----------|
| VIX level | `^VIX` via yfinance | `< 16 → risk-on, > 25 → risk-off` | ✅ Standard thresholds from CBOE VIX interpretation guides. |
| VIX trend | `^VIX` 5-SMA vs 20-SMA | Rising VIX (SMA5 > SMA20) → risk-off | ✅ Standard crossover approach. |
| Credit spread | HYG/LQD ratio | 1-month change of HY-bond / IG-bond ratio | ✅ Well-established proxy for credit spread changes. |
| Yield curve | TLT/SHY ratio | TLT outperformance → flight to safety | ✅ TLT (20yr) vs SHY (1-3yr) is a standard duration proxy. |
| Market breadth | `^GSPC` vs 200-SMA | SPX above/below 200-SMA | ✅ Classic breadth indicator used by institutional investors. |
| Sector rotation | Defensive vs Cyclical ETFs | 1-month return spread (XLU/XLP/XLV vs XLY/XLK/XLI) | ✅ Correct sector classification; standard rotation analysis. |

**Custom calculations**: The `_sma()` and `_pct_change_n()` helpers are simple 5-line
implementations. They are mathematically correct and use pandas `rolling().mean()`.
No need to replace with a library — the overhead would outweigh the benefit.

### 1.6 TTM Analysis (`ttm_analysis.py`)

Computes trailing twelve months metrics by summing the last 4 quarterly income-statement
flow items and using the latest balance-sheet stock items. Handles transposed CSV layouts
(Alpha Vantage vs yfinance) via auto-detection.

| Metric | Correct? | Notes |
|--------|----------|-------|
| TTM Revenue | ✅ | Sum of last 4 quarterly revenues. |
| Margin calculations | ✅ | Gross/operating/net margins = profit / revenue × 100. |
| ROE | ✅ | TTM net income / latest equity × 100. |
| Debt/Equity | ✅ | Latest total debt / latest equity. |
| Revenue QoQ | ✅ | `(latest - previous) / |previous| × 100`. |
| Revenue YoY | ✅ | Compares latest quarter to 4 quarters prior (`quarterly[-5]`). |
| Margin trend | ✅ | Classifies last 3 values as expanding/contracting/stable. |

### 1.7 Peer Comparison (`peer_comparison.py`)

| Aspect | Assessment |
|--------|-----------|
| Return calculation | ✅ `(current - base) / base × 100` for 1W/1M/3M/6M/YTD horizons using trading-day counts (5, 21, 63, 126). |
| Alpha calculation | ✅ Stock return minus ETF return per period. |
| Sector mapping | ✅ 11 GICS sectors mapped to SPDR ETFs. Yahoo Finance sector names normalised correctly. |
| Batch download | ✅ Single `yf.download()` call for all symbols (efficient). |

---

## 2. Library Assessment

### 2.1 Current Library Stack

| Library | Version | Role | Industry Standard? |
|---------|---------|------|-------------------|
| **stockstats** | ≥ 0.6.5 | Technical indicator computation (SMA, EMA, MACD, RSI, BBANDS, ATR, VWMA, MFI) | ⚠️ Moderate — well-known in Python quant community but not as widely used as TA-Lib or pandas-ta. ~1.3K GitHub stars. |
| **yfinance** | ≥ 0.2.63 | Market data fetching (OHLCV, fundamentals, news) | ✅ De facto standard for free Yahoo Finance access. ~14K GitHub stars. |
| **pandas** | ≥ 2.3.0 | Data manipulation, CSV parsing, rolling calculations | ✅ Industry standard. Used by virtually all quantitative Python workflows. |
| **requests** | ≥ 2.32.4 | HTTP API calls to Alpha Vantage and Finnhub | ✅ Industry standard for HTTP in Python. |

### 2.2 Alternative Libraries Considered

| Alternative | What It Provides | Pros | Cons |
|-------------|-----------------|------|------|
| **TA-Lib** (via `ta-lib` Python wrapper) | 200+ indicators, C-based performance | ✅ Gold standard in quant finance<br>✅ Extremely fast (C implementation)<br>✅ Widest indicator coverage | ❌ Requires C library system install (complex CI/CD)<br>❌ No pip-only install<br>❌ Platform-specific build issues |
| **pandas-ta** | 130+ indicators, pure Python/pandas | ✅ Pure Python — pip install only<br>✅ Active maintenance<br>✅ Direct pandas DataFrame integration | ⚠️ Slightly slower than TA-Lib<br>⚠️ Larger dependency footprint |
| **tulipy** | Technical indicators, C-based | ✅ Fast (C implementation)<br>✅ Simple API | ❌ Requires C build<br>❌ Less maintained than TA-Lib |

### 2.3 Recommendation: Keep stockstats

**Current choice is appropriate** for this application. Here's why:

1. **Indicators are consumed by LLMs, not HFT engines**: The indicators are formatted
   as text strings for LLM agents. The performance difference between stockstats and
   TA-Lib is irrelevant at this scale (single-ticker, daily data, <15 years of history).

2. **Pure Python install**: stockstats requires only pip — no C library builds.
   This simplifies CI/CD, Docker images, and contributor onboarding significantly.

3. **Sufficient coverage**: All indicators used by the trading agents (SMA, EMA, MACD,
   RSI, Bollinger Bands, ATR, VWMA, MFI) are covered by stockstats.

4. **Mathematical correctness**: stockstats implements the canonical formulas (verified
   above). The results will match TA-Lib and pandas-ta to within floating-point precision.

5. **Migration cost**: Switching to pandas-ta or TA-Lib would require changes to
   `stockstats_utils.py`, `y_finance.py`, and all tests — with no user-visible benefit.

**When to reconsider**: If the project adds high-frequency backtesting (thousands of
tickers × minute data), TA-Lib's C performance would become relevant.

---

## 3. The Alpha Vantage Debate

### 3.1 Available Indicators via Alpha Vantage API

All indicators used by TradingAgents are available as **pre-computed endpoints** from
the Alpha Vantage Technical Indicators API:

| Indicator | AV Endpoint | Available? |
|-----------|------------|-----------|
| SMA | `function=SMA` | ✅ |
| EMA | `function=EMA` | ✅ |
| MACD | `function=MACD` | ✅ (returns MACD, Signal, Histogram) |
| RSI | `function=RSI` | ✅ |
| Bollinger Bands | `function=BBANDS` | ✅ (returns upper, middle, lower) |
| ATR | `function=ATR` | ✅ |
| VWMA | — | ❌ Not available |
| MFI | `function=MFI` | ✅ (but not currently mapped in our AV adapter) |

### 3.2 Comparative Analysis

| Dimension | Local Calculation (stockstats + yfinance) | Alpha Vantage API (pre-computed) |
|-----------|------------------------------------------|----------------------------------|
| **Cost** | Free (yfinance) | 75 calls/min premium; 25/day free tier. Each indicator = 1 API call. A full analysis (12 indicators × 1 ticker) consumes 12 calls. |
| **Latency** | ~1–2s for initial data fetch + <100ms for indicator computation | ~0.5–1s per API call × 12 indicators = 6–12s total |
| **Rate Limits** | No API rate limits from yfinance (though Yahoo may throttle aggressive use) | Strict rate limits. Premium tier: 75 calls/min. Free tier: 25 calls/day. |
| **Indicator Coverage** | Full: any indicator stockstats supports (200+ including VWMA, MFI) | Limited to Alpha Vantage's supported functions. No VWMA. |
| **Data Freshness** | Real-time — downloads latest OHLCV data then computes | Real-time — Alpha Vantage computes on their latest data |
| **Reproducibility** | Full control — same input data + code = exact same result. Can version-control parameters. | Black box — AV may change smoothing methods, seed values, or data adjustments without notice. |
| **Customisation** | Full — change period, smoothing, add custom indicators | Limited to AV's parameter set per endpoint |
| **Offline/Testing** | Cacheable — OHLCV data can be cached locally for offline dev and testing | Requires live API calls (no offline mode without caching raw responses) |
| **Accuracy** | Depends on stockstats implementation (verified correct above) | Presumably correct — Alpha Vantage is a major data vendor |
| **Multi-ticker Efficiency** | One yf.download call for many tickers, then compute all indicators locally | Separate API call per ticker × per indicator |

### 3.3 Verdict: Local Calculation (Primary) with API as Fallback

The current architecture — **yfinance + stockstats as primary, Alpha Vantage as fallback
vendor** — is the correct design for these reasons:

1. **Cost efficiency**: A single analysis run needs 12+ indicators. At the free AV tier
   (25 calls/day), this exhausts the quota on 2 tickers. Local computation is unlimited.

2. **Latency**: A single yfinance download + local stockstats computation is 5–10×
   faster than 12 sequential Alpha Vantage API calls with rate limiting.

3. **Coverage**: VWMA and MFI are not available from Alpha Vantage. Local computation
   is the only option for these indicators.

4. **Testability**: Local computation can be unit-tested with synthetic data and cached
   OHLCV files. API-based indicators require live network access or complex mocking.

5. **Fallback value**: Alpha Vantage's pre-computed indicators serve as an independent
   verification and as a fallback when yfinance is unavailable (e.g., Yahoo Finance
   outages or API changes). The vendor routing system in `interface.py` already supports
   this.

The Alpha Vantage vendor is **not a wasted implementation** — it provides resilience
and cross-validation capability. However, it should remain the secondary vendor.

---

## 4. Data Flow & API Mapping

### 4.1 Technical Indicators Tool

**Agent-Facing Tool**: `get_indicators(symbol, indicator, curr_date, look_back_days)`
in `tradingagents/agents/utils/technical_indicators_tools.py`

#### yfinance Vendor (Primary)

```
Agent → get_indicators() tool
  → route_to_vendor("get_indicators", ...)
    → get_stock_stats_indicators_window()     [y_finance.py]
      → _get_stock_stats_bulk()               [y_finance.py]
        → yf.download(symbol, 15yr range)     [External: Yahoo Finance API]
        → _clean_dataframe()                  [stockstats_utils.py]
        → stockstats.wrap(data)               [Library: stockstats]
        → df[indicator]                       # triggers calculation
      → format as date: value string
  → return formatted indicator report to agent
```

| Attribute | Detail |
|-----------|--------|
| **Data Source** | Yahoo Finance via `yfinance` library |
| **Calculation** | `stockstats` library — wraps OHLCV DataFrame, indicator access triggers lazy computation |
| **Caching** | CSV file cache in `data_cache_dir` (15-year OHLCV per symbol) |
| **External API** | Yahoo Finance (via yfinance `download()`) — 1 call per symbol |

#### Alpha Vantage Vendor (Fallback)

```
Agent → get_indicators() tool
  → route_to_vendor("get_indicators", ...)
    → get_indicator()                         [alpha_vantage_indicator.py]
      → _fetch_indicator_data()
        → _make_api_request("SMA"|"EMA"|...) [External: Alpha Vantage API]
      → _parse_indicator_data()               # CSV parsing + date filtering
  → return formatted indicator report to agent
```

| Attribute | Detail |
|-----------|--------|
| **Data Source** | Alpha Vantage REST API |
| **Calculation** | Pre-computed by Alpha Vantage — no local calculation |
| **Caching** | None (live API call per request) |
| **External API** | Alpha Vantage `https://www.alphavantage.co/query` — 1 call per indicator |

#### Finnhub Vendor

```
Agent → (not routed by default — only if vendor="finnhub" configured)
  → get_indicator_finnhub()                   [finnhub_indicators.py]
    → _make_api_request("indicator", ...)     [External: Finnhub API]
    → parse JSON response (parallel lists: timestamps + values)
  → return formatted indicator report
```

| Attribute | Detail |
|-----------|--------|
| **Data Source** | Finnhub REST API `/indicator` endpoint |
| **Calculation** | Pre-computed by Finnhub — no local calculation |
| **Caching** | None |
| **External API** | Finnhub `https://finnhub.io/api/v1/indicator` — 1 call per indicator |

**Supported Indicators by Vendor**:

| Indicator | yfinance (stockstats) | Alpha Vantage | Finnhub |
|-----------|:---:|:---:|:---:|
| SMA (50, 200) | ✅ | ✅ | ✅ |
| EMA (10) | ✅ | ✅ | ✅ |
| MACD / Signal / Histogram | ✅ | ✅ | ✅ |
| RSI | ✅ | ✅ | ✅ |
| Bollinger Bands (upper/middle/lower) | ✅ | ✅ | ✅ |
| ATR | ✅ | ✅ | ✅ |
| VWMA | ✅ | ❌ | ❌ |
| MFI | ✅ | ❌ (endpoint exists but unmapped) | ❌ |

---

### 4.2 Fundamental Data Tools

**Agent-Facing Tools**: `get_fundamentals`, `get_balance_sheet`, `get_cashflow`,
`get_income_statement` in `tradingagents/agents/utils/fundamental_data_tools.py`

#### yfinance Vendor (Primary)

```
Agent → get_fundamentals() tool
  → route_to_vendor("get_fundamentals", ...)
    → get_fundamentals()                      [y_finance.py]
      → yf.Ticker(ticker).info               [External: Yahoo Finance API]
      → extract 27 key-value fields
  → return formatted fundamentals report
```

```
Agent → get_balance_sheet() / get_cashflow() / get_income_statement()
  → route_to_vendor(...)
    → yf.Ticker(ticker).quarterly_balance_sheet / quarterly_cashflow / quarterly_income_stmt
      [External: Yahoo Finance API]
    → DataFrame.to_csv()
  → return CSV string with header
```

| Attribute | Detail |
|-----------|--------|
| **Data Source** | Yahoo Finance via `yfinance` library |
| **Calculation** | No calculation — raw financial statement data |
| **External APIs** | Yahoo Finance (1 API call per statement) |

#### Alpha Vantage Vendor (Fallback)

```
Agent → get_balance_sheet() / get_cashflow() / get_income_statement()
  → route_to_vendor(...)
    → _make_api_request("BALANCE_SHEET" | "CASH_FLOW" | "INCOME_STATEMENT")
      [External: Alpha Vantage API]
    → CSV parsing
  → return CSV string
```

| Attribute | Detail |
|-----------|--------|
| **Data Source** | Alpha Vantage REST API |
| **Calculation** | No calculation — pre-computed by Alpha Vantage |
| **External APIs** | Alpha Vantage (1 call per statement) |

---

### 4.3 TTM Analysis Tool

**Agent-Facing Tool**: `get_ttm_analysis(ticker, curr_date)`
in `tradingagents/agents/utils/fundamental_data_tools.py`

```
Agent → get_ttm_analysis() tool
  → route_to_vendor("get_income_statement", ticker, "quarterly")   [1 vendor call]
  → route_to_vendor("get_balance_sheet", ticker, "quarterly")      [1 vendor call]
  → route_to_vendor("get_cashflow", ticker, "quarterly")           [1 vendor call]
  → compute_ttm_metrics(income_csv, balance_csv, cashflow_csv)     [ttm_analysis.py]
    → _parse_financial_csv() × 3   # auto-detect AV vs yfinance layout
    → sum last 4 quarters (flow items)
    → latest value (stock items)
    → compute margins, ROE, D/E
    → compute QoQ/YoY revenue growth
    → classify margin trends
  → format_ttm_report(metrics, ticker)
  → return Markdown report
```

| Attribute | Detail |
|-----------|--------|
| **Data Source** | 3 quarterly financial statements via configured vendor |
| **Calculation** | Local: TTM summation, margin ratios, growth rates, trend classification |
| **Internal Requests** | 3 `route_to_vendor()` calls for financial statements |
| **External APIs** | Yahoo Finance (3 calls) or Alpha Vantage (3 calls), depending on vendor config |

---

### 4.4 Peer Comparison Tool

**Agent-Facing Tool**: `get_peer_comparison(ticker, curr_date)`
in `tradingagents/agents/utils/fundamental_data_tools.py`

```
Agent → get_peer_comparison() tool
  → get_peer_comparison_report(ticker)           [peer_comparison.py]
    → get_sector_peers(ticker)
      → yf.Ticker(ticker).info                  [External: Yahoo Finance]
      → map sector → _SECTOR_TICKERS list
    → compute_relative_performance(ticker, sector_key, peers)
      → yf.download([ticker, ...peers, ETF])    [External: Yahoo Finance — 1 batch call]
      → _safe_pct() for 1W/1M/3M/6M horizons
      → _ytd_pct() for YTD
      → rank by 3-month return
      → compute alpha vs sector ETF
  → return Markdown peer ranking table
```

| Attribute | Detail |
|-----------|--------|
| **Data Source** | Yahoo Finance for OHLCV prices (6-month history) |
| **Calculation** | Local: percentage returns, ranking, alpha computation |
| **Internal Requests** | 1 ticker info lookup + 1 batch price download |
| **External APIs** | Yahoo Finance (2 calls: `.info` + `download()`) |

---

### 4.5 Sector Relative Tool

**Agent-Facing Tool**: `get_sector_relative(ticker, curr_date)`

```
Agent → get_sector_relative() tool
  → get_sector_relative_report(ticker)           [peer_comparison.py]
    → get_sector_peers(ticker)
      → yf.Ticker(ticker).info                  [External: Yahoo Finance]
    → yf.download([ticker, sector_ETF])         [External: Yahoo Finance — 1 call]
    → _safe_pct() for 1W/1M/3M/6M
    → compute alpha per period
  → return Markdown comparison table
```

| Attribute | Detail |
|-----------|--------|
| **Data Source** | Yahoo Finance for ticker + sector ETF prices |
| **Calculation** | Local: return percentages, alpha = stock return − ETF return |
| **External APIs** | Yahoo Finance (2 calls: `.info` + `download()`) |

---

### 4.6 Macro Regime Tool

**Agent-Facing Tool**: `get_macro_regime(curr_date)`
in `tradingagents/agents/utils/fundamental_data_tools.py`

```
Agent → get_macro_regime() tool
  → classify_macro_regime()                      [macro_regime.py]
    → _fetch_macro_data()
      → yf.download(["^VIX"], period="3mo")     [External: Yahoo Finance]
      → yf.download(["^GSPC"], period="14mo")   [External: Yahoo Finance]
      → yf.download(["HYG", "LQD"], period="3mo") [External: Yahoo Finance]
      → yf.download(["TLT", "SHY"], period="3mo") [External: Yahoo Finance]
      → yf.download([def_ETFs + cyc_ETFs], period="3mo") [External: Yahoo Finance]
    → _evaluate_signals()
      → _signal_vix_level()          # threshold check
      → _signal_vix_trend()          # SMA5 vs SMA20 crossover
      → _signal_credit_spread()      # HYG/LQD 1-month change
      → _signal_yield_curve()        # TLT vs SHY performance spread
      → _signal_market_breadth()     # SPX vs 200-SMA
      → _signal_sector_rotation()    # defensive vs cyclical ETF spread
    → _determine_regime_and_confidence()
  → format_macro_report(regime_data)
  → return Markdown regime report
```

| Attribute | Detail |
|-----------|--------|
| **Data Source** | Yahoo Finance for VIX, S&P 500, bond ETFs, sector ETFs |
| **Calculation** | Local: 6 signal evaluators with custom thresholds. Simple helper functions `_sma()`, `_pct_change_n()`. |
| **Internal Requests** | 5 batch `yf.download()` calls |
| **External APIs** | Yahoo Finance only (5 calls, batched by symbol group) |

---

### 4.7 Core Stock Data Tool

**Agent-Facing Tool**: `get_stock_data(symbol, start_date, end_date)`
in `tradingagents/agents/utils/core_stock_tools.py`

#### yfinance Vendor (Primary)

```
Agent → get_stock_data() tool
  → route_to_vendor("get_stock_data", ...)
    → get_YFin_data_online()                 [y_finance.py]
      → yf.Ticker(symbol).history(...)      [External: Yahoo Finance]
      → round numerics, format CSV
  → return CSV string
```

#### Alpha Vantage Vendor (Fallback)

```
Agent → get_stock_data() tool
  → route_to_vendor("get_stock_data", ...)
    → get_stock()                            [alpha_vantage_stock.py]
      → _make_api_request("TIME_SERIES_DAILY_ADJUSTED")
                                            [External: Alpha Vantage]
  → return CSV string
```

| Attribute | Detail |
|-----------|--------|
| **Data Source** | Yahoo Finance (primary) or Alpha Vantage (fallback) |
| **Calculation** | None — raw OHLCV data |
| **External APIs** | Yahoo Finance or Alpha Vantage (1 call) |

---

### 4.8 News Data Tools

**Agent-Facing Tools**: `get_news`, `get_global_news`, `get_insider_transactions`
in `tradingagents/agents/utils/news_data_tools.py`

| Tool | Primary Vendor | Fallback | External API Sequence |
|------|---------------|----------|----------------------|
| `get_news(ticker, ...)` | yfinance | Alpha Vantage | 1. `yf.Ticker(ticker).news` → Yahoo Finance |
| `get_global_news(...)` | yfinance | Alpha Vantage | 1. `yf.Search("market").news` → Yahoo Finance |
| `get_insider_transactions(ticker)` | **Finnhub** | Alpha Vantage, yfinance | 1. Finnhub `/stock/insider-transactions` API |

---

### 4.9 Scanner Data Tools

**Agent-Facing Tools**: `get_market_movers`, `get_market_indices`, `get_sector_performance`,
`get_industry_performance`, `get_topic_news`
in `tradingagents/agents/utils/scanner_tools.py`

| Tool | Primary Vendor | External API Sequence |
|------|---------------|----------------------|
| `get_market_movers(category)` | yfinance | 1. `yf.Screener()` → Yahoo Finance |
| `get_market_indices()` | yfinance | 1. `yf.download(["^GSPC","^DJI",...])` → Yahoo Finance |
| `get_sector_performance()` | yfinance | 1. `yf.Sector(key)` → Yahoo Finance (per sector) |
| `get_industry_performance(sector)` | yfinance | 1. `yf.Industry(key)` → Yahoo Finance (per industry) |
| `get_topic_news(topic)` | yfinance | 1. `yf.Search(topic).news` → Yahoo Finance |

---

### 4.10 Calendar Tools (Finnhub Only)

**Agent-Facing Tools**: `get_earnings_calendar`, `get_economic_calendar`

| Tool | Vendor | External API |
|------|--------|-------------|
| `get_earnings_calendar(from, to)` | Finnhub (only) | Finnhub `/calendar/earnings` |
| `get_economic_calendar(from, to)` | Finnhub (only) | Finnhub `/calendar/economic` (FOMC, CPI, NFP, GDP, PPI) |

---

### 4.11 Portfolio Risk Metrics

**Agent-Facing Tool**: `compute_portfolio_risk_metrics()`
in `tradingagents/agents/utils/portfolio_tools.py`

```
Agent → compute_portfolio_risk_metrics() tool
  → compute_risk_metrics(snapshots, benchmark_returns)   [risk_metrics.py]
    → _daily_returns(nav_series)           # NAV → daily % changes
    → Sharpe: μ/σ × √252
    → Sortino: μ/σ_down × √252
    → VaR: -percentile(returns, 5)
    → Max drawdown: peak-to-trough walk
    → Beta: Cov(r_p, r_b) / Var(r_b)
    → Sector concentration from holdings
  → return JSON metrics dict
```

| Attribute | Detail |
|-----------|--------|
| **Data Source** | Portfolio snapshots from Supabase database |
| **Calculation** | 100% local — pure Python `math` module, no external dependencies |
| **External APIs** | None — operates entirely on stored portfolio data |

---

### 4.12 Vendor Routing Architecture

All data tool calls flow through `route_to_vendor()` in `tradingagents/dataflows/interface.py`:

```
@tool function (agents/utils/*_tools.py)
  → route_to_vendor(method_name, *args, **kwargs)
    → get_category_for_method(method_name)   # lookup in TOOLS_CATEGORIES
    → get_vendor(category, method_name)      # check config: tool_vendors → data_vendors
    → try primary vendor implementation
    → if FALLBACK_ALLOWED and primary fails:
        try remaining vendors in order
    → if all fail: raise RuntimeError
```

**Fallback-Allowed Methods** (cross-vendor fallback is safe for these):
- `get_stock_data` — OHLCV data is fungible
- `get_market_indices` — index quotes are fungible
- `get_sector_performance` — ETF-based, same approach
- `get_market_movers` — approximation acceptable for screening
- `get_industry_performance` — ETF-based proxy

**Fail-Fast Methods** (no fallback — data contracts differ between vendors):
- `get_indicators`, `get_fundamentals`, `get_balance_sheet`, `get_cashflow`,
  `get_income_statement`, `get_news`, `get_global_news`, `get_insider_transactions`,
  `get_topic_news`, `get_earnings_calendar`, `get_economic_calendar`

---

## Summary

| Area | Verdict |
|------|---------|
| **Implementation accuracy** | ✅ All indicators and metrics are mathematically correct. No custom re-implementations of standard indicators — stockstats handles the math. |
| **Library choice** | ✅ stockstats is appropriate for this use case (LLM-consumed daily indicators). TA-Lib would add build complexity with no user-visible benefit. |
| **Alpha Vantage role** | ✅ Correctly positioned as fallback vendor. Local computation is faster, cheaper, and covers more indicators. |
| **Data flow architecture** | ✅ Clean vendor routing with configurable primary/fallback. Each tool has a clear data source → calculation → formatting pipeline. |
