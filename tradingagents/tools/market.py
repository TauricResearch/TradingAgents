"""Market data tools: real-time-first quote (write-through) + volume spike."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from ..indicators import core
from ..indicators.db import recent_bars
from ..storage import repository as repo


def get_realtime_quote(
    session: Session,
    symbol: str,
    *,
    live_fn: Optional[Callable[[str], Optional[float]]] = None,
) -> Optional[float]:
    """Current price, **real-time first** with write-through to the DB.

    If a live source is available, use it and persist a copy (so the DB stays
    the single source of truth); otherwise fall back to the latest stored bar.
    """
    if live_fn is not None:
        price = live_fn(symbol)
        if price is not None:
            now = datetime.now(timezone.utc)
            # write-through: keep real-time ticks on a separate interval so they
            # never pollute the daily OHLCV history.
            repo.insert_price_bars(session, symbol, [{
                "ts": now, "interval": "rt",
                "open": price, "high": price, "low": price, "close": price,
                "vendor": "realtime", "reference_date": now.date(), "publication_date": now.date(),
            }])
            return price
    bar = repo.latest_price(session, symbol)
    return bar.close if bar is not None else None


def volume_spike(
    session: Session, symbol: str, *, window: int = 20, z_threshold: float = 2.0
) -> dict[str, Any]:
    """Detect an abnormal volume spike on the latest bar (rolling z-score)."""
    bars = recent_bars(session, symbol, lookback=window + 1)
    vols = [float(b["volume"]) for b in bars if b.get("volume") is not None]
    if len(vols) < window:
        return {"spike": False, "z": None}
    sample = vols[-window:]
    mean = sum(sample) / window
    var = sum((v - mean) ** 2 for v in sample) / window
    std = var ** 0.5
    last = vols[-1]
    z = (last - mean) / std if std > 0 else 0.0
    return {"spike": z >= z_threshold, "z": z, "mean": mean, "last": last}
