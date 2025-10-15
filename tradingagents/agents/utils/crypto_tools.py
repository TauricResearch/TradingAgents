"""
Crypto-specific tools for TradingAgents
On-chain metrics, exchange flows, whale activity, and crypto fundamentals
"""
from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_onchain_metrics(
    asset: Annotated[str, "Cryptocurrency symbol (e.g., 'BTC', 'ETH')"],
    days: Annotated[int, "Number of days of historical data"] = 30
) -> str:
    """
    Get comprehensive on-chain metrics for a cryptocurrency.

    Provides network health, exchange flows, valuation metrics, and profitability data.
    Useful for understanding blockchain-level activity and sentiment.

    Args:
        asset: Cryptocurrency symbol (BTC, ETH, SOL, etc.)
        days: Number of days of historical data (default: 30)

    Returns:
        Formatted string with on-chain metrics including:
        - Active addresses and transaction counts
        - Exchange balance and net flows
        - MVRV and NVT ratios
        - Supply profitability
    """
    try:
        result = route_to_vendor("get_onchain_metrics", asset=asset, days=days)
        return result
    except Exception as e:
        return f"Error fetching on-chain metrics: {e}\nNote: On-chain data requires Glassnode API key."


@tool
def get_exchange_flows(
    asset: Annotated[str, "Cryptocurrency symbol"],
    days: Annotated[int, "Number of days to analyze"] = 7
) -> str:
    """
    Analyze cryptocurrency exchange inflows and outflows.

    Exchange flows are a key indicator of market sentiment:
    - Net OUTFLOW (bullish): Investors moving coins to cold storage (accumulation)
    - Net INFLOW (bearish): Investors moving coins to exchanges (potential selling)

    Args:
        asset: Cryptocurrency symbol (BTC, ETH, etc.)
        days: Number of days to analyze

    Returns:
        Analysis of exchange flows with trading implications
    """
    try:
        result = route_to_vendor("get_exchange_flows", asset=asset, days=days)
        return result
    except Exception as e:
        return f"Error fetching exchange flows: {e}\nNote: Requires Glassnode API key."


@tool
def get_whale_activity(
    asset: Annotated[str, "Cryptocurrency symbol"],
    days: Annotated[int, "Number of days to analyze"] = 30
) -> str:
    """
    Analyze whale (large holder) wallet activity.

    Whale movements can signal market direction:
    - Whale ACCUMULATION (bullish): Large holders increasing positions
    - Whale DISTRIBUTION (bearish): Large holders reducing positions

    Args:
        asset: Cryptocurrency symbol
        days: Number of days to analyze

    Returns:
        Analysis of whale holdings and activity patterns
    """
    try:
        result = route_to_vendor("get_whale_activity", asset=asset, days=days)
        return result
    except Exception as e:
        return f"Error fetching whale activity: {e}\nNote: Requires Glassnode API key."


@tool
def get_crypto_market_data(
    symbol: Annotated[str, "Trading pair (e.g., 'BTC/USDT', 'ETH/USD')"],
    timeframe: Annotated[str, "Timeframe (1m, 5m, 15m, 1h, 4h, 1d, 1w)"] = "1d",
    limit: Annotated[int, "Number of candles"] = 100,
    exchange: Annotated[str, "Exchange name"] = "binance"
) -> str:
    """
    Get cryptocurrency OHLCV (Open, High, Low, Close, Volume) price data.

    Args:
        symbol: Trading pair (e.g., 'BTC/USDT', 'ETH/USDT')
        timeframe: Candle timeframe (1m, 5m, 15m, 1h, 4h, 1d, 1w)
        limit: Number of candles to fetch
        exchange: Exchange name (binance, coinbase, kraken)

    Returns:
        OHLCV data with price statistics
    """
    try:
        from tradingagents.dataflows.ccxt_vendor import get_crypto_ohlcv
        result = get_crypto_ohlcv(symbol, timeframe, limit=limit, exchange=exchange)
        return result
    except Exception as e:
        return f"Error fetching crypto market data: {e}"


