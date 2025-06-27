"""
Cached API Wrappers for Financial Data
Integrates the TimeSeriesCache with existing financial APIs
"""

import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import logging

from .time_series_cache import (
    get_cache, DataType, 
    fetch_ohlcv_with_cache, fetch_news_with_cache, fetch_fundamentals_with_cache
)
from .interface import get_data_in_range
from .googlenews_utils import getNewsData
from .config import get_config, DATA_DIR

logger = logging.getLogger(__name__)


# YFinance OHLCV Data Caching
def fetch_yfinance_data_cached(symbol: str, start_date: datetime, end_date: datetime) -> pd.DataFrame:
    """
    Fetch YFinance OHLCV data with intelligent caching
    
    Args:
        symbol: Stock ticker symbol
        start_date: Start date for data
        end_date: End date for data
    
    Returns:
        DataFrame with OHLCV data
    """
    
    def _fetch_yfinance_api(symbol: str, start_date: datetime, end_date: datetime) -> pd.DataFrame:
        """Internal function to fetch from YFinance API"""
        try:
            ticker = yf.Ticker(symbol)
            
            # Add one day to end_date to make it inclusive
            end_date_inclusive = end_date + timedelta(days=1)
            
            data = ticker.history(
                start=start_date.strftime('%Y-%m-%d'),
                end=end_date_inclusive.strftime('%Y-%m-%d'),
                auto_adjust=True,
                progress=False
            )
            
            if data.empty:
                logger.warning(f"No YFinance data found for {symbol} from {start_date.date()} to {end_date.date()}")
                return pd.DataFrame()
            
            # Reset index to make Date a column
            data = data.reset_index()
            
            # Standardize column names and add date column
            data['date'] = data['Date']
            data['symbol'] = symbol
            
            # Round numeric columns
            numeric_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
            for col in numeric_cols:
                if col in data.columns:
                    data[col] = data[col].round(4)
            
            return data
            
        except Exception as e:
            logger.error(f"Failed to fetch YFinance data for {symbol}: {e}")
            return pd.DataFrame()
    
    return fetch_ohlcv_with_cache(symbol, start_date, end_date, _fetch_yfinance_api)


def fetch_yfinance_window_cached(symbol: str, curr_date: datetime, look_back_days: int) -> pd.DataFrame:
    """
    Fetch YFinance data for a window of days before current date with caching
    
    Args:
        symbol: Stock ticker symbol
        curr_date: Current/end date
        look_back_days: Number of days to look back
    
    Returns:
        DataFrame with OHLCV data
    """
    start_date = curr_date - timedelta(days=look_back_days)
    return fetch_yfinance_data_cached(symbol, start_date, curr_date)


# News Data Caching
def fetch_finnhub_news_cached(symbol: str, start_date: datetime, end_date: datetime) -> pd.DataFrame:
    """
    Fetch Finnhub news data with caching
    
    Args:
        symbol: Stock ticker symbol
        start_date: Start date for news
        end_date: End date for news
    
    Returns:
        DataFrame with news data
    """
    
    def _fetch_finnhub_news_api(symbol: str, start_date: datetime, end_date: datetime) -> pd.DataFrame:
        """Internal function to fetch Finnhub news from cached files"""
        try:
            # Use existing get_data_in_range function
            data = get_data_in_range(
                symbol, 
                start_date.strftime('%Y-%m-%d'), 
                end_date.strftime('%Y-%m-%d'), 
                "news_data", 
                DATA_DIR
            )
            
            if not data:
                return pd.DataFrame()
            
            # Convert to DataFrame format
            news_records = []
            for date_str, news_list in data.items():
                for news_item in news_list:
                    record = {
                        'date': pd.to_datetime(date_str),
                        'symbol': symbol,
                        'headline': news_item.get('headline', ''),
                        'summary': news_item.get('summary', ''),
                        'source': news_item.get('source', ''),
                        'url': news_item.get('url', ''),
                        'datetime': pd.to_datetime(news_item.get('datetime', date_str))
                    }
                    news_records.append(record)
            
            return pd.DataFrame(news_records)
            
        except Exception as e:
            logger.error(f"Failed to fetch Finnhub news for {symbol}: {e}")
            return pd.DataFrame()
    
    return fetch_news_with_cache(symbol, start_date, end_date, _fetch_finnhub_news_api)


