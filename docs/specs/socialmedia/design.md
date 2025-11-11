# Social Media Domain - Technical Design Document

## Executive Summary

This document specifies the complete greenfield implementation of the Social Media domain within TradingAgents, transitioning from empty stubs to a production-ready system for collecting and analyzing social media sentiment from financial subreddits. This domain will provide AI agents with social sentiment context for trading decisions through a PostgreSQL + TimescaleDB + pgvectorscale architecture with RAG-powered capabilities.

**Implementation Scope**: Complete domain implementation (0% → 100% completion)
**Architecture**: PostgreSQL + TimescaleDB + pgvectorscale with PRAW Reddit integration and OpenRouter LLM processing
**Target**: 400+ posts daily across 4 financial subreddits with 85%+ test coverage

---

## 1. Architecture Overview

### 1.1 System Architecture

The Social Media domain follows the established layered architecture pattern while introducing new capabilities for social media data collection and semantic search:

```
┌─────────────────────────────────────────────────────────────┐
│                    Dagster Pipeline                         │
│                 (Scheduled Collection)                      │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│                 RedditClient                                │
│           (PRAW + Rate Limiting)                           │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│              SocialMediaService                             │
│        (Business Logic + LLM Integration)                  │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│              SocialRepository                               │
│    (PostgreSQL + TimescaleDB + pgvectorscale)             │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│         PostgreSQL + TimescaleDB + pgvectorscale           │
│          (Time-series + Vector Storage)                    │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 Data Flow Architecture

**Collection Flow:**
```
Reddit API → RedditClient → SocialMediaService → OpenRouter LLM → 
SocialRepository → PostgreSQL + Vector Storage
```

**Agent Query Flow:**
```
AgentToolkit → SocialMediaService → SocialRepository → 
Vector Similarity Search + Sentiment Aggregation → Structured Response
```

### 1.3 Key Architectural Principles

- **Consistent Patterns**: Follow news domain architecture for maintainability
- **Vector-Enhanced Search**: Semantic similarity using pgvectorscale for contextual social media analysis
- **Best-Effort Processing**: Continue operation even when LLM services are unavailable
- **Rate Limiting Compliance**: Respect Reddit API limits with exponential backoff
- **Event-Driven Design**: Publish domain events for system integration

---

## 2. Domain Model

### 2.1 Core Entities

#### SocialPost (Domain Entity)

The primary domain entity managing business rules and data transformations:

```python
@dataclass
class SocialPost:
    """Core domain entity for Reddit posts with sentiment and engagement data."""
    
    # Core Reddit Data
    post_id: str                    # Reddit unique ID (e.g., 't3_abc123')
    title: str                      # Post title
    content: Optional[str]          # Post content (selftext for text posts)
    author: str                     # Reddit username
    subreddit: str                  # Subreddit name
    created_utc: datetime           # Post creation time
    url: str                        # Reddit permalink or external URL
    
    # Engagement Metrics
    upvotes: int                    # Post score
    downvotes: int                  # Calculated from score + upvote_ratio
    comments_count: int             # Number of comments
    
    # Enhanced Data
    sentiment_score: Optional[SentimentScore] = None
    tickers: List[str] = field(default_factory=list)
    title_embedding: Optional[List[float]] = None
    content_embedding: Optional[List[float]] = None
    
    def from_praw_submission(cls, submission: praw.Submission) -> 'SocialPost':
        """Create SocialPost from PRAW Submission object."""
        
    def to_entity(self) -> SocialMediaPostEntity:
        """Transform to database entity for storage."""
        
    def validate(self) -> List[str]:
        """Validate business rules and return errors."""
        
    def extract_tickers(self) -> List[str]:
        """Extract stock ticker symbols from title and content."""
        
    def has_reliable_sentiment(self) -> bool:
        """Check if sentiment confidence >= 0.5."""
        
    def to_response(self) -> Dict[str, Any]:
        """Format for agent consumption."""
