#!/usr/bin/env python3
"""
Optimized US Stock Data Fetcher
Integrates caching strategy to reduce API calls and improve response speed
"""

import os
import time
import random
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import yfinance as yf
import pandas as pd
from .cache_manager import get_cache
from .config import get_config


class OptimizedUSDataProvider:
    """Optimized US Stock Data Provider - Integrates caching and API rate limiting"""
    
    def __init__(self):
        self.cache = get_cache()
        self.config = get_config()
        self.last_api_call = 0
        self.min_api_interval = 1.0  # Minimum API call interval (seconds)
        
        print("📊 Optimized US stock data provider initialized")
    
    def _wait_for_rate_limit(self):
        """Wait for API rate limit"""
        current_time = time.time()
        time_since_last_call = current_time - self.last_api_call
        
        if time_since_last_call < self.min_api_interval:
            wait_time = self.min_api_interval - time_since_last_call
            print(f"⏳ API rate limit wait {wait_time:.1f}s...")
            time.sleep(wait_time)
        
        self.last_api_call = time.time()
    
    def get_stock_data(self, symbol: str, start_date: str, end_date: str, 
                      force_refresh: bool = False) -> str:
        """
        Get US stock data - prioritize cache usage
        
        Args:
            symbol: Stock symbol
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            force_refresh: Whether to force refresh cache
            
        Returns:
            Formatted stock data string
        """
        try:
            # Check cache first (unless force refresh)
            if not force_refresh:
                cache_key = self.cache.find_cached_stock_data(
                    symbol, start_date, end_date, "optimized_yfinance"
                )
                
                if cache_key and self.cache.is_cache_valid(cache_key, symbol):
                    cached_data = self.cache.load_stock_data(cache_key)
                    if cached_data:
                        print(f"📖 Using cached data for {symbol}")
                        if isinstance(cached_data, pd.DataFrame):
                            return self._format_stock_data(cached_data, symbol)
                        else:
                            return cached_data
            
            # Fetch new data from API
            print(f"🌐 Fetching new data for {symbol} from {start_date} to {end_date}")
            
            # Wait for rate limit
            self._wait_for_rate_limit()
            
            # Try Yahoo Finance first
            try:
                data = self._fetch_from_yfinance(symbol, start_date, end_date)
                if data is not None and not data.empty:
                    # Cache the DataFrame
                    cache_key = self.cache.save_stock_data(
                        symbol, data, start_date, end_date, "optimized_yfinance"
                    )
                    
                    # Format and return
                    formatted_data = self._format_stock_data(data, symbol)
                    print(f"✅ Successfully fetched and cached data for {symbol}")
                    return formatted_data
                else:
                    print(f"⚠️ No data returned from Yahoo Finance for {symbol}")
            
            except Exception as e:
                print(f"❌ Yahoo Finance error for {symbol}: {e}")
            
            # Fallback: Try FINNHUB (if API key available)
            try:
                finnhub_data = self._fetch_from_finnhub(symbol, start_date, end_date)
                if finnhub_data:
                    # Cache the string data
                    cache_key = self.cache.save_stock_data(
                        symbol, finnhub_data, start_date, end_date, "optimized_finnhub"
                    )
                    print(f"✅ Successfully fetched data from FINNHUB for {symbol}")
                    return finnhub_data
            
            except Exception as e:
                print(f"❌ FINNHUB error for {symbol}: {e}")
            
            # If all fails, return error message
            error_msg = f"❌ Failed to fetch data for {symbol} from {start_date} to {end_date}"
            print(error_msg)
            return error_msg
            
        except Exception as e:
            error_msg = f"❌ Unexpected error fetching data for {symbol}: {e}"
            print(error_msg)
            return error_msg
    
    def _fetch_from_yfinance(self, symbol: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """Fetch data from Yahoo Finance"""
        try:
            ticker = yf.Ticker(symbol)
            data = ticker.history(start=start_date, end=end_date)
            
            if data.empty:
                print(f"⚠️ No data available for {symbol} in the specified date range")
                return None
            
            # Reset index to make Date a column
            data = data.reset_index()
            
            # Ensure we have the required columns
            required_columns = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
            missing_columns = [col for col in required_columns if col not in data.columns]
            
            if missing_columns:
                print(f"⚠️ Missing columns for {symbol}: {missing_columns}")
                return None
            
            return data[required_columns]
            
        except Exception as e:
            print(f"❌ Yahoo Finance fetch error for {symbol}: {e}")
            return None
    
    def _fetch_from_finnhub(self, symbol: str, start_date: str, end_date: str) -> Optional[str]:
        """Fetch data from FINNHUB API"""
        try:
            # Check if FINNHUB API key is available
            finnhub_api_key = os.getenv('FINNHUB_API_KEY')
            if not finnhub_api_key:
                print("⚠️ FINNHUB API key not found, skipping FINNHUB data fetch")
                return None
            
            import finnhub
            
            # Initialize FINNHUB client
            finnhub_client = finnhub.Client(api_key=finnhub_api_key)
            
            # Convert dates to timestamps
            start_timestamp = int(datetime.strptime(start_date, '%Y-%m-%d').timestamp())
            end_timestamp = int(datetime.strptime(end_date, '%Y-%m-%d').timestamp())
            
            # Fetch candle data
            candle_data = finnhub_client.stock_candles(symbol, 'D', start_timestamp, end_timestamp)
            
            if candle_data['s'] != 'ok':
                print(f"⚠️ FINNHUB returned status: {candle_data['s']} for {symbol}")
                return None
            
            # Format data
            formatted_data = self._format_finnhub_data(candle_data, symbol)
            return formatted_data
            
        except ImportError:
            print("⚠️ finnhub-python package not installed, skipping FINNHUB data fetch")
            return None
        except Exception as e:
            print(f"❌ FINNHUB fetch error for {symbol}: {e}")
            return None
    
    def _format_stock_data(self, data: pd.DataFrame, symbol: str) -> str:
        """Format DataFrame stock data into string"""
        try:
            # Ensure Date column is properly formatted
            if 'Date' in data.columns:
                data['Date'] = pd.to_datetime(data['Date']).dt.strftime('%Y-%m-%d')
            
            # Round numerical columns to 2 decimal places
            numeric_columns = ['Open', 'High', 'Low', 'Close']
            for col in numeric_columns:
                if col in data.columns:
                    data[col] = data[col].round(2)
            
            # Format volume as integer
            if 'Volume' in data.columns:
                data['Volume'] = data['Volume'].astype(int)
            
            # Create formatted string
            formatted_lines = [f"Stock Data for {symbol}:"]
            formatted_lines.append("Date,Open,High,Low,Close,Volume")
            
            for _, row in data.iterrows():
                line = f"{row['Date']},{row['Open']},{row['High']},{row['Low']},{row['Close']},{row['Volume']}"
                formatted_lines.append(line)
            
            # Add summary statistics
            if len(data) > 0:
                formatted_lines.append(f"\nSummary for {symbol}:")
                formatted_lines.append(f"Period: {data['Date'].iloc[0]} to {data['Date'].iloc[-1]}")
                formatted_lines.append(f"Total trading days: {len(data)}")
                formatted_lines.append(f"Average volume: {data['Volume'].mean():,.0f}")
                formatted_lines.append(f"Price range: ${data['Low'].min():.2f} - ${data['High'].max():.2f}")
                
                # Calculate basic statistics
                start_price = data['Open'].iloc[0]
                end_price = data['Close'].iloc[-1]
                price_change = end_price - start_price
                price_change_pct = (price_change / start_price) * 100
                
                formatted_lines.append(f"Period return: {price_change_pct:+.2f}% (${price_change:+.2f})")
            
            return "\n".join(formatted_lines)
            
        except Exception as e:
            print(f"❌ Error formatting stock data for {symbol}: {e}")
            return f"Error formatting data for {symbol}: {str(e)}"
    
    def _format_finnhub_data(self, candle_data: Dict, symbol: str) -> str:
        """Format FINNHUB candle data into string"""
        try:
            # Extract data arrays
            timestamps = candle_data['t']
            opens = candle_data['o']
            highs = candle_data['h']
            lows = candle_data['l']
            closes = candle_data['c']
            volumes = candle_data['v']
            
            # Create formatted string
            formatted_lines = [f"Stock Data for {symbol} (FINNHUB):"]
            formatted_lines.append("Date,Open,High,Low,Close,Volume")
            
            for i in range(len(timestamps)):
                date = datetime.fromtimestamp(timestamps[i]).strftime('%Y-%m-%d')
                line = f"{date},{opens[i]:.2f},{highs[i]:.2f},{lows[i]:.2f},{closes[i]:.2f},{int(volumes[i])}"
                formatted_lines.append(line)
            
            # Add summary
            if len(timestamps) > 0:
                start_date = datetime.fromtimestamp(timestamps[0]).strftime('%Y-%m-%d')
                end_date = datetime.fromtimestamp(timestamps[-1]).strftime('%Y-%m-%d')
                
                formatted_lines.append(f"\nSummary for {symbol}:")
                formatted_lines.append(f"Period: {start_date} to {end_date}")
                formatted_lines.append(f"Total trading days: {len(timestamps)}")
                formatted_lines.append(f"Average volume: {sum(volumes)/len(volumes):,.0f}")
                formatted_lines.append(f"Price range: ${min(lows):.2f} - ${max(highs):.2f}")
                
                # Calculate return
                price_change = closes[-1] - opens[0]
                price_change_pct = (price_change / opens[0]) * 100
                formatted_lines.append(f"Period return: {price_change_pct:+.2f}% (${price_change:+.2f})")
            
            return "\n".join(formatted_lines)
            
        except Exception as e:
            print(f"❌ Error formatting FINNHUB data for {symbol}: {e}")
            return f"Error formatting FINNHUB data for {symbol}: {str(e)}"
    
    def get_stock_with_indicators(self, symbol: str, start_date: str, end_date: str,
                                 indicators: list = None) -> str:
        """
        Get stock data with technical indicators
        
        Args:
            symbol: Stock symbol
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            indicators: List of indicators to calculate ['sma_20', 'rsi', 'macd']
            
        Returns:
            Formatted stock data with indicators
        """
        try:
            # Get basic stock data
            basic_data = self.get_stock_data(symbol, start_date, end_date)
            
            if basic_data.startswith("❌"):
                return basic_data
            
            # If no indicators requested, return basic data
            if not indicators:
                return basic_data
            
            # Fetch DataFrame for indicator calculation
            data_df = self._fetch_from_yfinance(symbol, start_date, end_date)
            if data_df is None or data_df.empty:
                return basic_data
            
            # Calculate indicators
            indicator_data = self._calculate_indicators(data_df, indicators)
            
            # Combine basic data with indicators
            combined_data = basic_data + "\n\nTechnical Indicators:\n" + indicator_data
            
            return combined_data
            
        except Exception as e:
            error_msg = f"❌ Error getting stock data with indicators for {symbol}: {e}"
            print(error_msg)
            return error_msg
    
    def _calculate_indicators(self, data: pd.DataFrame, indicators: list) -> str:
        """Calculate technical indicators"""
        try:
            indicator_lines = []
            
            for indicator in indicators:
                if indicator == 'sma_20':
                    data['SMA_20'] = data['Close'].rolling(window=20).mean()
                    latest_sma = data['SMA_20'].iloc[-1]
                    indicator_lines.append(f"SMA(20): ${latest_sma:.2f}")
                
                elif indicator == 'rsi':
                    # Simple RSI calculation
                    delta = data['Close'].diff()
                    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                    rs = gain / loss
                    rsi = 100 - (100 / (1 + rs))
                    latest_rsi = rsi.iloc[-1]
                    indicator_lines.append(f"RSI(14): {latest_rsi:.2f}")
                
                elif indicator == 'macd':
                    # Simple MACD calculation
                    ema_12 = data['Close'].ewm(span=12).mean()
                    ema_26 = data['Close'].ewm(span=26).mean()
                    macd_line = ema_12 - ema_26
                    signal_line = macd_line.ewm(span=9).mean()
                    latest_macd = macd_line.iloc[-1]
                    latest_signal = signal_line.iloc[-1]
                    indicator_lines.append(f"MACD: {latest_macd:.4f}, Signal: {latest_signal:.4f}")
            
            return "\n".join(indicator_lines)
            
        except Exception as e:
            print(f"❌ Error calculating indicators: {e}")
            return f"Error calculating indicators: {str(e)}"


# Global provider instance
_global_provider = None

def get_optimized_us_data_provider() -> OptimizedUSDataProvider:
    """
    Get global optimized US data provider instance
    
    Returns:
        OptimizedUSDataProvider instance
    """
    global _global_provider
    if _global_provider is None:
        _global_provider = OptimizedUSDataProvider()
    return _global_provider


# Convenience functions
def get_optimized_stock_data(symbol: str, start_date: str, end_date: str, 
                           force_refresh: bool = False) -> str:
    """Get optimized stock data (convenience function)"""
    provider = get_optimized_us_data_provider()
    return provider.get_stock_data(symbol, start_date, end_date, force_refresh)


def get_stock_with_indicators(symbol: str, start_date: str, end_date: str,
                            indicators: list = None) -> str:
    """Get stock data with technical indicators (convenience function)"""
    provider = get_optimized_us_data_provider()
    return provider.get_stock_with_indicators(symbol, start_date, end_date, indicators)


if __name__ == "__main__":
    # Test the optimized data provider
    print("🧪 Testing Optimized US Data Provider...")
    
    # Initialize provider
    provider = OptimizedUSDataProvider()
    
    # Test data fetch
    data = provider.get_stock_data("AAPL", "2024-01-01", "2024-01-31")
    print("Sample data:")
    print(data[:500] + "..." if len(data) > 500 else data)
    
    # Test with indicators
    data_with_indicators = provider.get_stock_with_indicators(
        "AAPL", "2024-01-01", "2024-01-31", 
        indicators=['sma_20', 'rsi', 'macd']
    )
    print("\nData with indicators:")
    print(data_with_indicators[-500:] if len(data_with_indicators) > 500 else data_with_indicators)
    
    print("✅ Optimized data provider test completed!")