def fetch_google_news_cached(query: str, start_date: datetime, end_date: datetime) -> pd.DataFrame:
    """
    Fetch Google News data with caching
    
    Args:
        query: Search query
        start_date: Start date for news
        end_date: End date for news
    
    Returns:
        DataFrame with news data
    """
    
    def _fetch_google_news_api(query: str, start_date: datetime, end_date: datetime) -> pd.DataFrame:
        """Internal function to fetch from Google News API"""
        try:
            query_formatted = query.replace(" ", "+")
            news_results = getNewsData(
                query_formatted, 
                start_date.strftime('%Y-%m-%d'), 
                end_date.strftime('%Y-%m-%d')
            )
            
            if not news_results:
                return pd.DataFrame()
            
            # Convert to DataFrame
            news_records = []
            for news_item in news_results:
                record = {
                    'date': pd.to_datetime(news_item.get('date', start_date)),
                    'query': query,
                    'title': news_item.get('title', ''),
                    'snippet': news_item.get('snippet', ''),
                    'source': news_item.get('source', ''),
                    'url': news_item.get('url', ''),
                    'published': pd.to_datetime(news_item.get('published', start_date))
                }
                news_records.append(record)
            
            return pd.DataFrame(news_records)
            
        except Exception as e:
            logger.error(f"Failed to fetch Google News for query '{query}': {e}")
            return pd.DataFrame()
    
    return fetch_news_with_cache(query, start_date, end_date, _fetch_google_news_api)


# Technical Indicators Caching
def fetch_technical_indicators_cached(symbol: str, indicator: str, start_date: datetime, end_date: datetime, **kwargs) -> pd.DataFrame:
    """
    Fetch technical indicators with caching
    
    Args:
        symbol: Stock ticker symbol
        indicator: Technical indicator name
        start_date: Start date
        end_date: End date
        **kwargs: Additional parameters for indicator calculation
    
    Returns:
        DataFrame with indicator data
    """
    
    def _fetch_indicator_api(symbol: str, start_date: datetime, end_date: datetime, **kwargs) -> pd.DataFrame:
        """Internal function to calculate technical indicators"""
        try:
            from .stockstats_utils import StockstatsUtils
            
            # First get the underlying price data
            price_data = fetch_yfinance_data_cached(symbol, start_date, end_date)
            
            if price_data.empty:
                return pd.DataFrame()
            
            # Calculate indicator for each date
            indicator_records = []
            for _, row in price_data.iterrows():
                try:
                    curr_date = row['date'].strftime('%Y-%m-%d')
                    indicator_value = StockstatsUtils.get_stock_stats(
                        symbol,
                        indicator,
                        curr_date,
                        DATA_DIR,
                        online=True
                    )
                    
                    record = {
                        'date': row['date'],
                        'symbol': symbol,
                        'indicator': indicator,
                        'value': float(indicator_value) if indicator_value else None,
                        **kwargs
                    }
                    indicator_records.append(record)
                    
                except Exception as e:
                    logger.warning(f"Failed to calculate {indicator} for {symbol} on {curr_date}: {e}")
                    continue
            
            return pd.DataFrame(indicator_records)
            
        except Exception as e:
            logger.error(f"Failed to fetch indicators for {symbol}: {e}")
            return pd.DataFrame()
    
    cache = get_cache()
    return cache.fetch_with_cache(symbol, DataType.INDICATORS, start_date, end_date, _fetch_indicator_api, indicator=indicator, **kwargs)


# Insider Trading Data Caching
def fetch_insider_data_cached(symbol: str, start_date: datetime, end_date: datetime, data_type: str = "insider_trans") -> pd.DataFrame:
    """
    Fetch insider trading data with caching
    
    Args:
        symbol: Stock ticker symbol
        start_date: Start date
        end_date: End date
        data_type: Type of insider data ('insider_trans' or 'insider_senti')
    
    Returns:
        DataFrame with insider data
    """
    
    def _fetch_insider_api(symbol: str, start_date: datetime, end_date: datetime, data_type: str = "insider_trans") -> pd.DataFrame:
        """Internal function to fetch insider data"""
        try:
            data = get_data_in_range(
                symbol,
                start_date.strftime('%Y-%m-%d'),
                end_date.strftime('%Y-%m-%d'),
                data_type,
                DATA_DIR
            )
            
            if not data:
                return pd.DataFrame()
            
            # Convert to DataFrame
            records = []
            for date_str, items in data.items():
                for item in items:
                    record = {
                        'date': pd.to_datetime(date_str),
                        'symbol': symbol,
                        'data_type': data_type,
                        **item  # Include all fields from the insider data
                    }
                    records.append(record)
            
            return pd.DataFrame(records)
            
        except Exception as e:
            logger.error(f"Failed to fetch insider data for {symbol}: {e}")
            return pd.DataFrame()
    
    cache = get_cache()
    cache_data_type = DataType.INSIDER if data_type == "insider_trans" else DataType.SENTIMENT
    return cache.fetch_with_cache(symbol, cache_data_type, start_date, end_date, _fetch_insider_api, data_type=data_type)


