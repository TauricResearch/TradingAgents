# Technical Standards - TradingAgents

## Database Architecture

### Core Stack: PostgreSQL + TimescaleDB + pgvectorscale

**Primary Database**: PostgreSQL 16+ with TimescaleDB and pgvector extensions
- **TimescaleDB**: Optimized for time-series financial data (prices, volumes, news timestamps)
- **pgvector/pgvectorscale**: Vector embeddings for RAG-powered agents
- **Connection**: asyncpg driver for high-performance async operations

**Database URL Pattern**:
```python
# Development
DATABASE_URL = "postgresql+asyncpg://postgres:tradingagents@localhost:5432/tradingagents"

# Production
DATABASE_URL = "postgresql+asyncpg://username:password@host:port/database"
```

**Required Extensions**:
```sql
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
CREATE EXTENSION IF NOT EXISTS vector CASCADE;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
```

### Schema Design Standards

**Time-Series Tables (TimescaleDB)**:
```sql
-- Market data with time-based partitioning
CREATE TABLE market_data (
    id UUID PRIMARY KEY DEFAULT uuid7(),
    symbol VARCHAR(20) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    price DECIMAL(18,8),
    volume BIGINT,
    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Convert to hypertable for time-series optimization
SELECT create_hypertable('market_data', 'timestamp');

-- Indexes for common query patterns
CREATE INDEX ON market_data (symbol, timestamp DESC);
```

**Vector-Enabled Tables**:
```sql
-- News articles with embeddings
CREATE TABLE news_articles (
    id UUID PRIMARY KEY DEFAULT uuid7(),
    headline TEXT NOT NULL,
    url TEXT UNIQUE NOT NULL,  -- Deduplication key
    published_date DATE NOT NULL,
    title_embedding VECTOR(1536),  -- OpenAI embedding size
    content_embedding VECTOR(1536),
    -- TimescaleDB partitioning on published_date
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Vector similarity index
CREATE INDEX ON news_articles USING ivfflat (title_embedding vector_cosine_ops);
```

**Composite Indexes for Query Optimization**:
```sql
-- Common query patterns
CREATE INDEX idx_symbol_date ON news_articles (symbol, published_date);
CREATE INDEX idx_published_date ON news_articles (published_date);
CREATE INDEX idx_url_unique ON news_articles (url);
```

### Connection Management

**Async Session Factory**:
```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

class DatabaseManager:
    def __init__(self, database_url: str, echo: bool = False):
        # Ensure asyncpg driver
        if not database_url.startswith("postgresql+asyncpg://"):
            database_url = database_url.replace("postgresql://", "postgresql+asyncpg://")
        
        self.engine = create_async_engine(
            database_url,
            echo=echo,
            pool_recycle=3600,  # 1-hour connection recycling
            pool_pre_ping=True,  # Connection health checks
        )
        
        self.AsyncSessionLocal = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            autocommit=False,
            autoflush=False,
        )
```

**Session Context Management**:
```python
@asynccontextmanager
async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
    """Type-checker friendly session management"""
    session = self.AsyncSessionLocal()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
```

## LLM Integration Standards

### OpenRouter as Unified Provider

**Configuration**:
```python
# Environment variables
OPENROUTER_API_KEY = "your_openrouter_key"
LLM_PROVIDER = "openrouter"
DEEP_THINK_LLM = "openai/gpt-4o"      # Complex analysis
QUICK_THINK_LLM = "openai/gpt-4o-mini" # Fast responses
BACKEND_URL = "https://openrouter.ai/api/v1"
```

**Model Selection Strategy**:
- **Deep Think**: Complex reasoning, debates, risk analysis (`openai/gpt-4o`, `anthropic/claude-3.5-sonnet`)
- **Quick Think**: Data formatting, simple queries (`openai/gpt-4o-mini`, `anthropic/claude-3-haiku`)

**Cost Optimization**:
```python
# Development/testing configuration
config = TradingAgentsConfig(
    llm_provider="openrouter",
    deep_think_llm="openai/gpt-4o-mini",     # Lower cost
    quick_think_llm="openai/gpt-4o-mini",    # Consistent model
    max_debate_rounds=1,                     # Reduce API calls
    online_tools=False,                      # Use cached data
)
```

### Agent Integration Patterns

**Anti-Corruption Layer**:
```python
class AgentToolkit:
    """Mediates between LLM agents and domain services"""
    
    def __init__(self, config: TradingAgentsConfig):
        self.config = config
        self.services = self._initialize_services()
    
    async def get_news_context(self, symbol: str, date: date) -> dict:
        """Convert domain models to structured LLM context"""
        articles = await self.news_service.get_articles(symbol, date)
        
        return {
            "articles": [article.to_dict() for article in articles],
            "count": len(articles),
            "data_quality": self._assess_data_quality(articles),
            "source_distribution": self._analyze_sources(articles)
        }
```

## Layered Architecture Enforcement

### Standard Layer Pattern

**Data Flow**: `Request → Router → Service → Repository → Entity → Database`

