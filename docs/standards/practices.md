# Development Practices - TradingAgents

## Testing Standards

### Pragmatic Outside-In TDD

**Philosophy**: Mock I/O boundaries, test real logic, optimize for fast feedback.

**Core Principle**: Test behavior, not implementation. Focus on public interfaces and data transformations while mocking external dependencies (HTTP, database, filesystem).

### Testing Strategy by Layer

#### 1. Services (Business Logic) - Mock Boundaries
```python
# tests/domains/news/test_news_service.py
import pytest
from unittest.mock import Mock, AsyncMock
from tradingagents.domains.news.news_service import NewsService
from tradingagents.domains.news.news_repository import NewsArticle

@pytest.fixture
def mock_repository():
    return AsyncMock(spec=NewsRepository)

@pytest.fixture
def mock_google_client():
    return AsyncMock(spec=GoogleNewsClient)

async def test_get_articles_returns_empty_on_repository_error(mock_repository):
    # Mock repository failure
    mock_repository.list.side_effect = Exception("Database connection failed")
    
    service = NewsService(repository=mock_repository, clients={})
    
    # Service should handle error gracefully
    articles = await service.get_articles("AAPL", date(2024, 1, 15))
    
    assert articles == []
    mock_repository.list.assert_called_once_with("AAPL", date(2024, 1, 15))

async def test_update_articles_transforms_external_data_correctly():
    # Real business logic: test data transformation and coordination
    external_articles = [create_external_article("Breaking News", "CNN")]
    
    mock_repository = AsyncMock()
    mock_google_client = AsyncMock()
    mock_google_client.search.return_value = external_articles
    
    service = NewsService(
        repository=mock_repository, 
        clients={"google": mock_google_client}
    )
    
    # Test business logic: coordination and transformation
    result_count = await service.update_articles("AAPL", date(2024, 1, 15))
    
    # Verify transformation happened correctly
    stored_articles = mock_repository.upsert_batch.call_args[0][0]
    assert len(stored_articles) == 1
    assert isinstance(stored_articles[0], NewsArticle)
    assert stored_articles[0].headline == "Breaking News"
```

#### 2. Repositories (Data Access) - Real Persistence
```python
# tests/domains/news/test_news_repository.py
import pytest
from tradingagents.lib.database import create_test_database_manager
from tradingagents.domains.news.news_repository import NewsRepository, NewsArticle

@pytest.fixture
async def db_manager():
    """Use real PostgreSQL for repository tests"""
    manager = create_test_database_manager()
    await manager.create_tables()
    yield manager
    await manager.drop_tables()
    await manager.close()

async def test_upsert_batch_handles_duplicates_correctly(db_manager):
    """Test actual database behavior with real SQL operations"""
    repository = NewsRepository(db_manager)
    
    # Insert initial articles
    articles = [
        NewsArticle("Apple Earnings Beat", "https://cnn.com/1", "CNN", date(2024, 1, 15)),
        NewsArticle("Apple Stock Rises", "https://cnn.com/2", "CNN", date(2024, 1, 15))
    ]
    
    result1 = await repository.upsert_batch(articles, "AAPL")
    assert len(result1) == 2
    
    # Update one article (same URL)
    updated_articles = [
        NewsArticle("Apple Earnings Beat Expectations", "https://cnn.com/1", "CNN", date(2024, 1, 15))
    ]
    
    result2 = await repository.upsert_batch(updated_articles, "AAPL")
    
    # Should update existing, not create duplicate
    all_articles = await repository.list("AAPL", date(2024, 1, 15))
    assert len(all_articles) == 2
    assert any("Beat Expectations" in a.headline for a in all_articles)

async def test_list_by_date_range_performance(db_manager):
    """Test query performance with indexed queries"""
    repository = NewsRepository(db_manager)
    
    # Insert test data
    articles = [
        NewsArticle(f"News {i}", f"https://example.com/{i}", "Test", date(2024, 1, i+1))
        for i in range(100)
    ]
    await repository.upsert_batch(articles, "AAPL")
    
    # Test indexed query performance
    start_time = time.time()
    results = await repository.list_by_date_range(
        "AAPL", date(2024, 1, 1), date(2024, 1, 10), limit=50
    )
    elapsed = time.time() - start_time
    
    assert len(results) == 10
    assert elapsed < 0.1  # < 100ms for simple query
```

