from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tradingagents_service.db.repository import ShadowRunRepository
from tradingagents_service.db.session import create_session_factory

_session_factory: async_sessionmaker[AsyncSession] | None = None


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = create_session_factory()
    return _session_factory


async def get_db_session() -> AsyncIterator[AsyncSession]:
    session = _get_session_factory()()
    try:
        yield session
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_shadow_run_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AsyncIterator[ShadowRunRepository]:
    yield ShadowRunRepository(session)
