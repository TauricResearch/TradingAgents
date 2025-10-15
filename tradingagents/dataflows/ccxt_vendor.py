"""
CCXT Crypto Data Vendor - Multi-exchange cryptocurrency market data
Supports: Binance, Coinbase, Kraken, and 100+ other exchanges
"""
import ccxt
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
import os


class CCXTVendor:
    """Wrapper for CCXT library to fetch crypto market data from multiple exchanges."""

    def __init__(self, exchange_id: str = "binance", api_key: str = None, api_secret: str = None):
        """
        Initialize CCXT exchange connection.

        Args:
            exchange_id: Exchange name (binance, coinbase, kraken, etc.)
            api_key: API key for authenticated endpoints (optional)
            api_secret: API secret for authenticated endpoints (optional)
        """
        self.exchange_id = exchange_id

        # Get API credentials from environment if not provided
        if api_key is None:
            api_key = os.getenv(f"{exchange_id.upper()}_API_KEY", "")
        if api_secret is None:
            api_secret = os.getenv(f"{exchange_id.upper()}_API_SECRET", "")

        # Initialize exchange
        exchange_class = getattr(ccxt, exchange_id)
        self.exchange = exchange_class({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,  # Respect rate limits
            'options': {
                'defaultType': 'spot',  # Default to spot markets
            }
        })

        # Load markets
        self.exchange.load_markets()

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = '1d',
        since: Optional[str] = None,
        limit: int = 100
    ) -> pd.DataFrame:
        """
        Fetch OHLCV (Open, High, Low, Close, Volume) data.

        Args:
            symbol: Trading pair (e.g., 'BTC/USDT', 'ETH/USD')
            timeframe: Candle timeframe ('1m', '5m', '15m', '1h', '4h', '1d', '1w')
            since: Start date (ISO format or timestamp)
            limit: Number of candles to fetch

        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
        """
        # Convert since to timestamp if provided
        since_ts = None
        if since:
            if isinstance(since, str):
                since_dt = pd.to_datetime(since)
                since_ts = int(since_dt.timestamp() * 1000)
            else:
                since_ts = since

        # Fetch OHLCV data
        ohlcv = self.exchange.fetch_ohlcv(
            symbol=symbol,
            timeframe=timeframe,
            since=since_ts,
            limit=limit
        )

        # Convert to DataFrame
        df = pd.DataFrame(
            ohlcv,
            columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
        )

        # Convert timestamp to datetime
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)

        return df

    def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch current ticker information (24h stats).

        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')

        Returns:
            Dictionary with current price, volume, changes, etc.
        """
        ticker = self.exchange.fetch_ticker(symbol)
        return ticker

    def get_order_book(self, symbol: str, limit: int = 20) -> Dict[str, Any]:
        """
        Fetch order book (bids and asks).

        Args:
            symbol: Trading pair
            limit: Depth of order book

        Returns:
            Dictionary with 'bids' and 'asks' arrays
        """
        order_book = self.exchange.fetch_order_book(symbol, limit=limit)
        return order_book

    def get_trades(self, symbol: str, since: Optional[str] = None, limit: int = 100) -> pd.DataFrame:
        """
        Fetch recent trades.

        Args:
            symbol: Trading pair
            since: Start time (ISO format or timestamp)
            limit: Number of trades

        Returns:
            DataFrame with trade history
        """
        # Convert since to timestamp if provided
        since_ts = None
        if since:
            if isinstance(since, str):
                since_dt = pd.to_datetime(since)
                since_ts = int(since_dt.timestamp() * 1000)
            else:
                since_ts = since

        trades = self.exchange.fetch_trades(symbol, since=since_ts, limit=limit)

        df = pd.DataFrame(trades)
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

        return df

    def get_markets(self) -> List[str]:
        """
        Get list of available trading pairs.

        Returns:
            List of trading pair symbols
        """
        return list(self.exchange.markets.keys())

    def get_balance(self) -> Dict[str, Any]:
        """
        Fetch account balance (requires API key).

        Returns:
            Dictionary with account balances
        """
        balance = self.exchange.fetch_balance()
        return balance


# Convenience functions for integration with existing dataflow interface

def get_crypto_ohlcv(
    symbol: str,
    timeframe: str = '1d',
    since: Optional[str] = None,
    limit: int = 100,
    exchange: str = "binance"
) -> str:
    """
    Get crypto OHLCV data formatted as string.

    Args:
        symbol: Trading pair (e.g., 'BTC/USDT')
        timeframe: Candle timeframe
        since: Start date
        limit: Number of candles
        exchange: Exchange name

    Returns:
        Formatted string with OHLCV data
    """
    vendor = CCXTVendor(exchange_id=exchange)
    df = vendor.get_ohlcv(symbol, timeframe, since, limit)

    # Format as string for LLM consumption
    result = f"OHLCV Data for {symbol} on {exchange} ({timeframe} timeframe):\n\n"
    result += df.to_string()
    result += f"\n\nLatest Price: ${df['close'].iloc[-1]:.2f}"
    result += f"\n24h Change: {((df['close'].iloc[-1] / df['close'].iloc[-2] - 1) * 100):.2f}%"
    result += f"\n24h High: ${df['high'].iloc[-1]:.2f}"
    result += f"\n24h Low: ${df['low'].iloc[-1]:.2f}"
    result += f"\n24h Volume: {df['volume'].iloc[-1]:,.0f}"

    return result


def get_crypto_ticker(symbol: str, exchange: str = "binance") -> str:
    """
    Get current crypto ticker information.

    Args:
        symbol: Trading pair
        exchange: Exchange name

    Returns:
        Formatted string with ticker data
    """
    vendor = CCXTVendor(exchange_id=exchange)
    ticker = vendor.get_ticker(symbol)

    result = f"Ticker for {symbol} on {exchange}:\n\n"
    result += f"Last Price: ${ticker.get('last', 0):.2f}\n"
    result += f"Bid: ${ticker.get('bid', 0):.2f}\n"
    result += f"Ask: ${ticker.get('ask', 0):.2f}\n"
    result += f"24h High: ${ticker.get('high', 0):.2f}\n"
    result += f"24h Low: ${ticker.get('low', 0):.2f}\n"
    result += f"24h Volume: {ticker.get('quoteVolume', 0):,.0f}\n"
    result += f"24h Change: {ticker.get('percentage', 0):.2f}%\n"

    return result


def get_crypto_order_book(symbol: str, limit: int = 20, exchange: str = "binance") -> str:
    """
    Get order book depth.

    Args:
        symbol: Trading pair
        limit: Order book depth
        exchange: Exchange name

    Returns:
        Formatted string with order book data
    """
    vendor = CCXTVendor(exchange_id=exchange)
    order_book = vendor.get_order_book(symbol, limit)

    result = f"Order Book for {symbol} on {exchange} (Top {limit}):\n\n"

    result += "ASKS (Sell Orders):\n"
    for price, amount in order_book['asks'][:10]:
        result += f"  ${price:.2f} - {amount:.4f}\n"

    result += "\nBIDS (Buy Orders):\n"
    for price, amount in order_book['bids'][:10]:
        result += f"  ${price:.2f} - {amount:.4f}\n"

    # Calculate spread
    if order_book['bids'] and order_book['asks']:
        best_bid = order_book['bids'][0][0]
        best_ask = order_book['asks'][0][0]
        spread = best_ask - best_bid
        spread_pct = (spread / best_bid) * 100
        result += f"\nSpread: ${spread:.2f} ({spread_pct:.3f}%)"

    return result


def get_crypto_fundamentals(symbol: str, exchange: str = "binance") -> str:
    """
    Get crypto fundamental metrics (volume, liquidity, market data).

    Note: For true on-chain fundamentals, use Glassnode or Messari.
    This provides exchange-level trading fundamentals.

    Args:
        symbol: Trading pair
        exchange: Exchange name

    Returns:
        Formatted string with fundamental data
    """
    vendor = CCXTVendor(exchange_id=exchange)

    # Get ticker for current stats
    ticker = vendor.get_ticker(symbol)

    # Get order book for liquidity analysis
    order_book = vendor.get_order_book(symbol, limit=100)

    # Calculate liquidity metrics
    bid_liquidity = sum(price * amount for price, amount in order_book['bids'][:20])
    ask_liquidity = sum(price * amount for price, amount in order_book['asks'][:20])
    total_liquidity = bid_liquidity + ask_liquidity

    result = f"Fundamental Metrics for {symbol} on {exchange}:\n\n"
    result += f"Market Price: ${ticker.get('last', 0):.2f}\n"
    result += f"24h Volume (USD): ${ticker.get('quoteVolume', 0):,.0f}\n"
    result += f"24h Trades: {ticker.get('info', {}).get('count', 'N/A')}\n"
    result += f"Bid Liquidity (Top 20): ${bid_liquidity:,.0f}\n"
    result += f"Ask Liquidity (Top 20): ${ask_liquidity:,.0f}\n"
    result += f"Total Liquidity: ${total_liquidity:,.0f}\n"
    result += f"Bid/Ask Ratio: {bid_liquidity/ask_liquidity if ask_liquidity > 0 else 0:.2f}\n"

    # Calculate volatility from recent data
    try:
        df = vendor.get_ohlcv(symbol, timeframe='1h', limit=24)
        returns = df['close'].pct_change().dropna()
        volatility = returns.std() * 100
        result += f"1-Day Volatility: {volatility:.2f}%\n"
    except:
        pass

    return result
