# News Domain Completion - Task Implementation Guide

## Overview

Complete the final 5% of the news domain by implementing OpenRouter-only LLM sentiment analysis, vector embeddings, and APScheduler job execution. This builds on 95% complete infrastructure with PostgreSQL + TimescaleDB + pgvectorscale stack.

**Total Estimated Time**: 12-16 hours with AI assistance  
**Target Completion**: 3-4 days  
**Test Coverage Requirement**: Maintain >85%  
**Architecture Pattern**: Database → Entity → Repository → Service → Scheduling

## Implementation Phases

### Phase 1: Foundation (4-7 hours)
Database and entity layer enhancements for LLM integration

### Phase 2: Data Access (2-3 hours) 
Repository layer enhancements for vector and job operations

### Phase 3: LLM Integration (5-8 hours)
OpenRouter clients and service integration

### Phase 4: Scheduling (4-6 hours)
Job scheduling and CLI integration  

### Phase 5: Validation (3-5 hours)
Testing, documentation, and monitoring

---

## Task Breakdown

### Phase 1: Foundation

#### T001: Database Migration - NewsJobConfig Table
**Priority**: Critical | **Duration**: 1-2 hours | **Dependencies**: None

**Description**: Create database migration for news job configurations table with proper indexes

**Acceptance Criteria**:
- [ ] `news_job_configs` table created with UUID primary key
- [ ] JSONB fields for symbols and categories with validation
- [ ] Proper indexes for enabled/frequency queries
- [ ] Migration script tests with rollback capability

**Implementation Details**:
```python
# Migration structure
def upgrade():
    op.create_table(
        'news_job_configs',
        sa.Column('id', postgresql.UUID(), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('symbols', postgresql.JSONB(), nullable=False),
        sa.Column('categories', postgresql.JSONB(), nullable=False),
        sa.Column('frequency_cron', sa.String(100), nullable=False),
        sa.Column('enabled', sa.Boolean(), default=True),
        sa.Column('last_run', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), default=func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), default=func.now())
    )
    
    # Indexes
    op.create_index('idx_news_jobs_enabled_frequency', 'news_job_configs', 
                   ['enabled', 'frequency_cron'])
    op.create_index('idx_news_jobs_last_run', 'news_job_configs', 
                   ['last_run'], postgresql_where=sa.text('enabled = true'))
```

**Files to Modify**:
- `/Users/martinrichards/code/TradingAgents/tradingagents/data/migrations/add_news_job_configs.py`

**Test Requirements**:
- Migration up/down tests
- Index performance validation
- Constraint validation tests

---

#### T002: Enhance NewsArticle Entity - Sentiment and Embeddings  
**Priority**: Critical | **Duration**: 2-3 hours | **Dependencies**: T001

**Description**: Add LLM sentiment fields and embedding validation to NewsArticle entity

**Acceptance Criteria**:
- [ ] Add `sentiment_score`, `sentiment_confidence`, `sentiment_label` fields
- [ ] Add `title_embedding` and `content_embedding` vector fields
- [ ] Enhanced `validate()` method with sentiment range checks
- [ ] Updated transformations for vector handling
- [ ] Embedding dimension validation (1536)

**Implementation Details**:
```python
@dataclass
class NewsArticle:
    # Existing fields...
    
    # LLM sentiment fields
    sentiment_score: Optional[float] = None  # [-1.0, 1.0]
    sentiment_confidence: Optional[float] = None  # [0.0, 1.0]
    sentiment_label: Optional[str] = None  # "positive", "negative", "neutral"
    
    # Vector embedding fields
    title_embedding: Optional[List[float]] = None  # 1536 dimensions
    content_embedding: Optional[List[float]] = None  # 1536 dimensions
    
    def validate(self) -> Dict[str, List[str]]:
        errors = super().validate()
        
        # Sentiment validation
        if self.sentiment_score is not None:
            if not -1.0 <= self.sentiment_score <= 1.0:
                errors["sentiment_score"] = ["Must be between -1.0 and 1.0"]
        
        if self.sentiment_confidence is not None:
            if not 0.0 <= self.sentiment_confidence <= 1.0:
                errors["sentiment_confidence"] = ["Must be between 0.0 and 1.0"]
        
        # Vector dimension validation
        for field, vector in [("title_embedding", self.title_embedding), 
                             ("content_embedding", self.content_embedding)]:
            if vector is not None and len(vector) != 1536:
                errors[field] = ["Must be exactly 1536 dimensions"]
        
        return errors
    
    def to_record(self) -> Dict[str, Any]:
        record = super().to_record()
        # Convert vectors to pgvector format if present
        if self.title_embedding:
            record["title_embedding"] = self.title_embedding
        if self.content_embedding:
            record["content_embedding"] = self.content_embedding
        return record
```

