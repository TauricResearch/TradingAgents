"""
Indian Market Data Utilities
Handles data fetching from multiple Indian market sources with fallbacks
"""

import os
import requests
import pandas as pd
import yfinance as yf
from typing import Dict, List, Optional, Union, Any
from datetime import datetime, timedelta
import time
import logging
from functools import wraps
import json

from .ticker_utils import TickerFormatter, TickerValidator, format_indian_ticker

logger = logging.getLogger(__name__)

class RateLimiter:
    """Simple rate limiter for API calls"""
    
    def __init__(self, calls_per_minute: int = 60):
        self.calls_per_minute = calls_per_minute
        self.calls = []
    
    def wait_if_needed(self):
        """Wait if rate limit would be exceeded"""
        now = time.time()
        # Remove calls older than 1 minute
        self.calls = [call_time for call_time in self.calls if now - call_time < 60]
        
        if len(self.calls) >= self.calls_per_minute:
            sleep_time = 60 - (now - self.calls[0])
            if sleep_time > 0:
                logger.info(f"Rate limit reached, sleeping for {sleep_time:.2f} seconds")
                time.sleep(sleep_time)
        
        self.calls.append(now)

def retry_on_failure(max_retries: int = 3, delay: float = 1.0):
    """Decorator to retry function calls on failure"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logger.warning(f"Attempt {attempt + 1} failed for {func.__name__}: {e}")
                        time.sleep(delay * (2 ** attempt))  # Exponential backoff
                    else:
                        logger.error(f"All {max_retries} attempts failed for {func.__name__}")
            raise last_exception
        return wrapper
    return decorator

class AlphaVantageAPI:
    """Alpha Vantage API client for Indian market data"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://www.alphavantage.co/query"
        self.rate_limiter = RateLimiter(calls_per_minute=5)  # Alpha Vantage free tier limit
    
    @retry_on_failure(max_retries=3)
    def get_daily_data(self, symbol: str, outputsize: str = "compact") -> pd.DataFrame:
        """
        Get daily stock data from Alpha Vantage
        
        Args:
            symbol: Stock symbol (e.g., 'RELIANCE.NS')
            outputsize: 'compact' (100 days) or 'full' (all available)
            
        Returns:
            DataFrame with OHLCV data
        """
        self.rate_limiter.wait_if_needed()
        
        params = {
            'function': 'TIME_SERIES_DAILY',
            'symbol': symbol,
            'outputsize': outputsize,
            'apikey': self.api_key
        }
        
        response = requests.get(self.base_url, params=params)
        response.raise_for_status()
        
        data = response.json()
        
        if 'Error Message' in data:
            raise ValueError(f"Alpha Vantage error: {data['Error Message']}")
        
        if 'Note' in data:
            raise ValueError(f"Alpha Vantage rate limit: {data['Note']}")
        
        time_series = data.get('Time Series (Daily)', {})
        if not time_series:
            raise ValueError(f"No data found for symbol {symbol}")
        
        # Convert to DataFrame
        df = pd.DataFrame.from_dict(time_series, orient='index')
        df.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
        df.index = pd.to_datetime(df.index)
        df = df.astype(float)
        df.sort_index(inplace=True)
        
        return df
    
    @retry_on_failure(max_retries=3)
    def get_company_overview(self, symbol: str) -> Dict[str, Any]:
        """Get company fundamental data"""
        self.rate_limiter.wait_if_needed()
        
        params = {
            'function': 'OVERVIEW',
            'symbol': symbol,
            'apikey': self.api_key
        }
        
        response = requests.get(self.base_url, params=params)
        response.raise_for_status()
        
        data = response.json()
        
        if 'Error Message' in data:
            raise ValueError(f"Alpha Vantage error: {data['Error Message']}")
        
        return data

