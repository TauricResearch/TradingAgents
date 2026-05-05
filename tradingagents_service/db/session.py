import os
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import AsyncIterator, Optional

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

DEFAULT_DATABASE_URL = "postgresql+psycopg://tradingagents:tradingagents@localhost:5432/tradingagents"


def get_database_url(explicit_url: Optional[str] = None) -> str:
    if explicit_url:
        return explicit_url
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


@lru_cache(maxsize=8)
def _cached_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(
        database_url,
        future=True,
        pool_pre_ping=True,
        pool_size=int(os.getenv("TRADINGAGENTS_DB_POOL_SIZE", "2")),
        max_overflow=int(os.getenv("TRADINGAGENTS_DB_MAX_OVERFLOW", "2")),
    )


def get_engine(database_url: Optional[str] = None) -> AsyncEngine:
    return _cached_engine(get_database_url(database_url))


def create_session_factory(database_url: Optional[str] = None) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=get_engine(database_url), class_=AsyncSession, expire_on_commit=False)


@asynccontextmanager
async def session_scope(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    session = factory()
    try:
        yield session
    finally:
        await session.close()