**Files to Modify**:
- `/Users/martinrichards/code/TradingAgents/tradingagents/domains/news/entities/news_article.py`

**Test Requirements**:
- Sentiment validation tests (range checks)
- Vector dimension validation tests  
- Transformation method tests
- Business rule violation tests

---

#### T003: Create NewsJobConfig Entity
**Priority**: Critical | **Duration**: 1-2 hours | **Dependencies**: T001

**Description**: Implement NewsJobConfig entity for scheduled job management

**Acceptance Criteria**:
- [ ] NewsJobConfig dataclass with all required fields
- [ ] Business rule validation for job configuration
- [ ] Cron expression validation for frequency  
- [ ] Symbol list validation
- [ ] JSON serialization for database storage

**Implementation Details**:
```python
@dataclass
class NewsJobConfig:
    id: Optional[UUID] = None
    name: str = ""
    symbols: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)  
    frequency_cron: str = ""
    enabled: bool = True
    last_run: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def validate(self) -> Dict[str, List[str]]:
        errors = {}
        
        # Name validation
        if not self.name or len(self.name) > 255:
            errors["name"] = ["Name required and must be <= 255 characters"]
        
        # Symbol validation
        if not self.symbols:
            errors["symbols"] = ["At least one symbol required"]
        for symbol in self.symbols:
            if not symbol.isupper() or not symbol.isalpha():
                errors["symbols"] = ["Symbols must be uppercase letters only"]
        
        # Cron validation
        try:
            from croniter import croniter
            if not croniter.is_valid(self.frequency_cron):
                errors["frequency_cron"] = ["Invalid cron expression"]
        except ImportError:
            # Fallback validation for simple intervals
            if self.frequency_cron not in ["hourly", "daily", "weekly"]:
                errors["frequency_cron"] = ["Invalid frequency"]
        
        return errors
```

**Files to Create**:
- `/Users/martinrichards/code/TradingAgents/tradingagents/domains/news/entities/news_job_config.py`

**Test Requirements**:
- Job configuration validation tests
- Schedule parsing tests
- Symbol validation tests
- Serialization/deserialization tests

---

### Phase 2: Data Access

#### T004: Enhance NewsRepository - Vector and Job Operations
**Priority**: Critical | **Duration**: 2-3 hours | **Dependencies**: T002, T003

**Description**: Add vector similarity search and NewsJobConfig CRUD operations

**Acceptance Criteria**:
- [ ] Vector similarity search with cosine distance
- [ ] Batch embedding update operations  
- [ ] NewsJobConfig CRUD methods
- [ ] Optimized query performance for vector operations
- [ ] Proper async connection handling

