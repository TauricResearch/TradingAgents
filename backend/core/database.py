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
    # NOTE: These migrations are outside Alembic. After adding new entries here,
    # run `alembic revision --autogenerate` to keep migration history in sync.
    _ALLOWED = {
        "app_settings", "analysis_results", "portfolios", "orders",
        "holdings", "multi_ticker_analyses",
    }
    new_columns = [
        ("app_settings", "backend_url",                "VARCHAR(500)"),
        ("app_settings", "openai_reasoning_effort",    "VARCHAR(20)"),
        ("app_settings", "anthropic_effort",           "VARCHAR(20)"),
        ("app_settings", "google_thinking_level",      "VARCHAR(20)"),
        ("app_settings", "output_language",            "VARCHAR(50) DEFAULT 'English'"),
        ("app_settings", "analyst_concurrency_limit",  "INTEGER DEFAULT 1"),
        ("app_settings", "checkpoint_enabled",         "BOOLEAN DEFAULT FALSE"),
        ("app_settings", "max_recur_limit",            "INTEGER DEFAULT 1000"),
        ("app_settings", "news_article_limit",         "INTEGER DEFAULT 20"),
        ("app_settings", "global_news_article_limit",  "INTEGER DEFAULT 10"),
        ("app_settings", "global_news_lookback_days",  "INTEGER DEFAULT 7"),
        ("app_settings", "benchmark_ticker",           "VARCHAR(20)"),
        ("app_settings", "azure_deployment",           "VARCHAR(100)"),
        ("app_settings", "data_vendor_core_stock",     "VARCHAR(50) DEFAULT 'yfinance'"),
        ("app_settings", "data_vendor_technicals",     "VARCHAR(50) DEFAULT 'yfinance'"),
        ("app_settings", "data_vendor_fundamentals",   "VARCHAR(50) DEFAULT 'yfinance'"),
        ("app_settings", "data_vendor_news",           "VARCHAR(50) DEFAULT 'yfinance'"),
        # Phase 1B: debate history
        ("analysis_results", "bull_history",                "TEXT DEFAULT ''"),
        ("analysis_results", "bear_history",                "TEXT DEFAULT ''"),
        ("analysis_results", "investment_debate_history",   "TEXT DEFAULT ''"),
        ("analysis_results", "risk_debate_history",         "TEXT DEFAULT ''"),
        ("analysis_results", "judge_decision",              "TEXT DEFAULT ''"),
    ]
    from sqlalchemy import text
    for table, column, col_type in new_columns:
        if table not in _ALLOWED:
            raise ValueError(f"Unknown table in migration: {table!r}")
        await conn.execute(text(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type}"
        ))