class YahooFinanceAPI:
    """Yahoo Finance API client for Indian market data"""
    
    def __init__(self):
        self.rate_limiter = RateLimiter(calls_per_minute=30)
    
    @retry_on_failure(max_retries=3)
    def get_daily_data(self, symbol: str, period: str = "1y") -> pd.DataFrame:
        """
        Get daily stock data from Yahoo Finance
        
        Args:
            symbol: Stock symbol (e.g., 'RELIANCE.NS')
            period: Time period ('1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', '10y', 'ytd', 'max')
            
        Returns:
            DataFrame with OHLCV data
        """
        self.rate_limiter.wait_if_needed()
        
        ticker = yf.Ticker(symbol)
        data = ticker.history(period=period)
        
        if data.empty:
            raise ValueError(f"No data found for symbol {symbol}")
        
        # Remove timezone info for consistency
        if data.index.tz is not None:
            data.index = data.index.tz_localize(None)
        
        return data
    
    @retry_on_failure(max_retries=3)
    def get_company_info(self, symbol: str) -> Dict[str, Any]:
        """Get company information"""
        self.rate_limiter.wait_if_needed()
        
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        if not info or 'symbol' not in info:
            raise ValueError(f"No company info found for symbol {symbol}")
        
        return info
    
    @retry_on_failure(max_retries=3)
    def get_financial_statements(self, symbol: str) -> Dict[str, pd.DataFrame]:
        """Get financial statements"""
        self.rate_limiter.wait_if_needed()
        
        ticker = yf.Ticker(symbol)
        
        return {
            'income_statement': ticker.financials,
            'balance_sheet': ticker.balance_sheet,
            'cash_flow': ticker.cashflow
        }

class NSEDirectAPI:
    """Direct NSE API client (unofficial)"""
    
    def __init__(self):
        self.base_url = "https://www.nseindia.com/api"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9',
        })
        self.rate_limiter = RateLimiter(calls_per_minute=20)
    
    def _get_session_cookies(self):
        """Get session cookies from NSE"""
        try:
            response = self.session.get("https://www.nseindia.com")
            response.raise_for_status()
        except Exception as e:
            logger.warning(f"Failed to get NSE session cookies: {e}")
    
    @retry_on_failure(max_retries=2)
    def get_quote(self, symbol: str) -> Dict[str, Any]:
        """Get real-time quote from NSE"""
        self.rate_limiter.wait_if_needed()
        self._get_session_cookies()
        
        # Remove .NS suffix if present
        clean_symbol = symbol.replace('.NS', '')
        
        url = f"{self.base_url}/quote-equity"
        params = {'symbol': clean_symbol}
        
        response = self.session.get(url, params=params)
        response.raise_for_status()
        
        return response.json()

