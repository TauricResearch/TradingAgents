# Data Flow Architecture

This document describes how data flows through the TradingAgents system, from external data sources to final trading decisions.

## Overview

TradingAgents implements a flexible data abstraction layer that allows seamless switching between data vendors without changing agent code.

## Data Flow Diagram

```
External Sources          Abstraction Layer        Agents              Decision
─────────────────        ──────────────────      ────────            ─────────

yfinance        ─┐
Alpha Vantage   ─┼→  Interface Layer  →  Analysts  →  Researchers  →  Trader
Google News     ─┤    (config-driven)      ↓             ↓              ↓
Local Cache     ─┘                      Reports      Debates       Decision
                                           ↓             ↓              ↓
                                      Vector Memory  Synthesis    Risk Check
```

## Data Vendors

### Core Data Vendors

TradingAgents supports multiple data vendors, configurable per data category:

#### yfinance
- **Purpose**: Stock prices, technical indicators
- **Pros**: Free, reliable, comprehensive market data
- **Cons**: Limited fundamental data
- **Rate Limits**: None (public data)
- **Location**: `tradingagents/dataflows/yfinance.py`

#### Alpha Vantage
- **Purpose**: Fundamental data, news, company financials
- **Pros**: Rich fundamental data, partnership with TradingAgents for enhanced limits
- **Cons**: Requires API key
- **Rate Limits**: 60 requests/minute for TradingAgents users (normally 25/day free tier)
- **Location**: `tradingagents/dataflows/alpha_vantage.py`

#### Google News
- **Purpose**: News articles and headlines
- **Pros**: Real-time news, comprehensive coverage
- **Cons**: Requires API key for full access
- **Location**: `tradingagents/dataflows/google.py`

#### Local Cache
- **Purpose**: Offline backtesting, development
- **Pros**: Fast, no API limits, reproducible
- **Cons**: Data must be pre-downloaded
- **Location**: `tradingagents/dataflows/local.py`

### Data Categories

Data vendor configuration is organized by category:

```python
config["data_vendors"] = {
    "core_stock_apis": "yfinance",       # Price data, quotes
    "technical_indicators": "yfinance",  # MACD, RSI, etc.
    "fundamental_data": "alpha_vantage", # Financials, ratios
    "news_data": "alpha_vantage",        # News and events
}
```

## Interface Layer

### Unified Interface

All agents access data through a unified interface:

```python
from tradingagents.agents.utils.agent_utils import (
    get_stock_data,
    get_indicators,
    get_fundamentals,
    get_news
)
```

### Interface Routing

The interface layer routes requests to the configured vendor:

**Configuration:**
```python
from tradingagents.dataflows.config import set_config

config = {
    "data_vendors": {
        "core_stock_apis": "yfinance"
    }
}
set_config(config)
```

**Usage:**
```python
# Automatically routes to yfinance based on config
data = get_stock_data("NVDA", "2024-01-01", "2024-12-31")
```

**Implementation:**
```python
def get_stock_data(ticker: str, start_date: str, end_date: str):
    vendor = get_vendor_for_category("core_stock_apis")

    if vendor == "yfinance":
        return yfinance_get_stock_data(ticker, start_date, end_date)
    elif vendor == "alpha_vantage":
        return alphavantage_get_stock_data(ticker, start_date, end_date)
    elif vendor == "local":
        return local_get_stock_data(ticker, start_date, end_date)
```

Location: `tradingagents/dataflows/interface.py`

## Data Types

### Price Data

Historical stock prices (OHLCV):

```python
{
    "dates": ["2024-01-01", "2024-01-02", ...],
    "open": [150.0, 151.2, ...],
    "high": [152.5, 153.0, ...],
    "low": [149.8, 150.5, ...],
    "close": [151.0, 152.0, ...],
    "volume": [1000000, 1200000, ...]
}
```

### Technical Indicators

Calculated technical analysis metrics:

```python
{
    "MACD": {
        "macd": [...],
        "signal": [...],
        "histogram": [...]
    },
    "RSI": {
        "rsi": [...]
    },
    "BollingerBands": {
        "upper": [...],
        "middle": [...],
        "lower": [...]
    }
}
```

### Fundamental Data

Company financial metrics:

```python
{
    "MarketCapitalization": 2800000000000,
    "PERatio": 35.2,
    "PEGRatio": 1.8,
    "BookValue": 25.50,
    "DividendYield": 0.005,
    "ProfitMargin": 0.25,
    "OperatingMarginTTM": 0.30,
    "ReturnOnAssetsTTM": 0.22,
    "ReturnOnEquityTTM": 0.45
}
```

### News Data

News articles and headlines:

```python
{
    "articles": [
        {
            "title": "Company Announces Record Earnings",
            "source": "Reuters",
            "published_at": "2024-01-15T10:30:00Z",
            "sentiment": 0.8,  # -1 to 1
            "summary": "..."
        },
        ...
    ]
}
```

## Data Caching

### Cache Strategy

TradingAgents implements multi-level caching:

1. **Memory Cache**: In-process cache for repeated requests within a session
2. **Disk Cache**: Persistent cache for expensive API calls
3. **Vector Store**: Semantic cache for analysis results

### Cache Configuration

```python
config["data_cache_dir"] = "./dataflows/data_cache"
```

### Cache Keys

