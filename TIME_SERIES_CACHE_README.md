# Time Series Cache System for Financial Data

An intelligent caching system for TradingAgents that optimizes financial API calls through smart time series data management.

## 🚀 Overview

The Time Series Cache system provides intelligent caching for financial data APIs, automatically managing:
- **Date Range Optimization**: Detects overlapping queries and fetches only missing data
- **Multiple Data Types**: OHLCV, news, fundamentals, technical indicators, insider data
- **Storage Efficiency**: Uses Parquet format with SQLite indexing for fast retrieval
- **Cache Management**: Built-in statistics, cleanup, and monitoring tools

## 📊 Key Features

### ✅ Intelligent Gap Detection
- Automatically identifies what data is already cached
- Only fetches missing date ranges from APIs
- Seamlessly merges cached and new data

### ✅ Multiple Data Type Support
- **OHLCV Data**: Price, volume data from YFinance
- **News Data**: Finnhub news, Google News
- **Technical Indicators**: RSI, MACD, SMA, etc.
- **Insider Data**: SEC insider transactions and sentiment
- **Fundamentals**: Financial statements and ratios

### ✅ Performance Optimization
- **Fast Storage**: Parquet files for data, SQLite for indexing
- **Memory Efficient**: Loads only requested date ranges
- **Parallel Safe**: Thread-safe operations for concurrent access

### ✅ Cache Management
- Performance statistics and monitoring
- Automated cleanup of old data
- Symbol-specific and date-based clearing

## 🔧 Installation & Setup

The cache system is integrated into TradingAgents dataflows. No additional setup required!

Cache files are stored in: `data_cache/time_series/`

## 📖 Usage Examples

### Basic OHLCV Data Caching

```python
from tradingagents.dataflows import get_YFin_data_cached

# First call - fetches from API and caches
data = get_YFin_data_cached("AAPL", "2024-01-01", "2024-01-15")

# Second call - uses cache (much faster!)
data = get_YFin_data_cached("AAPL", "2024-01-01", "2024-01-15")

# Overlapping range - only fetches new dates
data = get_YFin_data_cached("AAPL", "2024-01-10", "2024-01-25")
```

### Window-Based Data Retrieval

```python
from tradingagents.dataflows import get_YFin_data_window_cached

# Get 30 days of data before current date
data = get_YFin_data_window_cached("TSLA", "2024-01-15", 30)
```

### News Data Caching

```python
from tradingagents.dataflows import get_finnhub_news_cached, get_google_news_cached

# Cache Finnhub news
news = get_finnhub_news_cached("AAPL", "2024-01-15", 7)

# Cache Google News
google_news = get_google_news_cached("stock market", "2024-01-15", 7)
```

### Technical Indicators Caching

```python
from tradingagents.dataflows import get_technical_indicators_cached

# Cache RSI calculations
rsi_data = get_technical_indicators_cached("AAPL", "rsi", "2024-01-15", 20)

# Cache MACD calculations  
macd_data = get_technical_indicators_cached("AAPL", "macd", "2024-01-15", 30)
```

### Cache Performance Monitoring

```python
from tradingagents.dataflows import get_cache_statistics

# Get comprehensive cache stats
stats = get_cache_statistics()
print(stats)

# Output example:
# ## Financial Data Cache Statistics
# 
# **Cache Performance:**
# - Total Entries: 42
# - Cache Size: 15.67 MB
# - Hit Ratio: 78.3%
# - Cache Hits: 89
# - Cache Misses: 25
# - API Calls Saved: 64
```

### Cache Management

```python
from tradingagents.dataflows import clear_cache_data

# Clear cache for specific symbol
clear_cache_data(symbol="AAPL")

# Clear data older than 30 days
clear_cache_data(older_than_days=30)

# Clear old data for specific symbol
clear_cache_data(symbol="AAPL", older_than_days=7)
```

## 🏗️ Architecture

### Core Components

1. **TimeSeriesCache**: Main cache engine with intelligent date range management
2. **CachedApiWrappers**: Integration layer with existing financial APIs
3. **Interface Functions**: Drop-in replacements for existing API calls

### Data Flow

```
API Request → Cache Check → Gap Detection → API Fetch (if needed) → Cache Store → Return Data
```

### Storage Structure

```
data_cache/time_series/
├── cache_index.db          # SQLite index for fast lookups
├── ohlcv/                  # OHLCV data files
│   ├── AAPL_abc123.parquet
│   └── TSLA_def456.parquet
├── news/                   # News data files
├── indicators/             # Technical indicators
├── insider/               # Insider trading data
└── sentiment/             # Sentiment analysis data
```

