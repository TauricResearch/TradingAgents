"""Crypto Fear & Greed Index vendor (alternative.me).

Surfaces a market-wide crypto sentiment composite (volatility, momentum,
social volume, dominance, search trends) — a keyless complement to the
ticker-specific news/social sentiment the sentiment analyst already builds.

Uses alternative.me's public Fear & Greed API — no key, no auth.
"""
import datetime as _dt
import logging

import requests

logger = logging.getLogger(__name__)

FNG_API = "https://api.alternative.me/fng/"

# Network timeout (seconds), consistent with the other vendors.
REQUEST_TIMEOUT = 15

DEFAULT_LIMIT = 5


def get_fear_greed_index() -> str:
    """Return the market-wide Crypto Fear & Greed Index.

    0-24 = Extreme Fear (often a contrarian buy zone), 25-49 = Fear,
    50-74 = Greed, 75-100 = Extreme Greed (often a contrarian caution zone).
    This is a whole-market gauge, not ticker-specific.

    Returns:
        A markdown report of the last DEFAULT_LIMIT daily readings.
    """
    try:
        response = requests.get(FNG_API, params={"limit": DEFAULT_LIMIT}, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        rows = response.json().get("data", [])
    except requests.RequestException as e:
        logger.warning("Fear & Greed Index fetch failed: %s", e)
        return f"Fear & Greed Index is currently unavailable ({e})."

    if not rows:
        return "No Fear & Greed Index data returned."

    lines = [
        "### Crypto Fear & Greed Index (alternative.me, market-wide)",
        "",
        "| Date | Value | Classification |",
        "| --- | ---: | --- |",
    ]
    for row in rows:
        date = _dt.datetime.utcfromtimestamp(int(row["timestamp"])).strftime("%Y-%m-%d")
        lines.append(f"| {date} | {row['value']} | {row['value_classification']} |")
    return "\n".join(lines)
