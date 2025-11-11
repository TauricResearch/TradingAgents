# Style Guide - TradingAgents

## Python Code Style

### Formatting with Ruff

**Configuration** (pyproject.toml):
```toml
[tool.ruff]
target-version = "py313"
line-length = 88
fix = true
extend-exclude = [
    "migrations/",
    "alembic/versions/",
    ".env",
    "venv/",
    ".venv/",
]

[tool.ruff.lint]
select = [
    "E",     # pycodestyle errors
    "W",     # pycodestyle warnings
    "F",     # Pyflakes
    "I",     # isort
    "B",     # flake8-bugbear
    "C4",    # flake8-comprehensions
    "UP",    # pyupgrade
    "ERA",   # eradicate
    "PIE",   # flake8-pie
    "SIM",   # flake8-simplify
    "TCH",   # flake8-type-checking
    "ARG",   # flake8-unused-arguments
    "PTH",   # flake8-use-pathlib
    "FIX",   # flake8-fixme
    "TD",    # flake8-todos
]

ignore = [
    "E501",  # Line too long (handled by formatter)
    "B008",  # Do not perform function calls in argument defaults
    "B904",  # Use `raise ... from ...` for exception chaining
    "TD002", # Missing author in TODO
    "TD003", # Missing issue link on line following TODO
    "FIX002", # Line contains TODO
]

[tool.ruff.lint.per-file-ignores]
"tests/**/*.py" = [
    "S101",    # Use of assert detected
    "ARG001",  # Unused function argument
    "FBT001",  # Boolean positional arg
    "PLR2004", # Magic value used in comparison
]

"migrations/**/*.py" = [
    "ERA001",  # Found commented-out code
]

[tool.ruff.lint.isort]
known-first-party = ["tradingagents"]
force-sort-within-sections = true
```

### Type Hints and Annotations

**Modern Type Syntax** (Python 3.13):
```python
# Use built-in generics (no typing.List, typing.Dict)
def process_articles(articles: list[NewsArticle]) -> dict[str, int]:
    """Process articles and return symbol counts"""
    counts: dict[str, int] = {}
    for article in articles:
        symbol = article.symbol or "UNKNOWN"
        counts[symbol] = counts.get(symbol, 0) + 1
    return counts

# Union types with |
def get_article(article_id: str | int) -> NewsArticle | None:
    """Get article by ID (string or integer)"""
    if isinstance(article_id, str):
        return get_by_url(article_id)
    return get_by_id(article_id)

# Optional with explicit None
def calculate_sentiment(text: str, model: str | None = None) -> float | None:
    """Calculate sentiment score"""
    if not text.strip():
        return None
    # Implementation
    return 0.5
```

**Type Annotations for Complex Types**:
```python
from typing import TypeVar, Generic, Protocol, TypedDict, Awaitable
from collections.abc import Callable, AsyncGenerator
from datetime import date, datetime

# Type variables
T = TypeVar('T')
ArticleT = TypeVar('ArticleT', bound='NewsArticle')

# Protocol for type checking
class Repository(Protocol[T]):
    async def list(self, symbol: str, date: date) -> list[T]:
        ...
    
    async def upsert(self, item: T) -> T:
        ...

# TypedDict for structured data
class ArticleData(TypedDict):
    headline: str
    url: str
    published_date: str
    sentiment_score: float | None

# Callable types
ProcessorFunc = Callable[[list[NewsArticle]], Awaitable[dict[str, int]]]
```

### Docstring Standards

**Google Style Docstrings**:
```python
class NewsRepository:
    """Repository for news article data access with PostgreSQL backend.
    
    Handles CRUD operations for news articles with support for batch operations,
    vector similarity search, and TimescaleDB time-series optimization.
    
    Attributes:
        db_manager: AsyncIO database connection manager
        
    Example:
        >>> db_manager = DatabaseManager("postgresql://...")
        >>> repo = NewsRepository(db_manager)
        >>> articles = await repo.list("AAPL", date(2024, 1, 15))
    """
    
    def __init__(self, database_manager: DatabaseManager) -> None:
        """Initialize repository with database connection.
        
        Args:
            database_manager: Async database connection manager with 
                PostgreSQL + TimescaleDB + pgvector support.
        """
        self.db_manager = database_manager
    
    async def upsert_batch(
        self, 
        articles: list[NewsArticle], 
        symbol: str,
        *,
        chunk_size: int = 1000
    ) -> list[NewsArticle]:
        """Batch insert or update articles with deduplication.
        
        Uses PostgreSQL ON CONFLICT for atomic upserts based on URL uniqueness.
        Processes articles in chunks to optimize memory usage for large datasets.
        
        Args:
            articles: News articles to store
            symbol: Stock symbol to associate with articles
            chunk_size: Number of articles to process per database transaction.
                Defaults to 1000 for optimal PostgreSQL performance.
        
        Returns:
            List of stored articles with database-generated metadata
            
        Raises:
            IntegrityError: If URL constraint violations occur
            DatabaseConnectionError: If database is unavailable
            
        Example:
            >>> articles = [NewsArticle("Title", "https://...", ...)]
            >>> stored = await repo.upsert_batch(articles, "AAPL")
            >>> assert len(stored) == len(articles)
        """
        if not articles:
            return []
        
        # Implementation...
```

