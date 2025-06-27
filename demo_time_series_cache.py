#!/usr/bin/env python3
"""
Time Series Cache Demo for TradingAgents

This script demonstrates the intelligent time series caching system
that optimizes financial API calls by caching data locally.

Features demonstrated:
1. OHLCV data caching with YFinance
2. News data caching
3. Technical indicators caching
4. Cache performance monitoring
5. Cache management operations
"""

import os
import sys
from datetime import datetime, timedelta

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tradingagents.dataflows import (
    get_YFin_data_cached,
    get_YFin_data_window_cached,
    get_finnhub_news_cached,
    get_google_news_cached,
    get_technical_indicators_cached,
    get_cache_statistics,
    clear_cache_data
)


def demo_ohlcv_caching():
    """Demonstrate OHLCV data caching"""
    print("🏦 OHLCV Data Caching Demo")
    print("=" * 50)
    
    symbol = "AAPL"
    end_date = "2024-01-15"
    start_date = "2024-01-01"
    
    print(f"📊 Fetching {symbol} data from {start_date} to {end_date}")
    print("First call (will fetch from API and cache)...")
    
    # First call - should fetch from API
    start_time = datetime.now()
    data1 = get_YFin_data_cached(symbol, start_date, end_date)
    time1 = (datetime.now() - start_time).total_seconds()
    
    print(f"⏱️  First call took: {time1:.2f} seconds")
    print(f"📄 Data length: {len(data1.split('\\n'))} lines")
    
    print("\\nSecond call (should use cache)...")
    
    # Second call - should use cache
    start_time = datetime.now()
    data2 = get_YFin_data_cached(symbol, start_date, end_date)
    time2 = (datetime.now() - start_time).total_seconds()
    
    print(f"⏱️  Second call took: {time2:.2f} seconds")
    print(f"🚀 Speed improvement: {time1/max(time2, 0.001):.1f}x faster")
    print(f"✅ Data identical: {data1 == data2}")
    print()


def demo_window_caching():
    """Demonstrate window-based data caching"""
    print("🪟 Window-Based Caching Demo")
    print("=" * 50)
    
    symbol = "TSLA"
    curr_date = "2024-01-15"
    look_back_days = 30
    
    print(f"📊 Fetching {symbol} data: {look_back_days} days before {curr_date}")
    
    # Fetch data with windowing
    data = get_YFin_data_window_cached(symbol, curr_date, look_back_days)
    
    print(f"📄 Retrieved data length: {len(data.split('\\n'))} lines")
    print()


def demo_news_caching():
    """Demonstrate news data caching"""
    print("📰 News Data Caching Demo")
    print("=" * 50)
    
    symbol = "AAPL"
    curr_date = "2024-01-15"
    look_back_days = 7
    
    print(f"📰 Fetching news for {symbol}: {look_back_days} days before {curr_date}")
    
    try:
        # Fetch cached news data
        news_data = get_finnhub_news_cached(symbol, curr_date, look_back_days)
        
        if "No cached news found" in news_data:
            print("ℹ️  No news data available in cache (this is normal for demo)")
        else:
            print(f"📄 Retrieved news length: {len(news_data.split('\\n'))} lines")
            
    except Exception as e:
        print(f"ℹ️  News demo skipped: {e}")
    
    print()


def demo_google_news_caching():
    """Demonstrate Google News caching"""
    print("🔍 Google News Caching Demo")
    print("=" * 50)
    
    query = "stock market"
    curr_date = "2024-01-15"
    look_back_days = 7
    
    print(f"🔍 Fetching Google News for '{query}': {look_back_days} days before {curr_date}")
    
    try:
        # Fetch cached Google news
        news_data = get_google_news_cached(query, curr_date, look_back_days)
        
        if "No cached news found" in news_data:
            print("ℹ️  No Google News data available (API may not be configured)")
        else:
            print(f"📄 Retrieved Google News length: {len(news_data.split('\\n'))} lines")
            
    except Exception as e:
        print(f"ℹ️  Google News demo skipped: {e}")
    
    print()


def demo_technical_indicators():
    """Demonstrate technical indicators caching"""
    print("📈 Technical Indicators Caching Demo")
    print("=" * 50)
    
    symbol = "AAPL"
    indicator = "rsi"
    curr_date = "2024-01-15"
    look_back_days = 20
    
    print(f"📈 Calculating {indicator.upper()} for {symbol}: {look_back_days} days before {curr_date}")
    
    try:
        # Fetch cached technical indicators
        indicator_data = get_technical_indicators_cached(symbol, indicator, curr_date, look_back_days)
        
        if "No cached indicator data found" in indicator_data:
            print("ℹ️  No indicator data available (may need price data first)")
        else:
            print(f"📄 Retrieved indicator data length: {len(indicator_data.split('\\n'))} lines")
            
    except Exception as e:
        print(f"ℹ️  Technical indicators demo skipped: {e}")
    
    print()


def demo_cache_statistics():
    """Show cache performance statistics"""
    print("📊 Cache Performance Statistics")
    print("=" * 50)
    
    try:
        stats = get_cache_statistics()
        print(stats)
    except Exception as e:
        print(f"ℹ️  Cache statistics unavailable: {e}")
    
    print()


def demo_cache_management():
    """Demonstrate cache management operations"""
    print("🧹 Cache Management Demo")
    print("=" * 50)
    
    print("Available cache management operations:")
    print("1. Clear cache for specific symbol:")
    print("   clear_cache_data(symbol='AAPL')")
    print()
    print("2. Clear old cache data:")
    print("   clear_cache_data(older_than_days=30)")
    print()
    print("3. Clear cache for symbol older than N days:")
    print("   clear_cache_data(symbol='AAPL', older_than_days=7)")
    print()
    
    # Demonstrate getting cache help
    try:
        help_text = clear_cache_data()
        print(f"📝 Cache management help: {help_text}")
    except Exception as e:
        print(f"ℹ️  Cache management info: {e}")
    
    print()


def main():
    """Run all demonstrations"""
    print("🚀 TradingAgents Time Series Cache Demo")
    print("=" * 60)
    print()
    
    # Run all demos
    demo_ohlcv_caching()
    demo_window_caching()
    demo_news_caching()
    demo_google_news_caching()
    demo_technical_indicators()
    demo_cache_statistics()
    demo_cache_management()
    
    print("✅ Demo completed!")
    print()
    print("💡 Key Benefits of Time Series Caching:")
    print("   • Reduces API calls and costs")
    print("   • Faster data retrieval for repeated queries")
    print("   • Intelligent gap-filling for overlapping date ranges")
    print("   • Automatic data format standardization")
    print("   • Built-in cache management and statistics")
    print()
    print("🔧 Integration Tips:")
    print("   • Replace get_YFin_data() with get_YFin_data_cached()")
    print("   • Use get_cache_statistics() to monitor performance")
    print("   • Periodically clear old cache with clear_cache_data()")
    print("   • Cache directory: data_cache/time_series/")


if __name__ == "__main__":
    main() 