**Implementation Details**:
```python
class NewsRepository:
    # Existing methods...
    
    async def find_similar_articles(self, 
                                  embedding: List[float], 
                                  limit: int = 10,
                                  threshold: float = 0.8) -> List[NewsArticle]:
        """Find articles similar to given embedding using cosine distance"""
        query = """
        SELECT *, 1 - (title_embedding <=> %s::vector) as similarity
        FROM news_articles 
        WHERE title_embedding IS NOT NULL
        AND 1 - (title_embedding <=> %s::vector) > %s
        ORDER BY title_embedding <=> %s::vector
        LIMIT %s
        """
        
        async with self._get_connection() as conn:
            rows = await conn.fetch(query, embedding, embedding, threshold, embedding, limit)
            return [NewsArticle.from_record(dict(row)) for row in rows]
    
    async def batch_update_embeddings(self, 
                                    articles: List[NewsArticle]) -> None:
        """Efficiently update embeddings for multiple articles"""
        if not articles:
            return
        
        query = """
        UPDATE news_articles 
        SET title_embedding = %s, content_embedding = %s, updated_at = now()
        WHERE id = %s
        """
        
        async with self._get_connection() as conn:
            await conn.executemany(query, [
                (article.title_embedding, article.content_embedding, article.id)
                for article in articles
                if article.id and (article.title_embedding or article.content_embedding)
            ])
    
    # NewsJobConfig CRUD operations
    async def create_job_config(self, config: NewsJobConfig) -> NewsJobConfig:
        """Create new job configuration"""
        query = """
        INSERT INTO news_job_configs (id, name, symbols, categories, frequency_cron, enabled)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING *
        """
        
        config.id = config.id or uuid4()
        async with self._get_connection() as conn:
            row = await conn.fetchrow(query, 
                config.id, config.name, json.dumps(config.symbols),
                json.dumps(config.categories), config.frequency_cron, config.enabled)
            return NewsJobConfig.from_record(dict(row))
    
    async def get_active_job_configs(self) -> List[NewsJobConfig]:
        """Get all enabled job configurations"""
        query = "SELECT * FROM news_job_configs WHERE enabled = true"
        async with self._get_connection() as conn:
            rows = await conn.fetch(query)
            return [NewsJobConfig.from_record(dict(row)) for row in rows]
```

**Files to Modify**:
- `/Users/martinrichards/code/TradingAgents/tradingagents/domains/news/repositories/news_repository.py`

**Test Requirements**:
- Vector similarity search tests with mock data
- Batch operation performance tests  
- Job config CRUD tests
- Database connection pooling tests

---

### Phase 3: LLM Integration

#### T005: OpenRouter Client - Sentiment Analysis
**Priority**: Critical | **Duration**: 2-3 hours | **Dependencies**: T002

**Description**: Implement OpenRouter client for LLM sentiment analysis

**Acceptance Criteria**:
- [ ] OpenRouter API integration for sentiment analysis
- [ ] Structured prompts for financial news sentiment
- [ ] Response parsing with Pydantic models
- [ ] Error handling with graceful fallbacks
- [ ] Retry logic with exponential backoff

**Implementation Details**:
```python
class OpenRouterSentimentClient:
    def __init__(self, config: TradingAgentsConfig):
        self.api_key = config.openrouter_api_key
        self.model = config.quick_think_llm
        self.base_url = "https://openrouter.ai/api/v1"
        
    async def analyze_sentiment(self, title: str, content: str) -> SentimentResult:
        """Analyze sentiment of news article"""
        prompt = f"""
        Analyze the sentiment of this financial news article:
        
        Title: {title}
        Content: {content[:1000]}...
        
        Provide sentiment analysis as JSON:
        {{
            "score": float between -1.0 (very negative) and 1.0 (very positive),
            "confidence": float between 0.0 and 1.0,
            "label": "positive" | "negative" | "neutral",
            "reasoning": "brief explanation"
        }}
        """
        
        try:
            async with aiohttp.ClientSession() as session:
                response = await self._make_request(session, prompt)
                return self._parse_sentiment_response(response)
        except Exception as e:
            logger.warning(f"LLM sentiment analysis failed: {e}")
            return self._fallback_sentiment(title, content)
    
    def _fallback_sentiment(self, title: str, content: str) -> SentimentResult:
        """Keyword-based fallback sentiment analysis"""
        # Simple keyword-based sentiment as fallback
        positive_words = ["gain", "profit", "up", "growth", "buy"]
        negative_words = ["loss", "down", "decline", "sell", "drop"]
        
        text = (title + " " + content).lower()
        pos_count = sum(word in text for word in positive_words)
        neg_count = sum(word in text for word in negative_words)
        
        if pos_count > neg_count:
            return SentimentResult(score=0.3, confidence=0.5, label="positive")
        elif neg_count > pos_count:
            return SentimentResult(score=-0.3, confidence=0.5, label="negative")
        else:
            return SentimentResult(score=0.0, confidence=0.5, label="neutral")
```

**Files to Create**:
- `/Users/martinrichards/code/TradingAgents/tradingagents/domains/news/clients/openrouter_sentiment_client.py`