class IndianMarketDataManager:
    """Main manager for Indian market data with multiple sources and fallbacks"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        
        # Initialize API clients
        self.alpha_vantage = None
        self.yahoo_finance = YahooFinanceAPI()
        self.nse_direct = NSEDirectAPI()
        
        # Initialize Alpha Vantage if API key is available
        av_key = config.get('api_keys', {}).get('alpha_vantage')
        if av_key:
            self.alpha_vantage = AlphaVantageAPI(av_key)
        else:
            logger.warning("Alpha Vantage API key not found, will use fallback sources")
    
    def get_market_data(self, 
                       symbol: str, 
                       start_date: str, 
                       end_date: str, 
                       exchange: str = "NSE") -> str:
        """
        Get market data with multiple source fallbacks
        
        Args:
            symbol: Stock symbol
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            exchange: Exchange (NSE or BSE)
            
        Returns:
            Formatted string with market data
        """
        # Format ticker
        formatted_ticker = format_indian_ticker(symbol, exchange)
        
        # Try multiple sources in order of preference
        sources = [
            ("Alpha Vantage", self._get_alpha_vantage_data),
            ("Yahoo Finance", self._get_yahoo_finance_data),
        ]
        
        for source_name, source_func in sources:
            try:
                logger.info(f"Trying {source_name} for {formatted_ticker}")
                df = source_func(formatted_ticker, start_date, end_date)
                
                if df is not None and not df.empty:
                    # Filter by date range
                    start_dt = pd.to_datetime(start_date)
                    end_dt = pd.to_datetime(end_date)
                    df = df[(df.index >= start_dt) & (df.index <= end_dt)]
                    
                    if not df.empty:
                        return self._format_market_data(df, formatted_ticker, source_name)
                
            except Exception as e:
                logger.warning(f"{source_name} failed for {formatted_ticker}: {e}")
                continue
        
        return f"No market data found for {formatted_ticker} between {start_date} and {end_date}"
    
    def _get_alpha_vantage_data(self, symbol: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """Get data from Alpha Vantage"""
        if not self.alpha_vantage:
            return None
        
        return self.alpha_vantage.get_daily_data(symbol, outputsize="full")
    
    def _get_yahoo_finance_data(self, symbol: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """Get data from Yahoo Finance"""
        # Calculate period for Yahoo Finance
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        days_diff = (end_dt - start_dt).days
        
        if days_diff <= 5:
            period = "5d"
        elif days_diff <= 30:
            period = "1mo"
        elif days_diff <= 90:
            period = "3mo"
        elif days_diff <= 365:
            period = "1y"
        else:
            period = "max"
        
        return self.yahoo_finance.get_daily_data(symbol, period)
    
    def _format_market_data(self, df: pd.DataFrame, symbol: str, source: str) -> str:
        """Format market data for display"""
        # Round numerical values
        numeric_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
        for col in numeric_columns:
            if col in df.columns:
                if col == 'Volume':
                    df[col] = df[col].astype(int)
                else:
                    df[col] = df[col].round(2)
        
        # Convert to CSV string
        csv_string = df.to_csv()
        
        # Add header information
        header = f"# Indian Stock Data for {symbol}\n"
        header += f"# Total records: {len(df)}\n"
        header += f"# Data source: {source}\n"
        header += f"# Retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}\n\n"
        
        return header + csv_string
    
    def get_company_fundamentals(self, symbol: str, exchange: str = "NSE") -> str:
        """
        Get company fundamental data
        
        Args:
            symbol: Stock symbol
            exchange: Exchange (NSE or BSE)
            
        Returns:
            Formatted string with fundamental data
        """
        formatted_ticker = format_indian_ticker(symbol, exchange)
        
        # Try multiple sources
        sources = [
            ("Alpha Vantage", self._get_alpha_vantage_fundamentals),
            ("Yahoo Finance", self._get_yahoo_finance_fundamentals),
        ]
        
        for source_name, source_func in sources:
            try:
                logger.info(f"Trying {source_name} fundamentals for {formatted_ticker}")
                data = source_func(formatted_ticker)
                
                if data:
                    return self._format_fundamentals_data(data, formatted_ticker, source_name)
                
            except Exception as e:
                logger.warning(f"{source_name} fundamentals failed for {formatted_ticker}: {e}")
                continue
        
        return f"No fundamental data found for {formatted_ticker}"
    
    def _get_alpha_vantage_fundamentals(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get fundamentals from Alpha Vantage"""
        if not self.alpha_vantage:
            return None
        
        return self.alpha_vantage.get_company_overview(symbol)
    
    def _get_yahoo_finance_fundamentals(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get fundamentals from Yahoo Finance"""
        info = self.yahoo_finance.get_company_info(symbol)
        
        # Also get financial statements
        try:
            statements = self.yahoo_finance.get_financial_statements(symbol)
            info['financial_statements'] = statements
        except Exception as e:
            logger.warning(f"Could not get financial statements: {e}")
        
        return info
    
    def _format_fundamentals_data(self, data: Dict[str, Any], symbol: str, source: str) -> str:
        """Format fundamental data for display"""
        result = f"# Fundamental Data for {symbol}\n"
        result += f"# Data source: {source}\n"
        result += f"# Retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}\n\n"
        
        # Key metrics to highlight
        key_metrics = [
            'marketCap', 'MarketCapitalization', 'trailingPE', 'PERatio',
            'priceToBook', 'BookValue', 'dividendYield', 'DividendYield',
            'eps', 'EPS', 'revenue', 'RevenueTTM', 'sector', 'Sector',
            'industry', 'Industry', 'country', 'Country'
        ]
        
        result += "## Key Metrics:\n"
        for metric in key_metrics:
            if metric in data and data[metric] not in [None, 'None', '']:
                result += f"- {metric}: {data[metric]}\n"
        
        # Add financial statements if available
        if 'financial_statements' in data:
            statements = data['financial_statements']
            for stmt_name, stmt_df in statements.items():
                if not stmt_df.empty:
                    result += f"\n## {stmt_name.replace('_', ' ').title()}:\n"
                    result += stmt_df.head().to_string() + "\n"
        
        return result
    
    def get_real_time_quote(self, symbol: str, exchange: str = "NSE") -> str:
        """
        Get real-time quote (NSE only)
        
        Args:
            symbol: Stock symbol
            exchange: Exchange (only NSE supported for real-time)
            
        Returns:
            Formatted string with quote data
        """
        if exchange.upper() != "NSE":
            return "Real-time quotes only available for NSE stocks"
        
        try:
            quote_data = self.nse_direct.get_quote(symbol)
            return self._format_quote_data(quote_data, symbol)
        except Exception as e:
            logger.error(f"Failed to get real-time quote for {symbol}: {e}")
            return f"Failed to get real-time quote for {symbol}: {e}"
    
    def _format_quote_data(self, data: Dict[str, Any], symbol: str) -> str:
        """Format quote data for display"""
        if 'priceInfo' not in data:
            return f"No quote data available for {symbol}"
        
        price_info = data['priceInfo']
        
        result = f"# Real-time Quote for {symbol}\n"
        result += f"# Retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}\n\n"
        
        result += "## Price Information:\n"
        result += f"- Last Price: ₹{price_info.get('lastPrice', 'N/A')}\n"
        result += f"- Change: ₹{price_info.get('change', 'N/A')}\n"
        result += f"- % Change: {price_info.get('pChange', 'N/A')}%\n"
        result += f"- Open: ₹{price_info.get('open', 'N/A')}\n"
        result += f"- High: ₹{price_info.get('dayHigh', 'N/A')}\n"
        result += f"- Low: ₹{price_info.get('dayLow', 'N/A')}\n"
        result += f"- Previous Close: ₹{price_info.get('previousClose', 'N/A')}\n"
        
        return result

# Convenience functions
def get_indian_market_data(symbol: str, 
                          start_date: str, 
                          end_date: str, 
                          exchange: str = "NSE",
                          config: Optional[Dict[str, Any]] = None) -> str:
    """Get Indian market data with fallbacks"""
    if config is None:
        from tradingagents.indian_config import get_indian_config
        config = get_indian_config()
    
    manager = IndianMarketDataManager(config)
    return manager.get_market_data(symbol, start_date, end_date, exchange)

def get_indian_fundamentals(symbol: str, 
                           exchange: str = "NSE",
                           config: Optional[Dict[str, Any]] = None) -> str:
    """Get Indian company fundamentals"""
    if config is None:
        from tradingagents.indian_config import get_indian_config
        config = get_indian_config()
    
    manager = IndianMarketDataManager(config)
    return manager.get_company_fundamentals(symbol, exchange)

def get_indian_quote(symbol: str, 
                    exchange: str = "NSE",
                    config: Optional[Dict[str, Any]] = None) -> str:
    """Get Indian real-time quote"""
    if config is None:
        from tradingagents.indian_config import get_indian_config
        config = get_indian_config()
    
    manager = IndianMarketDataManager(config)
    return manager.get_real_time_quote(symbol, exchange) 