# Data Flows API Reference

This document describes the data vendor abstraction layer and available data sources.

## Overview

TradingAgents uses a vendor-agnostic interface for data access, allowing seamless switching between data providers.

Location: `tradingagents/dataflows/`

## Configuration

### Setting Data Vendors

```python
from tradingagents.dataflows.config import set_config

config = {
    "data_vendors": {
        "core_stock_apis": "yfinance",
        "technical_indicators": "yfinance",
        "fundamental_data": "alpha_vantage",
        "news_data": "alpha_vantage"
    }
}

set_config(config)
```

### Getting Current Configuration

```python
from tradingagents.dataflows.config import get_config

config = get_config()
print(config["data_vendors"])
```

## Data Vendors

### yfinance

**Location**: `tradingagents/dataflows/yfinance.py`

**Capabilities**:
- Stock prices (OHLCV)
- Technical indicators
- Basic company information

**Setup**: No API key required

**Rate Limits**: None (public data)

**Example**:
```python
from tradingagents.dataflows.yfinance import (
    yfinance_get_stock_data,
    yfinance_get_indicators
)

# Get stock data
data = yfinance_get_stock_data("NVDA", "2024-01-01", "2024-12-31")

# Get indicators
indicators = yfinance_get_indicators("NVDA", ["MACD", "RSI"])
```

### Alpha Vantage

**Location**: `tradingagents/dataflows/alpha_vantage.py`

**Capabilities**:
- Fundamental data
- Company financials
- News articles
- Economic indicators

**Setup**:
```bash
export ALPHA_VANTAGE_API_KEY=your_key_here
```

**Rate Limits**: 60 requests/minute for TradingAgents users

**Example**:
```python
from tradingagents.dataflows.alpha_vantage import (
    alphavantage_get_fundamentals,
    alphavantage_get_news
)

# Get fundamentals
fundamentals = alphavantage_get_fundamentals("NVDA")

# Get news
news = alphavantage_get_news("NVDA", "2024-01-15")
```

### Google News

**Location**: `tradingagents/dataflows/google.py`

**Capabilities**:
- Real-time news articles
- Global news search

**Setup**:
```bash
export GOOGLE_API_KEY=your_key_here  # Optional for basic usage
```

**Example**:
```python
from tradingagents.dataflows.google import google_get_news

news = google_get_news("NVDA", "2024-01-15")
```

### Local Cache

**Location**: `tradingagents/dataflows/local.py`

**Capabilities**:
- Offline backtesting
- Pre-downloaded data access

**Setup**: Place data files in `data_cache_dir`

**Example**:
```python
from tradingagents.dataflows.local import local_get_stock_data

data = local_get_stock_data("NVDA", "2024-01-01", "2024-12-31")
```

## Interface Layer

**Location**: `tradingagents/dataflows/interface.py`

### Unified Data Access

The interface layer provides vendor-agnostic functions:

```python
from tradingagents.dataflows.interface import (
    get_stock_data,
    get_indicators,
    get_fundamentals,
    get_news
)
```

### Automatic Routing

Based on configuration, requests are automatically routed:

```python
# Config says: "core_stock_apis": "yfinance"
data = get_stock_data("NVDA", "2024-01-01", "2024-12-31")
# Automatically calls yfinance_get_stock_data()
```

## Data Schemas

### Stock Data (OHLCV)

```python
{
    "ticker": "NVDA",
    "dates": ["2024-01-01", "2024-01-02", ...],
    "open": [150.0, 151.2, ...],
    "high": [152.5, 153.0, ...],
    "low": [149.8, 150.5, ...],
    "close": [151.0, 152.0, ...],
    "volume": [1000000, 1200000, ...],
    "adj_close": [151.0, 152.0, ...]  # Optional
}
```

### Technical Indicators

```python
{
    "MACD": {
        "macd": [0.5, 0.6, ...],
        "signal": [0.4, 0.5, ...],
        "histogram": [0.1, 0.1, ...]
    },
    "RSI": {
        "rsi": [65.0, 67.5, ...]
    },
    "BollingerBands": {
        "upper": [155.0, 156.0, ...],
        "middle": [150.0, 151.0, ...],
        "lower": [145.0, 146.0, ...]
    }
}
```

