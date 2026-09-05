"""Persist game-opportunity snapshots and derive explainable change events."""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from tradingagents.dataflows.utils import safe_ticker_component

from .artifact_store import JsonArtifactStore
from .game_opportunity import (
    GameOpportunitySnapshot,
    build_game_opportunity_board,
)


class GameOpportunityEventType(str, Enum):
    BASELINE_CREATED = "baseline_created"
    LEVEL_CHANGED = "level_changed"
    SCORE_CHANGED = "score_changed"
    FACTOR_CHANGED = "factor_changed"
    NEW_APPROVAL = "new_approval"


class GameOpportunityEventSeverity(str, Enum):
    INFO = "info"
    NOTABLE = "notable"


class GameOpportunityEvent(BaseModel):
    """One deterministic difference between two persisted radar snapshots."""

    model_config = ConfigDict(frozen=True)

    event_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    as_of_date: date
    event_type: GameOpportunityEventType
    severity: GameOpportunityEventSeverity
    title: str = Field(min_length=1)
    detail: str = Field(min_length=1)
    factor_id: str | None = None
    previous_value: str | int | float | None = None
    current_value: str | int | float | None = None


class GameOpportunityTrackingResult(BaseModel):
    """Persisted snapshot plus events emitted by that observation."""

    model_config = ConfigDict(frozen=True)

    snapshot: GameOpportunitySnapshot
    previous_as_of_date: date | None = None
    events: list[GameOpportunityEvent] = Field(default_factory=list)


class GameOpportunityTrackingBatch(BaseModel):
    """One local universe observation run."""

    model_config = ConfigDict(frozen=True)

    as_of_date: date
    recorded_at: datetime
    results: list[GameOpportunityTrackingResult] = Field(default_factory=list)
    event_count: int = Field(default=0, ge=0)


