# yfinance Integration — API Reference & Architecture

## 1. yfinance API Catalog

Tất cả API bên dưới truy cập qua `yfinance.Ticker(symbol)`.
Symbol convention: stock = `AAPL`, crypto = `BTC-USD`, forex = `EURUSD=X`.

---

### 1.1 Price & Market Data

| Method / Property | Returns | Mapping trong TradingAgents |
|---|---|---|
| `history(period, interval, start, end)` | OHLCV DataFrame | `get_stock_data` |
| `fast_info` | Dict: price, market_cap, shares, 52w range | supplementary info |
| `info` | Full metadata dict (~100 fields) | `get_fundamentals` (partial) |
| `get_history_metadata()` | Exchange timezone, currency, data range | internal validation |
| `options` | List of expiry dates | — (future) |
| `option_chain(date)` | Calls & Puts DataFrames | — (future) |

### 1.2 Fundamental Data

| Method / Property | Returns | Mapping trong TradingAgents |
|---|---|---|
| `financials` / `quarterly_financials` | Income Statement DataFrame | `get_income_statement` |
| `balance_sheet` / `quarterly_balance_sheet` | Balance Sheet DataFrame | `get_balance_sheet` |
| `cashflow` / `quarterly_cashflow` | Cash Flow DataFrame | `get_cashflow` |
| `earnings` / `quarterly_earnings` | Revenue + Earnings DataFrame | `get_fundamentals` |
| `income_stmt` / `quarterly_income_stmt` | Income Statement (alt accessor) | `get_income_statement` |

### 1.3 Analysis & Valuation

| Method / Property | Returns | Mapping trong TradingAgents |
|---|---|---|
| `analyst_price_targets` | Dict: current, low, high, mean, median | enrichment data |
| `recommendations` | DataFrame: firm, grade, action | enrichment data |
| `recommendations_summary` | Buy/Hold/Sell counts | enrichment data |
| `upgrades_downgrades` | History of rating changes | enrichment data |
| `earnings_estimate` | EPS estimates DataFrame | enrichment data |
| `revenue_estimate` | Revenue estimates DataFrame | enrichment data |
| `earnings_trend` | Earnings trend analysis | enrichment data |
| `growth_estimates` | Growth projections | enrichment data |

### 1.4 Corporate Actions & Events

| Method / Property | Returns | Mapping trong TradingAgents |
|---|---|---|
| `actions` | Dividends + Stock Splits DataFrame | — |
| `dividends` | Dividends Series | — |
| `splits` | Stock Splits Series | — |
| `capital_gains` | Capital gains (mutual funds) | — |
| `calendar` | Upcoming earnings/ex-div dates | — |

### 1.5 Holders & Insider Activity

| Method / Property | Returns | Mapping trong TradingAgents |
|---|---|---|
| `major_holders` | % held by institutions/insiders | `get_insider_transactions` |
| `institutional_holders` | Top institutional holders | `get_insider_transactions` |
| `mutualfund_holders` | Top mutual fund holders | enrichment data |
| `insider_transactions` | Recent insider buys/sells | `get_insider_transactions` |
| `insider_purchases` | Aggregated insider purchases | `get_insider_transactions` |

### 1.6 News

| Method / Property | Returns | Mapping trong TradingAgents |
|---|---|---|
| `news` | List of dicts: title, link, publisher, date | `get_news` |

### 1.7 Technical Indicators (computed from history)

yfinance không tính indicators trực tiếp — ta dùng `stockstats` wrap lên `history()` DataFrame,
giống cách Binance module hiện tại đang làm.

| Indicator | stockstats key | Mô tả |
|---|---|---|
| SMA | `close_N_sma` | Simple Moving Average (N periods) |
| EMA | `close_N_ema` | Exponential Moving Average |
| MACD | `macd`, `macds`, `macdh` | Moving Average Convergence Divergence |
| RSI | `rsi_N` | Relative Strength Index |
| Bollinger Bands | `boll`, `boll_ub`, `boll_lb` | Bollinger Bands |
| ATR | `atr` | Average True Range |
| VWMA | `vwma` | Volume Weighted Moving Average |
| MFI | `mfi` | Money Flow Index |

### 1.8 Crypto-specific Notes