#### 3. Clients (External APIs) - pytest-vcr
```python
# tests/domains/news/test_google_news_client.py
import pytest
import pytest_vcr
from tradingagents.domains.news.google_news_client import GoogleNewsClient

class TestGoogleNewsClient:
    @pytest_vcr.use_cassette("google_news_apple_search.yaml")
    async def test_search_returns_structured_articles(self):
        """Real HTTP calls recorded with VCR cassettes"""
        client = GoogleNewsClient()
        
        articles = await client.search("AAPL", max_results=5)
        
        # Test real API response structure
        assert len(articles) > 0
        assert all(article.title for article in articles)
        assert all(article.link.startswith("http") for article in articles)
        assert all(article.source for article in articles)
    
    @pytest_vcr.use_cassette("google_news_no_results.yaml")
    async def test_search_handles_no_results_gracefully(self):
        """Test error cases with real API responses"""
        client = GoogleNewsClient()
        
        articles = await client.search("NONEXISTENT_SYMBOL_XYZ", max_results=5)
        
        assert articles == []
```

### Quality Standards

#### Coverage Requirements
- **85% minimum coverage** across all domains
- **100% coverage** for critical financial calculations
- **Branch coverage** for error handling paths

**Coverage Enforcement**:
```bash
# mise tasks for coverage
[tasks.test-coverage]
description = "Run tests with coverage report"
run = "uv run pytest --cov=tradingagents --cov-report=html --cov-fail-under=85"

[tasks.coverage-report]
description = "Open coverage report in browser"
run = "open htmlcov/index.html"
```

#### Performance Standards
- **< 100ms per unit test** (fast feedback)
- **< 5s for integration test suite** (rapid development)
- **< 30s for full test suite** (CI/CD efficiency)

**Performance Monitoring**:
```python
# conftest.py - Test timing
@pytest.fixture(autouse=True)
def test_timer(request):
    start_time = time.time()
    yield
    duration = time.time() - start_time
    if duration > 0.1:  # 100ms threshold
        pytest.warn(f"Slow test: {request.node.nodeid} took {duration:.2f}s")
```

#### Test Structure Standards

**Mirror Source Structure**:
```
tests/
├── conftest.py                     # Shared fixtures
├── domains/
│   ├── news/
│   │   ├── test_news_service.py    # Business logic tests (mocked boundaries)
│   │   ├── test_news_repository.py # Data persistence tests (real DB)
│   │   └── test_google_news_client.py # External API tests (VCR cassettes)
│   ├── marketdata/
│   └── socialmedia/
├── agents/
│   └── test_trading_graph.py       # Agent workflow tests
└── integration/
    └── test_end_to_end.py          # Full system tests
```

**Naming Conventions**:
- `test_{method_name}_{expected_behavior}_{context}`
- Example: `test_upsert_batch_handles_duplicates_correctly`

## Development Workflow with Mise

### Daily Development Commands

**Core Development Flow**:
```bash
# 1. Start development environment
mise run docker    # Start PostgreSQL + TimescaleDB

# 2. Install/update dependencies
mise run install   # uv sync --dev

# 3. Development iteration
mise run format    # Auto-format with ruff
mise run lint      # Check code quality
mise run typecheck # Type checking with pyrefly
mise run test      # Run test suite

# 4. Run application
mise run dev       # Interactive CLI
mise run run       # Direct execution
```

**Quality Assurance**:
```bash
# Run all quality checks before commit
mise run all       # format + lint + typecheck

# Coverage analysis
mise run test-coverage
mise run coverage-report
```

**Troubleshooting**:
```bash
# Clean build artifacts
mise run clean

# Reset development environment
mise run docker    # Restart containers
mise run install   # Reinstall dependencies
```

### Code Quality Standards

#### Linting with Ruff
```toml
# pyproject.toml
[tool.ruff]
target-version = "py313"
line-length = 88
extend-exclude = ["migrations/", "alembic/"]

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings  
    "F",   # Pyflakes
    "I",   # isort
    "B",   # flake8-bugbear
    "C4",  # flake8-comprehensions
    "UP",  # pyupgrade
    "ERA", # eradicate
    "PIE", # flake8-pie
    "SIM", # flake8-simplify
]

ignore = [
    "E501",  # Line too long (handled by formatter)
    "B008",  # Do not perform function calls in argument defaults
    "B904",  # raise ... from None
]

[tool.ruff.lint.per-file-ignores]
"tests/**/*.py" = [
    "S101",  # Use of assert detected
    "ARG",   # Unused function args
    "FBT",   # Boolean trap
]
```

