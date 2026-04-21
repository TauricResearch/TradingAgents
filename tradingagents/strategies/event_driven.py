"""Event-Driven strategy signal (§5.1 — Event-Driven / Earnings & Dividend Proximity).

Flags proximity to upcoming earnings or ex-dividend dates as event catalysts.

Reference:
    Kakushadze & Serur, "151 Trading Strategies", §5.1
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .base import BaseStrategy, StrategySignal
from ._data import get_info


class EventDrivenStrategy(BaseStrategy):
    name = "Event-Driven (§5.1)"
    roles = ["fundamentals", "news", "researcher"]

    def compute(self, ticker: str, date: str, context: dict[str, Any] | None = None) -> StrategySignal | None:
        info = get_info(ticker, context)
        if not info:
            return None

        try:
            ref = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return None

        events: list[str] = []
        days_to_event: int | None = None

        # Check earnings date proximity
        for key in ("earningsDate", "nextEarningsDate"):
            raw = info.get(key)
            if raw is None:
                continue
            # yfinance may return a timestamp or list
            if isinstance(raw, (list, tuple)) and raw:
                raw = raw[0]
            try:
                dt = datetime.fromtimestamp(int(raw)) if isinstance(raw, (int, float)) else datetime.strptime(str(raw)[:10], "%Y-%m-%d")
                delta = (dt - ref).days
                if 0 <= delta <= 30:
                    events.append(f"earnings in {delta}d")
                    days_to_event = min(days_to_event, delta) if days_to_event is not None else delta
            except Exception:
                continue

        # Check ex-dividend date
        ex_div = info.get("exDividendDate")
        if ex_div:
            try:
                dt = datetime.fromtimestamp(int(ex_div)) if isinstance(ex_div, (int, float)) else datetime.strptime(str(ex_div)[:10], "%Y-%m-%d")
                delta = (dt - ref).days
                if 0 <= delta <= 30:
                    events.append(f"ex-div in {delta}d")
                    days_to_event = min(days_to_event, delta) if days_to_event is not None else delta
            except Exception:
                pass

        if not events:
            return None

        # Closer event → stronger signal (event risk / catalyst)
        # Neutral direction — events are catalysts, not directional
        proximity = max(0.0, 1.0 - (days_to_event or 30) / 30.0)
        strength = round(proximity * 0.5, 4)  # cap at 0.5 — events are informational

        return StrategySignal(
            name=self.name,
            ticker=ticker,
            date=date,
            signal_strength=strength,
            direction="neutral",
            detail=f"Upcoming: {', '.join(events)}",
        )