**Component Responsibilities**:

1. **Entity (Domain Model)**:
```python
@dataclass
class NewsArticle:
    """Domain entity with business rules and transformations"""
    
    headline: str
    url: str
    published_date: date
    sentiment_score: float | None = None
    
    def to_entity(self, symbol: str | None = None) -> NewsArticleEntity:
        """Transform to database model"""
        return NewsArticleEntity(
            headline=self.headline,
            url=self.url,
            published_date=self.published_date,
            symbol=symbol
        )
    
    @staticmethod
    def from_entity(entity: NewsArticleEntity) -> 'NewsArticle':
        """Transform from database model"""
        return NewsArticle(
            headline=entity.headline,
            url=entity.url,
            published_date=entity.published_date,
            sentiment_score=entity.sentiment_score
        )
    
    def validate(self) -> list[str]:
        """Business rule validation"""
        errors = []
        if not self.headline.strip():
            errors.append("Headline cannot be empty")
        if not self.url.startswith(("http://", "https://")):
            errors.append("Invalid URL format")
        return errors
```

2. **Repository (Data Access)**:
```python
class NewsRepository:
    """Handles data persistence with async operations"""
    
    def __init__(self, database_manager: DatabaseManager):
        self.db_manager = database_manager
    
    async def list(self, symbol: str, date: date) -> list[NewsArticle]:
        """Query with proper error handling and logging"""
        async with self.db_manager.get_session() as session:
            result = await session.execute(
                select(NewsArticleEntity)
                .filter(and_(
                    NewsArticleEntity.symbol == symbol,
                    NewsArticleEntity.published_date == date
                ))
                .order_by(NewsArticleEntity.published_date.desc())
            )
            entities = result.scalars().all()
            return [NewsArticle.from_entity(e) for e in entities]
    
    async def upsert_batch(self, articles: list[NewsArticle], symbol: str) -> list[NewsArticle]:
        """Bulk operations for performance"""
        if not articles:
            return []
        
        async with self.db_manager.get_session() as session:
            # Use PostgreSQL ON CONFLICT for atomic upserts
            stmt = insert(NewsArticleEntity).values([
                article.to_entity(symbol).__dict__ for article in articles
            ])
            upsert_stmt = stmt.on_conflict_do_update(
                index_elements=["url"],
                set_={k: stmt.excluded[k] for k in stmt.excluded.keys()}
            ).returning(NewsArticleEntity)
            
            result = await session.execute(upsert_stmt)
            entities = result.scalars().all()
            return [NewsArticle.from_entity(e) for e in entities]
```

3. **Service (Business Logic)**:
```python
class NewsService:
    """Orchestrates business operations"""
    
    def __init__(self, repository: NewsRepository, clients: dict):
        self.repository = repository
        self.clients = clients
    
    async def get_articles(self, symbol: str, date: date) -> list[NewsArticle]:
        """Business logic with error handling"""
        try:
            articles = await self.repository.list(symbol, date)
            logger.info(f"Retrieved {len(articles)} articles for {symbol}")
            return articles
        except Exception as e:
            logger.error(f"Failed to get articles for {symbol}: {e}")
            return []  # Graceful degradation
    
    async def update_articles(self, symbol: str, date: date) -> int:
        """Coordinated data refresh"""
        new_articles = await self._fetch_from_sources(symbol, date)
        if new_articles:
            stored = await self.repository.upsert_batch(new_articles, symbol)
            return len(stored)
        return 0
```

### Domain Isolation

**Three Core Domains**:

1. **News Domain** (`tradingagents/domains/news/`)
2. **Market Data Domain** (`tradingagents/domains/marketdata/`)
3. **Social Media Domain** (`tradingagents/domains/socialmedia/`)

**Domain Boundary Rules**:
- Domains communicate through service interfaces only
- No direct database access between domains
- Shared types in `tradingagents/types/`
- Domain events for loose coupling

## Vector Integration and RAG Patterns

### Vector Embedding Storage

**OpenAI Embeddings (1536 dimensions)**:
```python
# Entity definition
class NewsArticleEntity(Base):
    title_embedding: Mapped[list[float] | None] = mapped_column(
        Vector(1536), nullable=True
    )
    content_embedding: Mapped[list[float] | None] = mapped_column(
        Vector(1536), nullable=True
    )

# Similarity search
async def find_similar_articles(self, query_embedding: list[float], limit: int = 10) -> list[NewsArticle]:
    async with self.db_manager.get_session() as session:
        result = await session.execute(
            select(NewsArticleEntity)
            .order_by(NewsArticleEntity.title_embedding.cosine_distance(query_embedding))
            .limit(limit)
        )
        return [NewsArticle.from_entity(e) for e in result.scalars()]
```

### RAG Context Assembly