#### Type Checking with Pyrefly
```toml
[tool.pyrefly]
python-version = "3.13"
warn-unused-ignores = true
show-error-codes = true
strict = true

# Enable async-aware type checking
plugins = ["sqlalchemy.ext.mypy.plugin"]

# Per-module configuration  
[[tool.pyrefly.overrides]]
module = "tests.*"
disallow_untyped_defs = false
```

### Database Development Patterns

#### Migration Workflow
```bash
# 1. Create migration after model changes
alembic revision --autogenerate -m "Add user preferences table"

# 2. Review generated migration
# Edit alembic/versions/{hash}_add_user_preferences_table.py

# 3. Apply migration
alembic upgrade head

# 4. Test with sample data
mise run test-migrations
```

#### Development Database Management
```bash
# Reset development database
mise run docker         # Stop/start containers
alembic upgrade head    # Apply all migrations
python scripts/seed_dev_data.py  # Load sample data
```

#### Testing Database Strategy
```python
# Test database isolation
@pytest.fixture(scope="function")
async def clean_db():
    """Fresh database for each test"""
    db_manager = create_test_database_manager()
    await db_manager.create_tables()
    yield db_manager
    await db_manager.drop_tables()
    await db_manager.close()

# Shared test data
@pytest.fixture
def sample_news_articles():
    """Reusable test data across test modules"""
    return [
        NewsArticle("Apple Earnings", "https://cnn.com/1", "CNN", date(2024, 1, 15)),
        NewsArticle("Tesla Updates", "https://reuters.com/2", "Reuters", date(2024, 1, 16))
    ]
```

## Error Handling and Retry Strategies

### Resilient External API Integration

#### Exponential Backoff with Circuit Breaker
```python
import asyncio
import logging
from functools import wraps
from typing import TypeVar, Callable, Any

T = TypeVar('T')

class APIClient:
    def __init__(self):
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            reset_timeout=60,
            expected_exception=aiohttp.ClientError
        )
    
    @retry_with_backoff(max_retries=3, base_delay=1.0)
    async def fetch_data(self, url: str) -> dict:
        """Resilient HTTP requests with retry logic"""
        async with self.circuit_breaker:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=30) as response:
                    if response.status >= 500:
                        raise aiohttp.ClientError(f"Server error: {response.status}")
                    return await response.json()

def retry_with_backoff(max_retries: int = 3, base_delay: float = 1.0):
    """Decorator for exponential backoff retry logic"""
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt == max_retries:
                        break
                    
                    delay = base_delay * (2 ** attempt)  # Exponential backoff
                    jitter = random.uniform(0.1, 0.9)     # Add jitter
                    await asyncio.sleep(delay * jitter)
                    
                    logging.warning(f"Retry {attempt + 1}/{max_retries} for {func.__name__}: {e}")
            
            raise last_exception
        return wrapper
    return decorator
```

### Database Error Handling

#### Graceful Degradation
```python
class NewsService:
    async def get_articles(self, symbol: str, date: date) -> list[NewsArticle]:
        """Service-level error handling with fallbacks"""
        try:
            # Try primary repository
            articles = await self.repository.list(symbol, date)
            logger.info(f"Retrieved {len(articles)} articles from database")
            return articles
            
        except DatabaseConnectionError:
            logger.warning("Database unavailable, trying cache fallback")
            # Fallback to file cache
            return await self.cache_repository.list(symbol, date)
            
        except Exception as e:
            logger.error(f"Failed to retrieve articles for {symbol}: {e}")
            # Graceful degradation - return empty list rather than crash
            return []

    async def update_articles_with_partial_failure_handling(self, symbol: str, date: date) -> dict:
        """Handle partial failures in batch operations"""
        results = {"successful": 0, "failed": 0, "errors": []}
        
        try:
            # Attempt batch fetch from multiple sources
            sources = ["google_news", "finnhub", "alpha_vantage"]
            articles_by_source = {}
            
            for source in sources:
                try:
                    client = self.clients[source]
                    articles = await client.fetch_news(symbol, date)
                    articles_by_source[source] = articles
                    logger.info(f"Fetched {len(articles)} from {source}")
                except Exception as e:
                    results["errors"].append(f"{source}: {str(e)}")
                    logger.warning(f"Failed to fetch from {source}: {e}")
            
            # Process successful fetches
            all_articles = []
            for source, articles in articles_by_source.items():
                try:
                    validated = [a for a in articles if self.validate_article(a)]
                    all_articles.extend(validated)
                    results["successful"] += len(validated)
                except Exception as e:
                    results["failed"] += len(articles)
                    results["errors"].append(f"Validation failed for {source}: {str(e)}")
            
            # Store successfully processed articles
            if all_articles:
                await self.repository.upsert_batch(all_articles, symbol)
            
            return results
            
        except Exception as e:
            logger.error(f"Critical error in update_articles: {e}")
            results["errors"].append(f"Critical failure: {str(e)}")
            return results
```

