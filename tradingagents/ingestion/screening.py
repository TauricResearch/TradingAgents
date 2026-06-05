"""Deterministic screening (the funnel's Quick Thinker).

No LLM: a cheap, explainable score computed from stored bars. It writes
``ticker_card.screening_score`` so the priority queue can rank tickers and send
only the survivors to the expensive deep dive.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..storage import repository as repo
from ..storage.models import PriceBar, TickerCard


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def compute_screening_signals(bars: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute raw screening signals + a composite score in [0, 1].

    Signals (all deterministic):
    - ``total_return``  : last close / first close - 1 over the window
    - ``avg_range_pct`` : mean (high-low)/close, a cheap volatility proxy
    - ``momentum_ratio``: last close / simple moving average of closes
    - ``range_position``: where the last close sits in the [min low, max high] band
    The composite blends trend (return) and position in range; tune in backtest.
    """
    closes = [float(b["close"]) for b in bars]
    if len(closes) < 2:
        return {"n": len(closes), "score": None}

    highs = [float(b["high"]) for b in bars]
    lows = [float(b["low"]) for b in bars]

    total_return = closes[-1] / closes[0] - 1.0 if closes[0] else 0.0
    avg_range_pct = sum((h - l) / c for h, l, c in zip(highs, lows, closes) if c) / len(closes)
    sma = sum(closes) / len(closes)
    momentum_ratio = closes[-1] / sma if sma else 1.0

    band = max(highs) - min(lows)
    range_position = (closes[-1] - min(lows)) / band if band else 0.5

    score = _clamp01(0.5 * range_position + 0.5 * _clamp01(0.5 + 5.0 * total_return))

    return {
        "n": len(closes),
        "total_return": total_return,
        "avg_range_pct": avg_range_pct,
        "momentum_ratio": momentum_ratio,
        "range_position": range_position,
        "score": score,
    }


def screen_ticker(
    session: Session,
    symbol: str,
    *,
    interval: str = "1d",
    lookback: int = 60,
) -> Optional[TickerCard]:
    """Read the most recent stored bars, score the ticker, update its card."""
    rows = list(
        session.scalars(
            select(PriceBar)
            .where(PriceBar.symbol == symbol, PriceBar.interval == interval)
            .order_by(PriceBar.ts.desc())
            .limit(lookback)
        )
    )
    if not rows:
        return None
    rows.reverse()  # chronological
    bars = [{"high": r.high, "low": r.low, "close": r.close} for r in rows]
    signals = compute_screening_signals(bars)

    return repo.upsert_ticker_card(
        session,
        symbol,
        screening_score=signals.get("score"),
        screening_signals=signals,
        last_screened_at=datetime.now(timezone.utc),
    )
