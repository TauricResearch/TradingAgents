"""
Professional Finnhub Market Data Integration
Uses the user's existing FINNHUB_API_KEY for reliable market data
"""

import os
import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import time
import logging

logger = logging.getLogger(__name__)


class FinnhubMarketData:
    """Professional Finnhub API integration for market data"""
    
    def __init__(self, api_key: str = None):
        """Initialize with Finnhub API key"""
        self.api_key = api_key or os.getenv('FINNHUB_API_KEY')
        if not self.api_key:
            raise ValueError("FINNHUB_API_KEY is required")
        
        self.base_url = "https://finnhub.io/api/v1"
        self.session = requests.Session()
        
    def get_stock_candles(self, symbol: str, start_date: datetime, end_date: datetime, 
                         resolution: str = "D") -> pd.DataFrame:
        """
        Get OHLCV candlestick data from Finnhub
        
        Args:
            symbol: Stock ticker symbol (e.g., 'TSLA')
            start_date: Start date
            end_date: End date  
            resolution: Resolution (1, 5, 15, 30, 60, D, W, M)
        
        Returns:
            DataFrame with OHLCV data
        """
        try:
            # Convert dates to Unix timestamps
            start_ts = int(start_date.timestamp())
            end_ts = int(end_date.timestamp())
            
            url = f"{self.base_url}/stock/candle"
            params = {
                'symbol': symbol.upper(),
                'resolution': resolution,
                'from': start_ts,
                'to': end_ts,
                'token': self.api_key
            }
            
            response = self.session.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('s') != 'ok':
                logger.warning(f"Finnhub returned status: {data.get('s')} for {symbol}")
                return pd.DataFrame()
            
            # Convert to DataFrame
            df = pd.DataFrame({
                'Date': pd.to_datetime(data['t'], unit='s'),
                'Open': data['o'],
                'High': data['h'], 
                'Low': data['l'],
                'Close': data['c'],
                'Volume': data['v']
            })
            
            # Add additional columns for compatibility
            df['date'] = df['Date']
            df['symbol'] = symbol.upper()
            df['Adj Close'] = df['Close']  # Finnhub provides adjusted prices
            
            # Sort by date
            df = df.sort_values('Date').reset_index(drop=True)
            
            logger.info(f"Retrieved {len(df)} records for {symbol} from Finnhub")
            return df
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Finnhub API request failed for {symbol}: {e}")
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"Error processing Finnhub data for {symbol}: {e}")
            return pd.DataFrame()
    
    def get_quote(self, symbol: str) -> Dict[str, Any]:
        """
        Get real-time quote data
        
        Args:
            symbol: Stock ticker symbol
            
        Returns:
            Dictionary with quote data
        """
        try:
            url = f"{self.base_url}/quote"
            params = {
                'symbol': symbol.upper(),
                'token': self.api_key
            }
            
            response = self.session.get(url, params=params)
            response.raise_for_status()
            
            return response.json()
            
        except Exception as e:
            logger.error(f"Error getting quote for {symbol}: {e}")
            return {}
    
    def get_technical_indicator(self, symbol: str, indicator: str, 
                               start_date: datetime, end_date: datetime,
                               **kwargs) -> pd.DataFrame:
        """
        Get technical indicators from Finnhub
        
        Args:
            symbol: Stock ticker symbol
            indicator: Technical indicator (rsi, macd, etc.)
            start_date: Start date
            end_date: End date
            **kwargs: Additional parameters for indicators
            
        Returns:
            DataFrame with indicator data
        """
        try:
            # First get price data
            price_data = self.get_stock_candles(symbol, start_date, end_date)
            
            if price_data.empty:
                return pd.DataFrame()
            
            # Calculate indicators using stockstats or ta-lib
            # This would integrate with your existing indicator calculation
            from ..stockstats_utils import StockstatsUtils
            
            indicator_results = []
            for _, row in price_data.iterrows():
                try:
                    curr_date = row['Date'].strftime('%Y-%m-%d')
                    # Use existing stockstats integration with Finnhub data
                    value = StockstatsUtils.calculate_indicator_from_data(
                        price_data, indicator, curr_date
                    )
                    
                    indicator_results.append({
                        'date': row['Date'],
                        'symbol': symbol,
                        'indicator': indicator,
                        'value': value
                    })
                except Exception as e:
                    logger.warning(f"Failed to calculate {indicator} for {symbol} on {curr_date}: {e}")
                    continue
            
            return pd.DataFrame(indicator_results)
            
        except Exception as e:
            logger.error(f"Error calculating {indicator} for {symbol}: {e}")
            return pd.DataFrame()


# Integration functions for drop-in replacement
def get_finnhub_ohlcv_data(symbol: str, start_date: str, end_date: str) -> str:
    """
    Get OHLCV data from Finnhub (professional API replacement for YFinance)
    
    Args:
        symbol: Stock ticker symbol
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        
    Returns:
        Formatted string compatible with existing interface
    """
    try:
        finnhub = FinnhubMarketData()
        
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        
        df = finnhub.get_stock_candles(symbol, start_dt, end_dt)
        
        if df.empty:
            return f"No Finnhub data found for {symbol} between {start_date} and {end_date}"
        
        # Format similar to existing YFinance interface
        header = f"# Professional Finnhub data for {symbol.upper()} from {start_date} to {end_date}\n"
        header += f"# Total records: {len(df)}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        csv_string = df[['Date', 'Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume']].to_csv(index=False)
        
        return header + csv_string
        
    except Exception as e:
        logger.error(f"Finnhub professional API failed: {e}")
        # Fallback message
        return f"Finnhub professional API unavailable for {symbol}: {e}"


def get_finnhub_window_data(symbol: str, curr_date: str, look_back_days: int) -> str:
    """
    Get window-based data from Finnhub
    
    Args:
        symbol: Stock ticker symbol
        curr_date: Current date in YYYY-MM-DD format
        look_back_days: Number of days to look back
        
    Returns:
        Formatted string with market data
    """
    try:
        end_dt = datetime.strptime(curr_date, '%Y-%m-%d')
        start_dt = end_dt - timedelta(days=look_back_days)
        
        return get_finnhub_ohlcv_data(symbol, start_dt.strftime('%Y-%m-%d'), curr_date)
        
    except Exception as e:
        return f"Error retrieving Finnhub window data for {symbol}: {e}"


def test_finnhub_connection():
    """Test Finnhub API connection"""
    try:
        finnhub = FinnhubMarketData()
        quote = finnhub.get_quote('AAPL')
        
        if quote and 'c' in quote:
            print(f"✅ Finnhub API working! AAPL current price: ${quote['c']}")
            return True
        else:
            print("❌ Finnhub API test failed - no data returned")
            return False
            
    except Exception as e:
        print(f"❌ Finnhub API test failed: {e}")
        return False


if __name__ == "__main__":
    # Test the professional API
    test_finnhub_connection() 