"""
SQLAlchemy 2.x async infrastructure.

Pure infrastructure — no app-specific model imports here. Models live in
app/models.py and import `Base` from this file. Treat this as a
python-temp-pro template file.

Three exports:
- `Base`         — declarative base for ORM models
- `engine`       — process-wide async engine (lazy via getter)
- `get_db`       — FastAPI dependency yielding an AsyncSession

The `_asyncpg_url` helper normalizes Postgres URLs for asyncpg:
- Coerces `postgresql://` and `postgres://` → `postgresql+asyncpg://`
- Strips libpq-only query params (sslmode, channel_binding) that asyncpg
  rejects with a TypeError at connect time
- Translates `sslmode=require` → `connect_args={"ssl": "require"}`

Same helper used by alembic/env.py so migrations and runtime hit the
URL the exact same way.
"""

from __future__ import annotations

from typing import AsyncIterator
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    """Declarative base for all SQLAlchemy models in this service."""


def asyncpg_url(raw: str) -> tuple[str, dict]:
    """
    Normalize a Postgres URL for asyncpg + SQLAlchemy. Returns
    (sqlalchemy_url, connect_args).

    asyncpg doesn't accept libpq-style query params (`sslmode`,
    `channel_binding`) that psycopg2 and Prisma include in their
    connection strings — they trip
    `TypeError: connect() got an unexpected keyword argument 'sslmode'`
    at connect time. We strip them from the URL and translate
    `sslmode=require` → `connect_args={"ssl": "require"}`.
    """
    url = raw
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)

    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query))

    connect_args: dict = {}
    sslmode = query.pop("sslmode", None)
    # channel_binding is a libpq SCRAM option asyncpg handles automatically;
    # asyncpg rejects it as a kwarg, so we just drop it.
    query.pop("channel_binding", None)

    if sslmode in ("require", "verify-ca", "verify-full"):
        connect_args["ssl"] = "require"

    cleaned = parsed._replace(query=urlencode(query))
    return urlunparse(cleaned), connect_args


# ── Engine + sessionmaker ─────────────────────────────────────────────────
# Lazy construction so importing this module doesn't connect on its own —
# tests can override settings before the engine is built.

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Return the process-wide async engine, constructing on first call."""
    global _engine
    if _engine is None:
        url, connect_args = asyncpg_url(settings.DATABASE_URL)
        _engine = create_async_engine(
            url,
            connect_args=connect_args,
            # pool_pre_ping=True guards against stale connections after
            # Neon scales down — pings before each checkout.
            pool_pre_ping=True,
            # Default pool size is fine for a single-replica service.
            # Bump when we shard or scale out.
            pool_size=5,
            max_overflow=10,
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide session factory."""
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _sessionmaker


async def get_db() -> AsyncIterator[AsyncSession]:
    """
    FastAPI dependency yielding a per-request AsyncSession. Commits or
    rolls back automatically based on whether the route handler raised.

    Usage:
        from fastapi import Depends
        from app.db import get_db

        @app.post("/something")
        async def handler(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    """Close the engine's connection pool. Call on app shutdown."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
