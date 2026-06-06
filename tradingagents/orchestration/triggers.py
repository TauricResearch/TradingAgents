"""Trigger Engine: centralise every reason the system wakes up.

All sources (due checkpoints, screening candidates, price alerts, calendar,
news) are normalised into a single ``TriggerEvent`` and de-duplicated. The cycle
runner consumes the resulting ordered list — a single queue, not five pollers.

For the alpha this implements the two DB-backed sources we already store:
due ``next_check_date`` checkpoints and top screening scores. Price-alert and
calendar sources slot in here later behind the same ``TriggerEvent`` shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..indicators import core as ind_core
from ..indicators.db import recent_bars
from ..storage.models import Instrument, TickerCard


@dataclass(frozen=True)
class TriggerEvent:
    type: str          # "checkpoint" | "screening" | "price_alert" | "calendar" | "news"
    symbol: str
    reason: str
    priority: float = 0.0
    payload: dict[str, Any] = field(default_factory=dict, compare=False)


def due_checkpoints(session: Session, *, today: Optional[date] = None) -> list[TriggerEvent]:
    """Tickers whose Dynamic Temporal Checkpoint (next_check_date) is due."""
    today = today or date.today()
    cards = session.scalars(
        select(TickerCard).where(
            TickerCard.next_check_date.is_not(None),
            TickerCard.next_check_date <= today,
        )
    )
    return [
        TriggerEvent("checkpoint", c.symbol, f"next_check_date {c.next_check_date} due",
                     priority=1.0, payload={"next_check_date": str(c.next_check_date)})
        for c in cards
    ]


def screening_candidates(session: Session, *, top_k: int = 5) -> list[TriggerEvent]:
    """Highest screening scores (the funnel's origination source)."""
    cards = session.scalars(
        select(TickerCard)
        .where(TickerCard.screening_score.is_not(None))
        .order_by(TickerCard.screening_score.desc())
        .limit(top_k)
    )
    return [
        TriggerEvent("screening", c.symbol, f"screening_score {c.screening_score:.3f}",
                     priority=float(c.screening_score or 0.0),
                     payload={"screening_score": c.screening_score})
        for c in cards
    ]


def price_alerts(
    session: Session, *, threshold_atr: float = 1.5, lookback: int = 20
) -> list[TriggerEvent]:
    """Anomalous price moves (efficient-markets alert): |last move| > k·ATR.

    A price that jumps more than ``threshold_atr`` ATRs since the previous bar
    is the signal that something happened — the system wakes to find out why.
    """
    events: list[TriggerEvent] = []
    for symbol in session.scalars(select(Instrument.symbol)):
        bars = recent_bars(session, symbol, lookback=lookback)
        if len(bars) < 16:  # need enough bars for ATR(14) + a prior close
            continue
        atr = ind_core.atr(bars, 14)
        if not atr:
            continue
        move = bars[-1]["close"] - bars[-2]["close"]
        if abs(move) > threshold_atr * atr:
            mult = abs(move) / atr
            events.append(
                TriggerEvent(
                    "price_alert", symbol, f"move {move:+.2f} = {mult:.1f}x ATR",
                    priority=0.9, payload={"move": move, "atr": atr, "atr_mult": mult},
                )
            )
    return events


def collect_triggers(
    session: Session, *, top_k: int = 5, today: Optional[date] = None
) -> list[TriggerEvent]:
    """Gather all sources, de-dup by symbol (keep highest priority), sort desc.

    Precedence for the same symbol: checkpoint (1.0) > price_alert (0.9) >
    screening (its score). An open position due for review or an anomalous move
    matters more than a fresh screening candidate.
    """
    events = (
        due_checkpoints(session, today=today)
        + price_alerts(session)
        + screening_candidates(session, top_k=top_k)
    )
    best: dict[str, TriggerEvent] = {}
    for ev in events:
        cur = best.get(ev.symbol)
        if cur is None or ev.priority > cur.priority:
            best[ev.symbol] = ev
    return sorted(best.values(), key=lambda e: e.priority, reverse=True)
