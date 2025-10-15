"""
Crypto-specific configuration for TradingAgents
Extends the default config with crypto market settings
"""
import os
from .default_config import DEFAULT_CONFIG

# Crypto-specific configuration
CRYPTO_CONFIG = DEFAULT_CONFIG.copy()

# Update data vendors for crypto markets
CRYPTO_CONFIG.update({
    # Crypto Data vendor configuration
    "data_vendors": {
        "core_stock_apis": "ccxt",          # CCXT for crypto OHLCV data
        "technical_indicators": "ccxt",     # CCXT for crypto technical indicators
        "fundamental_data": "messari",      # Messari for crypto fundamentals
        "news_data": "messari",             # Messari for crypto news
        "onchain_data": "glassnode",        # Glassnode for on-chain metrics
    },

    # Tool-level configuration for crypto (takes precedence over category-level)
    "tool_vendors": {
        "get_stock_data": "ccxt",                   # Use CCXT for price data
        "get_indicators": "ccxt",                   # Use CCXT for indicators
        "get_fundamentals": "messari",              # Use Messari for fundamentals
        "get_news": "messari",                      # Use Messari for news
        "get_onchain_metrics": "glassnode",         # Use Glassnode for on-chain
        "get_exchange_flows": "glassnode",          # Exchange flow analysis
        "get_whale_activity": "glassnode",          # Whale tracking
    },

    # Crypto Market Settings
    "market_type": "crypto",
    "trading_hours": "24/7",
    "asset_classes": ["spot", "perpetuals", "futures", "options"],

    # Default Crypto Exchange
    "default_exchange": "binance",  # Options: binance, coinbase, kraken, etc.
    "supported_exchanges": [
        "binance",
        "coinbase",
        "kraken",
        "bybit",
        "okx",
        "huobi",
        "kucoin",
        "bitfinex"
    ],

    # Risk Management (adjusted for crypto volatility)
    "risk_multiplier": 3.0,              # Crypto is 3x more volatile than stocks
    "max_position_size": 0.05,           # 5% per position (vs 10% for stocks)
    "max_drawdown_tolerance": 0.30,      # 30% max drawdown (vs 15% for stocks)
    "position_sizing_tiers": {
        "BTC": 0.20,        # BTC can be up to 20% of portfolio
        "ETH": 0.15,        # ETH can be up to 15%
        "major_altcoins": 0.05,  # Top 20 altcoins: 5% max each
        "small_caps": 0.02,      # Small cap: 2% max each
    },

    # Crypto-Specific Timeframes
    "default_timeframes": {
        "scalping": "1m",
        "intraday": "15m",
        "swing": "4h",
        "position": "1d",
        "long_term": "1w"
    },

    # Data Fetching Parameters
    "default_lookback_days": 30,
    "ohlcv_limit": 100,              # Number of candles to fetch
    "orderbook_depth": 20,           # Order book depth

    # On-Chain Analysis Settings
    "onchain_metrics_enabled": True,
    "whale_threshold": {
        "BTC": 100,    # 100+ BTC = whale
        "ETH": 1000,   # 1000+ ETH = whale
    },

    # Asset Categories for Analysis
    "asset_categories": {
        "layer1": ["BTC", "ETH", "SOL", "ADA", "AVAX", "DOT"],
        "layer2": ["ARB", "OP", "MATIC", "IMX"],
        "defi": ["UNI", "AAVE", "MKR", "CRV", "SNX"],
        "exchange_tokens": ["BNB", "FTT", "OKB", "KCS"],
        "stablecoins": ["USDT", "USDC", "DAI", "BUSD"],
        "meme": ["DOGE", "SHIB", "PEPE", "WIF"],
    },

    # Sentiment Analysis Sources (crypto-specific)
    "sentiment_sources": {
        "twitter": ["crypto_twitter", "bitcoin", "ethereum"],
        "reddit": ["r/cryptocurrency", "r/bitcoin", "r/ethtrader"],
        "telegram": True,  # Enable Telegram sentiment if available
        "discord": True,   # Enable Discord sentiment if available
    },

    # News Sources (crypto-specific)
    "news_sources": [
        "messari",
        "coindesk",
        "theblock",
        "decrypt",
        "cointelegraph"
    ],

    # Technical Analysis Settings (crypto-adjusted)
    "technical_indicators": {
        "trend": ["EMA_12", "EMA_26", "SMA_50", "SMA_200"],
        "momentum": ["RSI_14", "MACD", "Stochastic"],
        "volatility": ["ATR", "Bollinger_Bands"],
        "volume": ["OBV", "Volume_SMA"],
        "crypto_specific": [
            "Funding_Rate",      # Perpetuals funding rate
            "Open_Interest",     # Futures open interest
            "Long_Short_Ratio"   # Long/short ratio
        ]
    },

    # Analyst Team Configuration for Crypto
    "analyst_team": {
        "technical_analyst": {
            "enabled": True,
            "focus": ["price_action", "indicators", "chart_patterns"],
        },
        "fundamental_analyst": {
            "enabled": True,
            "focus": ["tokenomics", "project_health", "development_activity"],
        },
        "onchain_analyst": {
            "enabled": True,  # New analyst for crypto!
            "focus": ["whale_activity", "exchange_flows", "network_health"],
        },
        "sentiment_analyst": {
            "enabled": True,
            "focus": ["social_media", "news", "fear_greed_index"],
        },
        "news_analyst": {
            "enabled": True,
            "focus": ["regulatory", "partnerships", "protocol_upgrades"],
        },
    },

    # Backtesting Settings (crypto-adjusted)
    "backtest_config": {
        "initial_capital": 10000,
        "commission": 0.001,              # 0.1% (higher than stocks)
        "slippage": 0.002,                # 0.2% (higher than stocks)
        "sharpe_target": 1.5,             # Target Sharpe ratio
        "max_leverage": 3,                # Max leverage for crypto
    },

    # Alert Thresholds (crypto-adjusted for higher volatility)
    "alert_thresholds": {
        "price_change_1h": 0.05,          # 5% in 1 hour
        "price_change_24h": 0.15,         # 15% in 24 hours
        "volume_spike": 3.0,              # 3x average volume
        "whale_movement": 1000000,        # $1M+ whale transaction
        "exchange_inflow_spike": 2.0,     # 2x normal inflow
        "funding_rate_extreme": 0.01,     # 1% funding rate
    },

    # API Rate Limits (requests per minute)
    "rate_limits": {
        "ccxt": 1200,        # Varies by exchange
        "glassnode": 60,     # 60 requests per minute
        "messari": 20,       # 20 requests per minute (free tier)
    },
})


