"""Local decision journal linked to immutable research runs.

The journal is intentionally separate from archived reports.  A report captures
the research state at one point in time, while a journal entry records a
personal decision and its later review without changing that report.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .agent_contracts import TradeDirection, TradeHorizon, TradeSignal
from .data_contracts import PriceBar


class DecisionJournalStatus(str, Enum):
    OPEN = "open"
    DUE = "due"
    REVIEWED = "reviewed"


class DecisionJournalReview(BaseModel):
    """A deliberately recorded review of one local investment decision."""

    model_config = ConfigDict(frozen=True)

    reviewed_on: date
    recorded_at: datetime
    review_price: float = Field(gt=0)
    review_price_date: date
    market_return_pct: float
    directional_return_pct: float
    note: str | None = Field(default=None, max_length=4000)


class DecisionJournalEntry(BaseModel):
    """A personal decision snapshot tied to one archived research run."""

    model_config = ConfigDict(frozen=True)

    entry_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    research_run_id: str = Field(min_length=1)
    decision_as_of_date: date
    recorded_at: datetime
    review_due_date: date
    direction: TradeDirection
    horizon: TradeHorizon
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=1)
    proposed_position_pct: float | None = Field(default=None, ge=0.0, le=1.0)
    invalidation_triggers: list[str] = Field(default_factory=list)
    entry_price: float = Field(gt=0)
    entry_price_date: date
    currency: str | None = None
    review: DecisionJournalReview | None = None


class DecisionJournalEntryView(BaseModel):
    """Journal entry plus its current review state for API and cockpit views."""

    model_config = ConfigDict(frozen=True)

    entry: DecisionJournalEntry
    status: DecisionJournalStatus
    latest_available_price: float | None = None
    latest_available_price_date: date | None = None
    market_return_pct: float | None = None
    directional_return_pct: float | None = None


class JsonDecisionJournal:
    """Small JSON persistence boundary for mutable local journal entries."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def list_entries(self, symbol: str | None = None) -> list[DecisionJournalEntry]:
        entries = self._load_entries()
        if symbol is not None:
            normalized_symbol = symbol.strip().upper()
            entries = [entry for entry in entries if entry.symbol == normalized_symbol]
        return sorted(entries, key=lambda entry: (entry.recorded_at, entry.entry_id), reverse=True)

    def get_entry(self, entry_id: str) -> DecisionJournalEntry | None:
        return next((entry for entry in self._load_entries() if entry.entry_id == entry_id), None)

    def find_for_run(self, symbol: str, research_run_id: str) -> DecisionJournalEntry | None:
        normalized_symbol = symbol.strip().upper()
        return next(
            (
                entry
                for entry in self._load_entries()
                if entry.symbol == normalized_symbol and entry.research_run_id == research_run_id
            ),
            None,
        )

    def add_entry(self, entry: DecisionJournalEntry) -> DecisionJournalEntry:
        entries = self._load_entries()
        if any(item.entry_id == entry.entry_id for item in entries):
            raise ValueError("decision journal entry already exists")
        entries.append(entry)
        self._write_entries(entries)
        return entry

    def replace_entry(self, entry: DecisionJournalEntry) -> DecisionJournalEntry:
        entries = self._load_entries()
        for index, item in enumerate(entries):
            if item.entry_id == entry.entry_id:
                entries[index] = entry
                self._write_entries(entries)
                return entry
        raise ValueError("decision journal entry was not found")

    def _load_entries(self) -> list[DecisionJournalEntry]:
        path = self._path()
        if not path.exists():
            return []
        try:
            payload = path.read_text(encoding="utf-8")
            return [DecisionJournalEntry.model_validate(item) for item in json.loads(payload)]
        except (OSError, TypeError, ValueError):
            return []

    def _write_entries(self, entries: Iterable[DecisionJournalEntry]) -> None:
        path = self._path()
        path.parent.mkdir(parents=True, exist_ok=True)
        items = sorted(entries, key=lambda entry: (entry.recorded_at, entry.entry_id))
        payload = json.dumps(
            [entry.model_dump(mode="json") for entry in items], indent=2, ensure_ascii=True
        )
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(payload + "\n", encoding="utf-8")
        tmp_path.replace(path)

    def _path(self) -> Path:
        return self.root / "decision_journal.json"


