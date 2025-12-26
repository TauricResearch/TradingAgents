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

### FRED (Federal Reserve Economic Data)

**Location**: `tradingagents/dataflows/fred.py` and `tradingagents/dataflows/fred_common.py`

**Capabilities**:
- Interest rates (Federal Funds Rate)
- Treasury rates (2Y, 5Y, 10Y, 30Y yields)
- Money supply (M1, M2 monetary aggregates)
- GDP (nominal and real growth data)
- Inflation (CPI and PCE price indexes)
- Unemployment rate

**Setup**:
```bash
export FRED_API_KEY=your_key_here
```

**Rate Limits**: 120 requests per minute with built-in retry logic and exponential backoff (1-2-4s delays)

**Features**:
- Local file caching with 24-hour TTL to reduce API quota consumption
- Retry logic with exponential backoff for transient failures
- Custom exceptions (FredRateLimitError, FredInvalidSeriesError) for robust error handling
- Date range filtering with flexible date format support
- All functions return pandas DataFrames with 'date' and 'value' columns

**Example**:
```python
from tradingagents.dataflows.fred import (
    get_interest_rates,
    get_treasury_rates,
    get_gdp,
    get_inflation,
    get_unemployment,
    get_money_supply,
    get_fred_series
)

# Get Federal Funds Rate
fed_funds = get_interest_rates()

# Get 10-year treasury yield with date range
treasury_10y = get_treasury_rates(
    maturity='10Y',
    start_date='2024-01-01',
    end_date='2024-12-31'
)

# Get real GDP data
gdp_data = get_gdp(series_type='real')

# Get unemployment rate
unemployment = get_unemployment()

# Get inflation (CPI)
inflation = get_inflation(inflation_type='CPI')

# Get M2 money supply
m2 = get_money_supply(money_measure='M2')

# Get any FRED series by ID
custom_series = get_fred_series('UNRATE')  # Also returns unemployment

# Disable caching for real-time data
live_data = get_interest_rates(use_cache=False)
```

**Available Functions**:
- `get_interest_rates()` - Federal Funds Rate
- `get_treasury_rates(maturity='10Y')` - Treasury yields (2Y, 5Y, 10Y, 30Y)
- `get_money_supply(money_measure='M1')` - M1 or M2 monetary aggregates
- `get_gdp(series_type='real')` - Real or nominal GDP
- `get_inflation(inflation_type='CPI')` - CPI or PCE inflation
- `get_unemployment()` - Unemployment rate
- `get_fred_series(series_id)` - Generic series access by FRED ID

**Error Handling**:
```python
from tradingagents.dataflows.fred_common import (
    FredRateLimitError,
    FredInvalidSeriesError
)

try:
    data = get_interest_rates()
except FredRateLimitError as e:
    print(f"Rate limit hit. Retry after {e.retry_after}s")
except FredInvalidSeriesError as e:
    print(f"Invalid FRED series: {e.series_id}")
```

### Multi-Timeframe Aggregation

**Location**: `tradingagents/dataflows/multi_timeframe.py`

**Capabilities**:
- Convert daily OHLCV data to weekly timeframe
- Convert daily OHLCV data to monthly timeframe
- Preserve timezone information
- Handle partial periods

**Setup**: No external dependencies, uses pandas

**Features**:
- Proper OHLCV aggregation rules: Open=first, High=max, Low=min, Close=last, Volume=sum
- Configurable week anchor (Sunday or Monday)
- Month-end or month-start labels for aggregated periods
- Input validation with descriptive error messages
- Returns DataFrame on success, error string on failure

**Example**:
```python
from tradingagents.dataflows.multi_timeframe import (
    aggregate_to_weekly,
    aggregate_to_monthly
)
import pandas as pd

# Create sample daily data
dates = pd.date_range('2024-01-01', periods=60, freq='D')
daily_data = pd.DataFrame({
    'Open': range(100, 160),
    'High': range(102, 162),
    'Low': range(99, 159),
    'Close': range(101, 161),
    'Volume': range(1000000, 1060000, 1000)
}, index=dates)

# Aggregate to weekly (Sunday anchor, default)
weekly = aggregate_to_weekly(daily_data, anchor='SUN')
# Returns DataFrame with weekly OHLCV bars

# Aggregate to weekly (Monday anchor)
weekly_mon = aggregate_to_weekly(daily_data, anchor='MON')

# Aggregate to monthly (month-end labels)
monthly = aggregate_to_monthly(daily_data, period_end=True)
# Returns DataFrame with monthly OHLCV bars

# Aggregate to monthly (month-start labels)
monthly_start = aggregate_to_monthly(daily_data, period_end=False)
```

**Available Functions**:
- `aggregate_to_weekly(data, anchor='SUN')` - Convert daily to weekly bars
  - Supports week anchors: 'SUN' (Sunday), 'MON' (Monday)
  - Returns DataFrame with weekly aggregated OHLCV data
- `aggregate_to_monthly(data, period_end=True)` - Convert daily to monthly bars
  - period_end=True: Month-end labels and boundaries
  - period_end=False: Month-start labels and boundaries
  - Returns DataFrame with monthly aggregated OHLCV data

**Return Formats**:
- Success: pandas DataFrame with DatetimeIndex and OHLCV columns
- Failure: Error string describing validation error

**Error Handling**:
```python
result = aggregate_to_weekly(data, anchor='SUN')
if isinstance(result, str):
    print(f"Error: {result}")
else:
    print(f"Weekly data: {result}")
```

**Validation Requirements**:
- DataFrame must not be empty
- DataFrame must have DatetimeIndex
- DataFrame must contain columns: Open, High, Low, Close, Volume

**Timezone Notes**:
- Timezone information in the index is preserved through aggregation
- Both UTC and localized timezones (e.g., America/New_York) are supported
- Partial periods (e.g., < 7 days for weekly) are aggregated correctly

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
