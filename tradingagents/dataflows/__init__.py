"""Data layer for the Kalshi prediction-market pipeline.

Modules:
    coinbase            — public OHLCV / spot price (BTC-USD ref for Kalshi)
    kalshi_market       — Kalshi market metadata + YES/NO mid (signed reads)
    crypto_news         — RSS aggregation across reputable crypto outlets
    sentiment_sources   — Reddit + CoinMarketCap (creds-gated, graceful fallback)
    onchain             — blockchain.com + mempool.space (free, key-less)
    indicators          — pandas-native technical indicators
    interface           — vendor-routing registry for analyst tools
    config              — runtime config singleton (set/get from CLI / runner)
"""