**Test Requirements**:
- Sentiment analysis API tests with VCR
- Error handling tests
- Response parsing tests  
- Fallback mechanism tests

---

#### T006: OpenRouter Client - Vector Embeddings
**Priority**: Critical | **Duration**: 1-2 hours | **Dependencies**: T002

**Description**: Implement OpenRouter client for vector embeddings generation

**Acceptance Criteria**:
- [ ] OpenRouter embeddings API integration  
- [ ] Text preprocessing for embedding generation
- [ ] Batch processing for multiple articles
- [ ] 1536-dimensional vector validation
- [ ] Proper error handling and retries

**Implementation Details**:
```python
class OpenRouterEmbeddingsClient:
    def __init__(self, config: TradingAgentsConfig):
        self.api_key = config.openrouter_api_key
        self.model = "openai/text-embedding-ada-002"  # Via OpenRouter
        self.base_url = "https://openrouter.ai/api/v1"
        
    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts"""
        if not texts:
            return []
            
        try:
            async with aiohttp.ClientSession() as session:
                response = await self._make_embeddings_request(session, texts)
                embeddings = self._parse_embeddings_response(response)
                
                # Validate dimensions
                for i, embedding in enumerate(embeddings):
                    if len(embedding) != 1536:
                        raise ValueError(f"Invalid embedding dimension at index {i}: {len(embedding)}")
                
                return embeddings
        except Exception as e:
            logger.error(f"Embeddings generation failed: {e}")
            # Return zero vectors as fallback
            return [[0.0] * 1536 for _ in texts]
    
    async def generate_article_embeddings(self, article: NewsArticle) -> Tuple[List[float], List[float]]:
        """Generate embeddings for article title and content"""
        texts = []
        
        # Prepare texts for embedding
        if article.title:
            texts.append(self._preprocess_text(article.title))
        if article.summary:
            # Combine title and summary for comprehensive embedding  
            combined_text = f"{article.title} {article.summary}"
            texts.append(self._preprocess_text(combined_text))
        
        if not texts:
            return [0.0] * 1536, [0.0] * 1536
            
        embeddings = await self.generate_embeddings(texts)
        title_embedding = embeddings[0] if len(embeddings) > 0 else [0.0] * 1536
        content_embedding = embeddings[1] if len(embeddings) > 1 else [0.0] * 1536
        
        return title_embedding, content_embedding
    
    def _preprocess_text(self, text: str) -> str:
        """Preprocess text for optimal embedding generation"""
        # Remove extra whitespace and limit length
        cleaned = " ".join(text.split())
        return cleaned[:8000]  # OpenAI embedding limit
```

**Files to Create**:
- `/Users/martinrichards/code/TradingAgents/tradingagents/domains/news/clients/openrouter_embeddings_client.py`

**Test Requirements**:
- Embeddings API tests with VCR
- Batch processing tests
- Vector dimension validation tests
- Text preprocessing tests

---

#### T007: Enhance NewsService - LLM Integration  
**Priority**: Critical | **Duration**: 2-3 hours | **Dependencies**: T005, T006

**Description**: Integrate OpenRouter LLM clients into NewsService workflow

**Acceptance Criteria**:
- [ ] Replace keyword sentiment with LLM analysis
- [ ] Add embedding generation to article processing
- [ ] End-to-end article processing pipeline  
- [ ] Proper error handling and fallback strategies
- [ ] Integration with existing service methods