```

**Validation Rules:**
- `post_id` must match Reddit format (starts with 't3_')
- `title` cannot be empty
- `created_utc` cannot be in the future
- `sentiment_score.confidence` must be 0.0-1.0
- `embeddings` must be 1536 dimensions if present
- `subreddit` must be in allowed financial subreddits list

#### SentimentScore (Value Object)

Structured sentiment analysis result from OpenRouter LLM:

```python
@dataclass
class SentimentScore:
    """Structured sentiment analysis result with confidence and reasoning."""
    
    sentiment: Literal['positive', 'negative', 'neutral']
    confidence: float  # 0.0-1.0
    reasoning: str     # Brief explanation
    
    def is_reliable(self) -> bool:
        """Check if confidence >= 0.5 for reliable sentiment."""
        return self.confidence >= 0.5
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON storage."""
```

#### SocialJobConfig (Configuration)

Configuration for scheduled Reddit collection:

```python
@dataclass
class SocialJobConfig:
    """Configuration for scheduled Reddit data collection."""
    
    # Collection Settings
    subreddits: List[str] = field(default_factory=lambda: [
        'wallstreetbets', 'investing', 'stocks', 'SecurityAnalysis'
    ])
    max_posts_per_subreddit: int = 50
    lookback_hours: int = 12
    min_score: int = 10
    
    # Processing Settings
    sentiment_model: str = "anthropic/claude-3.5-haiku"
    embedding_model: str = "text-embedding-3-large"
    
    # Rate Limiting
    rate_limit_delay: float = 1.0  # seconds between API calls
    
    # Scheduling
    schedule_times: List[str] = field(default_factory=lambda: [
        '0 6 * * *',   # 6 AM UTC
        '0 18 * * *'   # 6 PM UTC
    ])
```

---

## 3. Database Design

### 3.1 Schema Definition

The `social_media_posts` table leverages PostgreSQL with TimescaleDB for time-series optimization and pgvectorscale for vector similarity search:

```sql
-- Core table definition
CREATE TABLE social_media_posts (
    id UUID PRIMARY KEY DEFAULT uuid7(),
    post_id VARCHAR(50) UNIQUE NOT NULL,
    title TEXT NOT NULL,
    content TEXT,
    author VARCHAR(100) NOT NULL,
    subreddit VARCHAR(50) NOT NULL,
    created_utc TIMESTAMPTZ NOT NULL,
    upvotes INTEGER NOT NULL DEFAULT 0,
    downvotes INTEGER NOT NULL DEFAULT 0,
    comments_count INTEGER NOT NULL DEFAULT 0,
    url TEXT NOT NULL,
    sentiment_score JSONB,
    sentiment_label VARCHAR(20),
    tickers TEXT[] DEFAULT '{}',
    title_embedding VECTOR(1536),
    content_embedding VECTOR(1536),
    inserted_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- TimescaleDB hypertable for time-series optimization
SELECT create_hypertable('social_media_posts', 'created_utc', 
                         chunk_time_interval => INTERVAL '1 day');

-- Performance indexes
CREATE UNIQUE INDEX idx_social_posts_post_id ON social_media_posts (post_id);
CREATE INDEX idx_social_posts_subreddit_time ON social_media_posts (subreddit, created_utc DESC);
CREATE INDEX idx_social_posts_tickers_gin ON social_media_posts USING GIN (tickers);
CREATE INDEX idx_social_posts_title_embedding ON social_media_posts 
    USING vectors (title_embedding vector_cosine_ops);
CREATE INDEX idx_social_posts_content_embedding ON social_media_posts 
    USING vectors (content_embedding vector_cosine_ops);
CREATE INDEX idx_social_posts_sentiment ON social_media_posts 
    (((sentiment_score->>'sentiment'))) WHERE sentiment_score IS NOT NULL;

-- Data validation constraints
ALTER TABLE social_media_posts ADD CONSTRAINT chk_sentiment_score 
    CHECK (sentiment_score IS NULL OR 
           ((sentiment_score->>'confidence')::float BETWEEN 0 AND 1));
ALTER TABLE social_media_posts ADD CONSTRAINT chk_created_utc 
    CHECK (created_utc <= NOW());
```

### 3.2 SQLAlchemy Entity

```python
class SocialMediaPostEntity(Base):
    """SQLAlchemy entity for PostgreSQL persistence with vector support."""
    
    __tablename__ = "social_media_posts"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    post_id = Column(String(50), unique=True, nullable=False, index=True)
    title = Column(Text, nullable=False)
    content = Column(Text)
    author = Column(String(100), nullable=False)
    subreddit = Column(String(50), nullable=False)
    created_utc = Column(DateTime(timezone=True), nullable=False)
    upvotes = Column(Integer, nullable=False, default=0)
    downvotes = Column(Integer, nullable=False, default=0)
    comments_count = Column(Integer, nullable=False, default=0)
    url = Column(Text, nullable=False)
    sentiment_score = Column(JSONB)
    sentiment_label = Column(String(20))
    tickers = Column(ARRAY(String), default=[])
    title_embedding = Column(Vector(1536))
    content_embedding = Column(Vector(1536))
    inserted_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
    
    def to_domain(self) -> SocialPost:
        """Convert to domain entity."""
        
    @classmethod
    def from_domain(cls, post: SocialPost) -> 'SocialMediaPostEntity':
        """Create from domain entity."""
```

### 3.3 Access Patterns and Query Optimization

**Common Access Patterns:**
- Ticker-based queries: `SELECT * WHERE 'AAPL' = ANY(tickers)`
- Time-range filtering: `SELECT * WHERE created_utc BETWEEN ? AND ?`
- Vector similarity: `SELECT * ORDER BY embedding <=> ? LIMIT 10`
- Sentiment aggregations: `SELECT AVG(sentiment_score) GROUP BY subreddit`

**Performance Targets:**
- Vector similarity queries: < 1s for top 10 results
- Batch upserts: < 5s for 1000 posts
- Ticker-based queries: < 100ms for 30-day ranges

---

## 4. API Integration

### 4.1 Reddit Client (PRAW Integration)

Complete implementation of Reddit data collection using PRAW (Python Reddit API Wrapper):

```python
class RedditClient:
    """PRAW wrapper with rate limiting and error handling."""
    
    def __init__(self, config: RedditClientConfig):
        """Initialize Reddit client with OAuth2 credentials."""
        self.reddit = praw.Reddit(
            client_id=config.client_id,
            client_secret=config.client_secret,
            user_agent=config.user_agent
        )
        self.rate_limiter = AsyncLimiter(1, 1)  # 1 request per second
        
    async def fetch_subreddit_posts(
        self, 
        subreddit: str, 
        limit: int = 50, 
        time_filter: str = 'day'
    ) -> List[Dict[str, Any]]:
        """Fetch hot posts from subreddit with rate limiting."""
        
    async def search_posts(
        self, 
        query: str, 
        subreddit: Optional[str] = None, 
        limit: int = 25
    ) -> List[Dict[str, Any]]:
        """Search posts with ticker symbols or keywords."""
        
    async def get_post_details(self, post_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information for a specific post."""
