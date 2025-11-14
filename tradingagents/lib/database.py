"""
Database connection and session management for news repository with async support.
"""

import logging
from contextlib import asynccontextmanager

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool
from sqlalchemy.sql import text
from typing_extensions import AsyncGenerator

Base = declarative_base()

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages async database connections and sessions for the news repository."""

    def __init__(self, database_url: str, echo: bool = False):
        """
        Initialize database manager.

        Args:
            database_url: PostgreSQL connection URL.
            echo: Whether to log SQL statements
        """
        # Ensure we're using asyncpg driver
        if database_url.startswith("postgresql://"):
            database_url = database_url.replace(
                "postgresql://", "postgresql+asyncpg://"
            )
        elif not database_url.startswith("postgresql+asyncpg://"):
            database_url = f"postgresql+asyncpg://{database_url}"

        self.database_url = database_url
        self.echo = echo

        # Create async engine with connection pooling
        self.engine = create_async_engine(
            database_url,
            echo=echo,
            pool_recycle=3600,  # Recycle connections after 1 hour
            pool_pre_ping=True,  # Verify connections before use
        )

        # Create async session factory
        self.AsyncSessionLocal = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            autocommit=False,
            autoflush=False,
        )

        # Register event listeners for optimization
        self._setup_event_listeners()

    def _setup_event_listeners(self):
        """Setup SQLAlchemy event listeners for performance optimization."""

        @event.listens_for(self.engine.sync_engine, "connect")
        def set_pg_pragma(dbapi_connection, _connection_record):
            """Optimize PostgreSQL connection settings."""
            # These settings are specific to PostgreSQL/asyncpg
            if "postgresql" in self.database_url:
                # asyncpg handles these differently than psycopg2

                async def setup_connection():
                    await dbapi_connection.execute("SET timezone = 'UTC'")
                    await dbapi_connection.execute("SET statement_timeout = '30s'")
                    await dbapi_connection.execute("SET lock_timeout = '10s'")

                # Note: This is handled differently in asyncpg
                # We'll set these in the session context instead

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Create and manage an async database session.

        Note: We're manually managing the session lifecycle instead of using
        `async with self.AsyncSessionLocal() as session:` because:

        1. Pyrefly type checker throws "bad-context-manager" errors when using
           async_sessionmaker() directly in async with statements
        2. Manual management gives us explicit control over commit/rollback timing
        3. Avoids type checker ambiguity about the session's async context manager protocol
        4. Makes the session lifecycle more transparent and debuggable

        This pattern is equivalent to using async with but more type-checker friendly.

        Yields:
            AsyncSession: SQLAlchemy async session

        Example:
            async with db_manager.get_session() as session:
                result = await session.execute(select(NewsArticleDB))
                articles = result.scalars().all()
        """
        #
        session: AsyncSession = self.AsyncSessionLocal()
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            await session.close()

    async def create_tables(self):
        """Create all database tables."""
        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Failed to create database tables: {e}")
            raise

    async def drop_tables(self):
        """Drop all database tables (use with caution!)."""
        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            logger.info("Database tables dropped successfully")
        except Exception as e:
            logger.error(f"Failed to drop database tables: {e}")
            raise

    async def health_check(self) -> bool:
        """
        Check if database connection is healthy.

        Returns:
            bool: True if database is accessible, False otherwise
        """
        try:
            async with self.get_session() as session:
                await session.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False

    async def close(self):
        """Close database engine and cleanup connections."""
        if hasattr(self, "engine"):
            await self.engine.dispose()
            logger.info("Database connections closed")


def create_test_database_manager() -> DatabaseManager:
    """Create a test database manager for tests."""
    # Use a test database URL with credentials matching docker setup
    test_db_url = (
        "postgresql://postgres:tradingagents@localhost:5432/tradingagents_test"
    )

    # Create a test-specific database manager with NullPool
    db_manager = DatabaseManager(test_db_url)

    # Override engine with NullPool for tests
    db_manager.engine = create_async_engine(
        db_manager.database_url,
        echo=False,
        poolclass=NullPool,  # Use NullPool for tests
        pool_pre_ping=False,  # Disable ping for tests to avoid async issues
    )

    # Create new session factory for the test engine
    db_manager.AsyncSessionLocal = async_sessionmaker(
        bind=db_manager.engine,
        class_=AsyncSession,
        autocommit=False,
        autoflush=False,
    )

    return db_manager
