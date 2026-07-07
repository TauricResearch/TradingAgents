"""Pro ingestion layer (Phase 2): typed feed adapters -> MarketSnapshot.

See docs/DATA_SOURCES.md for the source-by-source decision table.
"""

from tradingagents.pro.ingestion.base import (
    BarsFeed,
    HttpTransport,
    MetricsFeed,
    QuoteFeed,
    RequestsTransport,
)
from tradingagents.pro.ingestion.binance import BinanceDerivativesFeed, BinanceSpotFeed
from tradingagents.pro.ingestion.builder import (
    SnapshotBuilder,
    build_bitcoin_pipeline,
    build_gold_pipeline,
)
from tradingagents.pro.ingestion.fred_macro import FredMacroFeed
from tradingagents.pro.ingestion.gold_feeds import GoldCrossAssetFeed, YFinanceDailyBarsFeed
from tradingagents.pro.ingestion.indicators import (
    DEFAULT_INDICATOR_NAMES,
    INDICATOR_SPECS,
    compute_indicators,
)
from tradingagents.pro.ingestion.onchain import (
    BlockchainComFeed,
    CoinMetricsFeed,
    FearGreedFeed,
)
from tradingagents.pro.ingestion.sessions import current_session

__all__ = [
    "BarsFeed",
    "HttpTransport",
    "MetricsFeed",
    "QuoteFeed",
    "RequestsTransport",
    "BinanceDerivativesFeed",
    "BinanceSpotFeed",
    "SnapshotBuilder",
    "build_bitcoin_pipeline",
    "build_gold_pipeline",
    "FredMacroFeed",
    "GoldCrossAssetFeed",
    "YFinanceDailyBarsFeed",
    "DEFAULT_INDICATOR_NAMES",
    "INDICATOR_SPECS",
    "compute_indicators",
    "BlockchainComFeed",
    "CoinMetricsFeed",
    "FearGreedFeed",
    "current_session",
]