```

**Configuration Requirements:**
- Reddit App Credentials: `client_id`, `client_secret`, `user_agent`
- Rate Limiting: 1 request per second (60 requests/minute limit)
- Error Handling: Exponential backoff for rate limits, graceful degradation for authentication errors

### 4.2 OpenRouter LLM Integration

Leverage existing OpenRouter infrastructure with social media-specific enhancements:

**Sentiment Analysis Prompt:**
```
Analyze this Reddit post about stocks/finance. Consider the informal language, 
memes, and community context typical of financial subreddits.

Post: {title} - {content}

Respond with valid JSON:
{
  "sentiment": "positive|negative|neutral",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation considering context"
}
```

**Embedding Configuration:**
- Model: `text-embedding-3-large` (1536 dimensions)
- Batch processing for efficiency
- Generate embeddings for both title and content when available
- Store NULL for failed embedding generation (best-effort processing)

---

## 5. Component Architecture

### 5.1 Repository Layer (Data Access)

```python
class SocialRepository:
    """Data access layer for social media posts with vector capabilities."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        
    async def find_by_ticker(
        self, 
        ticker: str, 
        days: int = 30, 
        limit: int = 50
    ) -> List[SocialPost]:
        """Find posts mentioning specific ticker within time range."""
        
    async def find_similar_posts(
        self, 
        query_embedding: List[float], 
        ticker: Optional[str] = None, 
        limit: int = 10
    ) -> List[SocialPost]:
        """Find semantically similar posts using vector similarity."""
        
    async def get_sentiment_summary(
        self, 
        ticker: str, 
        subreddit: Optional[str] = None, 
        hours: int = 24
    ) -> Dict[str, Any]:
        """Generate sentiment aggregation for ticker."""
        
    async def upsert_batch(self, posts: List[SocialPost]) -> List[SocialPost]:
        """Batch upsert posts with conflict resolution."""
        
    async def cleanup_old_posts(self, days: int = 90) -> int:
        """Remove posts older than retention period."""
```

### 5.2 Service Layer (Business Logic)

```python
class SocialMediaService:
    """Business logic orchestration with LLM integration."""
    
    def __init__(
        self, 
        repository: SocialRepository,
        reddit_client: RedditClient,
        openrouter_client: OpenRouterClient
    ):
        self.repository = repository
        self.reddit_client = reddit_client
        self.openrouter_client = openrouter_client
        
    async def collect_subreddit_posts(self, config: SocialJobConfig) -> int:
        """Orchestrate complete collection process for configured subreddits."""
        
    async def update_post_sentiment(
        self, 
        posts: List[SocialPost]
    ) -> List[SocialPost]:
        """Add sentiment analysis to posts using OpenRouter LLM."""
        
    async def generate_embeddings(
        self, 
        posts: List[SocialPost]
    ) -> List[SocialPost]:
        """Generate vector embeddings for semantic search."""
        
    async def find_trending_tickers(
        self, 
        hours: int = 24
    ) -> List[Dict[str, Any]]:
        """Identify trending ticker mentions across subreddits."""
```

### 5.3 Agent Integration Layer

```python
class SocialMediaAgentToolkit:
    """RAG methods for AI agent integration."""
    
    def __init__(self, service: SocialMediaService):
        self.service = service
        
    async def get_reddit_sentiment(
        self, 
        ticker: str, 
        days: int = 7
    ) -> Dict[str, Any]:
        """Get sentiment summary for ticker from Reddit discussions."""
        
    async def search_social_posts(
        self, 
        query: str, 
        ticker: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Semantic search for relevant social media posts."""
        
    async def get_trending_discussions(
        self, 
        ticker: str
    ) -> List[Dict[str, Any]]:
        """Get trending discussions and sentiment for specific ticker."""
        
    async def get_subreddit_analysis(
        self, 
        subreddit: str, 
        ticker: str
    ) -> Dict[str, Any]:
        """Analyze sentiment and engagement for ticker in specific subreddit."""
