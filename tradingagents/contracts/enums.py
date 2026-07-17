"""Enumerations shared across all Pro contracts.

String-valued enums so payloads stay human-readable in JSON, logs, and the
memory store, and so LangGraph state serializes without custom encoders.
"""

from __future__ import annotations

from enum import Enum


class AssetClass(str, Enum):
    """Assets the Pro pipeline specializes in.

    The base framework keeps supporting arbitrary equity tickers; these are
    the assets that get dedicated ingestion adapters and agent rosters.
    """

    GOLD = "XAU"
    BITCOIN = "BTC"
    ETHEREUM = "ETH"
    SOLANA = "SOL"


# Default broker-style symbol per asset. The existing dataflows layer
# (symbol_utils.normalize_symbol) already maps these to vendor symbols
# (XAUUSD -> GC=F on Yahoo, BTC-USD stays as is).
DEFAULT_SYMBOLS: dict[AssetClass, str] = {
    AssetClass.GOLD: "XAUUSD",
    AssetClass.BITCOIN: "BTC-USD",
    AssetClass.ETHEREUM: "ETH-USD",
    AssetClass.SOLANA: "SOL-USD",
}

# Crypto assets share one ingestion/agent wiring (derivatives + on-chain
# + sentiment feeds parameterized by symbol).
CRYPTO_ASSETS: frozenset[AssetClass] = frozenset(
    {AssetClass.BITCOIN, AssetClass.ETHEREUM, AssetClass.SOLANA}
)


class TradingMode(str, Enum):
    BACKTEST = "backtest"
    PAPER = "paper"
    LIVE = "live"


class Direction(str, Enum):
    """Directional stance attached to a single evidence claim."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class TradeAction(str, Enum):
    """Final recommendation action (uppercase per the Pro contract spec)."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class Timeframe(str, Enum):
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"
    W1 = "1w"


class MarketRegime(str, Enum):
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    CRISIS = "crisis"
    UNKNOWN = "unknown"


class TradingSession(str, Enum):
    """Session awareness matters for gold (liquidity/volatility cycles)."""

    ASIA = "asia"
    LONDON = "london"
    NEW_YORK = "new_york"
    CLOSED = "closed"


class AgentTeam(str, Enum):
    """Teams from the Pro agent roster (Phase 3)."""

    EXECUTIVE = "executive"
    TECHNICAL = "technical"
    MACRO = "macro"
    NEWS_SENTIMENT = "news_sentiment"
    QUANT = "quant"
    RISK = "risk"


class SourceType(str, Enum):
    """Provenance category for a piece of evidence."""

    MARKET_DATA = "market_data"
    INDICATOR = "indicator"
    MACRO_RELEASE = "macro_release"
    NEWS = "news"
    SOCIAL = "social"
    ONCHAIN = "onchain"
    PREDICTION_MARKET = "prediction_market"
    MEMORY = "memory"
    MODEL = "model"