**Module-Level Docstrings**:
```python
"""
News repository with PostgreSQL + TimescaleDB backend.

This module provides data access patterns for financial news articles with
support for:
- Time-series queries optimized by TimescaleDB
- Vector similarity search using pgvector
- Bulk operations with PostgreSQL-specific optimizations
- Async/await patterns for high-performance I/O

Example Usage:
    from tradingagents.domains.news.news_repository import NewsRepository
    from tradingagents.lib.database import DatabaseManager
    
    db = DatabaseManager("postgresql+asyncpg://...")
    repo = NewsRepository(db)
    
    # Get articles for a symbol and date
    articles = await repo.list("AAPL", date(2024, 1, 15))
    
    # Batch store new articles
    new_articles = [...]
    stored = await repo.upsert_batch(new_articles, "AAPL")
"""

from __future__ import annotations
```

### Variable and Function Naming

**Snake Case for Everything**:
```python
# Variables
article_count = len(articles)
sentiment_threshold = 0.5
openrouter_api_key = os.getenv("OPENROUTER_API_KEY")

# Functions
def calculate_portfolio_risk(positions: list[Position]) -> float:
    """Calculate portfolio-wide risk metrics"""
    
async def fetch_news_articles(symbol: str, date: date) -> list[NewsArticle]:
    """Fetch news articles from external APIs"""

# Private methods
def _validate_sentiment_score(score: float | None) -> bool:
    """Internal validation for sentiment scores"""

# Constants
MAX_ARTICLES_PER_REQUEST = 100
DEFAULT_LOOKBACK_DAYS = 30
OPENAI_EMBEDDING_DIMENSIONS = 1536
```

**Descriptive Names Over Short Names**:
```python
# Good - Clear intent
async def update_articles_for_symbol(symbol: str, target_date: date) -> int:
    successful_count = 0
    failed_count = 0
    
    for news_source in self.configured_sources:
        try:
            articles = await news_source.fetch(symbol, target_date)
            stored_articles = await self.repository.upsert_batch(articles, symbol)
            successful_count += len(stored_articles)
        except Exception as e:
            failed_count += 1
            logger.warning(f"Failed to fetch from {news_source.name}: {e}")
    
    return successful_count

# Avoid - Unclear abbreviations
async def upd_arts(sym: str, dt: date) -> int:
    cnt = 0
    for src in self.srcs:
        arts = await src.get(sym, dt)
        cnt += len(arts)
    return cnt
```

### Import Organization

**Import Order with isort**:
```python
# 1. Standard library imports
import asyncio
import logging
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

# 2. Third-party imports  
import aiohttp
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
import pytest

# 3. First-party imports
from tradingagents.config import TradingAgentsConfig
from tradingagents.domains.news.news_repository import NewsArticle, NewsRepository
from tradingagents.lib.database import DatabaseManager

# 4. Relative imports (avoid when possible)
from .google_news_client import GoogleNewsClient
```

**Import Aliases**:
```python
# Standard aliases for common packages
import pandas as pd
import numpy as np
from datetime import datetime as dt, date

# Avoid long module paths
from tradingagents.domains.news.news_repository import (
    NewsArticle,
    NewsRepository, 
    NewsArticleEntity
)

# Type-only imports for forward references
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from tradingagents.agents.trading_agent import TradingAgent
```

## Database Naming Conventions

### Table Names

**Snake Case with Domain Prefix**:
```sql
-- Domain-prefixed tables
news_articles           -- Core news data
news_article_embeddings -- Vector embeddings (if separate)

market_data_daily       -- Daily market prices  
market_data_intraday    -- Intraday tick data

social_media_posts      -- Social media content
social_sentiment_scores -- Sentiment analysis results

-- Agent-specific tables
agent_decisions         -- Trading decisions
agent_portfolios        -- Portfolio states
agent_memories          -- RAG memory store
```

### Column Names