class GameOpportunityHistoryView(BaseModel):
    """Recent snapshots and events for cockpit/API rendering."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    snapshots: list[GameOpportunitySnapshot] = Field(default_factory=list)
    latest_events: list[GameOpportunityEvent] = Field(default_factory=list)

class JsonGameOpportunityHistory:
    """Atomic per-symbol JSONL history with one snapshot per calendar date."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def save(self, snapshot: GameOpportunitySnapshot) -> None:
        records = {item.as_of_date: item for item in self.list(snapshot.symbol)}
        records[snapshot.as_of_date] = snapshot
        path = self._path(snapshot.symbol)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".jsonl.tmp")
        temporary.write_text(
            "".join(records[key].model_dump_json() + "\n" for key in sorted(records)),
            encoding="utf-8",
        )
        temporary.replace(path)

    def list(
        self,
        symbol: str,
        *,
        end: date | None = None,
        limit: int | None = None,
    ) -> list[GameOpportunitySnapshot]:
        path = self._path(symbol)
        if not path.exists():
            return []
        records = [
            GameOpportunitySnapshot.model_validate_json(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if end is not None:
            records = [item for item in records if item.as_of_date <= end]
        records.sort(key=lambda item: item.as_of_date, reverse=True)
        return records[:limit] if limit is not None else records

    def latest(
        self,
        symbol: str,
        *,
        end: date | None = None,
    ) -> GameOpportunitySnapshot | None:
        records = self.list(symbol, end=end, limit=1)
        return records[0] if records else None

    def _path(self, symbol: str) -> Path:
        return self.root / "game_opportunity_history" / f"{safe_ticker_component(symbol)}.jsonl"


def compare_game_opportunities(
    previous: GameOpportunitySnapshot | None,
    current: GameOpportunitySnapshot,
) -> list[GameOpportunityEvent]:
    """Return deterministic, user-facing changes from previous to current."""

    if previous is None:
        return [
            _event(
                current,
                GameOpportunityEventType.BASELINE_CREATED,
                GameOpportunityEventSeverity.INFO,
                "Opportunity baseline created",
                f"Initial attention level is {current.level.value} at {current.score}/{current.max_score}.",
                current_value=current.score,
            )
        ]
    events: list[GameOpportunityEvent] = []
    if previous.level != current.level:
        events.append(
            _event(
                current,
                GameOpportunityEventType.LEVEL_CHANGED,
                GameOpportunityEventSeverity.NOTABLE,
                "Attention level changed",
                f"Level moved from {previous.level.value} to {current.level.value}.",
                previous_value=previous.level.value,
                current_value=current.level.value,
            )
        )
    if previous.score != current.score:
        events.append(
            _event(
                current,
                GameOpportunityEventType.SCORE_CHANGED,
                GameOpportunityEventSeverity.NOTABLE,
                "Opportunity score changed",
                f"Score moved from {previous.score} to {current.score}.",
                previous_value=previous.score,
                current_value=current.score,
            )
        )

    previous_factors = {item.factor_id: item for item in previous.factors}
    for factor in current.factors:
        old = previous_factors.get(factor.factor_id)
        if old is None:
            continue
        if old.score != factor.score:
            events.append(
                _event(
                    current,
                    GameOpportunityEventType.FACTOR_CHANGED,
                    GameOpportunityEventSeverity.INFO,
                    f"{factor.label} factor changed",
                    f"{factor.label} moved from {old.score}/{old.max_score} to "
                    f"{factor.score}/{factor.max_score}.",
                    factor_id=factor.factor_id,
                    previous_value=old.score,
                    current_value=factor.score,
                )
            )
        if factor.factor_id == "approvals":
            old_count = _metric_int(old.metrics.get("approvals_365d"))
            new_count = _metric_int(factor.metrics.get("approvals_365d"))
            if new_count > old_count:
                events.append(
                    _event(
                        current,
                        GameOpportunityEventType.NEW_APPROVAL,
                        GameOpportunityEventSeverity.NOTABLE,
                        "New company-linked approval detected",
                        f"Exact approvals in the 365-day window increased from "
                        f"{old_count} to {new_count}.",
                        factor_id="approvals",
                        previous_value=old_count,
                        current_value=new_count,
                    )
                )
    return events


def record_game_opportunity_board(
    store: JsonArtifactStore,
    *,
    as_of_date: date | None = None,
    recorded_at: datetime | None = None,
) -> GameOpportunityTrackingBatch:
    """Build, compare, and persist the current covered-universe radar."""

    reference_date = as_of_date or date.today()
    recorded = recorded_at or datetime.now(timezone.utc)
    history = JsonGameOpportunityHistory(store.root)
    results: list[GameOpportunityTrackingResult] = []
    for snapshot in build_game_opportunity_board(store, as_of_date=reference_date):
        previous = history.latest(snapshot.symbol, end=reference_date)
        events = compare_game_opportunities(previous, snapshot)
        history.save(snapshot)
        results.append(
            GameOpportunityTrackingResult(
                snapshot=snapshot,
                previous_as_of_date=(previous.as_of_date if previous is not None else None),
                events=events,
            )
        )
    return GameOpportunityTrackingBatch(
        as_of_date=reference_date,
        recorded_at=recorded,
        results=results,
        event_count=sum(len(item.events) for item in results),
    )


def build_game_opportunity_history_view(
    history: JsonGameOpportunityHistory,
    symbol: str,
    *,
    limit: int = 30,
) -> GameOpportunityHistoryView:
    """Return recent snapshots and the latest deterministic comparison."""

    normalized_symbol = symbol.strip().upper()
    snapshots = history.list(normalized_symbol, limit=limit)
    if not snapshots:
        events: list[GameOpportunityEvent] = []
    elif len(snapshots) == 1:
        events = compare_game_opportunities(None, snapshots[0])
    else:
        events = compare_game_opportunities(snapshots[1], snapshots[0])
    return GameOpportunityHistoryView(
        symbol=normalized_symbol,
        snapshots=snapshots,
        latest_events=events,
    )

def _event(
    snapshot: GameOpportunitySnapshot,
    event_type: GameOpportunityEventType,
    severity: GameOpportunityEventSeverity,
    title: str,
    detail: str,
    *,
    factor_id: str | None = None,
    previous_value: str | int | float | None = None,
    current_value: str | int | float | None = None,
) -> GameOpportunityEvent:
    fingerprint = "|".join(
        (
            snapshot.symbol,
            snapshot.as_of_date.isoformat(),
            event_type.value,
            factor_id or "",
            str(previous_value),
            str(current_value),
        )
    )
    event_id = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:24]
    return GameOpportunityEvent(
        event_id=event_id,
        symbol=snapshot.symbol,
        as_of_date=snapshot.as_of_date,
        event_type=event_type,
        severity=severity,
        title=title,
        detail=detail,
        factor_id=factor_id,
        previous_value=previous_value,
        current_value=current_value,
    )


def _metric_int(value: object) -> int:
    return int(value) if isinstance(value, (int, float)) else 0