| Feature | Stock (`AAPL`) | Crypto yfinance (`BTC-USD`) | Crypto Binance (`BTCUSDT`) |
|---|---|---|---|
| OHLCV | Yes | Yes | Yes |
| Fundamentals | Yes | No | No |
| News | Yes | Yes (limited) | No |
| Insider data | Yes | No | No |
| Options | Yes | No | No |
| 24/7 data | No | Yes | Yes |
| Real-time websocket | No | No | Yes (separate) |

---

## 2. Symbol Normalization — Hai tầng transform

### Vấn đề

Người dùng nhập crypto symbol theo nhiều format khác nhau, nhưng mỗi data vendor
yêu cầu format riêng:

| User Input | Binance expects | yfinance expects |
|---|---|---|
| `BTC/USD` | `BTCUSDT` | `BTC-USD` |
| `BTC/USDT` | `BTCUSDT` | `BTC-USDT` |
| `BTCUSDT` | `BTCUSDT` | `BTC-USDT` |
| `ETH/BTC` | `ETHBTC` | `ETH-BTC` |
| `btc-usdt` | `BTCUSDT` | `BTC-USDT` |
| `AAPL` | N/A | `AAPL` |
| `CNC.TO` | N/A | `CNC.TO` |

### Giải pháp: 2-Layer Symbol Normalizer

```
User Input (any format)
      │
      ▼
┌─────────────────────────────────┐
│  Layer 1: CLI Normalizer        │  cli/symbol_normalizer.py
│  ─────────────────────────────  │
│  • Strip whitespace, uppercase  │
│  • Detect asset class:          │
│    - crypto? stock? forex?      │
│  • Parse into CanonicalSymbol:  │
│    - base  = "BTC"              │
│    - quote = "USDT"             │
│    - asset_class = crypto       │
│    - exchange_suffix = None     │
│  • Output: CanonicalSymbol      │
└─────────────┬───────────────────┘
              │
              ▼
┌─────────────────────────────────┐
│  Layer 2: Vendor Formatter      │  tradingagents/dataflows/symbol_formatter.py
│  ─────────────────────────────  │
│  • Input: CanonicalSymbol       │
│  • Format per vendor:           │
│    - binance  → "BTCUSDT"      │
│    - yfinance → "BTC-USDT"     │
│    - alpha_vantage → "BTC"     │
│  • Stock symbols pass through   │
│  • Output: vendor-ready string  │
└─────────────────────────────────┘
```

### CanonicalSymbol Model

```python
@dataclass
class CanonicalSymbol:
    """Vendor-agnostic symbol representation."""
    raw: str                    # original user input
    base: str                   # e.g. "BTC", "AAPL"
    quote: str | None           # e.g. "USDT", "USD", None for stocks
    asset_class: AssetClass     # crypto | stock | forex
    exchange_suffix: str | None # e.g. ".TO", ".HK", ".T"

    @property
    def is_crypto(self) -> bool:
        return self.asset_class == AssetClass.CRYPTO

    def to_binance(self) -> str:
        """BTCUSDT format — no separator."""
        if not self.is_crypto:
            raise ValueError(f"Binance does not support {self.asset_class}")
        return f"{self.base}{self.quote}"

    def to_yfinance(self) -> str:
        """BTC-USDT format for crypto, AAPL for stocks."""
        if self.is_crypto:
            return f"{self.base}-{self.quote}"
        suffix = self.exchange_suffix or ""
        return f"{self.base}{suffix}"

    def to_alpha_vantage(self) -> str:
        """Alpha Vantage format."""
        return self.base
```

### Detect + Parse Logic