### Fundamental Data

```python
{
    "Symbol": "NVDA",
    "MarketCapitalization": 2800000000000,
    "PERatio": 35.2,
    "PEGRatio": 1.8,
    "BookValue": 25.50,
    "DividendYield": 0.005,
    "EPS": 4.25,
    "ProfitMargin": 0.25,
    "OperatingMarginTTM": 0.30,
    "ReturnOnAssetsTTM": 0.22,
    "ReturnOnEquityTTM": 0.45,
    "RevenueTTM": 60000000000,
    "GrossProfitTTM": 45000000000
}
```

### News Data

```python
{
    "ticker": "NVDA",
    "date": "2024-01-15",
    "articles": [
        {
            "title": "Company Announces Record Earnings",
            "source": "Reuters",
            "url": "https://...",
            "published_at": "2024-01-15T10:30:00Z",
            "sentiment": 0.8,  # -1 to 1
            "summary": "Full article summary...",
            "authors": ["John Doe"],
            "time_published": "20240115T103000"
        },
        ...
    ]
}
```

## Error Handling

### VendorError

Base exception for data vendor errors:

```python
from tradingagents.dataflows.exceptions import VendorError

try:
    data = get_stock_data("INVALID", "2024-01-01", "2024-12-31")
except VendorError as e:
    print(f"Vendor error: {e}")
```

### RateLimitError

Raised when API rate limits are exceeded:

```python
from tradingagents.dataflows.exceptions import RateLimitError

try:
    data = get_fundamentals("NVDA")
except RateLimitError as e:
    print(f"Rate limit hit. Retry after {e.retry_after}s")
    time.sleep(e.retry_after)
```

### DataUnavailableError

Raised when requested data is not available:

```python
from tradingagents.dataflows.exceptions import DataUnavailableError

try:
    data = get_stock_data("NVDA", "1900-01-01", "1900-12-31")
except DataUnavailableError:
    print("Historical data not available for this date range")
```

## Caching

### Cache Configuration

```python
config = {
    "data_cache_dir": "./dataflows/data_cache",
    "cache_ttl": {
        "stock_data": 3600,  # 1 hour
        "fundamentals": 86400,  # 1 day
        "news": 3600  # 1 hour
    }
}
```

### Cache Functions

```python
from tradingagents.dataflows.cache import (
    get_cached,
    save_cache,
    clear_cache
)

# Get from cache
cached_data = get_cached("nvda_stock_2024")

# Save to cache
save_cache("nvda_stock_2024", data, ttl=3600)

# Clear cache
clear_cache()
```

## Best Practices

1. **Use Configuration**: Don't hardcode vendors
2. **Handle Errors**: Implement retry logic for rate limits
3. **Cache Data**: Avoid redundant API calls
4. **Validate Inputs**: Check ticker symbols and dates
5. **Use Fallbacks**: Have backup vendors configured

## Examples

### Basic Data Retrieval

```python
from tradingagents.dataflows.interface import get_stock_data

data = get_stock_data("NVDA", "2024-01-01", "2024-12-31")
print(f"Close prices: {data['close']}")
```

### Multiple Indicators

```python
from tradingagents.dataflows.interface import get_indicators

indicators = get_indicators("NVDA", ["MACD", "RSI", "BollingerBands"])
print(f"RSI: {indicators['RSI']['rsi'][-1]}")
```

### With Error Handling

```python
from tradingagents.dataflows.interface import get_news
from tradingagents.dataflows.exceptions import VendorError
import time

def get_news_with_retry(ticker, date, max_retries=3):
    for attempt in range(max_retries):
        try:
            return get_news(ticker, date)
        except VendorError as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise
```

## See Also

- [Data Flow Architecture](../architecture/data-flow.md)
- [Configuration Guide](../guides/configuration.md)
- [Adding Data Vendor Guide](../guides/adding-data-vendor.md)
