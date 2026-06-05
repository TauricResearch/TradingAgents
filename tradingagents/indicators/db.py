"""DB-backed indicator helpers: read stored bars, return ready values.

These connect the indicator math to the persistence layer so the Technical desk
(and the deterministic risk engine) can ask for, e.g., the current ATR of a
ticker without handling raw bars.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..storage.models import PriceBar
from . import core


def recent_bars(
    session: Session, symbol: str, *, interval: str = "1d", lookback: int = 260
) -> list[dict[str, Any]]:
    """Return up to ``lookback`` most recent bars, chronological (oldest first)."""
    rows = list(
        session.scalars(
            select(PriceBar)
            .where(PriceBar.symbol == symbol, PriceBar.interval == interval)
            .order_by(PriceBar.ts.desc())
            .limit(lookback)
        )
    )
    rows.reverse()
    return [
        {"ts": r.ts, "open": r.open, "high": r.high, "low": r.low,
         "close": r.close, "volume": r.volume}
        for r in rows
    ]


def atr_from_db(
    session: Session, symbol: str, *, period: int = 14, interval: str = "1d"
) -> Optional[float]:
    bars = recent_bars(session, symbol, interval=interval, lookback=period + 1)
    return core.atr(bars, period)


def indicator_snapshot(
    session: Session, symbol: str, *, interval: str = "1d", lookback: int = 260
) -> dict[str, Any]:
    """A compact bundle of indicators the Technical desk uses."""
    bars = recent_bars(session, symbol, interval=interval, lookback=lookback)
    closes = [b["close"] for b in bars]
    return {
        "symbol": symbol,
        "n_bars": len(bars),
        "last_close": closes[-1] if closes else None,
        "atr_14": core.atr(bars, 14),
        "rsi_14": core.rsi(closes, 14),
        "sma_50": core.sma(closes, 50),
        "sma_200": core.sma(closes, 200),
        "max_drawdown": core.max_drawdown(closes) if closes else None,
        "range_52w": core.high_low_52w(bars),
    }
