"""Delayed last prices from Yahoo Finance, for the alerts' optional intraday poller.

Yahoo's quotes for NSE and BSE stocks lag the exchange (about 15 minutes), and
nothing here makes them real time: they only let a price alert fire during the
session instead of after the evening's bhavcopy. Nothing else reads them; the
screener, the Company page's figures and the agents keep their own sources.
"""

from __future__ import annotations

import math
from datetime import datetime

import yfinance as yf

from tradingagents.dataflows.errors import NoMarketDataError, VendorRateLimitError

DELAY_NOTE = "Yahoo Finance delayed quote (about 15 minutes behind NSE)"


def delayed_quote(symbol: str) -> dict:
    """``{"price", "time", "source"}`` for one symbol, or a VendorError."""
    try:
        info = yf.Ticker(symbol).fast_info
        price = info.get("lastPrice") if hasattr(info, "get") else info.last_price
    except Exception as exc:  # noqa: BLE001 — yfinance raises whatever its HTTP layer does
        if "Too Many Requests" in str(exc) or "429" in str(exc):
            raise VendorRateLimitError(f"Yahoo Finance throttled the quote for {symbol}") from exc
        raise NoMarketDataError(symbol, detail=f"no quote: {exc}") from exc
    if price is None or not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0:
        raise NoMarketDataError(symbol, detail="no last price in Yahoo's quote")
    return {"price": float(price), "time": datetime.now().isoformat(timespec="seconds"), "source": DELAY_NOTE}


def delayed_quotes(symbols: list[str]) -> dict[str, dict]:
    """The quotes Yahoo has for ``symbols``; a symbol it has none for is left out."""
    out = {}
    for symbol in dict.fromkeys(symbols):
        try:
            out[symbol] = delayed_quote(symbol)
        except NoMarketDataError:
            continue
    return out
