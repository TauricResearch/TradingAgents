"""SQLite persistence layer for the dashboard."""
from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime
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