def get_crypto_config():
    """
    Get the crypto-specific configuration.

    Returns:
        Dictionary with crypto configuration
    """
    return CRYPTO_CONFIG.copy()


def get_exchange_config(exchange: str = "binance"):
    """
    Get exchange-specific configuration.

    Args:
        exchange: Exchange name

    Returns:
        Dictionary with exchange-specific settings
    """
    exchange_configs = {
        "binance": {
            "name": "Binance",
            "api_key_env": "BINANCE_API_KEY",
            "api_secret_env": "BINANCE_API_SECRET",
            "default_pairs": ["BTC/USDT", "ETH/USDT", "BNB/USDT"],
            "min_order_size": 10,  # $10 minimum
            "maker_fee": 0.001,
            "taker_fee": 0.001,
        },
        "coinbase": {
            "name": "Coinbase Pro",
            "api_key_env": "COINBASE_API_KEY",
            "api_secret_env": "COINBASE_API_SECRET",
            "default_pairs": ["BTC/USD", "ETH/USD", "SOL/USD"],
            "min_order_size": 10,
            "maker_fee": 0.005,
            "taker_fee": 0.005,
        },
        "kraken": {
            "name": "Kraken",
            "api_key_env": "KRAKEN_API_KEY",
            "api_secret_env": "KRAKEN_API_SECRET",
            "default_pairs": ["XBT/USD", "ETH/USD", "SOL/USD"],
            "min_order_size": 10,
            "maker_fee": 0.0016,
            "taker_fee": 0.0026,
        },
    }

    return exchange_configs.get(exchange, exchange_configs["binance"])


def get_asset_config(asset: str):
    """
    Get asset-specific configuration.

    Args:
        asset: Asset symbol (e.g., 'BTC', 'ETH')

    Returns:
        Dictionary with asset-specific settings
    """
    asset_configs = {
        "BTC": {
            "name": "Bitcoin",
            "category": "layer1",
            "volatility_tier": "low",
            "max_position": 0.20,
            "preferred_pairs": ["BTC/USDT", "BTC/USD"],
            "min_price_precision": 2,
        },
        "ETH": {
            "name": "Ethereum",
            "category": "layer1",
            "volatility_tier": "medium",
            "max_position": 0.15,
            "preferred_pairs": ["ETH/USDT", "ETH/USD"],
            "min_price_precision": 2,
        },
        "SOL": {
            "name": "Solana",
            "category": "layer1",
            "volatility_tier": "high",
            "max_position": 0.08,
            "preferred_pairs": ["SOL/USDT", "SOL/USD"],
            "min_price_precision": 2,
        },
    }

    # Default config for unknown assets
    default_config = {
        "name": asset,
        "category": "altcoin",
        "volatility_tier": "high",
        "max_position": 0.02,
        "preferred_pairs": [f"{asset}/USDT"],
        "min_price_precision": 4,
    }

    return asset_configs.get(asset, default_config)
