"""OANDA gold intraday feed (XAU/USD spot, practice API).

Free practice-tier REST API: https://developer.oanda.com/rest-live-v20/.
Env: ``OANDA_API_TOKEN`` (bearer token from a practice account) and
optional ``OANDA_ENV`` (``practice`` default | ``live``). Missing token
raises VendorNotConfiguredError per the taxonomy — callers register the
gap (yfinance daily fallback in the dashboard registry) instead of
crashing.

Candles are requested as mid prices (deterministic: no bid/ask ambiguity)
and incomplete candles are dropped — the whole system assumes bar-close
semantics. Quotes derive bid/ask from the latest 5-second bid/ask candle,
which avoids needing an OANDA_ACCOUNT_ID for the pricing endpoint.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from tradingagents.contracts import OHLCVBar, SpotQuote, Timeframe
from tradingagents.dataflows.errors import NoMarketDataError, VendorNotConfiguredError
from tradingagents.pro.ingestion.base import HttpTransport, RequestsTransport

_HOSTS = {
    "practice": "https://api-fxpractice.oanda.com",
    "live": "https://api-fxtrade.oanda.com",
}


class OandaNotConfiguredError(VendorNotConfiguredError):
    pass


class OandaGoldFeed:
    """Bars + quotes for XAU_USD via OANDA v20 instruments endpoints."""

    name = "oanda_gold"

    GRANULARITY: dict[Timeframe, str] = {
        Timeframe.M1: "M1",
        Timeframe.M5: "M5",
        Timeframe.M15: "M15",
        Timeframe.M30: "M30",
        Timeframe.H1: "H1",
        Timeframe.H4: "H4",
        Timeframe.D1: "D",
        Timeframe.W1: "W",
    }

    def __init__(self, transport: HttpTransport | None = None,
                 token: str | None = None, env: str | None = None):
        token = token or os.environ.get("OANDA_API_TOKEN", "")
        if not token:
            raise OandaNotConfiguredError(
                "OANDA_API_TOKEN not set; gold intraday unavailable "
                "(daily bars fall back to yfinance)"
            )
        env = (env or os.environ.get("OANDA_ENV", "practice")).lower()
        if env not in _HOSTS:
            raise ValueError(f"OANDA_ENV must be one of {sorted(_HOSTS)}, got {env!r}")
        self._base = _HOSTS[env]
        self._transport = transport or RequestsTransport(
            headers={"Authorization": f"Bearer {token}"}
        )

    @staticmethod
    def configured() -> bool:
        return bool(os.environ.get("OANDA_API_TOKEN"))

    def _candles(self, instrument: str, params: dict) -> list[dict]:
        payload = self._transport.get_json(
            f"{self._base}/v3/instruments/{instrument}/candles", params
        )
        return payload.get("candles", [])

    def get_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        *,
        limit: int = 250,
        end: datetime | None = None,
    ) -> list[OHLCVBar]:
        granularity = self.GRANULARITY.get(timeframe)
        if granularity is None:
            raise ValueError(f"{self.name} does not support {timeframe.value}")
        params: dict = {
            "granularity": granularity,
            "count": min(max(limit + 1, 2), 5000),  # +1: last may be incomplete
            "price": "M",
        }
        if end is not None:
            params["to"] = end.astimezone(timezone.utc).isoformat()
        candles = self._candles(symbol, params)
        bars = [
            OHLCVBar(
                timeframe=timeframe,
                start=datetime.fromisoformat(row["time"].replace("Z", "+00:00")),
                open=float(row["mid"]["o"]),
                high=float(row["mid"]["h"]),
                low=float(row["mid"]["l"]),
                close=float(row["mid"]["c"]),
                volume=float(row.get("volume", 0)),
            )
            for row in candles
            if row.get("complete")  # bar-close semantics only
        ]
        if not bars:
            raise NoMarketDataError(symbol, detail="OANDA returned no complete candles")
        return bars[-limit:]

    def get_quote(self, symbol: str) -> SpotQuote:
        candles = self._candles(
            symbol, {"granularity": "S5", "count": 1, "price": "BAM"}
        )
        if not candles:
            raise NoMarketDataError(symbol, detail="OANDA returned no quote candle")
        row = candles[-1]  # freshest 5s candle; may be incomplete (that's fine
        # for a quote — it is the most recent traded picture)
        return SpotQuote(
            bid=float(row["bid"]["c"]),
            ask=float(row["ask"]["c"]),
            last=float(row["mid"]["c"]),
            ts=datetime.fromisoformat(row["time"].replace("Z", "+00:00")),
        )
