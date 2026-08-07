"""Binance perpetual futures vendor.

Surfaces derivatives positioning for crypto assets — funding rate and open
interest — that the stock-oriented dataflow layer has no equivalent for.
Complements price/technical data (what happened) with what leveraged traders
are currently positioned for.

Uses Binance's public Futures API (https://fapi.binance.com) — no key, no
auth.
"""
import datetime as _dt
import logging

import requests

logger = logging.getLogger(__name__)

FAPI_BASE = "https://fapi.binance.com/fapi/v1"

# Network timeout (seconds), consistent with the other vendors.
REQUEST_TIMEOUT = 15

# Funding prints every 8h; 6 covers the last 2 days.
DEFAULT_FUNDING_LIMIT = 6


def _request(path: str, params: dict) -> list | dict:
    response = requests.get(f"{FAPI_BASE}/{path}", params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


def _binance_symbol(ticker: str) -> str:
    """``BTC-USD`` / ``BTCUSD`` -> ``BTCUSDT`` (Binance's perpetual quote asset)."""
    base = ticker.upper().replace("-USD", "").replace("USD", "").replace("-USDT", "")
    return f"{base}USDT"


def get_funding_rate(ticker: str) -> str:
    """Return the recent perpetual futures funding rate history for a crypto ticker.

    Funding is paid between longs and shorts every 8 hours to keep the
    perpetual price anchored to spot. Persistently positive rates mean longs
    are paying shorts (crowded/expensive long positioning, a contrarian
    caution signal); persistently negative rates mean the opposite (crowded
    shorts, potential short-squeeze fuel).

    Args:
        ticker: Crypto ticker, e.g. "BTC-USD".

    Returns:
        A markdown report of the last DEFAULT_FUNDING_LIMIT funding prints.
    """
    symbol = _binance_symbol(ticker)
    try:
        rows = _request("fundingRate", {"symbol": symbol, "limit": DEFAULT_FUNDING_LIMIT})
    except requests.RequestException as e:
        logger.warning("Binance funding rate fetch failed for %s: %s", symbol, e)
        return f"Funding rate data is currently unavailable for {symbol} ({e})."

    if not rows:
        return f"No funding rate data returned for {symbol}."

    lines = [
        f"### Perpetual Funding Rate ({symbol}, Binance)",
        "",
        "| Time (UTC) | Funding Rate | Mark Price |",
        "| --- | ---: | ---: |",
    ]
    for row in rows:
        ts = _dt.datetime.utcfromtimestamp(row["fundingTime"] / 1000).strftime("%Y-%m-%d %H:%M")
        rate_pct = float(row["fundingRate"]) * 100
        lines.append(f"| {ts} | {rate_pct:+.4f}% | {float(row['markPrice']):,.2f} |")

    latest = float(rows[-1]["fundingRate"]) * 100
    if latest > 0.02:
        note = (
            "Elevated positive funding: longs are paying a premium — crowded "
            "long positioning, contrarian caution."
        )
    elif latest < -0.02:
        note = "Negative funding: shorts are paying — crowded short positioning, potential squeeze fuel."
    else:
        note = "Funding rate near neutral — no strong positioning skew."
    lines.append("")
    lines.append(f"**Read:** {note}")
    return "\n".join(lines)


def get_open_interest(ticker: str) -> str:
    """Return current perpetual futures open interest for a crypto ticker.

    Rising open interest alongside a rising price usually confirms a trend
    (new money entering); rising OI with a falling price often signals
    aggressive new shorts; falling OI signals position unwinding/deleveraging.

    Args:
        ticker: Crypto ticker, e.g. "BTC-USD".

    Returns:
        A markdown report with current open interest (in base units).
    """
    symbol = _binance_symbol(ticker)
    try:
        data = _request("openInterest", {"symbol": symbol})
    except requests.RequestException as e:
        logger.warning("Binance open interest fetch failed for %s: %s", symbol, e)
        return f"Open interest data is currently unavailable for {symbol} ({e})."

    oi = float(data.get("openInterest", 0))
    return (
        f"### Open Interest ({symbol}, Binance perpetual)\n\n"
        f"**Current open interest:** {oi:,.2f} {symbol.replace('USDT', '')} contracts\n\n"
        "Compare this figure across consecutive calls/days (no built-in history here) "
        "to judge whether OI is expanding (trend confirmation / rising leverage) or "
        "contracting (deleveraging)."
    )