**Descriptive Snake Case**:
```sql
-- Good - Clear and consistent
CREATE TABLE news_articles (
    id UUID PRIMARY KEY DEFAULT uuid7(),
    headline TEXT NOT NULL,
    url TEXT UNIQUE NOT NULL,
    published_date DATE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Foreign key relationships
    symbol VARCHAR(20) REFERENCES stocks(symbol),
    source_id UUID REFERENCES news_sources(id),
    
    -- Metrics and scores
    sentiment_score DECIMAL(3,2) CHECK (sentiment_score BETWEEN -1 AND 1),
    readability_score INTEGER CHECK (readability_score BETWEEN 0 AND 100),
    
    -- Vector embeddings
    title_embedding VECTOR(1536),
    content_embedding VECTOR(1536)
);

-- Avoid - Unclear abbreviations
CREATE TABLE art (
    id UUID,
    ttl TEXT,    -- title? 
    dt DATE,     -- published_date?
    scr DECIMAL, -- score? source? 
    emb VECTOR(1536)  -- embedding?
);
```

### Index Names

**Descriptive with Purpose**:
```sql
-- Pattern: idx_{table}_{columns}_{purpose}
CREATE INDEX idx_news_articles_symbol_date_lookup 
ON news_articles (symbol, published_date);

CREATE INDEX idx_news_articles_published_date_timeseries 
ON news_articles (published_date DESC);

CREATE INDEX idx_news_articles_url_unique 
ON news_articles (url);

-- Vector indexes with algorithm
CREATE INDEX idx_news_articles_title_embedding_cosine 
ON news_articles USING ivfflat (title_embedding vector_cosine_ops);

-- Partial indexes for specific queries
CREATE INDEX idx_news_articles_recent_high_sentiment 
ON news_articles (published_date, sentiment_score) 
WHERE published_date > CURRENT_DATE - INTERVAL '30 days' 
AND sentiment_score > 0.5;
```

## API Design Patterns

### RESTful URL Structure

**Resource-Based URLs**:
```python
# Good - Resource-oriented
GET    /api/v1/symbols/AAPL/articles?date=2024-01-15     # Get articles
POST   /api/v1/symbols/AAPL/articles                     # Create articles  
PUT    /api/v1/articles/{article_id}                     # Update article
DELETE /api/v1/articles/{article_id}                     # Delete article

GET    /api/v1/symbols/AAPL/market-data?start=2024-01-01&end=2024-01-31
POST   /api/v1/trading/decisions                         # Create trading decision
GET    /api/v1/agents/portfolios/{portfolio_id}          # Get portfolio state

# Avoid - Action-oriented
POST /api/v1/getArticles                                 # Should be GET
POST /api/v1/updateSymbolData                            # Should be PUT  
GET  /api/v1/performTradingAnalysis                      # Should be POST
```

**Query Parameter Standards**:
```python
from datetime import date
from pydantic import BaseModel, Field, validator

class ArticleQueryParams(BaseModel):
    """Query parameters for article endpoints"""
    
    # Date filtering
    date: date | None = None
    start_date: date | None = Field(None, alias="start")
    end_date: date | None = Field(None, alias="end")
    
    # Pagination
    limit: int = Field(default=50, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)
    
    # Filtering
    sources: list[str] | None = Field(None, description="Filter by news sources")
    min_sentiment: float | None = Field(None, ge=-1.0, le=1.0)
    max_sentiment: float | None = Field(None, ge=-1.0, le=1.0)
    
    # Search
    query: str | None = Field(None, max_length=200)
    
    @validator('end_date')
    def end_date_after_start(cls, v, values):
        if v and values.get('start_date') and v < values['start_date']:
            raise ValueError('end_date must be after start_date')
        return v
```

### Response Formats

**Consistent JSON Structure**:
```python
from typing import Generic, TypeVar
from pydantic import BaseModel

T = TypeVar('T')

class APIResponse(BaseModel, Generic[T]):
    """Standard API response wrapper"""
    
    data: T | None = None
    success: bool = True
    message: str | None = None
    errors: list[str] = []
    
    # Metadata
    request_id: str | None = None
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

class PaginatedResponse(APIResponse[list[T]]):
    """Paginated response with metadata"""
    
    pagination: dict[str, int] = Field(default_factory=dict)
    
    @classmethod
    def create(
        cls, 
        data: list[T], 
        total: int, 
        limit: int, 
        offset: int
    ) -> 'PaginatedResponse[T]':
        return cls(
            data=data,
            pagination={
                "total": total,
                "limit": limit, 
                "offset": offset,
                "has_more": offset + len(data) < total
            }
        )

# Usage example
@app.get("/api/v1/symbols/{symbol}/articles")
async def get_articles(
    symbol: str,
    params: ArticleQueryParams = Depends(),
    db: AsyncSession = Depends(get_db_session)
) -> PaginatedResponse[ArticleData]:
    """Get news articles for a symbol"""
    
    # Query implementation
    articles, total = await article_service.get_paginated(
        symbol=symbol,
        limit=params.limit,
        offset=params.offset,
        date_filter=params.date
    )
    
    return PaginatedResponse.create(
        data=[ArticleData.from_entity(a) for a in articles],
        total=total,
        limit=params.limit,
        offset=params.offset
    )
```

