"""Deterministic trading-session awareness for gold (XAU).

Boundaries are a documented approximation of FX/metals liquidity windows
in UTC (see ADR-0012); they are intentionally simple, timezone-fixed
(no DST shifting), and unit-tested:

    ASIA      22:00-07:00  (Sydney/Tokyo/Singapore/Hong Kong)
    LONDON    07:00-12:00
    NEW_YORK  12:00-21:00  (includes the London/NY overlap)
    CLOSED    21:00-22:00 daily settlement break, plus the weekend
              (Fri 21:00 -> Sun 22:00)

Crypto trades 24/7; callers for BTC simply don't attach a session.
"""

from __future__ import annotations

from datetime import datetime, timezone

from tradingagents.contracts import TradingSession

_FRIDAY, _SATURDAY, _SUNDAY = 4, 5, 6


def current_session(ts: datetime) -> TradingSession:
    """Session for a timezone-aware timestamp; naive input is rejected."""
    if ts.tzinfo is None:
        raise ValueError("naive datetime not allowed; pass a timezone-aware value")
    ts = ts.astimezone(timezone.utc)
    weekday, hour = ts.weekday(), ts.hour

    if weekday == _SATURDAY:
        return TradingSession.CLOSED
    if weekday == _FRIDAY and hour >= 21:
        return TradingSession.CLOSED
    if weekday == _SUNDAY and hour < 22:
        return TradingSession.CLOSED

    if hour >= 22 or hour < 7:
        return TradingSession.ASIA
    if hour < 12:
        return TradingSession.LONDON
    if hour < 21:
        return TradingSession.NEW_YORK
    return TradingSession.CLOSED
