"""Binance public-API adapters for Bitcoin market data.

Keyless REST endpoints only (spot api.binance.com, USD-M futures
fapi.binance.com). Rate limits: spot 6000 request-weight/min per IP,
futures 2400/min — one snapshot build uses ~5 requests, far below either.
Contract Timeframe values ("1m".."1w") are deliberately identical to
Binance kline intervals, so no mapping table is needed.
"""

from __future__ import annotations

from datetime import datetime, timezone

from tradingagents.contracts import MetricReading, OHLCVBar, SpotQuote, Timeframe
from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.pro.ingestion.base import HttpTransport, RequestsTransport
from tradingagents.pro.ingestion.derived import orderbook_imbalance

SPOT_BASE = "https://api.binance.com"
FUTURES_BASE = "https://fapi.binance.com"


def _ms_to_utc(ms: int | float) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


class BinanceSpotFeed:
    """Spot klines, top-of-book quote, and order-book depth imbalance."""

    name = "binance_spot"

    def __init__(self, transport: HttpTransport | None = None):
        self._transport = transport or RequestsTransport()

    def get_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        *,
        limit: int = 250,
        end: datetime | None = None,
    ) -> list[OHLCVBar]:
        params: dict = {"symbol": symbol, "interval": timeframe.value, "limit": limit}
        if end is not None:
            params["endTime"] = int(end.timestamp() * 1000)
        rows = self._transport.get_json(f"{SPOT_BASE}/api/v3/klines", params)
        if not rows:
            raise NoMarketDataError(symbol, detail="Binance returned no klines")
        return [
            OHLCVBar(
                timeframe=timeframe,
                start=_ms_to_utc(row[0]),
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
            )
            for row in rows
        ]

    def get_quote(self, symbol: str) -> SpotQuote:
        book = self._transport.get_json(
            f"{SPOT_BASE}/api/v3/ticker/bookTicker", {"symbol": symbol}
        )
        last = self._transport.get_json(f"{SPOT_BASE}/api/v3/ticker/price", {"symbol": symbol})
        return SpotQuote(
            bid=float(book["bidPrice"]),
            ask=float(book["askPrice"]),
            last=float(last["price"]),
            ts=datetime.now(timezone.utc),
        )

    def get_orderbook_imbalance(self, symbol: str, depth: int = 100) -> MetricReading:
        book = self._transport.get_json(
            f"{SPOT_BASE}/api/v3/depth", {"symbol": symbol, "limit": depth}
        )
        value = orderbook_imbalance(
            [(float(p), float(q)) for p, q in book["bids"]],
            [(float(p), float(q)) for p, q in book["asks"]],
        )
        return MetricReading(
            name=f"ORDERBOOK_IMBALANCE_{depth}",
            value=value,
            unit="ratio",
            as_of=datetime.now(timezone.utc),
            source=self.name,
        )


class BinanceDerivativesFeed:
    """USD-M perpetual metrics: funding rate, mark price, open interest."""

    name = "binance_derivatives"

    def __init__(self, transport: HttpTransport | None = None, symbol: str = "BTCUSDT"):
        self._transport = transport or RequestsTransport()
        self._symbol = symbol

    def get_metrics(self) -> list[MetricReading]:
        premium = self._transport.get_json(
            f"{FUTURES_BASE}/fapi/v1/premiumIndex", {"symbol": self._symbol}
        )
        oi = self._transport.get_json(
            f"{FUTURES_BASE}/fapi/v1/openInterest", {"symbol": self._symbol}
        )
        as_of = _ms_to_utc(premium["time"])
        return [
            MetricReading(
                name="FUNDING_RATE",
                value=float(premium["lastFundingRate"]),
                unit="rate_8h",
                as_of=as_of,
                source=self.name,
            ),
            MetricReading(
                name="MARK_PRICE",
                value=float(premium["markPrice"]),
                unit="USDT",
                as_of=as_of,
                source=self.name,
            ),
            MetricReading(
                name="OPEN_INTEREST",
                value=float(oi["openInterest"]),
                unit="BTC",
                as_of=_ms_to_utc(oi["time"]),
                source=self.name,
            ),
        ]
