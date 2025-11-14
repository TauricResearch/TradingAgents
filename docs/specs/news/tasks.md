# News Domain Completion - Task Implementation Guide

## Overview

Complete the final 5% of the news domain by implementing **Dagster orchestration**, **OpenRouter-powered LLM sentiment analysis**, **vector embeddings**, and **RAG-powered semantic search**. This builds on 95% complete infrastructure with PostgreSQL + TimescaleDB + pgvectorscale stack.

**Total Estimated Time**: 15-20 hours with AI assistance
**Target Completion**: 4-5 days
**Test Coverage Requirement**: Maintain >85%
**Architecture Pattern**: Entity → Repository → Service → Dagster Op → Dagster Job

## Implementation Phases

### Phase 1: Entity Layer (2-3 hours)
Database and entity layer enhancements for LLM integration

### Phase 2: Repository Layer (2-3 hours)
RAG-powered vector similarity search methods

### Phase 3: LLM Integration (4-5 hours)
OpenRouter clients for sentiment and embeddings

### Phase 4: Service Enhancement (2-3 hours)
Integrate LLM clients into NewsService workflow

### Phase 5: Dagster Orchestration (3-4 hours)
Jobs, ops, schedules, and sensors for automated collection

### Phase 6: Testing & Documentation (2-3 hours)
Integration tests, performance validation, and documentation updates

---

## Task Breakdown

### Phase 1: Entity Layer

#### T001: Enhance NewsArticle Dataclass - Sentiment Fields
**Priority**: Critical | **Duration**: 1-2 hours | **Dependencies**: None

**Description**: Add LLM sentiment fields to existing NewsArticle dataclass

**Acceptance Criteria**:
- [ ] Add `sentiment_confidence: Optional[float]` field (0.0-1.0 range)
- [ ] Add `sentiment_label: Optional[str]` field ("positive", "negative", "neutral")
- [ ] Update `to_entity()` method to include new sentiment fields
- [ ] Update `from_entity()` method to populate new sentiment fields
- [ ] Add `has_reliable_sentiment()` helper method (confidence >= 0.6)

**Implementation Details**:
```python
@dataclass
class NewsArticle:
    # Existing fields...
    sentiment_score: Optional[float] = None  # Already exists

    # New LLM sentiment fields
    sentiment_confidence: Optional[float] = None  # 0.0 to 1.0
    sentiment_label: Optional[str] = None  # "positive", "negative", "neutral"

    # Vector fields already exist from 95% complete infrastructure
    title_embedding: Optional[List[float]] = None
    content_embedding: Optional[List[float]] = None

    def has_reliable_sentiment(self) -> bool:
        """Check if sentiment analysis is reliable."""
        return bool(
            self.sentiment_score is not None
            and self.sentiment_confidence is not None
            and self.sentiment_confidence >= 0.6
        )
```

**Files to Modify**:
- `/Users/martinrichards/code/TradingAgents/tradingagents/domains/news/news_repository.py` (NewsArticle dataclass section)

**Test Requirements**:
- Dataclass instantiation with new fields
- `to_entity()` and `from_entity()` roundtrip conversion
- `has_reliable_sentiment()` validation logic
- Edge cases (None values, boundary conditions)

---

#### T002: Database Migration - Sentiment Fields
**Priority**: Critical | **Duration**: 1 hour | **Dependencies**: T001

**Description**: Create Alembic migration to add sentiment fields to news_articles table

**Acceptance Criteria**:
- [ ] Create Alembic migration script `add_sentiment_fields.py`
- [ ] Add `sentiment_confidence FLOAT` column (nullable)
- [ ] Add `sentiment_label VARCHAR(20)` column (nullable)
- [ ] Add index on `sentiment_label` for filtering
- [ ] Migration tested with upgrade and downgrade
- [ ] Rollback capability verified

**Implementation Details**:
```python
# alembic/versions/20250111_add_sentiment_fields.py
def upgrade():
    op.add_column('news_articles', sa.Column('sentiment_confidence', sa.Float(), nullable=True))
    op.add_column('news_articles', sa.Column('sentiment_label', sa.String(20), nullable=True))
    op.create_index('idx_news_sentiment_label', 'news_articles', ['sentiment_label'])

def downgrade():
    op.drop_index('idx_news_sentiment_label', table_name='news_articles')
    op.drop_column('news_articles', 'sentiment_label')
    op.drop_column('news_articles', 'sentiment_confidence')
```

