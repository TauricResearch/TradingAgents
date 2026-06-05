"""Core enumerations of the trading domain.

The conviction/direction vocabulary is the 5-level enum decided in the wiki
(``rating-scoring``): not a 0-100 score. Leverage (options) is reserved for the
``STRONG_*`` levels only.
"""

from __future__ import annotations

from enum import Enum


class Direction(str, Enum):
    """5-level directional signal, also used for conviction_level."""

    STRONG_BUY = "strong_buy"
    BUY = "buy"
    HOLD = "hold"
    SELL = "sell"
    STRONG_SELL = "strong_sell"

    @property
    def is_long(self) -> bool:
        return self in (Direction.STRONG_BUY, Direction.BUY)

    @property
    def is_short(self) -> bool:
        return self in (Direction.STRONG_SELL, Direction.SELL)

    @property
    def is_actionable(self) -> bool:
        return self is not Direction.HOLD

    @property
    def is_strong(self) -> bool:
        """Strong signals are the only ones allowed to use leverage (options)."""
        return self in (Direction.STRONG_BUY, Direction.STRONG_SELL)


class RiskVerdict(str, Enum):
    """Outcome of the Risk Analyst gate."""

    APPROVED = "approved"
    DECLINED = "declined"
    SEND_BACK = "send_back"