```python
# Known crypto base tokens (top by market cap)
KNOWN_CRYPTO_BASES = {
    "BTC", "ETH", "BNB", "SOL", "XRP", "DOGE", "ADA", "AVAX",
    "DOT", "MATIC", "LINK", "UNI", "ATOM", "LTC", "XLM", "ALGO",
    "NEAR", "FTM", "AAVE", "CRV", "XAG", "XAU", ...
}

KNOWN_QUOTE_CURRENCIES = {"USDT", "USDC", "USD", "BUSD", "BTC", "ETH", "BNB", "FDUSD"}

SEPARATORS = r"[/\-_]"

def parse_symbol(raw: str) -> CanonicalSymbol:
    """Parse any user input into a CanonicalSymbol."""
    cleaned = raw.strip().upper()

    # 1. Check exchange suffix → stock
    if "." in cleaned:
        return CanonicalSymbol(raw, cleaned.split(".")[0], None, AssetClass.STOCK, "." + cleaned.split(".")[-1])

    # 2. Try splitting by separator: BTC/USDT, BTC-USD, ETH_BTC
    parts = re.split(SEPARATORS, cleaned)
    if len(parts) == 2:
        base, quote = parts
        if base in KNOWN_CRYPTO_BASES:
            return CanonicalSymbol(raw, base, quote, AssetClass.CRYPTO, None)

    # 3. Try matching concatenated: BTCUSDT, ETHBTC
    for quote in sorted(KNOWN_QUOTE_CURRENCIES, key=len, reverse=True):
        if cleaned.endswith(quote) and cleaned[:-len(quote)] in KNOWN_CRYPTO_BASES:
            base = cleaned[:-len(quote)]
            return CanonicalSymbol(raw, base, quote, AssetClass.CRYPTO, None)

    # 4. Forex check: EURUSD=X pattern
    if cleaned.endswith("=X"):
        return CanonicalSymbol(raw, cleaned, None, AssetClass.FOREX, None)

    # 5. Default: treat as stock
    return CanonicalSymbol(raw, cleaned, None, AssetClass.STOCK, None)
```

---

## 3. Architecture Flow — After yfinance Integration

```
                            ┌──────────────────────────────────────────────┐
                            │              USER INPUT (CLI)                │
                            │  "BTC/USD"  "BTCUSDT"  "AAPL"  "CNC.TO"    │
                            └────────────────────┬─────────────────────────┘
                                                 │
                                                 ▼
                            ┌──────────────────────────────────────────────┐
                            │     LAYER 1: CLI Symbol Normalizer           │
                            │     cli/symbol_normalizer.py                 │
                            │                                              │
                            │  parse_symbol(raw) → CanonicalSymbol         │
                            │  • Detect asset class (crypto/stock/forex)   │
                            │  • Extract base, quote, exchange suffix      │
                            └────────────────────┬─────────────────────────┘
                                                 │
                                                 │  CanonicalSymbol
                                                 ▼
                            ┌──────────────────────────────────────────────┐
                            │     LAYER 2: Vendor Symbol Formatter         │
                            │     dataflows/symbol_formatter.py            │
                            │                                              │
                            │  format_for_vendor(symbol, vendor) → str     │
                            │  • binance  → "BTCUSDT"                     │
                            │  • yfinance → "BTC-USDT" / "AAPL"          │
                            │  • alpha_v  → "BTC" / "AAPL"               │
                            └────────────────────┬─────────────────────────┘
                                                 │
                                                 │  vendor-formatted string
                                                 ▼
                  ┌──────────────────────────────────────────────────────────────┐
                  │                   VENDOR ROUTER (interface.py)               │
                  │                                                              │
                  │  route_to_vendor(method, symbol, ...) → str                  │
                  │  • Reads config → picks primary vendor                       │
                  │  • Fallback chain on rate-limit errors                       │
                  │  • Delegates to vendor implementation                        │
                  └─────┬──────────────────┬──────────────────┬──────────────────┘
                        │                  │                  │
               ┌────────▼──────┐  ┌────────▼──────┐  ┌───────▼───────┐
               │   BINANCE     │  │   YFINANCE    │  │ ALPHA VANTAGE │
               │  binance.py   │  │  yfinance.py  │  │ alpha_*.py    │
               │               │  │               │  │               │
               │ • klines      │  │ • history()   │  │ • TIME_SERIES │
               │ • ticker/24hr │  │ • info        │  │ • OVERVIEW    │
               │ • depth       │  │ • financials  │  │ • NEWS        │
               │ • indicators  │  │ • news        │  │ • INDICATORS  │
               │   (stockstats)│  │ • holders     │  │               │
               │               │  │ • indicators  │  │               │
               │               │  │   (stockstats)│  │               │
               └───────────────┘  └───────────────┘  └───────────────┘
                        │                  │                  │
                        └────────┬─────────┘──────────┬───────┘
                                 │                    │
                                 ▼                    ▼
                  ┌──────────────────────────────────────────────────┐
                  │              TOOLS LAYER                         │
                  │  agents/utils/{core_stock_tools,                 │
                  │    technical_indicators_tools,                    │
                  │    fundamental_data_tools,                        │
                  │    news_data_tools}.py                            │
                  │                                                   │
                  │  Each tool calls route_to_vendor(method, ...)     │
                  └─────────────────────┬────────────────────────────┘
                                        │
                                        ▼
                  ┌──────────────────────────────────────────────────┐
                  │              AGENT GRAPH (LangGraph)             │
                  │                                                   │
                  │  ┌──────────────────────────────────────────┐    │
                  │  │ Analyst Team (parallel)                  │    │
                  │  │  Market │ Social │ News │ Fundamentals   │    │
                  │  └────────────────────┬─────────────────────┘    │
                  │                       ▼                          │
                  │  ┌──────────────────────────────────────────┐    │
                  │  │ Research Team (debate loop)              │    │
                  │  │  Bull ↔ Bear → Research Manager          │    │
                  │  └────────────────────┬─────────────────────┘    │
                  │                       ▼                          │
                  │  ┌──────────────────────────────────────────┐    │
                  │  │ Trader                                   │    │
                  │  └────────────────────┬─────────────────────┘    │
                  │                       ▼                          │
                  │  ┌──────────────────────────────────────────┐    │
                  │  │ Risk Management (debate loop)            │    │
                  │  │  Aggressive ↔ Conservative ↔ Neutral     │    │
                  │  └────────────────────┬─────────────────────┘    │
                  │                       ▼                          │
                  │  ┌──────────────────────────────────────────┐    │
                  │  │ Portfolio Manager → final_trade_decision │    │
                  │  └─────────────────────────────────────────┘    │
                  └─────────────────────────────────────────────────┘
```