**Files to Create**:
- `/Users/martinrichards/code/TradingAgents/alembic/versions/20250111_add_sentiment_fields.py`

**Test Requirements**:
- Migration upgrade succeeds
- Migration downgrade succeeds
- Index is created properly
- Existing data remains intact

---

### Phase 2: Repository Layer

#### T003: NewsRepository - Vector Similarity Search
**Priority**: Critical | **Duration**: 2-3 hours | **Dependencies**: T001, T002

**Description**: Add RAG-powered vector similarity search using pgvectorscale

**Acceptance Criteria**:
- [ ] Implement `find_similar_articles()` method with cosine distance
- [ ] Support similarity threshold filtering (0.0-1.0)
- [ ] Support optional symbol filtering
- [ ] Results ordered by similarity descending
- [ ] Proper async/await with session management
- [ ] Logging for debugging and monitoring

**Implementation Details**:
```python
async def find_similar_articles(
    self,
    embedding: List[float],
    limit: int = 10,
    threshold: float = 0.7,
    symbol: Optional[str] = None
) -> List[NewsArticle]:
    """
    Find articles similar to given embedding using pgvectorscale cosine distance.

    pgvectorscale operator: <=> for cosine distance
    Cosine similarity = 1 - cosine_distance
    """
    async with self.db_manager.get_session() as session:
        # Build query with vector similarity
        query = select(
            NewsArticleEntity,
            (1 - NewsArticleEntity.title_embedding.cosine_distance(embedding)).label('similarity')
        ).filter(
            NewsArticleEntity.title_embedding.is_not(None)
        )

        # Optional symbol filter
        if symbol:
            query = query.filter(NewsArticleEntity.symbol == symbol)

        # Filter by similarity threshold and order by distance
        query = query.filter(
            (1 - NewsArticleEntity.title_embedding.cosine_distance(embedding)) >= threshold
        ).order_by(
            NewsArticleEntity.title_embedding.cosine_distance(embedding)
        ).limit(limit)

        result = await session.execute(query)
        rows = result.all()

        articles = [NewsArticle.from_entity(row[0]) for row in rows]
        logger.info(f"Found {len(articles)} similar articles (threshold={threshold})")
        return articles
```

**Files to Modify**:
- `/Users/martinrichards/code/TradingAgents/tradingagents/domains/news/news_repository.py` (add method to NewsRepository class)

**Test Requirements**:
- Vector similarity returns correct results with test data
- Similarity threshold filtering works correctly
- Symbol filtering works correctly
- Empty result handling
- Performance test (<1s for typical queries)

---

#### T004: NewsRepository - Batch Embedding Updates
**Priority**: Medium | **Duration**: 1 hour | **Dependencies**: T003

**Description**: Add efficient batch embedding update method

**Acceptance Criteria**:
- [ ] Implement `batch_update_embeddings()` method
- [ ] Use PostgreSQL bulk update operations
- [ ] Support title and content embeddings
- [ ] Update timestamp on modification
- [ ] Return count of updated articles

**Implementation Details**:
```python
async def batch_update_embeddings(
    self,
    article_embeddings: List[Tuple[UUID, List[float], List[float]]]
) -> int:
    """Efficiently batch update embeddings for multiple articles."""
    if not article_embeddings:
        return 0

    async with self.db_manager.get_session() as session:
        stmt = update(NewsArticleEntity).where(
            NewsArticleEntity.id == bindparam('article_id')
        ).values(
            title_embedding=bindparam('title_emb'),
            content_embedding=bindparam('content_emb'),
            updated_at=func.now()
        )

        batch_data = [
            {
                'article_id': article_id,
                'title_emb': title_emb,
                'content_emb': content_emb
            }
            for article_id, title_emb, content_emb in article_embeddings
        ]

        await session.execute(stmt, batch_data)
        logger.info(f"Batch updated embeddings for {len(article_embeddings)} articles")
        return len(article_embeddings)
```

**Files to Modify**:
- `/Users/martinrichards/code/TradingAgents/tradingagents/domains/news/news_repository.py`