def create_journal_entry(
    *,
    symbol: str,
    research_run_id: str,
    signal: TradeSignal,
    review_due_date: date,
    price_bars: Iterable[PriceBar],
    recorded_at: datetime | None = None,
) -> DecisionJournalEntry:
    """Snapshot a manual signal using the last price available on its as-of date."""

    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol:
        raise ValueError("symbol is required")
    if signal.symbol.strip().upper() != normalized_symbol:
        raise ValueError("signal symbol does not match journal symbol")
    if review_due_date < signal.as_of_date:
        raise ValueError("review_due_date cannot be before the decision date")

    entry_bar = _latest_available_bar(price_bars, signal.as_of_date)
    if entry_bar is None:
        raise ValueError("no locally available price exists for the decision date")
    recorded = recorded_at or datetime.now(timezone.utc)
    return DecisionJournalEntry(
        entry_id=uuid4().hex,
        symbol=normalized_symbol,
        research_run_id=research_run_id,
        decision_as_of_date=signal.as_of_date,
        recorded_at=recorded,
        review_due_date=review_due_date,
        direction=signal.direction,
        horizon=signal.horizon,
        confidence=signal.confidence,
        rationale=signal.rationale,
        proposed_position_pct=signal.proposed_position_pct,
        invalidation_triggers=signal.invalidation_triggers,
        entry_price=entry_bar.close,
        entry_price_date=entry_bar.date,
        currency=entry_bar.currency,
    )


def review_journal_entry(
    entry: DecisionJournalEntry,
    *,
    reviewed_on: date,
    price_bars: Iterable[PriceBar],
    note: str | None = None,
    recorded_at: datetime | None = None,
) -> DecisionJournalEntry:
    """Record a review using only prices available on the selected review date."""

    if entry.review is not None:
        raise ValueError("decision journal entry has already been reviewed")
    if reviewed_on < entry.decision_as_of_date:
        raise ValueError("reviewed_on cannot be before the decision date")
    review_bar = _latest_available_bar(price_bars, reviewed_on)
    if review_bar is None:
        raise ValueError("no locally available price exists for the review date")
    market_return = review_bar.close / entry.entry_price - 1.0
    directional_return = _directional_return(entry.direction, market_return, entry.entry_price, review_bar.close)
    review = DecisionJournalReview(
        reviewed_on=reviewed_on,
        recorded_at=recorded_at or datetime.now(timezone.utc),
        review_price=review_bar.close,
        review_price_date=review_bar.date,
        market_return_pct=market_return,
        directional_return_pct=directional_return,
        note=note.strip() if note and note.strip() else None,
    )
    return entry.model_copy(update={"review": review})


def build_journal_views(
    entries: Iterable[DecisionJournalEntry],
    *,
    price_bars: Iterable[PriceBar],
    as_of_date: date,
) -> list[DecisionJournalEntryView]:
    """Build current status and indicative local-price returns without mutating entries."""

    bars = list(price_bars)
    return [
        _build_view(entry, bars=bars, as_of_date=as_of_date)
        for entry in sorted(entries, key=lambda item: (item.recorded_at, item.entry_id), reverse=True)
    ]


def _build_view(
    entry: DecisionJournalEntry,
    *,
    bars: list[PriceBar],
    as_of_date: date,
) -> DecisionJournalEntryView:
    if entry.review is not None:
        return DecisionJournalEntryView(entry=entry, status=DecisionJournalStatus.REVIEWED)
    latest_bar = _latest_available_bar(bars, as_of_date)
    if latest_bar is None:
        return DecisionJournalEntryView(entry=entry, status=_entry_status(entry, as_of_date))
    market_return = latest_bar.close / entry.entry_price - 1.0
    directional_return = _directional_return(entry.direction, market_return, entry.entry_price, latest_bar.close)
    return DecisionJournalEntryView(
        entry=entry,
        status=_entry_status(entry, as_of_date),
        latest_available_price=latest_bar.close,
        latest_available_price_date=latest_bar.date,
        market_return_pct=market_return,
        directional_return_pct=directional_return,
    )


def _entry_status(entry: DecisionJournalEntry, as_of_date: date) -> DecisionJournalStatus:
    return DecisionJournalStatus.DUE if as_of_date >= entry.review_due_date else DecisionJournalStatus.OPEN


def _latest_available_bar(price_bars: Iterable[PriceBar], as_of_date: date) -> PriceBar | None:
    candidates = [
        bar
        for bar in price_bars
        if bar.date <= as_of_date and bar.provenance.as_of_date <= as_of_date and bar.close > 0
    ]
    return max(candidates, key=lambda bar: (bar.date, bar.provenance.as_of_date), default=None)


def _directional_return(
    direction: TradeDirection,
    market_return: float,
    entry_price: float,
    review_price: float,
) -> float:
    if direction == TradeDirection.SELL:
        return entry_price / review_price - 1.0
    return market_return