### Logging Standards

#### Structured Logging Configuration
```python
import logging
import json
from datetime import datetime

class JSONFormatter(logging.Formatter):
    """Structured JSON logging for production"""
    
    def format(self, record):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add context information
        if hasattr(record, 'symbol'):
            log_entry["symbol"] = record.symbol
        if hasattr(record, 'user_id'):
            log_entry["user_id"] = record.user_id
        if hasattr(record, 'request_id'):
            log_entry["request_id"] = record.request_id
            
        # Add exception info
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
            
        return json.dumps(log_entry)

# Configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('tradingagents.log')
    ]
)

# Domain-specific loggers
news_logger = logging.getLogger('tradingagents.domains.news')
market_logger = logging.getLogger('tradingagents.domains.marketdata')
agent_logger = logging.getLogger('tradingagents.agents')
```

#### Contextual Logging in Services
```python
class NewsService:
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    async def get_articles(self, symbol: str, date: date) -> list[NewsArticle]:
        # Add context to log messages
        extra = {"symbol": symbol, "date": date.isoformat()}
        
        self.logger.info("Starting article retrieval", extra=extra)
        
        try:
            articles = await self.repository.list(symbol, date)
            self.logger.info(
                f"Successfully retrieved {len(articles)} articles", 
                extra={**extra, "count": len(articles)}
            )
            return articles
        except Exception as e:
            self.logger.error(
                f"Failed to retrieve articles: {e}", 
                extra=extra,
                exc_info=True
            )
            raise
```

## Performance Monitoring

### Application Metrics

#### Key Performance Indicators
```python
import time
import asyncio
from functools import wraps
from collections import defaultdict

class PerformanceMonitor:
    def __init__(self):
        self.metrics = defaultdict(list)
    
    def track_execution_time(self, operation: str):
        """Decorator to track method execution time"""
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                start_time = time.time()
                try:
                    result = await func(*args, **kwargs)
                    return result
                finally:
                    duration = time.time() - start_time
                    self.metrics[f"{operation}_duration"].append(duration)
                    
                    # Log slow operations
                    if duration > 1.0:
                        logging.warning(f"Slow operation {operation}: {duration:.2f}s")
            return wrapper
        return decorator
    
    def get_performance_summary(self) -> dict:
        """Get performance statistics"""
        summary = {}
        for operation, durations in self.metrics.items():
            if durations:
                summary[operation] = {
                    "count": len(durations),
                    "avg": sum(durations) / len(durations),
                    "min": min(durations),
                    "max": max(durations),
                    "p95": sorted(durations)[int(len(durations) * 0.95)]
                }
        return summary

# Usage in services
monitor = PerformanceMonitor()

class NewsService:
    @monitor.track_execution_time("news_fetch")
    async def get_articles(self, symbol: str, date: date) -> list[NewsArticle]:
        return await self.repository.list(symbol, date)
    
    @monitor.track_execution_time("news_update")  
    async def update_articles(self, symbol: str, date: date) -> int:
        return await self._fetch_and_store_articles(symbol, date)
```

### Database Query Optimization

#### Query Performance Monitoring
```python
# Custom SQLAlchemy event listener for query timing
from sqlalchemy import event
from sqlalchemy.engine import Engine
import logging

query_logger = logging.getLogger('tradingagents.database.queries')

@event.listens_for(Engine, "before_cursor_execute")
def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    context._query_start_time = time.time()

@event.listens_for(Engine, "after_cursor_execute")  
def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    total = time.time() - context._query_start_time
    
    # Log slow queries
    if total > 0.1:  # 100ms threshold
        query_logger.warning(
            f"Slow query ({total:.2f}s): {statement[:100]}...",
            extra={"duration": total, "query": statement[:200]}
        )
```

This comprehensive development practices document establishes the foundation for maintaining high code quality, rapid development cycles, and robust error handling in the TradingAgents system.