**Agent Context Pattern**:
```python
async def build_agent_context(self, symbol: str, date: date) -> dict:
    """Assemble multi-source context for agents"""
    
    # Recent news with embeddings
    news_articles = await self.news_service.get_articles(symbol, date)
    
    # Market data
    market_data = await self.market_service.get_recent_data(symbol, days=30)
    
    # Social sentiment
    social_data = await self.social_service.get_sentiment(symbol, date)
    
    return {
        "news": {
            "articles": [a.to_dict() for a in news_articles],
            "sentiment_avg": sum(a.sentiment_score or 0 for a in news_articles) / len(news_articles),
            "sources": list({a.source for a in news_articles})
        },
        "market": {
            "current_price": market_data.current_price,
            "volatility": market_data.volatility_30d,
            "volume_trend": market_data.volume_trend
        },
        "social": {
            "reddit_sentiment": social_data.reddit_score,
            "twitter_mentions": social_data.twitter_mentions
        },
        "context_quality": self._assess_context_quality(news_articles, market_data, social_data)
    }
```

## Migration and Deployment Standards

### Database Migrations

**Alembic Configuration**:
```python
# alembic/env.py
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from tradingagents.lib.database import Base

def run_async_migrations():
    config = context.config
    database_url = config.get_main_option("sqlalchemy.url")
    
    # Ensure asyncpg driver
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://")
    
    engine = create_async_engine(database_url)
    
    async def do_run_migrations():
        async with engine.begin() as connection:
            await connection.run_sync(do_run_migrations_sync)
    
    asyncio.run(do_run_migrations())
```

**TimescaleDB-Specific Migrations**:
```python
"""Add TimescaleDB hypertable

Revision ID: 001
"""

def upgrade():
    # Create table first
    op.create_table(
        'market_data',
        sa.Column('id', postgresql.UUID(), nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('timestamp', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('price', sa.Numeric(18, 8)),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Convert to hypertable
    op.execute("SELECT create_hypertable('market_data', 'timestamp');")
    
    # Add indexes
    op.create_index('idx_market_symbol_time', 'market_data', ['symbol', 'timestamp'])
```

### Docker Configuration

**Development Environment**:
```yaml
# docker-compose.yml
services:
  timescaledb:
    build: ./db
    container_name: tradingagents_timescaledb
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: tradingagents
      POSTGRES_DB: tradingagents
    ports:
      - "5432:5432"
    volumes:
      - ./seed.sql:/docker-entrypoint-initdb.d/seed.sql
      - timescale_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d tradingagents"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### Environment Configuration

**Required Environment Variables**:
```bash
# Database
DATABASE_URL=postgresql+asyncpg://postgres:tradingagents@localhost:5432/tradingagents

# OpenRouter LLM
OPENROUTER_API_KEY=your_openrouter_key
LLM_PROVIDER=openrouter
DEEP_THINK_LLM=openai/gpt-4o
QUICK_THINK_LLM=openai/gpt-4o-mini
BACKEND_URL=https://openrouter.ai/api/v1

# Application
TRADINGAGENTS_RESULTS_DIR=./results
TRADINGAGENTS_DATA_DIR=./data
DEFAULT_LOOKBACK_DAYS=30
ONLINE_TOOLS=true

# Performance
MAX_DEBATE_ROUNDS=1
MAX_RISK_DISCUSS_ROUNDS=1
```

## Quality Gates

### Database Performance

**Query Performance Standards**:
- Simple queries: < 100ms
- Complex aggregations: < 500ms
- Vector similarity searches: < 1s
- Batch operations: < 5s for 1000 records

**Monitoring Queries**:
```sql
-- Query performance monitoring
SELECT query, mean_exec_time, calls, total_exec_time
FROM pg_stat_statements
WHERE mean_exec_time > 100
ORDER BY mean_exec_time DESC;

-- TimescaleDB chunk information
SELECT * FROM chunk_relation_size('market_data');
```

### Connection Health

**Health Check Implementation**:
```python
async def health_check() -> dict:
    """Comprehensive system health check"""
    checks = {}
    
    # Database connectivity
    try:
        async with db_manager.get_session() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = {"status": "healthy", "latency_ms": None}
    except Exception as e:
        checks["database"] = {"status": "unhealthy", "error": str(e)}
    
    # OpenRouter API
    try:
        # Test API connection
        checks["llm_api"] = {"status": "healthy"}
    except Exception as e:
        checks["llm_api"] = {"status": "unhealthy", "error": str(e)}
    
    return checks
```

### Data Quality Enforcement

**Validation Pipeline**:
```python
class DataQualityValidator:
    """Ensures data meets quality standards before storage"""
    
    def validate_news_article(self, article: NewsArticle) -> list[str]:
        errors = []
        
        # Business rules
        if not article.headline.strip():
            errors.append("Empty headline")
        
        if len(article.headline) > 500:
            errors.append("Headline too long")
        
        if article.sentiment_score and not (-1 <= article.sentiment_score <= 1):
            errors.append("Invalid sentiment score range")
        
        # Data freshness
        if article.published_date > date.today():
            errors.append("Future publication date")
        
        return errors
```

This technical standards document provides the foundation for maintaining consistency across the TradingAgents codebase while ensuring optimal performance for financial data processing and AI agent operations.