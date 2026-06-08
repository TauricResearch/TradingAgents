"""Engine, session and schema bootstrap for the persistence layer.

Connection string resolution (first match wins):
1. explicit ``url`` argument
2. ``TRADINGAGENTS_DATABASE_URL`` env var
3. ``DATABASE_URL`` env var
4. local SQLite file at ``~/.tradingagents/trading_agent.db``

SQLite needs no setup and is perfect for the alpha. Point the env var at a
PostgreSQL/TimescaleDB instance for production; ``init_db`` will promote the
``price_bars`` table to a hypertable when the dialect is PostgreSQL.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Declarative base shared by every model."""


_DEFAULT_HOME = Path(os.path.expanduser("~")) / ".tradingagents"

_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker] = None


def resolve_url(url: Optional[str] = None) -> str:
    """Resolve the database URL using the documented precedence."""
    if url:
        return url
    env = os.environ.get("TRADINGAGENTS_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if env:
        return env
    _DEFAULT_HOME.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{_DEFAULT_HOME / 'trading_agent.db'}"


def get_engine(url: Optional[str] = None) -> Engine:
    """Return a process-wide cached engine (created on first use)."""
    global _engine, _SessionLocal
    if _engine is None or url is not None:
        resolved = resolve_url(url)
        # SQLite: allow cross-thread use (parallel evaluators) + wait on locks
        # instead of erroring immediately, since the fan-out writes concurrently.
        connect_args = (
            {"check_same_thread": False, "timeout": 30}
            if resolved.startswith("sqlite") else {}
        )
        _engine = create_engine(resolved, future=True, connect_args=connect_args)
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _engine


def _session_factory() -> sessionmaker:
    if _SessionLocal is None:
        get_engine()
    assert _SessionLocal is not None
    return _SessionLocal


@contextmanager
def get_session() -> Iterator[Session]:
    """Transactional session scope: commit on success, rollback on error."""
    session = _session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(url: Optional[str] = None, *, create_hypertable: bool = True) -> Engine:
    """Create all tables. On PostgreSQL, promote price_bars to a hypertable."""
    engine = get_engine(url)
    # Import models so they register on Base.metadata before create_all.
    from . import models  # noqa: F401

    Base.metadata.create_all(engine)

    if create_hypertable and engine.dialect.name == "postgresql":
        _try_create_hypertable(engine)
    return engine


def _try_create_hypertable(engine: Engine) -> None:
    """Best-effort TimescaleDB hypertable creation (no-op if extension absent)."""
    with engine.begin() as conn:
        try:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))
            conn.execute(
                text(
                    "SELECT create_hypertable('price_bars', 'ts', "
                    "if_not_exists => TRUE, migrate_data => TRUE)"
                )
            )
        except Exception:
            # TimescaleDB not installed: keep price_bars as a plain table.
            pass


def reset_engine() -> None:
    """Drop the cached engine/sessionmaker (used by tests for isolation)."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
