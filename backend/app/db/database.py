"""
Database configuration and connection management
"""
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL", "")

# Convert postgres:// to postgresql+asyncpg:// for async support
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)


class Base(DeclarativeBase):
    """Base class for all database models"""
    pass


# Create async engine (will be None if no DATABASE_URL)
engine = None
AsyncSessionLocal = None

if DATABASE_URL:
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,  # Set to True for SQL debugging
        pool_pre_ping=True,
        pool_size=20,
        max_overflow=20,
        pool_recycle=3600,
    )
    
    AsyncSessionLocal = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def get_db():
    """Dependency for getting database sessions"""
    if AsyncSessionLocal is None:
        raise RuntimeError("Database not configured")
    
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Initialize database tables"""
    if engine is None:
        print("Warning: DATABASE_URL not configured, skipping database initialization")
        return
    
    async with engine.begin() as conn:
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
        
        # Manual migrations for existing databases
        try:
            # Add language column if it doesn't exist
            await conn.execute(text("ALTER TABLE reports ADD COLUMN IF NOT EXISTS language VARCHAR(10);"))
            # Add indexes to optimize queries
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_reports_user_id ON reports (user_id);"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_reports_created_at ON reports (created_at);"))
            # Add composite index for common query pattern (user_id + created_at DESC)
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_reports_user_created ON reports (user_id, created_at DESC);"))
            # Add index for language filtering
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_reports_language ON reports (language);"))
            # Add composite index for user + market_type + language queries
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_reports_user_market_lang ON reports (user_id, market_type, language);"))
            # Covering index for counts query (GROUP BY market_type with language filter)
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_reports_user_market_lang_count ON reports (user_id, market_type, COALESCE(language, 'zh-TW'));"))
        except Exception as e:
            print(f"Skipping manual migration (might be SQLite or syntax not supported): {e}")
    
    print("Database tables initialized successfully")


async def check_db_connection():
    """Check if database connection is working"""
    if engine is None:
        return False
    
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        print(f"Database connection failed: {e}")
        return False
