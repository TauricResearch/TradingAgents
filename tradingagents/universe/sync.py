"""Universe reconciliation + watchlist seeding.

``sync_universe`` pulls the broker's tradable assets, upserts them, marks the
ones the broker no longer offers as inactive (the continuous "known vs real"
realignment Luca asked for), and tags S&P 500 constituents from the seed.
``seed_watchlist`` initialises the dynamic working set.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from ..storage import repository as repo
from .sources import Sp500Source


@dataclass
class SyncReport:
    added: list[str] = field(default_factory=list)      # new tradable symbols
    removed: list[str] = field(default_factory=list)    # marked inactive
    total: int = 0                                       # tradable after sync
    sp500: int = 0


def sync_universe(
    session: Session,
    broker: Any,
    *,
    sp500: Optional[Sp500Source] = None,
) -> SyncReport:
    """Reconcile the stored universe with the broker's tradable assets.

    Brokers that can't enumerate their universe (``list_assets() == []``, e.g.
    IBKR) fall back to the S&P 500 seed as the tradable set.
    """
    sp500 = sp500 or Sp500Source()
    constituents = sp500.constituents()  # {symbol: sector}

    assets = []
    try:
        assets = broker.list_assets() if broker is not None else []
    except Exception:
        assets = []

    # Fallback: no broker listing -> the S&P 500 seed IS the tradable universe.
    if not assets:
        assets = [{"symbol": sym, "asset_class": "us_equity", "tradable": True,
                   "sector": sec} for sym, sec in constituents.items()]

    now = datetime.now(timezone.utc)
    known = repo.universe_symbols(session, tradable_only=True, active_only=True)
    incoming = {a["symbol"] for a in assets if a.get("symbol")}

    rows = []
    for a in assets:
        symbol = a.get("symbol")
        if not symbol:
            continue
        rows.append({
            "symbol": symbol,
            "name": a.get("name"),
            "exchange": a.get("exchange"),
            "asset_class": a.get("asset_class"),
            "sector": a.get("sector") or constituents.get(symbol),
            "tradable": True,
            "active": True,
            "is_sp500": symbol in constituents,
            "last_synced_at": now,
        })
    repo.bulk_upsert_instruments(session, rows)

    # Reconcile: anything we knew as tradable but the broker no longer offers.
    removed = sorted(known - incoming)
    repo.mark_instruments_inactive(session, removed)

    return SyncReport(
        added=sorted(incoming - known),
        removed=removed,
        total=len(incoming),
        sp500=sum(1 for r in rows if r["is_sp500"]),
    )


def seed_watchlist(session: Session, *, mode: str = "sp500", max_size: int = 60) -> int:
    """Initialise the watchlist if empty. Returns how many were added.

    - ``sp500``     : S&P 500 constituents that are tradable (∩ universe)
    - ``portfolio`` : symbols currently held
    - ``empty``     : leave empty (grows from screening/news)
    """
    if repo.watchlist_size(session) > 0:
        return 0

    if mode == "empty":
        return 0

    if mode == "portfolio":
        snap = repo.latest_portfolio_snapshot(session)
        symbols = [p.get("symbol") for p in (snap.positions if snap else [])] if snap else []
        symbols = [s for s in symbols if s]
    else:  # sp500 ∩ tradable
        tradable = repo.universe_symbols(session, tradable_only=True, active_only=True)
        sp500 = repo.sp500_symbols(session)
        symbols = sorted(sp500 & tradable) if tradable else sorted(sp500)

    added = 0
    for symbol in symbols[:max_size]:
        repo.set_watchlist(session, symbol, True, reason=f"{mode}_seed")
        added += 1
    return added