```

**Agent Response Format:**
```json
{
  "posts": [
    {
      "post_id": "t3_abc123",
      "title": "AAPL earnings beat expectations",
      "subreddit": "stocks",
      "created_utc": "2024-01-15T14:30:00Z",
      "sentiment": {
        "sentiment": "positive",
        "confidence": 0.85,
        "reasoning": "Strong positive language about earnings"
      },
      "engagement": {
        "upvotes": 245,
        "comments_count": 67
      },
      "tickers": ["AAPL"],
      "url": "https://reddit.com/r/stocks/comments/abc123"
    }
  ],
  "summary": {
    "total_posts": 15,
    "sentiment_breakdown": {
      "positive": 0.6,
      "negative": 0.2,
      "neutral": 0.2
    },
    "avg_confidence": 0.78,
    "data_quality": "high"
  }
}
```

---

## 6. Dagster Pipeline Architecture

### 6.1 Scheduled Collection Pipeline

```python
@asset(
    partitions_def=DailyPartitionsDefinition(start_date="2024-01-01"),
    config_schema=SocialJobConfig.schema()
)
def reddit_posts_collection(context: AssetExecutionContext) -> MaterializeResult:
    """Collect Reddit posts from financial subreddits."""
    
@asset(deps=[reddit_posts_collection])
def reddit_sentiment_analysis(context: AssetExecutionContext) -> MaterializeResult:
    """Add sentiment analysis to collected posts."""
    
@asset(deps=[reddit_sentiment_analysis])
def reddit_embeddings_generation(context: AssetExecutionContext) -> MaterializeResult:
    """Generate vector embeddings for semantic search."""

