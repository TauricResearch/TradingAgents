"""Small local watchlist store for the personal research cockpit."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WatchlistEntry(BaseModel):
    """One ticker explicitly followed by the local user."""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1)
    added_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    name: str | None = None
    sectors: list[str] = Field(default_factory=list)
    source: str = "manual"

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol is required")
        return normalized

    @field_validator("sectors")
    @classmethod
    def _normalize_sectors(cls, values: list[str]) -> list[str]:
        return sorted({value.strip().lower() for value in values if value.strip()})


class JsonWatchlistStore:
    """Local JSON watchlist colocated with a research artifact cache."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def list_entries(self) -> list[WatchlistEntry]:
        if not self.path.exists():
            return []
        try:
            entries = [WatchlistEntry.model_validate(item) for item in self._read_payload()]
        except (OSError, ValueError):
            return []
        return sorted(entries, key=lambda entry: entry.symbol)

    def add(
        self,
        symbol: str,
        *,
        name: str | None = None,
        sectors: list[str] | None = None,
        source: str = "manual",
    ) -> WatchlistEntry:
        entry = WatchlistEntry(symbol=symbol, name=name, sectors=sectors or [], source=source)
        entries = {item.symbol: item for item in self.list_entries()}
        existing = entries.get(entry.symbol)
        if existing is None:
            entries[entry.symbol] = entry
        else:
            entries[entry.symbol] = existing.model_copy(
                update={
                    "name": entry.name or existing.name,
                    "sectors": sorted(set(existing.sectors) | set(entry.sectors)),
                    "source": existing.source if existing.source == "manual" else entry.source,
                }
            )
        self._write(list(entries.values()))
        return entries[entry.symbol]

    def add_many(self, entries: list[WatchlistEntry]) -> list[WatchlistEntry]:
        """Merge discovery results without deleting existing followed stocks."""

        merged = {item.symbol: item for item in self.list_entries()}
        for entry in entries:
            existing = merged.get(entry.symbol)
            if existing is None:
                merged[entry.symbol] = entry
                continue
            merged[entry.symbol] = existing.model_copy(
                update={
                    "name": entry.name or existing.name,
                    "sectors": sorted(set(existing.sectors) | set(entry.sectors)),
                    "source": existing.source if existing.source == "manual" else entry.source,
                }
            )
        values = sorted(merged.values(), key=lambda item: item.symbol)
        self._write(values)
        return values

    def remove(self, symbol: str) -> bool:
        normalized = WatchlistEntry(symbol=symbol).symbol
        entries = self.list_entries()
        kept = [entry for entry in entries if entry.symbol != normalized]
        if len(kept) == len(entries):
            return False
        self._write(kept)
        return True

    @property
    def path(self) -> Path:
        return self.root / "watchlist.json"

    def _read_payload(self) -> list[object]:
        payload = self.path.read_text(encoding="utf-8")
        from json import loads

        parsed = loads(payload)
        if not isinstance(parsed, list):
            raise ValueError("watchlist payload must be a list")
        return parsed

    def _write(self, entries: list[WatchlistEntry]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = "[\n" + ",\n".join(entry.model_dump_json(indent=2) for entry in entries) + "\n]\n"
        self.path.write_text(payload, encoding="utf-8")