@tool
def get_crypto_ticker(
    symbol: Annotated[str, "Trading pair"],
    exchange: Annotated[str, "Exchange name"] = "binance"
) -> str:
    """
    Get current cryptocurrency ticker (real-time price and 24h statistics).

    Args:
        symbol: Trading pair (e.g., 'BTC/USDT')
        exchange: Exchange name

    Returns:
        Current price, bid/ask, 24h high/low/volume, and price change
    """
    try:
        from tradingagents.dataflows.ccxt_vendor import get_crypto_ticker as fetch_ticker
        result = fetch_ticker(symbol, exchange)
        return result
    except Exception as e:
        return f"Error fetching ticker: {e}"


@tool
def get_crypto_fundamentals(
    asset_key: Annotated[str, "Asset slug (e.g., 'bitcoin', 'ethereum', 'solana')"]
) -> str:
    """
    Get comprehensive cryptocurrency fundamentals and tokenomics.

    Provides:
    - Project overview and category
    - Tokenomics (supply, inflation, distribution)
    - Market metrics (price, volume, market cap)
    - Technology (consensus mechanism, hashing algorithm)
    - Valuation metrics

    Args:
        asset_key: Asset slug in lowercase (bitcoin, ethereum, cardano, solana, etc.)

    Returns:
        Detailed fundamental analysis suitable for investment decisions
    """
    try:
        from tradingagents.dataflows.messari_vendor import get_crypto_fundamentals_messari
        result = get_crypto_fundamentals_messari(asset_key)
        return result
    except Exception as e:
        return f"Error fetching crypto fundamentals: {e}"


@tool
def get_crypto_news(
    asset_key: Annotated[str, "Asset slug (optional, for asset-specific news)"] = None,
    limit: Annotated[int, "Number of news items"] = 10
) -> str:
    """
    Get latest cryptocurrency news.

    Args:
        asset_key: Asset slug for asset-specific news (e.g., 'bitcoin')
                   Leave empty for general crypto news
        limit: Number of news items to fetch

    Returns:
        Recent crypto news with titles, dates, and URLs
    """
    try:
        from tradingagents.dataflows.messari_vendor import get_crypto_news_messari
        result = get_crypto_news_messari(asset_key, limit)
        return result
    except Exception as e:
        return f"Error fetching crypto news: {e}"


@tool
def get_order_book_analysis(
    symbol: Annotated[str, "Trading pair"],
    limit: Annotated[int, "Order book depth"] = 20,
    exchange: Annotated[str, "Exchange name"] = "binance"
) -> str:
    """
    Analyze cryptocurrency order book for liquidity and support/resistance.

    Order book analysis reveals:
    - Bid/Ask spread (liquidity indicator)
    - Buy/Sell wall locations
    - Market depth and liquidity

    Args:
        symbol: Trading pair
        limit: Depth of order book to analyze
        exchange: Exchange name

    Returns:
        Order book snapshot with liquidity analysis
    """
    try:
        from tradingagents.dataflows.ccxt_vendor import get_crypto_order_book
        result = get_crypto_order_book(symbol, limit, exchange)
        return result
    except Exception as e:
        return f"Error fetching order book: {e}"


@tool
def get_tokenomics(
    asset_key: Annotated[str, "Asset slug"]
) -> str:
    """
    Get detailed tokenomics analysis for a cryptocurrency.

    Analyzes:
    - Supply schedule (circulating, total, max supply)
    - Emission rate and inflation
    - Token distribution and vesting
    - Dilution potential

    Args:
        asset_key: Asset slug (bitcoin, ethereum, etc.)

    Returns:
        Comprehensive tokenomics breakdown
    """
    try:
        from tradingagents.dataflows.messari_vendor import get_tokenomics_analysis
        result = get_tokenomics_analysis(asset_key)
        return result
    except Exception as e:
        return f"Error fetching tokenomics: {e}"


@tool
def get_market_overview(
    limit: Annotated[int, "Number of top assets"] = 20
) -> str:
    """
    Get overview of top cryptocurrencies by market cap.

    Args:
        limit: Number of top assets to include

    Returns:
        Market overview table with rankings, prices, and 24h changes
    """
    try:
        from tradingagents.dataflows.messari_vendor import get_crypto_market_overview
        result = get_crypto_market_overview(limit)
        return result
    except Exception as e:
        return f"Error fetching market overview: {e}"