Cache keys are generated from request parameters:

```python
cache_key = f"{vendor}_{function}_{ticker}_{start_date}_{end_date}"
```

### Cache Invalidation

Caches expire based on data freshness requirements:

- **Price Data**: 1 hour (intraday), 1 day (historical)
- **Fundamental Data**: 1 day
- **News Data**: 1 hour
- **Technical Indicators**: Based on underlying price data

Location: `tradingagents/dataflows/cache.py`

## Data Validation

### Input Validation

All data inputs are validated before processing:

```python
def validate_ticker(ticker: str) -> bool:
    """Validate ticker symbol format."""
    return bool(re.match(r'^[A-Z]{1,5}$', ticker))

def validate_date(date_str: str) -> bool:
    """Validate date format (YYYY-MM-DD)."""
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
        return True
    except ValueError:
        return False
```

### Output Validation

Data vendor responses are validated for completeness:

```python
def validate_stock_data(data: dict) -> bool:
    """Ensure stock data has required fields."""
    required = ["dates", "open", "high", "low", "close", "volume"]
    return all(field in data for field in required)
```

## Error Handling

### Vendor Fallback

If a vendor fails, the system can fall back to alternatives:

```python
def get_stock_data_with_fallback(ticker, start_date, end_date):
    vendors = ["yfinance", "alpha_vantage", "local"]

    for vendor in vendors:
        try:
            return get_stock_data(ticker, start_date, end_date, vendor=vendor)
        except VendorError:
            continue

    raise DataUnavailableError(f"No vendor could provide data for {ticker}")
```

### Rate Limit Handling

Automatic retry with exponential backoff for rate limits:

```python
def handle_rate_limit(func, max_retries=3):
    for attempt in range(max_retries):
        try:
            return func()
        except RateLimitError as e:
            wait_time = e.retry_after or (2 ** attempt)
            time.sleep(wait_time)

    raise RateLimitExceeded("Max retries exceeded")
```

## Data Flow Examples

### Market Analyst Workflow

```python
# 1. Market Analyst requests technical data
data = get_stock_data("NVDA", "2024-01-01", "2024-12-31")
indicators = get_indicators("NVDA", ["MACD", "RSI", "BollingerBands"])

# 2. Interface routes to configured vendor (yfinance)
# 3. Data is fetched, cached, and validated
# 4. Analyst processes data and generates report
report = analyze_technical_signals(data, indicators)

# 5. Report is stored in agent state
state.analyst_reports["market"] = report
```

### Fundamentals Analyst Workflow

```python
# 1. Fundamentals Analyst requests financial data
fundamentals = get_fundamentals("NVDA")
balance_sheet = get_balance_sheet("NVDA")
income_statement = get_income_statement("NVDA")

# 2. Interface routes to configured vendor (alpha_vantage)
# 3. Data is fetched from Alpha Vantage API
# 4. Analyst evaluates financial health
report = analyze_financial_health(fundamentals, balance_sheet, income_statement)

# 5. Report is stored in agent state
state.analyst_reports["fundamentals"] = report
```

### News Analyst Workflow

```python
# 1. News Analyst requests news data
company_news = get_news("NVDA", "2024-01-15")
global_news = get_global_news("2024-01-15")

# 2. Interface routes to configured vendor (alpha_vantage or google)
# 3. News articles are fetched and sentiment scored
# 4. Analyst identifies market-moving events
report = analyze_news_impact(company_news, global_news)

# 5. Report is stored in agent state
state.analyst_reports["news"] = report
```

## Performance Optimization

### Batch Requests

Request multiple data points in a single API call:

```python
# Bad: Multiple API calls
data1 = get_stock_data("NVDA", "2024-01-01", "2024-01-02")
data2 = get_stock_data("NVDA", "2024-01-03", "2024-01-04")

# Good: Single API call
data = get_stock_data("NVDA", "2024-01-01", "2024-01-04")
```

### Parallel Requests

Fetch data for multiple tickers in parallel:

```python
import asyncio

async def fetch_multiple_tickers(tickers):
    tasks = [get_stock_data_async(ticker, start, end) for ticker in tickers]
    return await asyncio.gather(*tasks)
```

### Data Preprocessing

Preprocess data once and cache results:

```python
def get_preprocessed_indicators(ticker, start_date, end_date):
    cache_key = f"preprocessed_{ticker}_{start_date}_{end_date}"

    if cached := get_from_cache(cache_key):
        return cached

    data = get_stock_data(ticker, start_date, end_date)
    indicators = calculate_all_indicators(data)

    save_to_cache(cache_key, indicators)
    return indicators
```

## Best Practices

1. **Use Configuration**: Always configure vendors through config, not hardcoded
2. **Handle Errors Gracefully**: Implement fallbacks and retries
3. **Cache Aggressively**: Cache expensive API calls with appropriate TTL
4. **Validate Data**: Check data completeness before using
5. **Monitor Usage**: Track API quotas and rate limits
6. **Batch When Possible**: Minimize API calls through batching
7. **Use Async for Parallelism**: Fetch multiple resources concurrently

## References

- [Multi-Agent System](multi-agent-system.md)
- [Data Flows API](../api/dataflows.md)
- [Configuration Guide](../guides/configuration.md)
- [Adding Data Vendor Guide](../guides/adding-data-vendor.md)
