"""Coinbase Advanced Trade public market data.

We use Coinbase as the BTC price source because Kalshi's BTC daily
contracts settle against the Coinbase BTC-USD index. Aligning the
analysis price feed with the resolution venue eliminates basis risk
between what the agent committee deliberates over and what the contract
actually pays out on.

All endpoints used here are public (no auth) and free. Rate limits are
generous for read traffic; the disk cache keeps repeated calls within
an analyst run cheap.
"""

from __future__ import annotations

import datetime as _dt
from typing import Dict, List

import requests

from ._cache import cached_json


_PUBLIC_BASE = "https://api.exchange.coinbase.com"
_DEFAULT_PRODUCT = "BTC-USD"
_GRANULARITY_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "6h": 21600,
    "1d": 86400,
}


def _product_for(symbol: str) -> str:
    """Map an asset symbol to a Coinbase product id (e.g. BTC -> BTC-USD)."""
    sym = symbol.strip().upper()
    if "-" in sym:
        return sym
    return f"{sym}-USD"


def get_spot_price(symbol: str = "BTC") -> float:
    """Return the current spot price for ``symbol`` (e.g. ``BTC``)."""
    product = _product_for(symbol)
    url = f"{_PUBLIC_BASE}/products/{product}/ticker"

    def _fetch():
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return r.json()

    payload = cached_json(f"coinbase_ticker_{product}", ttl_seconds=30, fetcher=_fetch)
    return float(payload["price"])


def get_candles(
    symbol: str = "BTC",
    granularity: str = "1d",
    start: str | None = None,
    end: str | None = None,
) -> List[Dict]:
    """Fetch OHLCV candles for ``symbol`` from Coinbase public endpoint.

    Args:
        symbol: Asset symbol (e.g. ``BTC``) or full product id (``BTC-USD``).
        granularity: One of ``1m``, ``5m``, ``15m``, ``1h``, ``6h``, ``1d``.
        start: ISO date (``YYYY-MM-DD``) or ISO timestamp; defaults to 60d ago.
        end: ISO date or timestamp; defaults to now.

    Returns:
        List of ``{"time", "low", "high", "open", "close", "volume"}`` dicts,
        oldest-first. Coinbase caps each request at 300 candles.
    """
    if granularity not in _GRANULARITY_SECONDS:
        raise ValueError(f"Unknown granularity {granularity!r}; valid: {list(_GRANULARITY_SECONDS)}")

    granularity_secs = _GRANULARITY_SECONDS[granularity]
    product = _product_for(symbol)

    if end is None:
        end_dt = _dt.datetime.now(_dt.timezone.utc)
    else:
        end_dt = _parse_when(end)
    if start is None:
        start_dt = end_dt - _dt.timedelta(seconds=granularity_secs * 200)
    else:
        start_dt = _parse_when(start)

    params = {
        "granularity": granularity_secs,
        "start": start_dt.isoformat(),
        "end": end_dt.isoformat(),
    }
    url = f"{_PUBLIC_BASE}/products/{product}/candles"
    cache_key = f"coinbase_candles_{product}_{granularity}_{start_dt.date()}_{end_dt.date()}"

    def _fetch():
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        return r.json()

    raw = cached_json(cache_key, ttl_seconds=300, fetcher=_fetch)

    # Coinbase returns rows of [time, low, high, open, close, volume],
    # newest-first. Flip to oldest-first and tag fields.
    candles = []
    for row in reversed(raw):
        candles.append({
            "time": _dt.datetime.fromtimestamp(int(row[0]), tz=_dt.timezone.utc).isoformat(),
            "low": float(row[1]),
            "high": float(row[2]),
            "open": float(row[3]),
            "close": float(row[4]),
            "volume": float(row[5]),
        })
    return candles


def _parse_when(value: str) -> _dt.datetime:
    if "T" in value:
        return _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    return _dt.datetime.fromisoformat(value).replace(tzinfo=_dt.timezone.utc)


def render_candles_markdown(candles: List[Dict], max_rows: int = 30) -> str:
    """Render the most-recent N candles to a compact markdown table."""
    if not candles:
        return "No candles returned."

    rows = candles[-max_rows:]
    header = "| Time (UTC) | Open | High | Low | Close | Volume |"
    sep = "|---|---:|---:|---:|---:|---:|"
    body = "\n".join(
        f"| {c['time'][:16]} | {c['open']:,.2f} | {c['high']:,.2f} | "
        f"{c['low']:,.2f} | {c['close']:,.2f} | {c['volume']:,.2f} |"
        for c in rows
    )
    return "\n".join([header, sep, body])
