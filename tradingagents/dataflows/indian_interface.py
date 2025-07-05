"""
Indian Market Data Interface
Integration layer for Indian market data with the TradingAgents framework
"""

from typing import Annotated, Dict, Optional, List, Any
from datetime import datetime, timedelta
import pandas as pd
import logging
import os
import json

from .indian_market_utils import (
    IndianMarketDataManager, 
    get_indian_market_data,
    get_indian_fundamentals,
    get_indian_quote
)
from .ticker_utils import (
    format_indian_ticker, 
    validate_indian_ticker,
    get_plain_symbol,
    TickerManager
)
from .config import get_config

logger = logging.getLogger(__name__)

# Initialize ticker manager
ticker_manager = TickerManager()

def get_indian_market_data_interface(
    symbol: Annotated[str, "Indian stock symbol (e.g., RELIANCE, TCS)"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
    exchange: Annotated[str, "Exchange: NSE or BSE"] = "NSE"
) -> str:
    """
    Get Indian stock market data with multiple source fallbacks
    
    Args:
        symbol: Stock symbol (e.g., 'RELIANCE', 'TCS')
        start_date: Start date in yyyy-mm-dd format
        end_date: End date in yyyy-mm-dd format
        exchange: Exchange (NSE or BSE)
        
    Returns:
        Formatted string with market data
    """
    try:
        # Validate dates
        datetime.strptime(start_date, "%Y-%m-%d")
        datetime.strptime(end_date, "%Y-%m-%d")
        
        # Process ticker
        ticker_info = ticker_manager.process_ticker(symbol, exchange)
        if not ticker_info["is_valid"]:
            return f"Invalid ticker: {symbol}. Error: {ticker_info.get('error', 'Unknown error')}"
        
        # Get configuration
        config = get_config()
        
        # Get market data
        result = get_indian_market_data(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            exchange=exchange,
            config=config
        )
        
        return result
        
    except ValueError as e:
        error_msg = f"Date format error: {e}"
        logger.error(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"Error fetching market data for {symbol}: {e}"
        logger.error(error_msg)
        return error_msg

def get_indian_fundamentals_interface(
    symbol: Annotated[str, "Indian stock symbol (e.g., RELIANCE, TCS)"],
    exchange: Annotated[str, "Exchange: NSE or BSE"] = "NSE"
) -> str:
    """
    Get Indian company fundamental data
    
    Args:
        symbol: Stock symbol (e.g., 'RELIANCE', 'TCS')
        exchange: Exchange (NSE or BSE)
        
    Returns:
        Formatted string with fundamental data
    """
    try:
        # Process ticker
        ticker_info = ticker_manager.process_ticker(symbol, exchange)
        if not ticker_info["is_valid"]:
            return f"Invalid ticker: {symbol}. Error: {ticker_info.get('error', 'Unknown error')}"
        
        # Get configuration
        config = get_config()
        
        # Get fundamental data
        result = get_indian_fundamentals(
            symbol=symbol,
            exchange=exchange,
            config=config
        )
        
        return result
        
    except Exception as e:
        error_msg = f"Error fetching fundamentals for {symbol}: {e}"
        logger.error(error_msg)
        return error_msg

def get_indian_quote_interface(
    symbol: Annotated[str, "Indian stock symbol (e.g., RELIANCE, TCS)"],
    exchange: Annotated[str, "Exchange: NSE or BSE"] = "NSE"
) -> str:
    """
    Get Indian real-time quote data
    
    Args:
        symbol: Stock symbol (e.g., 'RELIANCE', 'TCS')
        exchange: Exchange (NSE or BSE)
        
    Returns:
        Formatted string with quote data
    """
    try:
        # Process ticker
        ticker_info = ticker_manager.process_ticker(symbol, exchange)
        if not ticker_info["is_valid"]:
            return f"Invalid ticker: {symbol}. Error: {ticker_info.get('error', 'Unknown error')}"
        
        # Get configuration
        config = get_config()
        
        # Get quote data
        result = get_indian_quote(
            symbol=symbol,
            exchange=exchange,
            config=config
        )
        
        return result
        
    except Exception as e:
        error_msg = f"Error fetching quote for {symbol}: {e}"
        logger.error(error_msg)
        return error_msg

def get_indian_technical_indicators(
    symbol: Annotated[str, "Indian stock symbol (e.g., RELIANCE, TCS)"],
    indicator: Annotated[str, "Technical indicator (e.g., rsi, macd, sma)"],
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    lookback_days: Annotated[int, "Number of days to look back"] = 30,
    exchange: Annotated[str, "Exchange: NSE or BSE"] = "NSE"
) -> str:
    """
    Get technical indicators for Indian stocks
    
    Args:
        symbol: Stock symbol
        indicator: Technical indicator name
        curr_date: Current date
        lookback_days: Number of days to look back
        exchange: Exchange
        
    Returns:
        Formatted string with indicator data
    """
    try:
        # Import stockstats here to avoid circular imports
        from .stockstats_utils import StockstatsUtils
        
        # Process ticker
        ticker_info = ticker_manager.process_ticker(symbol, exchange)
        if not ticker_info["is_valid"]:
            return f"Invalid ticker: {symbol}. Error: {ticker_info.get('error', 'Unknown error')}"
        
        # Calculate date range
        end_date = datetime.strptime(curr_date, "%Y-%m-%d")
        start_date = end_date - timedelta(days=lookback_days + 50)  # Extra days for indicator calculation
        
        # Get market data first
        market_data = get_indian_market_data_interface(
            symbol=symbol,
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=curr_date,
            exchange=exchange
        )
        
        if "Error" in market_data or "No data" in market_data:
            return f"Cannot calculate {indicator}: {market_data}"
        
        # For now, return a placeholder - full integration with stockstats would need more work
        result = f"# Technical Indicator: {indicator} for {ticker_info['formatted_ticker']}\n"
        result += f"# Date: {curr_date}\n"
        result += f"# Lookback period: {lookback_days} days\n\n"
        result += f"Technical indicator calculation for {indicator} would be performed here.\n"
        result += "This requires integration with the stockstats library using Indian market data.\n"
        
        return result
        
    except Exception as e:
        error_msg = f"Error calculating {indicator} for {symbol}: {e}"
        logger.error(error_msg)
        return error_msg

def get_indian_news_interface(
    symbol: Annotated[str, "Indian stock symbol (e.g., RELIANCE, TCS)"],
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    lookback_days: Annotated[int, "Number of days to look back"] = 7
) -> str:
    """
    Get Indian company news from local sources
    
    Args:
        symbol: Stock symbol
        curr_date: Current date
        lookback_days: Number of days to look back
        
    Returns:
        Formatted string with news data
    """
    try:
        # Process ticker
        ticker_info = ticker_manager.process_ticker(symbol)
        if not ticker_info["is_valid"]:
            return f"Invalid ticker: {symbol}. Error: {ticker_info.get('error', 'Unknown error')}"
        
        # Get company name for news search
        plain_symbol = ticker_info["plain_symbol"]
        
        # For now, return a placeholder for Indian news sources
        result = f"# Indian News for {plain_symbol}\n"
        result += f"# Date range: {(datetime.strptime(curr_date, '%Y-%m-%d') - timedelta(days=lookback_days)).strftime('%Y-%m-%d')} to {curr_date}\n\n"
        
        # Placeholder news items (in production, these would come from actual Indian news APIs)
        result += "## Recent News Headlines:\n\n"
        result += f"### Company-specific news for {plain_symbol} would be fetched from:\n"
        result += "- Economic Times\n"
        result += "- Moneycontrol\n"
        result += "- Business Standard\n"
        result += "- NSE/BSE announcements\n"
        result += "- Company investor relations\n\n"
        
        result += "### Market and sector news would include:\n"
        result += "- RBI policy announcements\n"
        result += "- SEBI regulatory updates\n"
        result += "- Sectoral developments\n"
        result += "- FII/DII flow data\n"
        result += "- Currency and commodity updates\n"
        
        return result
        
    except Exception as e:
        error_msg = f"Error fetching news for {symbol}: {e}"
        logger.error(error_msg)
        return error_msg

def get_indian_sentiment_interface(
    symbol: Annotated[str, "Indian stock symbol (e.g., RELIANCE, TCS)"],
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    lookback_days: Annotated[int, "Number of days to look back"] = 7
) -> str:
    """
    Get Indian social media sentiment data
    
    Args:
        symbol: Stock symbol
        curr_date: Current date
        lookback_days: Number of days to look back
        
    Returns:
        Formatted string with sentiment data
    """
    try:
        # Process ticker
        ticker_info = ticker_manager.process_ticker(symbol)
        if not ticker_info["is_valid"]:
            return f"Invalid ticker: {symbol}. Error: {ticker_info.get('error', 'Unknown error')}"
        
        plain_symbol = ticker_info["plain_symbol"]
        
        # For now, return a placeholder for Indian sentiment sources
        result = f"# Indian Social Media Sentiment for {plain_symbol}\n"
        result += f"# Date range: {(datetime.strptime(curr_date, '%Y-%m-%d') - timedelta(days=lookback_days)).strftime('%Y-%m-%d')} to {curr_date}\n\n"
        
        result += "## Sentiment Analysis Sources:\n\n"
        result += f"### Social Media Sentiment for {plain_symbol}:\n"
        result += "- Twitter India discussions\n"
        result += "- Indian stock forums (ValuePickr, etc.)\n"
        result += "- Reddit India finance communities\n"
        result += "- Telegram trading groups\n\n"
        
        result += "### Institutional Sentiment Indicators:\n"
        result += "- FII/DII buying/selling patterns\n"
        result += "- Mutual fund holdings changes\n"
        result += "- Analyst recommendations from Indian brokerages\n"
        result += "- Retail investor participation metrics\n"
        
        return result
        
    except Exception as e:
        error_msg = f"Error fetching sentiment for {symbol}: {e}"
        logger.error(error_msg)
        return error_msg

def get_indian_sector_analysis(
    sector: Annotated[str, "Sector name (e.g., banking, it, pharma)"],
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"]
) -> str:
    """
    Get Indian sector analysis and performance
    
    Args:
        sector: Sector name
        curr_date: Current date
        
    Returns:
        Formatted string with sector analysis
    """
    try:
        from tradingagents.indian_config import get_sector_stocks, INDIAN_SECTORS
        
        # Get stocks in the sector
        sector_stocks = get_sector_stocks(sector.lower())
        
        if not sector_stocks:
            available_sectors = list(INDIAN_SECTORS.keys())
            return f"Sector '{sector}' not found. Available sectors: {', '.join(available_sectors)}"
        
        result = f"# Indian {sector.title()} Sector Analysis\n"
        result += f"# Date: {curr_date}\n\n"
        
        result += f"## Key Stocks in {sector.title()} Sector:\n"
        for stock in sector_stocks[:10]:  # Limit to top 10
            result += f"- {stock}\n"
        
        result += f"\n## Sector Performance Metrics:\n"
        result += "- Sectoral index performance vs Nifty 50\n"
        result += "- Average P/E ratio for the sector\n"
        result += "- FII/DII flows into sector stocks\n"
        result += "- Government policy impact on sector\n"
        result += "- Regulatory changes affecting the sector\n"
        
        result += f"\n## Recent Sector Developments:\n"
        result += f"Sector-specific news and developments for {sector} would be analyzed here.\n"
        
        return result
        
    except Exception as e:
        error_msg = f"Error analyzing sector {sector}: {e}"
        logger.error(error_msg)
        return error_msg

def get_indian_market_overview(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"]
) -> str:
    """
    Get Indian market overview and indices performance
    
    Args:
        curr_date: Current date
        
    Returns:
        Formatted string with market overview
    """
    try:
        result = f"# Indian Market Overview\n"
        result += f"# Date: {curr_date}\n\n"
        
        result += "## Key Indices Performance:\n"
        result += "- Nifty 50 (^NSEI)\n"
        result += "- BSE Sensex (^BSESN)\n"
        result += "- Nifty Bank (^CNXBANK)\n"
        result += "- Nifty IT (^CNXIT)\n"
        result += "- Nifty Auto (^CNXAUTO)\n"
        result += "- Nifty Pharma (^CNXPHARMA)\n"
        
        result += "\n## Market Breadth:\n"
        result += "- Advances vs Declines\n"
        result += "- New highs vs New lows\n"
        result += "- Volume analysis\n"
        result += "- Market volatility (India VIX)\n"
        
        result += "\n## Key Market Drivers:\n"
        result += "- RBI monetary policy stance\n"
        result += "- Government fiscal policy\n"
        result += "- Global market sentiment\n"
        result += "- FII/DII flows\n"
        result += "- Currency (USD-INR) movement\n"
        result += "- Commodity prices impact\n"
        
        result += "\n## Regulatory Updates:\n"
        result += "- SEBI policy changes\n"
        result += "- Tax policy impacts\n"
        result += "- Corporate governance updates\n"
        
        return result
        
    except Exception as e:
        error_msg = f"Error generating market overview: {e}"
        logger.error(error_msg)
        return error_msg

# Integration functions for existing framework compatibility
def get_YFin_data_indian(
    symbol: Annotated[str, "Indian stock symbol"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"]
) -> str:
    """
    Compatibility wrapper for existing YFin interface
    Automatically detects Indian tickers and routes to Indian data sources
    """
    # Check if it's an Indian ticker
    if validate_indian_ticker(symbol) or any(symbol.upper() in stocks for stocks in [
        list(range(20))  # Placeholder - would check against known Indian stocks
    ]):
        return get_indian_market_data_interface(symbol, start_date, end_date)
    else:
        # Fall back to original YFin implementation
        from .interface import get_YFin_data
        return get_YFin_data(symbol, start_date, end_date)

def get_fundamentals_indian(
    symbol: Annotated[str, "Indian stock symbol"]
) -> str:
    """
    Compatibility wrapper for fundamentals data
    """
    return get_indian_fundamentals_interface(symbol)

# Export functions for use in agents
__all__ = [
    'get_indian_market_data_interface',
    'get_indian_fundamentals_interface', 
    'get_indian_quote_interface',
    'get_indian_technical_indicators',
    'get_indian_news_interface',
    'get_indian_sentiment_interface',
    'get_indian_sector_analysis',
    'get_indian_market_overview',
    'get_YFin_data_indian',
    'get_fundamentals_indian'
] 