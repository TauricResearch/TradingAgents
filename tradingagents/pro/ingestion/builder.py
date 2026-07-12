"""SnapshotBuilder: compose feed adapters into a frozen MarketSnapshot.

The builder is the single place where feed failures are absorbed: a feed
that raises lands in ``missing_feeds`` (agents must treat it as unknown —
contract semantics), it never fabricates or interpolates values. Bars and
the indicator engine are the exception: without price data there is no
snapshot, so bar failures raise.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from datetime import datetime, timezone

from tradingagents.contracts import (
    AssetClass,
    IndicatorReading,
    MarketSnapshot,
    MetricReading,
    OHLCVBar,
    Timeframe,
    TradingSession,
)
from tradingagents.pro.ingestion.base import BarsFeed, MetricsFeed, QuoteFeed
from tradingagents.pro.ingestion.binance import BinanceDerivativesFeed, BinanceSpotFeed
from tradingagents.pro.ingestion.fred_macro import FredMacroFeed
from tradingagents.pro.ingestion.gold_feeds import GoldCrossAssetFeed, YFinanceDailyBarsFeed
from tradingagents.pro.ingestion.indicators import DEFAULT_INDICATOR_NAMES, compute_indicators
from tradingagents.pro.ingestion.onchain import BlockchainComFeed, CoinMetricsFeed, FearGreedFeed
from tradingagents.pro.ingestion.sessions import current_session

logger = logging.getLogger(__name__)

SessionFn = Callable[[datetime], TradingSession]


class SnapshotBuilder:
    def __init__(
        self,
        *,
        bars_feed: BarsFeed,
        quote_feed: QuoteFeed | None = None,
        macro_feeds: Sequence[MetricsFeed] = (),
        onchain_feeds: Sequence[MetricsFeed] = (),
        extra_metric_fns: Sequence[Callable[[], MetricReading]] = (),
        indicator_names: Sequence[str] = DEFAULT_INDICATOR_NAMES,
        session_fn: SessionFn | None = None,
    ):
        self._bars_feed = bars_feed
        self._quote_feed = quote_feed
        self._macro_feeds = tuple(macro_feeds)
        self._onchain_feeds = tuple(onchain_feeds)
        self._extra_metric_fns = tuple(extra_metric_fns)
        self._indicator_names = tuple(indicator_names)
        self._session_fn = session_fn

    def build(
        self,
        symbol: str,
        asset: AssetClass,
        *,
        timeframes: Sequence[Timeframe] = (Timeframe.D1,),
        bar_limit: int = 250,
        as_of: datetime | None = None,
    ) -> MarketSnapshot:
        as_of = as_of or datetime.now(timezone.utc)
        missing: list[str] = []

        bars: list[OHLCVBar] = []
        indicators: list[IndicatorReading] = []
        for timeframe in timeframes:
            tf_bars = self._bars_feed.get_bars(symbol, timeframe, limit=bar_limit, end=as_of)
            bars.extend(tf_bars)
            indicators.extend(compute_indicators(tf_bars, self._indicator_names))

        quote = None
        if self._quote_feed is not None:
            try:
                quote = self._quote_feed.get_quote(symbol)
            except Exception:
                logger.warning("quote feed %s failed", self._quote_feed.name, exc_info=True)
                missing.append(self._quote_feed.name)

        macro = self._collect(self._macro_feeds, missing)
        onchain = self._collect(self._onchain_feeds, missing)
        for fn in self._extra_metric_fns:
            try:
                onchain.append(fn())
            except Exception:
                name = getattr(fn, "__name__", repr(fn))
                logger.warning("extra metric %s failed", name, exc_info=True)
                missing.append(name)

        return MarketSnapshot(
            symbol=symbol,
            asset=asset,
            as_of=as_of,
            quote=quote,
            bars=bars,
            indicators=indicators,
            macro=macro,
            onchain=onchain,
            session=self._session_fn(as_of) if self._session_fn else None,
            missing_feeds=missing,
        )

    @staticmethod
    def _collect(feeds: Sequence[MetricsFeed], missing: list[str]) -> list[MetricReading]:
        readings: list[MetricReading] = []
        for feed in feeds:
            try:
                readings.extend(feed.get_metrics())
            except Exception:
                logger.warning("metrics feed %s failed", feed.name, exc_info=True)
                missing.append(feed.name)
        return readings


def build_gold_pipeline(
    loader=None, transport=None, correlation_window: int = 30,
    cot_cache_path=None,
) -> SnapshotBuilder:
    """Default gold (XAU) pipeline: GC=F daily bars + cross-asset context +
    FRED macro + CFTC COT positioning + GVZ implied vol + session
    awareness. All feeds free; FRED needs its free key."""
    from tradingagents.pro.ingestion.positioning import GoldCotFeed, GoldVolFeed

    bars_feed = YFinanceDailyBarsFeed(loader=loader)
    return SnapshotBuilder(
        bars_feed=bars_feed,
        macro_feeds=(
            GoldCrossAssetFeed(bars_feed, correlation_window=correlation_window),
            FredMacroFeed(transport=transport),
            GoldCotFeed(transport=transport, cache_path=cot_cache_path),
            GoldVolFeed(bars_feed),
        ),
        session_fn=current_session,
    )


def build_bitcoin_pipeline(transport=None) -> SnapshotBuilder:
    """Default BTC pipeline: Binance spot bars/quote/depth + perp metrics +
    on-chain (CoinMetrics, blockchain.com) + Fear & Greed. All keyless."""
    spot = BinanceSpotFeed(transport=transport)
    return SnapshotBuilder(
        bars_feed=spot,
        quote_feed=spot,
        macro_feeds=(BinanceDerivativesFeed(transport=transport),),
        onchain_feeds=(
            CoinMetricsFeed(transport=transport),
            BlockchainComFeed(transport=transport),
            FearGreedFeed(transport=transport),
        ),
        extra_metric_fns=(lambda: spot.get_orderbook_imbalance("BTCUSDT"),),
    )
