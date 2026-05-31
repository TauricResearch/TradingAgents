"""Alternative.me Fear & Greed Index fetcher.

No API key required. Returns current crypto market sentiment on 0-100 scale.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_CACHE: Optional[tuple[float, str]] = None
_CACHE_TTL = 3600  # 1 hour (index updates daily)


def get_fear_greed_index() -> str:
    """Return the current Crypto Fear & Greed Index as a formatted string."""
    global _CACHE
    now = time.time()
    if _CACHE and (now - _CACHE[0]) < _CACHE_TTL:
        return _CACHE[1]

    try:
        resp = requests.get(
            "https://api.alternative.me/fng/?limit=7",
            timeout=10,
            headers={"accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        entries = data.get("data", [])
        if not entries:
            return "Fear & Greed Index: data unavailable."

        current = entries[0]
        value = int(current.get("value", 0))
        classification = current.get("value_classification", "Unknown")

        # Build 7-day trend
        trend_lines = []
        for e in entries[:7]:
            v = e.get("value", "?")
            c = e.get("value_classification", "?")
            trend_lines.append(f"  - {c} ({v})")

        result = (
            f"## Crypto Fear & Greed Index\n\n"
            f"**Current**: {value}/100 — {classification}\n"
            f"**Interpretation**: "
            + (
                "Extreme Fear — potential contrarian buy signal; market may be oversold."
                if value < 25 else
                "Fear — cautious sentiment; watch for reversal signals."
                if value < 45 else
                "Neutral — balanced market sentiment."
                if value < 55 else
                "Greed — positive momentum; watch for overextension."
                if value < 75 else
                "Extreme Greed — market may be overheated; caution advised."
            )
            + "\n\n**7-Day Trend** (most recent first):\n"
            + "\n".join(trend_lines)
        )
        _CACHE = (now, result)
        return result
    except Exception as exc:
        logger.warning("Fear & Greed Index fetch failed: %s", exc)
        return "Fear & Greed Index: data unavailable (network error)."