## 📈 Performance Benefits

### Speed Improvements
- **Cache Hits**: 10-100x faster than API calls
- **Gap Filling**: Only fetches missing data
- **Batch Operations**: Efficient for overlapping queries

### Cost Savings
- **Reduced API Calls**: Can reduce API usage by 60-90%
- **Rate Limit Friendly**: Avoids redundant API requests
- **Bandwidth Efficient**: Local storage reduces network usage

### Example Performance

```python
# First call: ~2.5 seconds (API fetch + cache)
data1 = get_YFin_data_cached("AAPL", "2024-01-01", "2024-01-15")

# Second call: ~0.05 seconds (cache hit)
data2 = get_YFin_data_cached("AAPL", "2024-01-01", "2024-01-15")

# 50x speed improvement!
```

## 🔄 Migration Guide

### Replace Existing Functions

| Old Function | New Cached Function |
|--------------|-------------------|
| `get_YFin_data()` | `get_YFin_data_cached()` |
| `get_YFin_data_window()` | `get_YFin_data_window_cached()` |
| `get_finnhub_news()` | `get_finnhub_news_cached()` |
| `get_google_news()` | `get_google_news_cached()` |

### Example Migration

```python
# Before
from tradingagents.dataflows import get_YFin_data
data = get_YFin_data("AAPL", "2024-01-01", "2024-01-15")

# After  
from tradingagents.dataflows import get_YFin_data_cached
data = get_YFin_data_cached("AAPL", "2024-01-01", "2024-01-15")

# Same interface, better performance!
```

## 🛠️ Advanced Configuration

### Custom Cache Directory

```python
from tradingagents.dataflows.time_series_cache import TimeSeriesCache

# Create cache with custom directory
cache = TimeSeriesCache(cache_dir="/path/to/custom/cache")
```

### Direct Cache API

```python
from tradingagents.dataflows.time_series_cache import get_cache, DataType
from datetime import datetime

cache = get_cache()

# Check cache coverage
gaps, cached = cache.check_cache_coverage(
    "AAPL", 
    DataType.OHLCV, 
    datetime(2024, 1, 1), 
    datetime(2024, 1, 15)
)

# Fetch with custom function
def my_fetch_function(symbol, start_date, end_date):
    # Your custom API fetch logic
    return pd.DataFrame(...)

data = cache.fetch_with_cache(
    "AAPL", 
    DataType.OHLCV,
    datetime(2024, 1, 1),
    datetime(2024, 1, 15), 
    my_fetch_function
)
```

## 🧪 Testing

Run the demo script to test the caching system:

```bash
python demo_time_series_cache.py
```

This will demonstrate:
- OHLCV data caching performance
- News data caching
- Technical indicators caching  
- Cache statistics and management

## 🔍 Troubleshooting

### Common Issues

**Cache directory permissions**
```bash
# Ensure write permissions
chmod 755 data_cache/time_series/
```

**SQLite database locked**
- Restart Python process
- Check for concurrent access

**Missing data dependencies**
```bash
# Install required packages
pip install pandas pyarrow sqlite3
```

### Debug Mode

```python
import logging
logging.basicConfig(level=logging.INFO)

# Cache operations will now show detailed logs
data = get_YFin_data_cached("AAPL", "2024-01-01", "2024-01-15")
```

## 📋 Cache Statistics Explained

| Metric | Description |
|--------|-------------|
| **Total Entries** | Number of cached data segments |
| **Cache Size** | Total disk space used (MB) |
| **Hit Ratio** | % of requests served from cache |
| **Cache Hits** | Number of successful cache retrievals |
| **Cache Misses** | Number of API calls required |
| **API Calls Saved** | Estimated API calls avoided |

## 🤝 Contributing

The cache system is designed to be extensible. To add new data types:

1. Add new `DataType` enum value
2. Create wrapper function in `cached_api_wrappers.py`
3. Add interface function in `interface.py`
4. Update exports in `__init__.py`

## 📚 Related Documentation

- [TradingAgents API Documentation](./README.md)
- [Financial Data Configuration](./tradingagents/dataflows/config.py)
- [Agent Utilities](./tradingagents/agents/utils/)

---

**💡 Pro Tip**: Monitor cache performance regularly with `get_cache_statistics()` to optimize your data retrieval patterns! 