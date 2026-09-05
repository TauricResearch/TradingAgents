"""Filesystem artifact store for normalized research-platform records."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from datetime import date
from pathlib import Path
from typing import Protocol, TypeVar

from pydantic import BaseModel

from tradingagents.dataflows.utils import safe_ticker_component

from .agent_contracts import AgentOutputEnvelope
from .data_contracts import FundamentalSnapshot, NewsItem, PriceBar

RecordT = TypeVar("RecordT", bound=BaseModel)


class ArtifactStore(Protocol):
    """Storage interface for normalized research artifacts."""

    def save_price_bars(self, records: Sequence[PriceBar]) -> None:
        """Persist normalized price bars."""

    def load_price_bars(
        self,
        symbol: str,
        start: date,
        end: date,
        *,
        as_of_date: date | None = None,
    ) -> list[PriceBar]:
        """Load price bars in a date range, optionally constrained by availability."""

    def save_fundamentals(self, records: Sequence[FundamentalSnapshot]) -> None:
        """Persist normalized fundamental snapshots."""

    def load_fundamentals(
        self,
        symbol: str,
        *,
        as_of_date: date | None = None,
    ) -> list[FundamentalSnapshot]:
        """Load fundamental snapshots for a symbol."""

    def save_news(self, records: Sequence[NewsItem]) -> None:
        """Persist normalized news items."""

    def load_news(
        self,
        symbol: str,
        start: date,
        end: date,
        *,
        as_of_date: date | None = None,
    ) -> list[NewsItem]:
        """Load news items in a date range, optionally constrained by availability."""

    def save_agent_outputs(self, records: Sequence[AgentOutputEnvelope]) -> None:
        """Persist structured agent outputs."""

    def load_agent_outputs(
        self,
        symbol: str,
        *,
        as_of_date: date | None = None,
    ) -> list[AgentOutputEnvelope]:
        """Load structured agent outputs for a symbol."""


class JsonArtifactStore:
    """Simple JSONL store for normalized records.

    This is intentionally small and local-first. It gives the rest of the
    platform a stable cache boundary before introducing SQLite, DuckDB, or
    Parquet-backed storage.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def save_price_bars(self, records: Sequence[PriceBar]) -> None:
        self._save_grouped(records, "prices", lambda r: r.symbol, _price_key)

    def load_price_bars(
        self,
        symbol: str,
        start: date,
        end: date,
        *,
        as_of_date: date | None = None,
    ) -> list[PriceBar]:
        records = self._load("prices", symbol, PriceBar)
        eligible = [
            record
            for record in records
            if start <= record.date <= end
            and (as_of_date is None or record.provenance.as_of_date <= as_of_date)
        ]
        return _latest_price_versions(eligible)

    def save_fundamentals(self, records: Sequence[FundamentalSnapshot]) -> None:
        self._save_grouped(records, "fundamentals", lambda r: r.symbol, _fundamental_key)

    def load_fundamentals(
        self,
        symbol: str,
        *,
        as_of_date: date | None = None,
    ) -> list[FundamentalSnapshot]:
        records = self._load("fundamentals", symbol, FundamentalSnapshot)
        return [
            record
            for record in records
            if as_of_date is None or record.provenance.as_of_date <= as_of_date
        ]

    def save_news(self, records: Sequence[NewsItem]) -> None:
        keyed_records = [record for record in records if record.symbol]
        self._save_grouped(keyed_records, "news", lambda r: r.symbol or "", _news_key)

    def load_news(
        self,
        symbol: str,
        start: date,
        end: date,
        *,
        as_of_date: date | None = None,
    ) -> list[NewsItem]:
        records = self._load("news", symbol, NewsItem)
        return [
            record
            for record in records
            if start <= record.published_at.date() <= end
            and (as_of_date is None or record.as_of_date <= as_of_date)
        ]

    def save_agent_outputs(self, records: Sequence[AgentOutputEnvelope]) -> None:
        self._save_grouped(records, "agent_outputs", lambda r: r.symbol, _agent_output_key)

    def load_agent_outputs(
        self,
        symbol: str,
        *,
        as_of_date: date | None = None,
    ) -> list[AgentOutputEnvelope]:
        records = self._load("agent_outputs", symbol, AgentOutputEnvelope)
        return [
            record for record in records if as_of_date is None or record.as_of_date <= as_of_date
        ]

    def _save_grouped(
        self,
        records: Sequence[RecordT],
        kind: str,
        symbol_getter: Callable[[RecordT], str],
        key_getter: Callable[[RecordT], str],
    ) -> None:
        grouped: dict[str, list[RecordT]] = {}
        for record in records:
            grouped.setdefault(symbol_getter(record), []).append(record)

        for symbol, group in grouped.items():
            path = self._path(kind, symbol)
            existing = self._load_path(path, type(group[0]))
            merged = {key_getter(record): record for record in existing}
            merged.update({key_getter(record): record for record in group})
            self._write_path(path, [merged[key] for key in sorted(merged)])

    def _load(self, kind: str, symbol: str, model: type[RecordT]) -> list[RecordT]:
        return self._load_path(self._path(kind, symbol), model)

    def _load_path(self, path: Path, model: type[RecordT]) -> list[RecordT]:
        if not path.exists():
            return []
        records: list[RecordT] = []

        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(model.model_validate_json(line))
        return records

    def _write_path(self, path: Path, records: Iterable[BaseModel]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(
            "\n".join(record.model_dump_json() for record in records) + "\n",
            encoding="utf-8",
        )
        tmp.replace(path)

    def _path(self, kind: str, symbol: str) -> Path:
        safe_symbol = safe_ticker_component(symbol)
        return self.root / kind / f"{safe_symbol}.jsonl"


def _latest_price_versions(records: Sequence[PriceBar]) -> list[PriceBar]:
    selected: dict[date, PriceBar] = {}
    for record in records:
        current = selected.get(record.date)
        candidate_rank = (
            record.adjusted_close is not None,
            record.provenance.as_of_date,
            record.provenance.retrieved_at,
        )
        current_rank = (
            (
                current.adjusted_close is not None,
                current.provenance.as_of_date,
                current.provenance.retrieved_at,
            )
            if current is not None
            else None
        )
        if current_rank is None or candidate_rank > current_rank:
            selected[record.date] = record
    return [selected[day] for day in sorted(selected)]


def _price_key(record: PriceBar) -> str:
    return "|".join(
        [
            record.date.isoformat(),
            record.provenance.as_of_date.isoformat(),
            record.provenance.provider,
        ]
    )


def _fundamental_key(record: FundamentalSnapshot) -> str:
    return "|".join(
        [
            record.period_end.isoformat(),
            record.fiscal_period or "",
            record.provenance.as_of_date.isoformat(),
            record.provenance.provider,
        ]
    )


def _news_key(record: NewsItem) -> str:
    if record.source_id:
        return record.source_id
    return "|".join(
        [
            record.published_at.isoformat(),
            record.provider,
            record.title,
            record.url or "",
        ]
    )


def _agent_output_key(record: AgentOutputEnvelope) -> str:
    return "|".join(
        [
            record.as_of_date.isoformat(),
            record.agent_id,
            record.output_type.value,
        ]
    )