**Implementation Details**:
```python
class NewsService:
    def __init__(self, 
                 repository: NewsRepository,
                 config: TradingAgentsConfig):
        self.repository = repository
        self.config = config
        self.sentiment_client = OpenRouterSentimentClient(config)
        self.embeddings_client = OpenRouterEmbeddingsClient(config)
    
    async def process_articles_with_llm(self, articles: List[NewsArticle]) -> List[NewsArticle]:
        """Process articles with LLM sentiment analysis and embeddings"""
        processed_articles = []
        
        for article in articles:
            try:
                # Generate sentiment analysis
                sentiment_result = await self.sentiment_client.analyze_sentiment(
                    article.title, article.summary or ""
                )
                
                # Generate embeddings
                title_embedding, content_embedding = await self.embeddings_client.generate_article_embeddings(article)
                
                # Update article with LLM results
                article.sentiment_score = sentiment_result.score
                article.sentiment_confidence = sentiment_result.confidence
                article.sentiment_label = sentiment_result.label
                article.title_embedding = title_embedding
                article.content_embedding = content_embedding
                
                processed_articles.append(article)
                
            except Exception as e:
                logger.warning(f"Failed to process article {article.id}: {e}")
                # Add article without LLM processing
                processed_articles.append(article)
        
        return processed_articles
    
    async def collect_and_process_news(self, symbols: List[str]) -> List[NewsArticle]:
        """Complete pipeline: collect → process → store with LLM analysis"""
        # Collect raw articles (existing functionality)
        raw_articles = await self.collect_news_articles(symbols)
        
        # Process with LLM
        processed_articles = await self.process_articles_with_llm(raw_articles)
        
        # Store processed articles
        stored_articles = []
        for article in processed_articles:
            stored_article = await self.repository.create_article(article)
            stored_articles.append(stored_article)
        
        # Batch update embeddings for efficiency
        articles_with_embeddings = [a for a in stored_articles 
                                  if a.title_embedding or a.content_embedding]
        if articles_with_embeddings:
            await self.repository.batch_update_embeddings(articles_with_embeddings)
        
        return stored_articles
```

**Files to Modify**:
- `/Users/martinrichards/code/TradingAgents/tradingagents/domains/news/services/news_service.py`

**Test Requirements**:
- Integration tests with mocked LLM clients
- Article processing pipeline tests
- Error handling and fallback tests
- Performance tests for batch operations

---

### Phase 4: Scheduling

#### T008: APScheduler Integration - Job Scheduling
**Priority**: High | **Duration**: 3-4 hours | **Dependencies**: T003, T004, T007

**Description**: Implement scheduled news collection using APScheduler

**Acceptance Criteria**:
- [ ] APScheduler setup with PostgreSQL job store
- [ ] Scheduled job execution with proper error handling
- [ ] Job configuration loading and validation
- [ ] Status monitoring and failure recovery
- [ ] CLI integration for job management

**Implementation Details**:
```python
class ScheduledNewsCollector:
    def __init__(self, 
                 news_service: NewsService,
                 repository: NewsRepository,
                 config: TradingAgentsConfig):
        self.news_service = news_service
        self.repository = repository
        self.config = config
        self.scheduler = None
        
    async def initialize_scheduler(self):
        """Initialize APScheduler with PostgreSQL job store"""
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
        
        jobstore = SQLAlchemyJobStore(url=self.config.database_url, 
                                     tablename='apscheduler_jobs')
        
        self.scheduler = AsyncIOScheduler()
        self.scheduler.add_jobstore(jobstore, 'default')
        
    async def load_job_configurations(self):
        """Load and schedule all active job configurations"""
        job_configs = await self.repository.get_active_job_configs()
        
        for config in job_configs:
            try:
                await self._schedule_job(config)
            except Exception as e:
                logger.error(f"Failed to schedule job {config.name}: {e}")
    
    async def _schedule_job(self, job_config: NewsJobConfig):
        """Schedule a single job configuration"""
        job_id = f"news_collection_{job_config.id}"
        
        # Remove existing job if present
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
        
        # Add new job
        from apscheduler.triggers.cron import CronTrigger
        trigger = CronTrigger.from_crontab(job_config.frequency_cron)
        
        self.scheduler.add_job(
            self._execute_news_collection,
            trigger=trigger,
            id=job_id,
            args=[job_config],
            name=f"News collection: {job_config.name}",
            replace_existing=True
        )
        
    async def _execute_news_collection(self, job_config: NewsJobConfig):
        """Execute news collection for a job configuration"""
        try:
            logger.info(f"Starting news collection job: {job_config.name}")
            
            # Collect and process news
            articles = await self.news_service.collect_and_process_news(job_config.symbols)
            
            # Update job last run timestamp
            job_config.last_run = datetime.now(timezone.utc)
            await self.repository.update_job_config(job_config)
            
            logger.info(f"Completed news collection job: {job_config.name}, "
                       f"collected {len(articles)} articles")
                       
        except Exception as e:
            logger.error(f"News collection job failed: {job_config.name}, error: {e}")
            # Could implement notification/alerting here
            
    async def start_scheduler(self):
        """Start the scheduler"""
        if not self.scheduler:
            await self.initialize_scheduler()
            
        await self.load_job_configurations()
        self.scheduler.start()
        logger.info("News collection scheduler started")
        
    async def stop_scheduler(self):
        """Stop the scheduler"""
        if self.scheduler:
            self.scheduler.shutdown(wait=True)
            logger.info("News collection scheduler stopped")
```

