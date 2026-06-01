from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import get_settings

settings = get_settings()

engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_all_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _migrate_add_columns(conn)


async def _migrate_add_columns(conn):
    """Safely add new columns to existing tables (idempotent)."""
    new_columns = [
        ("app_settings", "backend_url",               "VARCHAR(500)"),
        ("app_settings", "openai_reasoning_effort",   "VARCHAR(20)"),
        ("app_settings", "anthropic_effort",          "VARCHAR(20)"),
        ("app_settings", "google_thinking_level",     "VARCHAR(20)"),
        ("app_settings", "output_language",           "VARCHAR(50) DEFAULT 'English'"),
        ("app_settings", "analyst_concurrency_limit", "INTEGER DEFAULT 1"),
    ]
    from sqlalchemy import text
    for table, column, col_type in new_columns:
        await conn.execute(text(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type}"
        ))
