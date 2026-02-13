# China A-Share Support for TradingAgents

## Overview

Add China A-share (Shanghai SSE / Shenzhen SZSE) stock analysis capability to TradingAgents, using AKShare as the data vendor. The implementation leverages the existing vendor routing framework — no changes to agent logic, LangGraph workflow, or LLM client layer.

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Data source | AKShare | Free, no API key, covers OHLCV/fundamentals/news/social sentiment, actively maintained (~18k GitHub stars) |
| Chinese data handling | Feed Chinese text directly to LLM | Modern LLMs handle Chinese well; avoids translation overhead and loss of financial terminology accuracy |
| Market identification | Ticker suffix auto-detection (`.SH`/`.SZ`) | Zero config for users, no API signature changes, backward compatible |
| Implementation scope | All 4 analyst types at once | AKShare supports all data categories; incremental approach saves no real effort |
| Global macro news | Auto-switch by ticker market | A-share tickers get Chinese macro news (PBOC, policy); US tickers keep existing logic |
| Social sentiment | Append to `get_news` return | Avoids new tool definitions and agent binding changes |

## Architecture

### Data Flow

```
propagate("600519.SH", "2026-01-15")
    │
    ▼
ticker_utils.detect_market("600519.SH") → "CN_SH"
    │
    ▼
interface.route_to_vendor() → forces "akshare" for CN tickers
    │
    ▼
akshare_data.py / akshare_news.py
    │
    ▼
Analyst agents receive data (Chinese text) → LLM analyzes normally
```

For US tickers (e.g., `"NVDA"`), the existing yfinance/alpha_vantage routing is unchanged.

### Routing Priority

1. Ticker is A-share (`.SH`/`.SZ`) → **force akshare** (ignore config `data_vendors`)
2. Ticker is US/other → follow existing config routing (yfinance / alpha_vantage)

## New Files

### `tradingagents/dataflows/ticker_utils.py`

Ticker market detection and parsing utilities.

```python
def detect_market(ticker: str) -> str:
    """Detect market from ticker suffix.

    Returns: "CN_SH", "CN_SZ", "US", etc.
    """

def parse_ticker(ticker: str) -> tuple[str, str]:
    """Split ticker into code and exchange.

    "600519.SH" → ("600519", "sh")
    "NVDA" → ("NVDA", "")
    """

def is_china_stock(ticker: str) -> bool:
    """Shortcut: returns True for .SH/.SZ tickers."""
```

### `tradingagents/dataflows/akshare_data.py`

Core stock data and fundamentals via AKShare. All functions return formatted strings matching the existing yfinance output pattern, so analyst prompts work unchanged.

| Function | AKShare API | Notes |
|----------|------------|-------|
| `get_stock_data(ticker, start, end)` | `ak.stock_zh_a_hist()` | Daily OHLCV, output as CSV string |
| `get_indicators(ticker, start, end)` | OHLCV + `stockstats` calculation | Same approach as yfinance — compute SMA/EMA/MACD/RSI/BOLL from raw OHLCV using stockstats (already a project dependency) |
| `get_fundamentals(ticker)` | `ak.stock_individual_info_em()` + `ak.stock_financial_abstract_ths()` | Company overview, Market Cap, PE, ROE, etc. |
| `get_balance_sheet(ticker)` | `ak.stock_balance_sheet_by_report_em()` | Balance sheet (Chinese field names, LLM handles directly) |
| `get_cashflow(ticker)` | `ak.stock_cash_flow_sheet_by_report_em()` | Cash flow statement |
| `get_income_statement(ticker)` | `ak.stock_profit_sheet_by_report_em()` | Income/profit statement |

### `tradingagents/dataflows/akshare_news.py`

News, macro, insider, and social sentiment data.

| Function | AKShare API | Notes |
|----------|------------|-------|
| `get_news(ticker)` | `ak.stock_news_em()` + `ak.stock_hot_rank_em()` | Company news from Eastmoney, with social heat ranking/sentiment appended at the end |
| `get_global_news()` | `ak.news_cctv()` or `ak.stock_zh_a_alerts_cls()` | Chinese macro news (CCTV Finance / CLS alerts), replaces "Federal Reserve" queries |
| `get_insider_transactions(ticker)` | `ak.stock_share_hold_change_ths()` | Shareholder increase/decrease holdings |

## Modified Files

### `tradingagents/dataflows/interface.py`

Add market detection before vendor routing:

```python
from .ticker_utils import is_china_stock

def route_to_vendor(tool_name, category, config, ticker=None):
    # A-share auto-routing (highest priority)
    if ticker and is_china_stock(ticker):
        vendor = "akshare"
    else:
        # existing logic: check tool_vendors, then data_vendors
        vendor = config["tool_vendors"].get(tool_name) or config["data_vendors"].get(category, "yfinance")

    # add akshare dispatch
    if vendor == "akshare":
        if category == "news_data":
            return akshare_news_dispatch(tool_name, ...)
        else:
            return akshare_data_dispatch(tool_name, ...)
    # existing yfinance/alpha_vantage dispatch...
```

### `pyproject.toml` + `requirements.txt`

Add dependency:
```
akshare>=1.14.0
```

## Prerequisites & Risks

| Item | Status | Mitigation |
|------|--------|------------|
| AKShare library | Not installed | `pip install akshare` — no API key needed |
| A-share trading calendar | Chinese holidays differ (Spring Festival, Golden Week) | If date falls on non-trading day, AKShare returns empty data — add fallback to nearest trading day |
| Network access | AKShare scrapes Eastmoney/Sina — may be slow or blocked outside China | Document as known limitation; works well in domestic network |
| Financial report format | CAS (Chinese Accounting Standards), field names in Chinese | Pass Chinese text directly to LLM — confirmed approach |
| Error handling | AKShare calls may fail (network, rate limit) | Wrap all calls in try/except, return friendly error string (matches existing vendor pattern) |

## Out of Scope

- Hong Kong stocks (`.HK`) — can be added later with same pattern
- Real-time/intraday data — current system is daily granularity
- Agent prompt translation — LLMs handle mixed language data
- Config-based A-share vendor selection — A-share always uses AKShare for now
