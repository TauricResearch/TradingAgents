"""Technical indicators: fetch via stockstats, interpret, return structured signals."""

from __future__ import annotations

import logging
from typing import Any

from tradingagents.indicators.compute import fetch_indicators
from tradingagents.indicators.interpret import interpret_indicators

logger = logging.getLogger(__name__)


def get_indicator_signals(symbol: str, curr_date: str) -> dict[str, dict[str, Any]]:
    """Return structured indicator signals for *symbol* as of *curr_date*.

    Uses the same stockstats pipeline as the get_indicators LLM tool.
    Returns an empty dict on any failure. Never raises.
    """
    try:
        raw = fetch_indicators(symbol, curr_date)
        if not raw:
            return {}
        return interpret_indicators(raw)
    except Exception:
        logger.warning("indicators: failed for %s@%s", symbol, curr_date, exc_info=True)
        return {}
