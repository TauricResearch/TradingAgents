# -*- coding: utf-8 -*-
"""CNN Fear & Greed Index fetching via alternative.me public API (no auth required)."""

import logging
import requests
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_URL = "https://api.alternative.me/fng/"
_TIMEOUT = 10


def get_fear_greed(days: int = 7) -> str:
    """
    Fetch the CNN Fear & Greed Index time series from alternative.me.

    Returns one entry per day with a numeric score (0–100) and classification
    label (Extreme Fear / Fear / Neutral / Greed / Extreme Greed). This is a
    market-wide macro signal — not ticker-specific.

    Args:
        days: Number of past days to fetch (default 7)

    Returns:
        Formatted string of daily entries, or empty string on API failure.
    """
    try:
        r = requests.get(_URL, params={"limit": days}, timeout=_TIMEOUT)
    except requests.RequestException as e:
        logger.warning("Fear & Greed API request failed: %s", e)
        return ""

    if not r.ok:
        logger.warning("Fear & Greed API returned HTTP %s", r.status_code)
        return ""

    r.encoding = "utf-8"
    try:
        data = r.json().get("data", [])
    except ValueError:
        logger.warning("Fear & Greed API returned invalid JSON")
        return ""

    if not data:
        return ""

    lines = [f"CNN Fear & Greed Index (last {days} days, most recent first):\n"]
    for entry in data:
        ts = int(entry.get("timestamp", 0))
        date = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        score = entry.get("value", "?")
        label = entry.get("value_classification", "?")
        lines.append(f"{date} | Score: {score}/100 | {label}")

    return "\n".join(lines)
