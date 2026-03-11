"""DEX tool wrappers for TradingAgents."""
from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.dex.coingecko_provider import get_coin_ohlcv as _get_coin_ohlcv
from tradingagents.dataflows.dex.coingecko_provider import get_coin_info as _get_coin_info


@tool
def get_token_ohlcv(
    coin_id: Annotated[str, "CoinGecko ID (e.g., solana, bitcoin, ethereum)"],
    vs_currency: Annotated[str, "Target currency (default: usd)"] = "usd",
    days: Annotated[int, "Number of days (1-365, default: 7)"] = 7
) -> str:
    """Get OHLCV (Open-High-Low-Close-Volume) price data for a cryptocurrency token.

    Use this to analyze price movements, trends, and volatility.

    CoinGecko ID examples:
    - solana, bitcoin, ethereum, cardano, polygon, avalanche-2, chainlink

    Returns formatted OHLC data with price summary.
    """
    import asyncio
    return asyncio.run(_get_coin_ohlcv(coin_id, vs_currency, days))


@tool
def get_token_info(
    coin_id: Annotated[str, "CoinGecko ID (e.g., solana, bitcoin, ethereum)"]
) -> str:
    """Get comprehensive token metadata and market data.

    Includes: current price, market cap, volume, supply, ATH/ATL.
    Use this for fundamental analysis of cryptocurrency tokens.

    CoinGecko ID examples:
    - solana, bitcoin, ethereum, cardano, polygon, avalanche-2, chainlink
    """
    import asyncio
    return asyncio.run(_get_coin_info(coin_id))


@tool
def get_pool_data(
    pool_address: Annotated[str, "DEX pool contract address"],
    chain: Annotated[str, "Blockchain (solana, ethereum, bsc)"] = "solana"
) -> str:
    """Get DEX pool metrics: TVL, volume 24h, fees.

    Note: This requires DeFiLlama provider (Phase 2).
    Currently returns placeholder.
    """
    return "Pool data requires DeFiLlama provider (Phase 2). Use get_token_ohlcv for now."


@tool
def get_whale_transactions(
    token_address: Annotated[str, "Token contract address"],
    chain: Annotated[str, "Blockchain network"] = "solana",
    min_usd: Annotated[float, "Minimum USD value (default: 10000)"] = 10000
) -> str:
    """Track large holder (whale) movements.

    Note: This requires Birdeye provider (Phase 3).
    Currently returns placeholder.
    """
    return "Whale tracking requires Birdeye provider (Phase 3). Use get_token_ohlcv for now."