# Convenience Functions for Integration
def get_cached_price_data(symbol: str, start_date: str, end_date: str) -> str:
    """
    Get cached price data in string format (compatible with existing interface)
    
    Args:
        symbol: Stock ticker symbol
        start_date: Start date in 'YYYY-MM-DD' format
        end_date: End date in 'YYYY-MM-DD' format
    
    Returns:
        Formatted string with price data
    """
    try:
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        
        df = fetch_yfinance_data_cached(symbol, start_dt, end_dt)
        
        if df.empty:
            return f"No data found for {symbol} between {start_date} and {end_date}"
        
        # Format similar to existing interface
        with pd.option_context('display.max_rows', None, 'display.max_columns', None, 'display.width', None):
            df_string = df.to_string(index=False)
        
        return f"## Cached Market Data for {symbol} from {start_date} to {end_date}:\n\n{df_string}"
        
    except Exception as e:
        logger.error(f"Failed to get cached price data: {e}")
        return f"Error retrieving cached data for {symbol}: {e}"


def get_cached_news_data(symbol: str, curr_date: str, look_back_days: int = 7) -> str:
    """
    Get cached news data in string format (compatible with existing interface)
    
    Args:
        symbol: Stock ticker symbol
        curr_date: Current date in 'YYYY-MM-DD' format
        look_back_days: Number of days to look back
    
    Returns:
        Formatted string with news data
    """
    try:
        curr_dt = datetime.strptime(curr_date, '%Y-%m-%d')
        start_dt = curr_dt - timedelta(days=look_back_days)
        
        df = fetch_finnhub_news_cached(symbol, start_dt, curr_dt)
        
        if df.empty:
            return f"No cached news found for {symbol}"
        
        # Format similar to existing interface
        news_str = ""
        for _, row in df.iterrows():
            news_str += f"### {row['headline']} ({row['date'].strftime('%Y-%m-%d')})\n{row['summary']}\n\n"
        
        return f"## {symbol} Cached News, from {start_dt.strftime('%Y-%m-%d')} to {curr_date}:\n{news_str}"
        
    except Exception as e:
        logger.error(f"Failed to get cached news data: {e}")
        return f"Error retrieving cached news for {symbol}: {e}"


# Cache Management Functions
def get_cache_summary() -> Dict[str, Any]:
    """Get comprehensive cache statistics"""
    cache = get_cache()
    return cache.get_cache_stats()


def clear_old_cache_data(days: int = 30) -> int:
    """Clear cache data older than specified days"""
    cache = get_cache()
    return cache.clear_cache(older_than_days=days)


def clear_symbol_cache(symbol: str) -> int:
    """Clear all cached data for a specific symbol"""
    cache = get_cache()
    total_cleared = 0
    for data_type in DataType:
        cleared = cache.clear_cache(symbol=symbol, data_type=data_type)
        total_cleared += cleared
    return total_cleared


if __name__ == "__main__":
    # Example usage
    print("Testing cached API wrappers...")
    
    # Test OHLCV caching
    symbol = "AAPL"
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    
    print(f"Fetching {symbol} data from {start_date.date()} to {end_date.date()}")
    
    # First call - should fetch from API
    data1 = fetch_yfinance_data_cached(symbol, start_date, end_date)
    print(f"First call: {len(data1)} records")
    
    # Second call - should use cache
    data2 = fetch_yfinance_data_cached(symbol, start_date, end_date)
    print(f"Second call: {len(data2)} records")
    
    # Print cache stats
    stats = get_cache_summary()
    print(f"Cache stats: {stats}") 