**Files to Create**:
- `/Users/martinrichards/code/TradingAgents/tradingagents/domains/news/services/scheduled_news_collector.py`

**Test Requirements**:
- Job scheduling tests with test scheduler
- Job execution tests with mocked dependencies
- Error handling and retry tests
- Job configuration validation tests

---

#### T009: CLI Integration - Job Management Commands
**Priority**: Medium | **Duration**: 1-2 hours | **Dependencies**: T008

**Description**: Add CLI commands for news job management and manual execution

**Acceptance Criteria**:
- [ ] CLI commands for job creation/management
- [ ] Manual job execution commands
- [ ] Job status and monitoring commands
- [ ] Integration with existing CLI structure  
- [ ] Proper error handling and user feedback

**Implementation Details**:
```python
# Add to cli/commands/news_commands.py
@click.group()
def news():
    """News domain management commands"""
    pass

@news.group() 
def job():
    """Job management commands"""
    pass

@job.command()
@click.option('--name', required=True, help='Job name')
@click.option('--symbols', required=True, help='Comma-separated stock symbols')
@click.option('--frequency', required=True, help='Cron expression or simple frequency')
@click.option('--categories', help='Comma-separated news categories')
async def create(name: str, symbols: str, frequency: str, categories: str):
    """Create a new news collection job"""
    try:
        symbol_list = [s.strip().upper() for s in symbols.split(',')]
        category_list = [c.strip() for c in (categories or "").split(',')] if categories else []
        
        config = NewsJobConfig(
            name=name,
            symbols=symbol_list,
            categories=category_list,
            frequency_cron=frequency,
            enabled=True
        )
        
        # Validate configuration
        errors = config.validate()
        if errors:
            click.echo(f"❌ Invalid configuration: {errors}")
            return
            
        # Create job
        repository = NewsRepository(get_database_config())
        created_config = await repository.create_job_config(config)
        
        click.echo(f"✅ Created job: {created_config.name} (ID: {created_config.id})")
        
    except Exception as e:
        click.echo(f"❌ Failed to create job: {e}")

@job.command()
async def list():
    """List all job configurations"""
    try:
        repository = NewsRepository(get_database_config())
        configs = await repository.get_all_job_configs()
        
        if not configs:
            click.echo("No jobs configured")
            return
            
        click.echo("\n📋 News Collection Jobs:")
        click.echo("=" * 60)
        
        for config in configs:
            status = "🟢 Enabled" if config.enabled else "🔴 Disabled"
            last_run = config.last_run.strftime("%Y-%m-%d %H:%M") if config.last_run else "Never"
            
            click.echo(f"{config.name}")
            click.echo(f"  Status: {status}")
            click.echo(f"  Symbols: {', '.join(config.symbols)}")
            click.echo(f"  Schedule: {config.frequency_cron}")
            click.echo(f"  Last Run: {last_run}")
            click.echo()
            
    except Exception as e:
        click.echo(f"❌ Failed to list jobs: {e}")

@job.command()
@click.argument('job_id', type=str)
async def run(job_id: str):
    """Manually execute a job"""
    try:
        repository = NewsRepository(get_database_config())
        config = await repository.get_job_config(UUID(job_id))
        
        if not config:
            click.echo(f"❌ Job not found: {job_id}")
            return
            
        click.echo(f"🚀 Running job: {config.name}")
        
        # Execute job
        service = NewsService(repository, get_trading_config())
        articles = await service.collect_and_process_news(config.symbols)
        
        click.echo(f"✅ Completed: collected {len(articles)} articles")
        
    except Exception as e:
        click.echo(f"❌ Job execution failed: {e}")
```

**Files to Modify**:
- `/Users/martinrichards/code/TradingAgents/cli/commands/news_commands.py`

