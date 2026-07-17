"""On-demand market data for charts: symbol registry + TTL-cached bars.

Charts need arbitrary (symbol, timeframe, limit) on demand; pipeline
snapshots refresh hourly and only for the traded symbol, so this service
fetches through the same ingestion adapters the pipeline uses, behind a
small TTL cache with single-flight locking (concurrent chart loads never
stampede a vendor).

Endpoints stay sync (Starlette threadpool) so the blocking vendor calls
never touch the event loop. Capabilities are data, not code: /api/symbols
advertises exactly what each symbol supports so the UI never renders a
dead timeframe button.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from tradingagents.contracts import OHLCVBar, Timeframe

TIMEFRAME_SECONDS: dict[Timeframe, int] = {
    Timeframe.M1: 60,
    Timeframe.M5: 300,
    Timeframe.M15: 900,
    Timeframe.M30: 1800,
    Timeframe.H1: 3600,
    Timeframe.H4: 14400,
    Timeframe.D1: 86400,
    Timeframe.W1: 604800,
}

MAX_LIMIT = 1000
DEFAULT_LIMIT = 300


class UnknownSymbolError(KeyError):
    pass


class UnsupportedTimeframeError(ValueError):
    def __init__(self, symbol: str, timeframe: Timeframe, supported: Sequence[Timeframe]):
        self.supported = tuple(supported)
        super().__init__(
            f"{symbol} does not support {timeframe.value}; "
            f"available: {[t.value for t in self.supported]}"
        )


@dataclass(frozen=True)
class SymbolSpec:
    symbol: str                       # dashboard-facing name (BTC-USD, XAUUSD)
    vendor_symbol: str                # what the feed expects (BTCUSDT, GC=F)
    source: str                       # feed name for provenance display
    timeframes: tuple[Timeframe, ...]
    live: bool                        # true when a streaming transport exists
    feed_factory: Callable[[], object]
    tradeable: bool = False           # pipeline + venue support exists

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "vendor_symbol": self.vendor_symbol,
            "source": self.source,
            "timeframes": [t.value for t in self.timeframes],
            "live": self.live,
            "tradeable": self.tradeable,
        }


def default_registry() -> dict[str, SymbolSpec]:
    """Vendor preference is probe-gated, never assumed: Delta Exchange
    first for BTC (BTCUSD perp) and gold (XAUTUSD, Tether Gold ≈ spot)
    — the operator's reachable venue; else Binance for BTC and OANDA/
    yfinance for gold. Degradation is disclosed, never faked."""
    import logging

    from tradingagents.pro.ingestion.binance import BinanceSpotFeed
    from tradingagents.pro.ingestion.delta_exchange import DeltaExchangeFeed
    from tradingagents.pro.ingestion.gold_feeds import YFinanceDailyBarsFeed
    from tradingagents.pro.ingestion.oanda_gold import OandaGoldFeed

    logger = logging.getLogger(__name__)
    delta_alive = DeltaExchangeFeed.probe()
    if delta_alive:
        logger.info("Delta Exchange reachable — serving BTC-USD (BTCUSD perp) "
                    "and XAUUSD (XAUTUSD Tether Gold) live")

    # crypto perps share the Delta-first / Binance-fallback wiring
    def crypto_spec(symbol: str, delta_sym: str, binance_sym: str) -> SymbolSpec:
        if delta_alive:
            return SymbolSpec(
                symbol=symbol,
                vendor_symbol=delta_sym,
                source="delta_exchange",
                timeframes=tuple(TIMEFRAME_SECONDS),
                live=True,
                feed_factory=DeltaExchangeFeed,
                tradeable=True,
            )
        return SymbolSpec(
            symbol=symbol,
            vendor_symbol=binance_sym,
            source="binance_spot",
            timeframes=tuple(TIMEFRAME_SECONDS),
            live=True,
            feed_factory=BinanceSpotFeed,
            tradeable=True,
        )

    registry = {
        "BTC-USD": crypto_spec("BTC-USD", "BTCUSD", "BTCUSDT"),
        "ETH-USD": crypto_spec("ETH-USD", "ETHUSD", "ETHUSDT"),
        "SOL-USD": crypto_spec("SOL-USD", "SOLUSD", "SOLUSDT"),
    }
    # daily-only cross-asset series (correlation matrix, context charts)
    for symbol, vendor in (("DXY", "DX-Y.NYB"), ("SILVER", "SI=F"),
                           ("US10Y", "^TNX")):
        registry[symbol] = SymbolSpec(
            symbol=symbol,
            vendor_symbol=vendor,
            source="yfinance_daily",
            timeframes=(Timeframe.D1,),
            live=False,
            feed_factory=YFinanceDailyBarsFeed,
        )
    if delta_alive:
        registry["XAUUSD"] = SymbolSpec(
            symbol="XAUUSD",
            vendor_symbol="XAUTUSD",  # Tether Gold, ≈ spot (small basis)
            source="delta_exchange",
            timeframes=tuple(TIMEFRAME_SECONDS),
            live=True,
            feed_factory=DeltaExchangeFeed,
            tradeable=True,
        )
    elif OandaGoldFeed.configured() and OandaGoldFeed.probe():
        registry["XAUUSD"] = SymbolSpec(
            symbol="XAUUSD",
            vendor_symbol="XAU_USD",
            source="oanda_gold",
            timeframes=tuple(OandaGoldFeed.GRANULARITY),
            live=True,
            feed_factory=OandaGoldFeed,
            tradeable=True,
        )
    else:
        if OandaGoldFeed.configured():
            import logging

            logging.getLogger(__name__).warning(
                "OANDA_API_TOKEN is set but the API rejected it — "
                "falling back to yfinance daily gold"
            )
        registry["XAUUSD"] = SymbolSpec(
            symbol="XAUUSD",
            vendor_symbol="GC=F",
            source="yfinance_daily",
            timeframes=(Timeframe.D1,),
            live=False,
            feed_factory=YFinanceDailyBarsFeed,
            tradeable=True,
        )
    return registry


class MarketDataService:
    def __init__(
        self,
        registry: dict[str, SymbolSpec] | None = None,
        ttl_floor: float = 5.0,
        ttl_cap: float = 300.0,
        now: Callable[[], float] = time.monotonic,
    ):
        self._registry = registry
        self.ttl_floor = ttl_floor
        self.ttl_cap = ttl_cap
        self._now = now
        self._cache: dict[tuple[str, Timeframe], tuple[float, list[OHLCVBar]]] = {}
        self._feeds: dict[str, object] = {}
        self._lock = threading.Lock()
        self._flights: dict[tuple[str, Timeframe], threading.Lock] = {}

    @property
    def registry(self) -> dict[str, SymbolSpec]:
        if self._registry is None:
            self._registry = default_registry()  # lazy: env read at first use
        return self._registry

    def symbols(self) -> list[dict]:
        return [spec.as_dict() for spec in self.registry.values()]

    def spec(self, symbol: str) -> SymbolSpec:
        try:
            return self.registry[symbol]
        except KeyError:
            raise UnknownSymbolError(symbol) from None

    def _ttl(self, timeframe: Timeframe) -> float:
        return min(max(TIMEFRAME_SECONDS[timeframe] / 2, self.ttl_floor), self.ttl_cap)

    def _feed(self, spec: SymbolSpec):
        with self._lock:
            if spec.symbol not in self._feeds:
                self._feeds[spec.symbol] = spec.feed_factory()
            return self._feeds[spec.symbol]

    def get_bars(
        self, symbol: str, timeframe: Timeframe, limit: int = DEFAULT_LIMIT
    ) -> list[OHLCVBar]:
        spec = self.spec(symbol)
        if timeframe not in spec.timeframes:
            raise UnsupportedTimeframeError(symbol, timeframe, spec.timeframes)
        limit = max(1, min(limit, MAX_LIMIT))
        key = (symbol, timeframe)

        with self._lock:
            cached = self._cache.get(key)
            if cached and self._now() - cached[0] < self._ttl(timeframe):
                return cached[1][-limit:]
            flight = self._flights.setdefault(key, threading.Lock())

        with flight:  # single-flight: one vendor call per key
            with self._lock:
                cached = self._cache.get(key)
                if cached and self._now() - cached[0] < self._ttl(timeframe):
                    return cached[1][-limit:]
            bars = self._feed(spec).get_bars(
                spec.vendor_symbol, timeframe, limit=max(limit, DEFAULT_LIMIT)
            )
            with self._lock:
                self._cache[key] = (self._now(), list(bars))
            return list(bars)[-limit:]


def bars_view(bars: Sequence[OHLCVBar]) -> list[dict]:
    """Lightweight-Charts-native rows (unix-seconds time)."""
    return [
        {
            "time": int(bar.start.timestamp()),
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
        }
        for bar in bars
    ]


def indicator_series_view(bars: Sequence[OHLCVBar], names: Sequence[str]) -> dict:
    """Aligned {time, value} points per indicator line, warm-up Nones dropped."""
    from tradingagents.pro.ingestion.indicators import compute_indicator_series

    times = [int(bar.start.timestamp()) for bar in bars]
    result = {}
    for name, block in compute_indicator_series(bars, names).items():
        lines = {
            key: [
                {"time": t, "value": v}
                for t, v in zip(times, values, strict=True)
                if v is not None
            ]
            for key, values in block["series"].items()
        }
        result[name] = {"params": block["params"], "series": lines}
    return result
