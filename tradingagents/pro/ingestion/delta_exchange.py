"""Delta Exchange (India) market-data feed — BTC and tokenized gold.

Public REST endpoints (https://docs.delta.exchange): candles, tickers
(funding/OI/mark included). No signing needed for market data — the
DELTA_API_KEY/SECRET in the operator's .env are intentionally unused
here; they exist for possible future signed endpoints, never for
trading from the dashboard.

Instruments are perpetual futures (BTCUSD; PAXGUSD = Paxos tokenized
gold, ≈ spot with a small basis) — disclosed in /api/symbols, not
hidden. Candle rows arrive newest-first and are re-sorted ascending.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from tradingagents.contracts import MetricReading, OHLCVBar, SpotQuote, Timeframe
from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.pro.ingestion.base import HttpTransport, RequestsTransport

DEFAULT_BASE = "https://api.india.delta.exchange"

RESOLUTIONS: dict[Timeframe, str] = {
    Timeframe.M1: "1m",
    Timeframe.M5: "5m",
    Timeframe.M15: "15m",
    Timeframe.M30: "30m",
    Timeframe.H1: "1h",
    Timeframe.H4: "4h",
    Timeframe.D1: "1d",
    Timeframe.W1: "1w",
}

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


class DeltaExchangeFeed:
    """Bars + quotes + derivative metrics via Delta's public v2 API."""

    name = "delta_exchange"

    def __init__(self, transport: HttpTransport | None = None,
                 base_url: str | None = None):
        self._base = (base_url or os.environ.get("DELTA_BASE_URL", DEFAULT_BASE)).rstrip("/")
        self._transport = transport or RequestsTransport()

    @classmethod
    def probe(cls, timeout: float = 8.0) -> bool:
        """One cheap candles call decides vendor selection — geo-blocks
        and outages degrade to the existing fallbacks, never break.
        PRO_DISABLE_LIVE_VENDORS=1 forces fallbacks (hermetic tests)."""
        if os.environ.get("PRO_DISABLE_LIVE_VENDORS") == "1":
            return False
        try:
            feed = cls(transport=RequestsTransport(timeout=timeout))
            feed.get_bars("BTCUSD", Timeframe.H1, limit=2)
            return True
        except Exception:
            return False

    def get_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        *,
        limit: int = 250,
        end: datetime | None = None,
    ) -> list[OHLCVBar]:
        resolution = RESOLUTIONS.get(timeframe)
        if resolution is None:
            raise ValueError(f"{self.name} does not support {timeframe.value}")
        end_dt = end or datetime.now(timezone.utc)
        start_dt = end_dt - timedelta(
            seconds=TIMEFRAME_SECONDS[timeframe] * (limit + 2)
        )
        payload = self._transport.get_json(
            f"{self._base}/v2/history/candles",
            {
                "symbol": symbol,
                "resolution": resolution,
                "start": int(start_dt.timestamp()),
                "end": int(end_dt.timestamp()),
            },
        )
        rows = payload.get("result") or []
        bars = sorted(
            (
                OHLCVBar(
                    timeframe=timeframe,
                    start=datetime.fromtimestamp(row["time"], tz=timezone.utc),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume") or 0.0),
                )
                for row in rows
            ),
            key=lambda b: b.start,
        )
        if not bars:
            raise NoMarketDataError(symbol, detail="Delta returned no candles")
        return bars[-limit:]

    def _ticker(self, symbol: str) -> dict:
        payload = self._transport.get_json(f"{self._base}/v2/tickers/{symbol}")
        result = payload.get("result")
        if not result:
            raise NoMarketDataError(symbol, detail="Delta returned no ticker")
        return result

    def get_quote(self, symbol: str) -> SpotQuote:
        t = self._ticker(symbol)
        quotes = t.get("quotes") or {}
        bid = float(quotes.get("best_bid") or 0)
        ask = float(quotes.get("best_ask") or 0)
        mark = float(t.get("mark_price") or 0)
        if not (bid > 0 and ask > 0):
            raise NoMarketDataError(symbol, detail="Delta ticker missing book quotes")
        return SpotQuote(
            bid=bid,
            ask=ask,
            last=mark if mark > 0 else (bid + ask) / 2,
            ts=datetime.now(timezone.utc),
        )

    def get_metrics(self, symbol: str = "BTCUSD") -> list[MetricReading]:
        """Funding / open interest / mark from the perp ticker. Units kept
        as the venue reports them (funding is % per 8h) — labeled, not
        silently converted."""
        t = self._ticker(symbol)
        now = datetime.now(timezone.utc)
        readings: list[MetricReading] = []

        def add(name: str, raw, unit: str) -> None:
            if raw in (None, ""):
                return
            readings.append(MetricReading(
                name=name, value=float(raw), unit=unit,
                as_of=now, source=self.name,
            ))

        add("FUNDING_RATE", t.get("funding_rate"), "pct_8h")
        add("OPEN_INTEREST", t.get("oi_value_usd") or t.get("oi"), "usd")
        add("MARK_PRICE", t.get("mark_price"), "usd")
        return readings