**Test Requirements**:
- CLI command tests with mocked services
- User input validation tests
- Output formatting tests

---

### Phase 5: Validation

#### T010: Integration Tests - End-to-End Workflow  
**Priority**: High | **Duration**: 2-3 hours | **Dependencies**: T007, T008

**Description**: Comprehensive integration tests for complete news domain workflow

**Acceptance Criteria**:
- [ ] End-to-end workflow tests from RSS to vector storage
- [ ] Agent integration tests via AgentToolkit
- [ ] Performance tests for daily collection volumes
- [ ] Error recovery and fallback tests
- [ ] Test coverage maintained above 85%

**Implementation Details**:
```python
# tests/domains/news/integration/test_news_workflow.py
class TestNewsWorkflowIntegration:
    
    @pytest.mark.asyncio
    async def test_complete_news_processing_pipeline(self, test_db, mock_openrouter):
        """Test complete pipeline from RSS to vector storage"""
        # Setup
        config = TradingAgentsConfig.from_test_config()
        repository = NewsRepository(test_db)
        service = NewsService(repository, config)
        
        # Mock OpenRouter responses
        mock_openrouter.sentiment_response = {
            "score": 0.7,
            "confidence": 0.85, 
            "label": "positive"
        }
        mock_openrouter.embeddings_response = [[0.1] * 1536]
        
        # Execute pipeline
        articles = await service.collect_and_process_news(["AAPL"])
        
        # Verify results
        assert len(articles) > 0
        assert all(a.sentiment_score is not None for a in articles)
        assert all(a.title_embedding is not None for a in articles)
        
        # Verify database storage
        stored_articles = await repository.get_articles_by_symbol("AAPL")
        assert len(stored_articles) == len(articles)
        
        # Test vector similarity search
        similar = await repository.find_similar_articles(
            articles[0].title_embedding, limit=5
        )
        assert len(similar) > 0
    
    @pytest.mark.asyncio
    async def test_agent_toolkit_integration(self, test_db):
        """Test integration with AgentToolkit for RAG queries"""
        from tradingagents.agents.libs.toolkit import AgentToolkit
        
        # Setup with real data
        toolkit = AgentToolkit(test_db)
        
        # Test news context retrieval
        context = await toolkit.get_news_context("AAPL", days=7)
        assert "articles" in context
        assert "sentiment_summary" in context
        
        # Test vector similarity for context
        similar_context = await toolkit.get_similar_news(
            "Apple earnings beat expectations", limit=5
        )
        assert len(similar_context) <= 5
    
    @pytest.mark.asyncio  
    async def test_scheduler_integration(self, test_db):
        """Test APScheduler integration with job management"""
        config = TradingAgentsConfig.from_test_config()
        repository = NewsRepository(test_db)
        service = NewsService(repository, config)
        scheduler = ScheduledNewsCollector(service, repository, config)
        
        # Create test job configuration
        job_config = NewsJobConfig(
            name="test_job",
            symbols=["AAPL"],
            frequency_cron="0 */6 * * *",  # Every 6 hours
            enabled=True
        )
        await repository.create_job_config(job_config)
        
        # Test scheduler initialization
        await scheduler.initialize_scheduler()
        await scheduler.load_job_configurations()
        
        # Verify job was scheduled
        assert scheduler.scheduler.get_job(f"news_collection_{job_config.id}") is not None
        
        # Test manual job execution
        await scheduler._execute_news_collection(job_config)
        
        # Verify execution updated last_run
        updated_config = await repository.get_job_config(job_config.id)
        assert updated_config.last_run is not None
        
    @pytest.mark.asyncio
    async def test_error_recovery_and_fallbacks(self, test_db):
        """Test error handling and fallback mechanisms"""
        config = TradingAgentsConfig.from_test_config()
        repository = NewsRepository(test_db)
        service = NewsService(repository, config)
        
        # Test with failing LLM client
        with patch.object(service.sentiment_client, 'analyze_sentiment', side_effect=Exception("API Error")):
            articles = await service.collect_and_process_news(["AAPL"])
            
            # Should still process articles with fallback
            assert len(articles) > 0
            # Should have fallback sentiment values
            assert any(a.sentiment_score is not None for a in articles)
    
    @pytest.mark.asyncio
    async def test_performance_benchmarks(self, test_db):
        """Test performance meets requirements"""
        config = TradingAgentsConfig.from_test_config()
        repository = NewsRepository(test_db)
        
        # Create test articles with embeddings
        test_articles = await self._create_test_articles_with_embeddings(repository, count=1000)
        
        # Test query performance (< 100ms requirement)
        start_time = time.time()
        articles = await repository.get_recent_articles_by_symbol("AAPL", days=30)
        query_time = (time.time() - start_time) * 1000
        
        assert query_time < 100, f"Query took {query_time}ms, should be < 100ms"
        
        # Test vector similarity performance (< 1s requirement)
        start_time = time.time()
        similar = await repository.find_similar_articles(
            test_articles[0].title_embedding, limit=10
        )
        vector_time = (time.time() - start_time) * 1000
        
        assert vector_time < 1000, f"Vector search took {vector_time}ms, should be < 1s"
```