**Test Requirements**:
- Batch update modifies correct articles
- Performance test (sub-second for 50 articles)
- Empty list handling
- Database rollback on errors

---

### Phase 3: LLM Integration

#### T005: OpenRouter Sentiment Client
**Priority**: Critical | **Duration**: 2-3 hours | **Dependencies**: T001

**Description**: Implement OpenRouter client for LLM sentiment analysis

**Acceptance Criteria**:
- [ ] OpenRouter API integration using `quick_think_llm` (claude-3.5-haiku)
- [ ] Structured JSON output: score, confidence, label, reasoning
- [ ] Financial news-focused prompts
- [ ] Exponential backoff retry logic (3 attempts)
- [ ] Keyword-based fallback on API failures
- [ ] Proper error handling and logging

**Implementation Details**:
```python
@dataclass
class SentimentResult:
    """Result from sentiment analysis."""
    score: float  # -1.0 to 1.0
    confidence: float  # 0.0 to 1.0
    label: str  # "positive", "negative", "neutral"
    reasoning: str

class OpenRouterSentimentClient:
    """Client for sentiment analysis via OpenRouter."""

    def __init__(self, config: TradingAgentsConfig):
        self.api_key = config.openrouter_api_key
        self.model = config.quick_think_llm  # claude-3.5-haiku
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"

    async def analyze_sentiment(self, title: str, content: str) -> SentimentResult:
        """Analyze sentiment with fallback to keyword-based analysis."""
        try:
            prompt = self._build_sentiment_prompt(title, content)
            response = await self._call_openrouter(prompt)
            return self._parse_sentiment_response(response)
        except Exception as e:
            logger.warning(f"OpenRouter sentiment failed: {e}, using fallback")
            return self._fallback_sentiment(title, content)

    def _fallback_sentiment(self, title: str, content: str) -> SentimentResult:
        """Keyword-based fallback for sentiment analysis."""
        text = f"{title} {content}".lower()
        positive_keywords = ['gain', 'up', 'rise', 'growth', 'profit', 'beat']
        negative_keywords = ['loss', 'down', 'fall', 'decline', 'miss', 'concern']

        pos_count = sum(1 for kw in positive_keywords if kw in text)
        neg_count = sum(1 for kw in negative_keywords if kw in text)

        if pos_count > neg_count:
            return SentimentResult(0.3, 0.5, "positive", "Keyword-based fallback")
        elif neg_count > pos_count:
            return SentimentResult(-0.3, 0.5, "negative", "Keyword-based fallback")
        else:
            return SentimentResult(0.0, 0.5, "neutral", "Keyword-based fallback")
```

**Files to Create**:
- `/Users/martinrichards/code/TradingAgents/tradingagents/domains/news/clients/openrouter_sentiment_client.py`

**Test Requirements**:
- API response parsing tests with VCR
- Retry logic tests
- Fallback mechanism tests
- Error handling tests
- Integration test with real API (optional)

---

#### T006: OpenRouter Embeddings Client
**Priority**: Critical | **Duration**: 1-2 hours | **Dependencies**: T001

**Description**: Implement OpenRouter client for vector embeddings generation

**Acceptance Criteria**:
- [ ] OpenRouter embeddings API integration (text-embedding-ada-002)
- [ ] Text preprocessing (8000 char limit)
- [ ] Batch processing support for multiple texts
- [ ] 1536-dimensional vector validation
- [ ] Zero-vector fallback on API failures
- [ ] Proper error handling and logging