## Documentation Standards

### Code Comments

**When to Comment**:
```python
class NewsRepository:
    async def upsert_batch(self, articles: list[NewsArticle], symbol: str) -> list[NewsArticle]:
        # Don't comment obvious code
        if not articles:
            return []
        
        # DO comment complex business logic
        # Use PostgreSQL ON CONFLICT for atomic upsert operations.
        # This prevents race conditions when multiple processes
        # are updating the same articles simultaneously.
        stmt = insert(NewsArticleEntity).values(entity_data_list)
        upsert_stmt = stmt.on_conflict_do_update(
            index_elements=["url"],  # Deduplication key
            set_={
                # Update all fields except ID and created_at
                **{col: stmt.excluded[col] for col in updateable_columns},
                "updated_at": func.now(),
            },
        )
        
        # DO comment performance optimizations
        # Batch size of 1000 optimizes PostgreSQL memory usage
        # while avoiding transaction timeout for large datasets
        for chunk in chunks(entity_data_list, 1000):
            result = await session.execute(upsert_stmt)
```

**TODO Comments**:
```python
# TODO(martin): Implement caching layer for frequently accessed articles
# TODO(martin): Add vector similarity search for related articles
# FIXME(martin): Handle edge case where published_date is in future
# HACK(martin): Temporary workaround for API rate limiting - remove after v2.0
```

### README Structure

**Repository README.md Template**:
```markdown
# TradingAgents - Multi-Agent Financial Analysis

Brief description of what the project does and why it exists.

## Quick Start

```bash
# 1. Setup environment
export OPENROUTER_API_KEY="your_key"
mise run docker    # Start PostgreSQL

# 2. Install and run
mise run install
mise run dev       # Interactive CLI
```

## Architecture

High-level overview with diagrams if helpful.

## Development

### Prerequisites
- Python 3.13+
- PostgreSQL 16+ with TimescaleDB
- OpenRouter API access

### Setup
```bash
mise run install   # Install dependencies
mise run test      # Run test suite  
mise run format    # Format code
```

### Testing
Details about test strategy and running tests.

## Configuration

Environment variables and configuration options.

## Contributing

Link to contributing guidelines.
```

### Commit Message Conventions

**Conventional Commits Format**:
```
type(scope): description

[optional body]

[optional footer(s)]
```

**Types**:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, missing semicolons, etc.)
- `refactor`: Code refactoring
- `test`: Adding missing tests or correcting existing tests
- `chore`: Changes to build process or auxiliary tools

**Examples**:
```
feat(news): add vector similarity search for related articles

Implements pgvector-based similarity search using OpenAI embeddings.
Articles can now find related content based on semantic similarity
rather than just keyword matching.

- Add title_embedding and content_embedding columns
- Implement cosine similarity search in NewsRepository
- Add vector index for performance optimization

Closes #123

---

fix(database): handle connection timeouts in async sessions

Connection pooling was causing timeouts under high load.
Added proper timeout handling and connection recycling.

- Set pool_recycle=3600 for connection health
- Add retry logic for transient connection errors
- Improve error logging for debugging

---

test(news): add integration tests for batch upsert operations

Covers edge cases for duplicate URL handling and large batch processing.

---

docs(api): update OpenAPI spec for news endpoints

- Add pagination parameters
- Document error response formats
- Include example requests and responses
```

### Code Organization

**File and Directory Structure**:
```
tradingagents/
├── __init__.py
├── config.py                    # Application configuration
├── main.py                      # Entry point
├── 
├── domains/                     # Domain-driven design
│   ├── __init__.py
│   ├── news/                    # News domain
│   │   ├── __init__.py
│   │   ├── news_service.py      # Business logic
│   │   ├── news_repository.py   # Data access
│   │   ├── google_news_client.py # External API
│   │   └── models.py           # Domain models
│   ├── marketdata/             # Market data domain
│   └── socialmedia/            # Social media domain
│
├── agents/                      # LLM agents
│   ├── __init__.py
│   ├── trading_agent.py
│   ├── analyst_agent.py
│   └── libs/                   # Agent utilities
│       ├── __init__.py
│       └── agent_toolkit.py
│
├── lib/                        # Shared utilities
│   ├── __init__.py
│   ├── database.py            # Database connection
│   ├── logging.py             # Logging configuration
│   └── utils.py               # Common utilities
│
└── types/                     # Shared type definitions
    ├── __init__.py
    ├── common.py
    └── financial.py
```

This style guide ensures consistent, maintainable code across the TradingAgents project while leveraging modern Python features and database optimization techniques.