**Files to Create**:
- `/Users/martinrichards/code/TradingAgents/tests/domains/news/integration/test_news_workflow.py`

**Test Requirements**:
- Full workflow integration tests
- AgentToolkit integration tests
- Performance benchmark tests
- Error scenario tests

---

#### T011: Documentation and Monitoring
**Priority**: Medium | **Duration**: 1-2 hours | **Dependencies**: T010

**Description**: Update documentation and add monitoring for new functionality

**Acceptance Criteria**:
- [ ] Updated API documentation for new methods
- [ ] Job scheduling configuration examples
- [ ] Performance monitoring dashboard queries
- [ ] Troubleshooting guide for common issues
- [ ] Agent integration documentation

**Files to Modify**:
- `/Users/martinrichards/code/TradingAgents/docs/domains/news.md`
- `/Users/martinrichards/code/TradingAgents/docs/api-reference.md`

**Test Requirements**:
- Documentation accuracy validation
- Configuration example testing

---

## Parallel Development Opportunities

### AI Agent Collaboration Points

**Tasks T005 & T006** can be developed in parallel:
- Both are independent OpenRouter client implementations
- Different LLM capabilities (sentiment vs embeddings)
- Can be tested independently with VCR cassettes

**Phase 1 Tasks (T001, T002, T003)** have minimal dependencies:
- T002 and T003 both depend on T001 but can be developed simultaneously
- Entity layer changes are independent of each other

### Critical Path Analysis

**Critical Path**: T001 → T002/T003 → T004 → T005/T006 → T007 → T008

**Parallel Opportunities**:
1. **Foundation Phase**: T002 + T003 (after T001)
2. **LLM Integration**: T005 + T006 (after T002) 
3. **Testing**: Unit tests alongside implementation

### Risk Mitigation Strategies

**LLM API Dependencies**:
- Implement comprehensive fallback strategies
- Use VCR for deterministic testing
- Mock clients for unit tests

**Database Performance**:
- Test with realistic data volumes
- Monitor query performance during development
- Use proper indexes for vector operations

**Integration Complexity**:
- Build incrementally with testing at each step
- Maintain backward compatibility
- Use feature flags for gradual rollout

---

## Success Metrics

**Technical Metrics**:
- Test coverage >85% maintained
- Query performance <100ms
- Vector search performance <1s
- Zero breaking changes to AgentToolkit

**Functional Metrics**:
- Successful OpenRouter-only LLM integration
- Scheduled jobs executing reliably
- Agent context enriched with sentiment and similarity

**Quality Metrics**:
- All acceptance criteria met
- Comprehensive error handling
- Production-ready monitoring and documentation

---

## Implementation Guidelines

### TDD Approach
**Every task follows**: Write test → Write code → Refactor

### Layered Architecture Pattern
**Strict adherence to**: Database → Entity → Repository → Service → Scheduling

### Error Handling Strategy
**Graceful fallbacks** for all LLM API dependencies

### Performance Requirements  
**Async operations** with proper connection pooling throughout

### Testing Strategy
**Unit tests + Integration tests + VCR** for external API calls

---

This comprehensive task breakdown provides clear implementation guidance for completing the final 5% of the news domain while maintaining architectural consistency and leveraging AI-assisted development patterns.