**Implementation Details**:
```python
class OpenRouterEmbeddingsClient:
    """Client for generating embeddings via OpenRouter."""

    def __init__(self, config: TradingAgentsConfig):
        self.api_key = config.openrouter_api_key
        self.model = "openai/text-embedding-ada-002"  # Via OpenRouter
        self.base_url = "https://openrouter.ai/api/v1/embeddings"

    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate 1536-dim embeddings for multiple texts."""
        if not texts:
            return []

        try:
            processed_texts = [self._preprocess_text(text) for text in texts]

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            payload = {"model": self.model, "input": processed_texts}

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.base_url,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    response.raise_for_status()
                    data = await response.json()
                    embeddings = [item['embedding'] for item in data['data']]

                    # Validate dimensions
                    for i, emb in enumerate(embeddings):
                        if len(emb) != 1536:
                            raise ValueError(f"Invalid embedding dimension: {len(emb)}")

                    return embeddings

        except Exception as e:
            logger.error(f"Embeddings generation failed: {e}, using zero vectors")
            return [[0.0] * 1536 for _ in texts]

    async def generate_article_embeddings(
        self,
        article: NewsArticle
    ) -> Tuple[List[float], List[float]]:
        """Generate embeddings for article title and content."""
        texts = []
        if article.headline:
            texts.append(article.headline)
        if article.summary:
            combined = f"{article.headline} {article.summary}"
            texts.append(combined)

        if not texts:
            return [0.0] * 1536, [0.0] * 1536

        embeddings = await self.generate_embeddings(texts)
        title_embedding = embeddings[0] if len(embeddings) > 0 else [0.0] * 1536
        content_embedding = embeddings[1] if len(embeddings) > 1 else [0.0] * 1536

        return title_embedding, content_embedding

    def _preprocess_text(self, text: str) -> str:
        """Preprocess text for optimal embedding generation."""
        cleaned = " ".join(text.split())
        return cleaned[:8000]  # OpenAI embedding limit
```

**Files to Create**:
- `/Users/martinrichards/code/TradingAgents/tradingagents/domains/news/clients/openrouter_embeddings_client.py`

**Test Requirements**:
- API response parsing tests with VCR
- Batch processing tests
- Vector dimension validation tests
- Text preprocessing tests
- Zero-vector fallback tests

---

#### T007: Enhance NewsService - LLM Integration
**Priority**: Critical | **Duration**: 2-3 hours | **Dependencies**: T005, T006

**Description**: Integrate OpenRouter LLM clients into NewsService workflow