# Schedule: Twice daily collection
reddit_collection_schedule = ScheduleDefinition(
    name="reddit_collection_schedule",
    job=define_asset_job("reddit_collection", selection=[
        reddit_posts_collection,
        reddit_sentiment_analysis,
        reddit_embeddings_generation
    ]),
    cron_schedule="0 6,18 * * *"  # 6 AM and 6 PM UTC
)
```

### 6.2 Data Quality and Monitoring

**Collection Metrics:**
- Posts collected per subreddit per run
- Sentiment analysis success rate
- Embedding generation success rate
- API error rates and retry attempts

**Data Quality Checks:**
- Post deduplication verification
- Sentiment confidence distribution
- Embedding vector validation
- Reddit API rate limit utilization

**Failure Handling:**
- Best-effort processing: Continue with remaining subreddits if one fails
- Exponential backoff for Reddit API rate limits
- Graceful degradation: Store posts without sentiment/embeddings if LLM fails
- Dead letter queue for failed posts with retry mechanism

---

## 7. Testing Strategy

### 7.1 Test Structure

Following the project's pragmatic outside-in TDD approach:

```
tests/domains/socialmedia/
├── __init__.py
├── test_social_post.py                 # Domain entity validation
├── test_social_repository.py           # PostgreSQL + vector operations
├── test_reddit_client.py               # PRAW integration with VCR
├── test_social_media_service.py        # Business logic with mocked deps
├── test_social_agent_toolkit.py        # Agent integration methods
└── fixtures/
    ├── reddit_responses.json           # Sample PRAW responses
    └── vcr_cassettes/                   # HTTP cassettes for external APIs
```

### 7.2 Testing Approach

**Unit Tests (Mock I/O boundaries):**
- `SocialPost` entity validation and transformations
- `SocialRepository` with test PostgreSQL database
- `RedditClient` with mocked PRAW responses
- `SocialMediaService` with mocked dependencies

**Integration Tests (Real components):**
- End-to-end collection pipeline with test Reddit data
- Vector similarity search with actual pgvectorscale
- LLM integration with pytest-vcr cassettes
- Dagster pipeline execution

**Performance Tests:**
- Vector similarity query performance (< 1s target)
- Batch upsert performance (< 5s for 1000 posts)
- Memory usage during large collection runs

### 7.3 Test Fixtures and Mocking

**Reddit API Mocking:**
```python
@pytest.fixture
def mock_reddit_response():
    """Sample Reddit API response for testing."""
    return {
        "id": "abc123",
        "title": "AAPL earnings discussion",
        "selftext": "Strong quarter, bullish outlook",
        "author": "test_user",
        "subreddit_display_name": "stocks",
        "created_utc": 1705315200,
        "score": 150,
        "upvote_ratio": 0.85,
        "num_comments": 45,
        "permalink": "/r/stocks/comments/abc123/aapl_earnings/"
    }
```

**Vector Similarity Testing:**
```python
@pytest.mark.asyncio
async def test_vector_similarity_search(social_repository, sample_posts):
    """Test semantic similarity search using pgvectorscale."""
    # Insert test posts with embeddings
    await social_repository.upsert_batch(sample_posts)
    
    # Test similarity search
    query_embedding = [0.1] * 1536  # Sample embedding
    similar_posts = await social_repository.find_similar_posts(
        query_embedding, limit=5
    )
    
    assert len(similar_posts) <= 5
    assert all(post.title_embedding for post in similar_posts)
