"""OHLCV ingestion: fetch bars and write them through to the DB.

DB-first: historical bars are immutable, so we never re-download what we already
have (check-presence). Each bar carries the double date (reference/publication)
to guard against look-ahead bias.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Optional, Protocol, runtime_checkable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..storage import repository as repo
from ..storage.models import PriceBar


def _naive(dt: datetime) -> datetime:
    """Drop tz info so SQLite (tz-naive) and tz-aware bars compare equal."""
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


@dataclass
class IngestResult:
    symbol: str
    inserted: int
    skipped: int

    @property
    def fetched(self) -> int:
        return self.inserted + self.skipped


@runtime_checkable
class PriceFetcher(Protocol):
    """Anything that can return OHLCV bars as a list of plain dicts.

    Each bar must contain at least: ``ts`` (datetime), ``open``, ``high``,
    ``low``, ``close``; optionally ``volume``.
    """

    def fetch(
        self, symbol: str, start: str, end: str, interval: str
    ) -> list[dict[str, Any]]:
        ...


def ingest_price_bars(
    session: Session,
    symbol: str,
    *,
    fetcher: PriceFetcher,
    start: str,
    end: str,
    interval: str = "1d",
    vendor: Optional[str] = None,
    skip_existing: bool = True,
) -> IngestResult:
    """Fetch bars for ``symbol`` and insert the ones not already stored."""
    repo.upsert_instrument(session, symbol)
    bars = fetcher.fetch(symbol, start, end, interval)
    if not bars:
        return IngestResult(symbol, 0, 0)

    fetched = len(bars)
    if skip_existing:
        # Compare on naive (tz-stripped) timestamps: SQLite stores DateTime
        # without tz, so a tz-aware bar ts would never match a stored value.
        stored = session.scalars(
            select(PriceBar.ts).where(
                PriceBar.symbol == symbol,
                PriceBar.interval == interval,
            )
        )
        existing = {_naive(t) for t in stored}
        bars = [b for b in bars if _naive(b["ts"]) not in existing]

    today = datetime.now(timezone.utc).date()
    rows: list[dict[str, Any]] = []
    for b in bars:
        ts: datetime = b["ts"]
        rows.append(
            {
                "ts": ts,
                "interval": interval,
                "open": float(b["open"]),
                "high": float(b["high"]),
                "low": float(b["low"]),
                "close": float(b["close"]),
                "volume": (float(b["volume"]) if b.get("volume") is not None else None),
                "vendor": vendor or b.get("vendor"),
                "reference_date": ts.date() if isinstance(ts, datetime) else None,
                "publication_date": today,
            }
        )

    inserted = repo.insert_price_bars(session, symbol, rows) if rows else 0
    return IngestResult(symbol, inserted, fetched - inserted)


class YFinanceFetcher:
    """Real adapter over yfinance. Network-bound (integration use)."""

    def fetch(
        self, symbol: str, start: str, end: str, interval: str = "1d"
    ) -> list[dict[str, Any]]:
        import yfinance as yf  # local import: keep the package importable offline

        hist = yf.Ticker(symbol.upper()).history(start=start, end=end, interval=interval)
        if hist is None or hist.empty:
            return []
        if hist.index.tz is not None:
            hist.index = hist.index.tz_convert("UTC")
        bars: list[dict[str, Any]] = []
        for idx, row in hist.iterrows():
            ts = idx.to_pydatetime()
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            bars.append(
                {
                    "ts": ts,
                    "open": row["Open"],
                    "high": row["High"],
                    "low": row["Low"],
                    "close": row["Close"],
                    "volume": row.get("Volume"),
                    "vendor": "yfinance",
                }
            )
        return bars