---

## 4. Vendor Capability Matrix

Sau khi thêm yfinance, vendor router sẽ hỗ trợ 3 nguồn dữ liệu:

| Method | Binance | yfinance | Alpha Vantage | Notes |
|---|---|---|---|---|
| `get_stock_data` | Crypto only | Stocks + Crypto | Stocks only | yfinance = universal fallback |
| `get_indicators` | Crypto only | Stocks + Crypto | Stocks only | All use stockstats internally |
| `get_fundamentals` | — | Stocks only | Stocks only | Crypto has no fundamentals |
| `get_balance_sheet` | — | Stocks only | Stocks only | |
| `get_cashflow` | — | Stocks only | Stocks only | |
| `get_income_statement` | — | Stocks only | Stocks only | |
| `get_news` | — | Stocks + Crypto | Stocks only | |
| `get_global_news` | — | — | Stocks only | |
| `get_insider_transactions` | — | Stocks only | Stocks only | |

### Recommended Default Vendor Config

```python
DEFAULT_VENDOR_CONFIG = {
    # Crypto tickers
    "crypto": {
        "core_stock_apis": "binance,yfinance",       # Binance primary, yfinance fallback
        "technical_indicators": "binance,yfinance",
        "news_data": "yfinance",                      # Binance has no news
    },
    # Stock tickers
    "stock": {
        "core_stock_apis": "yfinance,alpha_vantage",  # yfinance primary (free, no key)
        "technical_indicators": "yfinance,alpha_vantage",
        "fundamental_data": "yfinance,alpha_vantage",
        "news_data": "yfinance,alpha_vantage",
    },
}
```

---

## 5. yfinance Rate Limiting

yfinance gần đây bị Yahoo Finance throttle khá mạnh. Cần implement:

| Strategy | Implementation |
|---|---|
| Request throttling | `time.sleep(0.5)` between calls |
| Retry with backoff | Exponential backoff on HTTP 429 |
| Caching | Cache `info` / `financials` per session (TTL = 5 min) |
| Fallback | Auto-fallback to Alpha Vantage on repeated 429s |

---

## 6. File Changes Required

| File | Action | Description |
|---|---|---|
| `cli/symbol_normalizer.py` | **NEW** | Layer 1 — parse user input → CanonicalSymbol |
| `dataflows/symbol_formatter.py` | **NEW** | Layer 2 — CanonicalSymbol → vendor string |
| `dataflows/yfinance.py` | **NEW** | yfinance vendor implementation |
| `dataflows/interface.py` | **MODIFY** | Add yfinance to VENDOR_METHODS + VENDOR_LIST |
| `cli/utils.py` | **MODIFY** | Use parse_symbol() instead of normalize_ticker_symbol() |
| `cli/main.py` | **MODIFY** | Pass CanonicalSymbol through the pipeline |
| `default_config.py` | **MODIFY** | Add yfinance vendor config defaults |
| `tests/test_symbol_normalizer.py` | **NEW** | Unit tests for symbol parsing |
| `tests/test_symbol_formatter.py` | **NEW** | Unit tests for vendor formatting |