```

---

## 8. Implementation Roadmap

### 8.1 Phase 1: Database Foundation (Week 1)

**Priority 1: Database Schema**
1. Create PostgreSQL migration for `social_media_posts` table
2. Add TimescaleDB hypertable configuration
3. Set up pgvectorscale indexes for vector similarity
4. Implement data validation constraints

**Priority 2: Core Entities**
1. `SocialMediaPostEntity` (SQLAlchemy entity)
2. `SocialPost` (domain entity with validation)
3. `SentimentScore` (value object)
4. Entity transformation methods (`to_domain`, `from_domain`)

### 8.2 Phase 2: Data Collection (Week 2)

**Priority 1: Reddit Integration**
1. `RedditClient` with PRAW implementation
2. Rate limiting and error handling
3. Subreddit post collection methods
4. Reddit API authentication setup

**Priority 2: Repository Layer**
1. `SocialRepository` with PostgreSQL operations
2. Vector similarity search methods
3. Batch upsert operations
4. Sentiment aggregation queries

### 8.3 Phase 3: Processing & Intelligence (Week 3)

**Priority 1: Service Layer**
1. `SocialMediaService` business logic
2. OpenRouter LLM integration for sentiment
3. Vector embedding generation
4. Batch processing workflows

**Priority 2: Agent Integration**
1. `SocialMediaAgentToolkit` RAG methods
2. Structured response formatting
3. Context-aware social media analysis
4. Integration with existing agent workflows

### 8.4 Phase 4: Automation & Monitoring (Week 4)

**Priority 1: Dagster Pipeline**
1. Scheduled Reddit collection assets
2. Processing pipeline orchestration
3. Data quality monitoring
4. Error handling and retry logic

**Priority 2: Testing & Documentation**
1. Comprehensive test suite (>85% coverage)
2. Performance testing and optimization
3. API documentation updates
4. Integration with existing test infrastructure

---

## 9. Monitoring and Observability

### 9.1 Key Metrics

**Collection Metrics:**
- Posts collected per subreddit per day
- Collection job success/failure rates
- Reddit API rate limit utilization
- Data deduplication effectiveness

**Processing Metrics:**
- Sentiment analysis success rate and latency
- Embedding generation success rate and latency
- LLM token usage and costs
- Vector similarity query performance

**Business Metrics:**
- Active tickers with social sentiment data
- Sentiment distribution across subreddits
- Trending ticker detection accuracy
- Agent query response times

### 9.2 Alerting Strategy

**Critical Alerts:**
- Collection job failures (> 2 consecutive failures)
- Reddit API authentication errors
- Database connection failures
- High LLM processing error rates (> 20%)

**Warning Alerts:**
- Low collection volumes (< 50% of expected)
- High sentiment analysis latency (> 30s per batch)
- Vector similarity performance degradation
- Approaching Reddit API rate limits

### 9.3 Logging and Debugging

**Structured Logging Format:**
```json
{
  "timestamp": "2024-01-15T14:30:00Z",
  "level": "INFO",
  "component": "SocialMediaService",
  "operation": "collect_subreddit_posts",
  "subreddit": "stocks",
  "posts_collected": 45,
  "sentiment_analyzed": 43,
  "embeddings_generated": 41,
  "duration_ms": 12500,
  "metadata": {
    "reddit_api_calls": 3,
    "llm_tokens_used": 15420
  }
}
```

---

## 10. Security and Compliance

### 10.1 Data Privacy

**Reddit Data Handling:**
- Store only publicly available Reddit posts
- Respect user privacy: hash usernames for analytics
- Implement data retention policies (90-day maximum)
- No collection of private or deleted content

**API Key Management:**
- Environment variable storage for Reddit credentials
- OpenRouter API key rotation support
- No credential logging or persistence in plain text

### 10.2 Rate Limiting Compliance

**Reddit API Compliance:**
- Respect 60 requests per minute OAuth limit
- Implement exponential backoff for rate limit violations
- User-Agent string identification as required
- Monitor and log API usage statistics

**OpenRouter Usage:**
- Monitor token usage and costs
- Implement request batching for efficiency
- Handle API rate limits gracefully
- Cost optimization through model selection

---

## 11. Future Enhancements

### 11.1 Extended Social Media Sources

**Twitter/X Integration:**
- Similar architecture pattern for Twitter API v2
- Real-time streaming for high-frequency updates
- Hashtag and mention tracking

**News Comment Sections:**
- Integration with financial news comment sections
- Cross-platform sentiment correlation
- Enhanced context for news articles

### 11.2 Advanced Analytics

**Sentiment Trend Analysis:**
- Time-series sentiment tracking
- Volatility correlation with social sentiment
- Predictive sentiment modeling

**Influence Network Analysis:**
- User influence scoring based on engagement
- Community detection within financial subreddits
- Viral content identification and tracking

### 11.3 Real-time Processing

**Streaming Architecture:**
- Real-time Reddit post collection
- Event-driven sentiment processing
- Live sentiment dashboards for agents

**Market Hours Integration:**
- Increased collection frequency during market hours
- After-hours sentiment tracking
- Weekend vs. weekday sentiment patterns

---

This technical design provides a comprehensive blueprint for implementing the complete Social Media domain from empty stubs to a production-ready system. The architecture leverages proven patterns from the news domain while introducing specialized capabilities for social media data collection, semantic search, and AI agent integration.