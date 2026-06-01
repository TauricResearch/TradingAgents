"""SQLite persistence layer for the dashboard."""
from __future__ import annotations

import os
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator, Optional

from sqlmodel import Field, SQLModel, Session, create_engine, select


_engine = None


class Watchlist(SQLModel, table=True):
    __tablename__ = "watchlist"
    ticker: str = Field(primary_key=True)
    company_name: str
    exchange: str
    added_at: datetime
    last_run_id: Optional[int] = None
    last_decision: Optional[str] = None
    last_decision_at: Optional[datetime] = None


class Run(SQLModel, table=True):
    __tablename__ = "run"
    id: Optional[int] = Field(default=None, primary_key=True)
    ticker: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    status: str  # queued | running | done | failed | cancelled
    cancel_requested: bool = False
    decision_action: Optional[str] = None
    decision_target: Optional[float] = None
    decision_rationale: Optional[str] = None
    decision_confidence: Optional[float] = None
    unpersisted: bool = False
    idempotency_key: str = Field(index=True)


class Event(SQLModel, table=True):
    __tablename__ = "event"
    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(index=True)
    ts: datetime
    type: str
    payload_json: str


def _make_engine():
    path = os.environ.get("TRADINGAGENTS_DASHBOARD_DB")
    if not path or path == ":memory:":
        from sqlalchemy.pool import StaticPool
        return create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    return create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})


def get_engine():
    global _engine
    if _engine is None:
        _engine = _make_engine()
    return _engine


def init_db() -> None:
    SQLModel.metadata.create_all(get_engine())


@contextmanager
def get_session() -> Iterator[Session]:
    with Session(get_engine()) as s:
        yield s


class DuplicateTicker(Exception):
    pass


def add_watchlist(row: Watchlist) -> None:
    with get_session() as s:
        existing = s.get(Watchlist, row.ticker)
        if existing is not None:
            raise DuplicateTicker(row.ticker)
        s.add(row)
        s.commit()


def remove_watchlist(ticker: str) -> None:
    with get_session() as s:
        row = s.get(Watchlist, ticker)
        if row is not None:
            s.delete(row)
            s.commit()


def list_watchlist() -> list[Watchlist]:
    with get_session() as s:
        return list(s.exec(select(Watchlist).order_by(Watchlist.added_at)))


def update_watchlist_last_decision(ticker: str, run_id: int, decision_text: str, at: datetime) -> None:
    with get_session() as s:
        row = s.get(Watchlist, ticker)
        if row is None:
            return
        row.last_run_id = run_id
        row.last_decision = decision_text
        row.last_decision_at = at
        s.add(row)
        s.commit()


def create_run(ticker: str, idempotency_key: str) -> int:
    with get_session() as s:
        existing = s.exec(select(Run).where(Run.idempotency_key == idempotency_key, Run.status != "running")).first()
        if existing is not None:
            return existing.id
        row = Run(ticker=ticker, started_at=datetime.now(timezone.utc), status="running", idempotency_key=idempotency_key)
        s.add(row)
        s.commit()
        s.refresh(row)
        return row.id


def get_run(run_id: int) -> Optional[Run]:
    with get_session() as s:
        return s.get(Run, run_id)


def list_runs(limit: int = 20) -> list[Run]:
    with get_session() as s:
        return list(s.exec(select(Run).order_by(Run.started_at.desc()).limit(limit)))


def append_event(run_id: int, type_: str, data: dict) -> int:
    with get_session() as s:
        row = Event(run_id=run_id, ts=datetime.now(timezone.utc), type=type_, payload_json=json.dumps(data))
        s.add(row)
        s.commit()
        s.refresh(row)
        return row.id


def events_for_run(run_id: int, since_id: int = 0) -> list[Event]:
    with get_session() as s:
        return list(s.exec(select(Event).where(Event.run_id == run_id, Event.id > since_id).order_by(Event.id)))


def mark_run_done(run_id: int, *, decision_action: str, decision_target: Optional[float], decision_rationale: str, decision_confidence: float) -> None:
    with get_session() as s:
        row = s.get(Run, run_id)
        if row is None:
            return
        row.status = "done"
        row.finished_at = datetime.now(timezone.utc)
        row.decision_action = decision_action
        row.decision_target = decision_target
        row.decision_rationale = decision_rationale
        row.decision_confidence = decision_confidence
        s.add(row)
        s.commit()


def mark_run_failed(run_id: int, reason: str) -> None:
    with get_session() as s:
        row = s.get(Run, run_id)
        if row is None:
            return
        row.status = "failed"
        row.finished_at = datetime.now(timezone.utc)
        if row.decision_rationale is None:
            row.decision_rationale = f"failed: {reason}"
        s.add(row)
        s.commit()


def request_cancellation(run_id: int) -> None:
    with get_session() as s:
        row = s.get(Run, run_id)
        if row is None:
            return
        row.cancel_requested = True
        s.add(row)
        s.commit()


def reap_stale_runs(timeout_s: int) -> int:
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=timeout_s)
    count = 0
    with get_session() as s:
        stale = list(s.exec(select(Run).where(Run.status == "running", Run.started_at < cutoff)))
        for row in stale:
            row.status = "failed"
            row.finished_at = datetime.now(timezone.utc)
            s.add(row)
            count += 1
        s.commit()
    return count