**Acceptance Criteria**:
- [ ] Add LLM clients to NewsService `__init__()`
- [ ] Implement `_enrich_articles()` method for LLM processing
- [ ] Update `update_company_news()` to call enrichment
- [ ] Implement `find_similar_news()` for RAG queries
- [ ] Best-effort processing (failures don't block storage)
- [ ] Proper error handling and logging

**Implementation Details**:
```python
class NewsService:
    def __init__(
        self,
        google_client: GoogleNewsClient,
        repository: NewsRepository,
        article_scraper: ArticleScraperClient,
        sentiment_client: OpenRouterSentimentClient,
        embeddings_client: OpenRouterEmbeddingsClient,
    ):
        self.google_client = google_client
        self.repository = repository
        self.article_scraper = article_scraper
        self.sentiment_client = sentiment_client
        self.embeddings_client = embeddings_client

    async def update_company_news(self, symbol: str) -> NewsUpdateResult:
        """
        Update company news with full LLM enrichment pipeline.

        Flow: RSS → Scrape → LLM Sentiment → Embeddings → Store
        """
        # 1. Get RSS feed
        google_articles = self.google_client.get_company_news(symbol)

        # 2. Scrape content
        scraped_articles = await self._scrape_articles(google_articles)

        # 3. Enrich with LLM (sentiment + embeddings)
        enriched_articles = await self._enrich_articles(scraped_articles)

        # 4. Store in repository
        stored_articles = await self.repository.upsert_batch(enriched_articles, symbol)

        return NewsUpdateResult(...)

    async def _enrich_articles(
        self,
        articles: List[NewsArticle]
    ) -> List[NewsArticle]:
        """Enrich articles with LLM sentiment and vector embeddings."""
        enriched = []

        for article in articles:
            try:
                # Generate sentiment
                sentiment_result = await self.sentiment_client.analyze_sentiment(
                    article.headline,
                    article.summary or ""
                )

                article.sentiment_score = sentiment_result.score
                article.sentiment_confidence = sentiment_result.confidence
                article.sentiment_label = sentiment_result.label

                # Generate embeddings
                title_emb, content_emb = await self.embeddings_client.generate_article_embeddings(article)
                article.title_embedding = title_emb
                article.content_embedding = content_emb

                enriched.append(article)

            except Exception as e:
                logger.warning(f"Failed to enrich article {article.url}: {e}")
                enriched.append(article)  # Store without enrichment

        return enriched

    async def find_similar_news(
        self,
        query_text: str,
        symbol: Optional[str] = None,
        limit: int = 5
    ) -> List[NewsArticle]:
        """Find news articles similar to query text using RAG vector search."""
        # Generate embedding for query
        query_embeddings = await self.embeddings_client.generate_embeddings([query_text])
        query_embedding = query_embeddings[0]

        # Search for similar articles
        similar_articles = await self.repository.find_similar_articles(
            embedding=query_embedding,
            limit=limit,
            threshold=0.7,
            symbol=symbol
        )

        return similar_articles
```

**Files to Modify**:
- `/Users/martinrichards/code/TradingAgents/tradingagents/domains/news/news_service.py`

**Test Requirements**:
- Mock LLM clients for unit tests
- Integration test with real services
- Error handling and fallback tests
- Performance test for batch enrichment

---

### Phase 4: Dagster Orchestration

#### T008: Dagster Directory Structure
**Priority**: High | **Duration**: 30 minutes | **Dependencies**: None

**Description**: Create directory structure for Dagster jobs, ops, and schedules

**Acceptance Criteria**:
- [ ] Create `tradingagents/data/` directory
- [ ] Create subdirectories: `jobs/`, `ops/`, `schedules/`, `sensors/`
- [ ] Create `__init__.py` files for all directories
- [ ] Import structure allows clean imports

**Implementation Details**:
```
tradingagents/data/
├── __init__.py
├── jobs/
│   ├── __init__.py
│   └── news_collection.py
├── ops/
│   ├── __init__.py
│   └── news_ops.py
├── schedules/
│   ├── __init__.py
│   └── news_schedules.py
└── sensors/
    ├── __init__.py
    └── news_sensors.py
```

**Files to Create**:
- All directory and `__init__.py` files above

**Test Requirements**:
- Import tests for all modules
- Directory structure validation

---

#### T009: Dagster Ops - News Collection
**Priority**: High | **Duration**: 2-3 hours | **Dependencies**: T007, T008

**Description**: Implement Dagster op for news collection per symbol

**Acceptance Criteria**:
- [ ] `collect_news_for_symbol` op implemented
- [ ] Proper resource management (database_manager)
- [ ] Error handling and logging
- [ ] Output metadata (articles_found, articles_scraped, etc.)
- [ ] Retry policy configured
- [ ] Op tested with build_op_context

**Implementation Details**:
```python
# tradingagents/data/ops/news_ops.py
from dagster import op, OpExecutionContext, Out, RetryPolicy

@op(
    required_resource_keys={"database_manager"},
    out=Out(dict),
    tags={"kind": "news", "domain": "news"},
    retry_policy=RetryPolicy(max_retries=3, delay=10, backoff=BackoffPolicy.EXPONENTIAL),
)
def collect_news_for_symbol(context: OpExecutionContext, symbol: str) -> dict:
    """
    Collect and process news for a single stock symbol.

    Returns dict with collection statistics.
    """
    context.log.info(f"Starting news collection for {symbol}")

    try:
        config = TradingAgentsConfig.from_env()
        db_manager = context.resources.database_manager
        news_service = NewsService.build(db_manager, config)

        result = await news_service.update_company_news(symbol)

        context.log.info(f"Completed: {result.articles_scraped} articles for {symbol}")

        return {
            "symbol": symbol,
            "articles_found": result.articles_found,
            "articles_scraped": result.articles_scraped,
            "articles_failed": result.articles_failed,
            "status": result.status,
        }

    except Exception as e:
        context.log.error(f"News collection failed for {symbol}: {e}")
        raise
```

**Files to Create**:
- `/Users/martinrichards/code/TradingAgents/tradingagents/data/ops/news_ops.py`

**Test Requirements**:
- Op execution tests with mock resources
- Error handling tests
- Retry logic tests
- Metadata validation tests

---

#### T010: Dagster Job - Daily News Collection
**Priority**: High | **Duration**: 1-2 hours | **Dependencies**: T009

**Description**: Implement Dagster job that orchestrates news collection across symbols

**Acceptance Criteria**:
- [ ] `news_collection_daily` job implemented
- [ ] Dynamic op mapping for parallel symbol processing
- [ ] Proper job tags and metadata
- [ ] Configuration for symbol list
- [ ] Job tested with execute_in_process

**Implementation Details**:
```python
# tradingagents/data/jobs/news_collection.py
from dagster import job, DynamicOut, DynamicOutput, OpExecutionContext, op
from tradingagents.data.ops.news_ops import collect_news_for_symbol

@op(out=DynamicOut())
def get_symbols_to_collect(context: OpExecutionContext) -> Generator[DynamicOutput, None, None]:
    """Get list of symbols to collect news for from config."""
    symbols = context.op_config.get("symbols", ["AAPL", "GOOGL", "MSFT", "TSLA"])
    context.log.info(f"Collecting news for {len(symbols)} symbols: {symbols}")

    for symbol in symbols:
        yield DynamicOutput(symbol, mapping_key=symbol)

@job(tags={"dagster/priority": "high", "domain": "news"})
def news_collection_daily():
    """
    Daily news collection job for all configured symbols.

    Workflow:
    1. Get symbols to collect
    2. Fan out: collect news for each symbol in parallel
    3. Aggregate results
    """
    get_symbols_to_collect().map(collect_news_for_symbol)
```

**Files to Create**:
- `/Users/martinrichards/code/TradingAgents/tradingagents/data/jobs/news_collection.py`

**Test Requirements**:
- Job execution tests
- Dynamic mapping tests
- Configuration tests
- Parallel execution validation

---

#### T011: Dagster Schedule - Daily Trigger
**Priority**: High | **Duration**: 1 hour | **Dependencies**: T010

**Description**: Implement Dagster schedule for daily news collection at 6 AM UTC

**Acceptance Criteria**:
- [ ] `news_collection_daily_schedule` schedule implemented
- [ ] Cron expression: `0 6 * * *` (daily at 6 AM UTC)
- [ ] RunRequest configuration with symbol list
- [ ] Proper tags and metadata
- [ ] Schedule tested with evaluate_tick

**Implementation Details**:
```python
# tradingagents/data/schedules/news_schedules.py
from dagster import schedule, ScheduleEvaluationContext, RunRequest
from tradingagents.data.jobs.news_collection import news_collection_daily

@schedule(
    job=news_collection_daily,
    cron_schedule="0 6 * * *",  # Daily at 6 AM UTC
    execution_timezone="UTC",
)
def news_collection_daily_schedule(context: ScheduleEvaluationContext):
    """Schedule for daily news collection at 6 AM UTC."""
    return RunRequest(
        run_key=f"news_collection_{context.scheduled_execution_time.isoformat()}",
        run_config={
            "ops": {
                "get_symbols_to_collect": {
                    "config": {
                        "symbols": ["AAPL", "GOOGL", "MSFT", "TSLA", "AMZN", "META", "NVDA"]
                    }
                }
            }
        },
        tags={
            "scheduled_time": context.scheduled_execution_time.isoformat(),
            "job_type": "news_collection",
        },
    )
```

**Files to Create**:
- `/Users/martinrichards/code/TradingAgents/tradingagents/data/schedules/news_schedules.py`

**Test Requirements**:
- Schedule evaluation tests
- Cron schedule validation
- RunRequest configuration tests
- Timezone handling tests

---

#### T012: Dagster Sensor - Failure Alerting
**Priority**: Medium | **Duration**: 1 hour | **Dependencies**: T010

**Description**: Implement Dagster sensor for job failure alerting

**Acceptance Criteria**:
- [ ] `news_collection_failure_sensor` run failure sensor implemented
- [ ] Monitors `news_collection_daily` job
- [ ] Logs failure details
- [ ] Placeholder for external alerting (Slack, PagerDuty, etc.)
- [ ] Sensor tested with run failure events

**Implementation Details**:
```python
# tradingagents/data/sensors/news_sensors.py
from dagster import run_failure_sensor, RunFailureSensorContext
from tradingagents.data.jobs.news_collection import news_collection_daily

@run_failure_sensor(
    name="news_collection_failure_sensor",
    monitored_jobs=[news_collection_daily],
)
def news_collection_failure_alert(context: RunFailureSensorContext):
    """Alert when news collection job fails."""
    context.log.error(
        f"News collection job failed!\n"
        f"Run ID: {context.dagster_run.run_id}\n"
        f"Failure: {context.failure_event.event_specific_data}"
    )

    # TODO: Implement external alerting
    # send_slack_alert(...)
    # send_pagerduty_alert(...)
```

**Files to Create**:
- `/Users/martinrichards/code/TradingAgents/tradingagents/data/sensors/news_sensors.py`

**Test Requirements**:
- Sensor evaluation tests
- Failure detection tests
- Logging validation tests

---

### Phase 5: Testing & Documentation

#### T013: Integration Tests - End-to-End Workflow
**Priority**: High | **Duration**: 2-3 hours | **Dependencies**: T007, T010

**Description**: Comprehensive integration tests for complete news domain workflow

**Acceptance Criteria**:
- [ ] End-to-end workflow test: RSS → Scrape → LLM → Vector → Store
- [ ] RAG query test: Vector similarity search with semantic matching
- [ ] AgentToolkit integration test
- [ ] Performance tests (< 2s queries, < 1s vector search)
- [ ] Error recovery and fallback tests
- [ ] Test coverage maintained above 85%

**Implementation Details**:
```python
# tests/domains/news/integration/test_news_workflow.py

@pytest.mark.asyncio
async def test_complete_news_pipeline_end_to_end(test_db_manager):
    """Test complete pipeline: RSS → Scrape → LLM → Vector → Store."""
    config = TradingAgentsConfig.from_test_env()
    service = NewsService.build(test_db_manager, config)

    # Execute full pipeline
    result = await service.update_company_news("AAPL")

    # Verify results
    assert result.status == "completed"
    assert result.articles_scraped > 0

    # Verify database storage
    articles = await service.repository.list_by_date_range(
        symbol="AAPL",
        start_date=date.today(),
        end_date=date.today()
    )

    assert len(articles) > 0

    # Verify LLM enrichment
    for article in articles:
        assert article.sentiment_score is not None
        assert article.sentiment_confidence is not None
        assert article.title_embedding is not None
        assert len(article.title_embedding) == 1536

@pytest.mark.asyncio
async def test_rag_vector_similarity_search(test_db_manager):
    """Test RAG vector similarity search functionality."""
    service = NewsService.build(test_db_manager, TradingAgentsConfig.from_test_env())

    # Find similar articles
    similar_articles = await service.find_similar_news(
        query_text="Apple earnings beat expectations",
        symbol="AAPL",
        limit=5
    )

    assert len(similar_articles) <= 5
    # Verify articles are relevant (high similarity scores)

@pytest.mark.asyncio
async def test_performance_benchmarks(test_db_manager):
    """Test performance meets requirements."""
    repository = NewsRepository(test_db_manager)

    # Test query performance (< 2s requirement)
    start_time = time.time()
    articles = await repository.list_by_date_range(
        symbol="AAPL",
        start_date=date.today() - timedelta(days=30),
        end_date=date.today()
    )
    query_time = time.time() - start_time

    assert query_time < 2.0, f"Query took {query_time}s, should be < 2s"

    # Test vector similarity performance (< 1s requirement)
    test_embedding = [0.1] * 1536
    start_time = time.time()
    similar = await repository.find_similar_articles(test_embedding, limit=10)
    vector_time = time.time() - start_time

    assert vector_time < 1.0, f"Vector search took {vector_time}s, should be < 1s"
```

**Files to Create**:
- `/Users/martinrichards/code/TradingAgents/tests/domains/news/integration/test_news_workflow.py`

**Test Requirements**:
- All integration tests pass
- Performance benchmarks met
- Test coverage > 85%

---

#### T014: Dagster Tests
**Priority**: Medium | **Duration**: 1 hour | **Dependencies**: T010, T011

**Description**: Unit tests for Dagster ops, jobs, and schedules

**Acceptance Criteria**:
- [ ] Op execution tests with mocked resources
- [ ] Job execution tests
- [ ] Schedule evaluation tests
- [ ] Error handling tests
- [ ] All Dagster components tested

**Implementation Details**:
```python
# tests/data/ops/test_news_ops.py
from dagster import build_op_context
from tradingagents.data.ops.news_ops import collect_news_for_symbol

def test_collect_news_for_symbol_op():
    """Test Dagster op for news collection."""
    context = build_op_context(
        resources={"database_manager": mock_database_manager}
    )

    result = collect_news_for_symbol(context, "AAPL")

    assert result["symbol"] == "AAPL"
    assert result["status"] == "completed"
    assert result["articles_found"] >= 0

# tests/data/jobs/test_news_collection.py
from dagster import execute_in_process
from tradingagents.data.jobs.news_collection import news_collection_daily

def test_news_collection_daily_job():
    """Test Dagster job execution."""
    result = execute_in_process(
        news_collection_daily,
        run_config={
            "ops": {
                "get_symbols_to_collect": {
                    "config": {"symbols": ["AAPL"]}
                }
            }
        }
    )

    assert result.success
```

**Files to Create**:
- `/Users/martinrichards/code/TradingAgents/tests/data/ops/test_news_ops.py`
- `/Users/martinrichards/code/TradingAgents/tests/data/jobs/test_news_collection.py`
- `/Users/martinrichards/code/TradingAgents/tests/data/schedules/test_news_schedules.py`

**Test Requirements**:
- All Dagster tests pass
- Coverage > 85% for Dagster code

---

#### T015: Documentation Updates
**Priority**: Medium | **Duration**: 1-2 hours | **Dependencies**: T013, T014

**Description**: Update documentation and monitoring for new functionality

**Acceptance Criteria**:
- [ ] Update API documentation for new methods
- [ ] Dagster job configuration examples
- [ ] Performance monitoring queries
- [ ] Troubleshooting guide for common issues
- [ ] AgentToolkit integration documentation
- [ ] README updates

**Files to Modify**:
- `/Users/martinrichards/code/TradingAgents/docs/domains/news.md`
- `/Users/martinrichards/code/TradingAgents/docs/api-reference.md`
- `/Users/martinrichards/code/TradingAgents/README.md`

**Test Requirements**:
- Documentation accuracy validation
- Configuration example testing
- Link validation

---

## Parallel Development Opportunities

### AI Agent Collaboration Points

**Tasks T005 & T006** can be developed in parallel:
- Both are independent OpenRouter client implementations
- Different LLM capabilities (sentiment vs embeddings)
- Can be tested independently with pytest-vcr

**Tasks T009, T010, T011** can be developed in parallel after T008:
- Ops, jobs, and schedules are independent components
- Can be tested separately
- Integration testing happens in T014

### Critical Path Analysis

**Critical Path**: T001 → T002 → T003 → T007 → T009 → T010 → T013

**Parallel Branches**:
1. **LLM Clients**: T005 + T006 (parallel with T003-T004)
2. **Dagster Components**: T009 + T010 + T011 (after T008)
3. **Testing**: Unit tests alongside implementation

---

## Success Metrics

**Technical Metrics**:
- Test coverage >85% maintained
- Query performance <2s for 30-day lookback
- Vector search performance <1s for top-10 results
- Zero breaking changes to AgentToolkit
- Dagster jobs execute successfully

**Functional Metrics**:
- OpenRouter LLM sentiment analysis operational
- Vector embeddings enable semantic search
- Dagster schedules running daily without failures
- Agent context enriched with sentiment and similarity

**Quality Metrics**:
- All acceptance criteria met for each task
- Comprehensive error handling and fallbacks
- Production-ready monitoring via Dagster UI
- Complete documentation for all new features

---

## Implementation Guidelines

### TDD Approach
**Every task follows**: Write test → Write code → Refactor

### Layered Architecture Pattern
**Strict adherence to**: Entity → Repository → Service → Dagster Op → Dagster Job

### Error Handling Strategy
**Graceful fallbacks** for all LLM API dependencies (keyword sentiment, zero vectors)

### Performance Requirements
**Async operations** with proper connection pooling throughout

### Testing Strategy
**Unit tests + Integration tests + pytest-vcr** for external API calls

---

## Risk Mitigation Strategies

### LLM API Dependencies
- Implement comprehensive fallback strategies
- Use pytest-vcr for deterministic testing
- Mock clients for unit tests
- Monitor API costs and rate limits

### Database Performance
- Test with realistic data volumes
- Monitor query performance during development
- Use proper indexes for vector operations
- Regular performance profiling

### Dagster Integration
- Start with simple ops and jobs
- Test incrementally before full integration
- Use Dagster UI for debugging
- Implement comprehensive logging

---

This comprehensive task breakdown provides clear implementation guidance for completing the final 5% of the news domain while maintaining architectural consistency with Dagster orchestration and leveraging AI-assisted development patterns.
