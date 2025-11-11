# Social Media Domain - Specification Lite

## Summary
Complete implementation of social media data collection from Reddit with LLM sentiment analysis and vector embeddings for AI agent RAG integration.

## Core Requirements

### Data Collection
- **Daily Reddit collection** from financial subreddits (wallstreetbets, investing, stocks, SecurityAnalysis)
- **OpenRouter LLM sentiment analysis** with confidence scoring
- **Vector embeddings** for semantic similarity search  
- **PostgreSQL storage** with TimescaleDB + pgvectorscale optimization

### Agent Integration
- **AgentToolkit methods**: `get_reddit_news()` and `get_reddit_stock_info()`
- **RAG-enhanced queries** with < 2 second response time
- **Vector similarity search** for contextual social media insights

## Technical Implementation

### Architecture Pattern
**Router → Service → Repository → Entity → Database** (matching news domain)

### Database Schema
```sql
social_media_posts (
    post_id, ticker, subreddit, title, content, author,
    created_at, upvotes, comment_count, 
    sentiment_score, sentiment_label, sentiment_confidence,
    embedding vector(1536), -- pgvectorscale
    data_quality_score, processing_status
)
```

### Key Components

#### 1. RedditClient 
- PRAW integration with rate limiting
- Financial subreddit targeting
- Ticker-specific post filtering

#### 2. SentimentAnalyzer
- OpenRouter LLM integration
- Structured sentiment scoring (-1.0 to +1.0)
- Financial context awareness

#### 3. SocialRepository
- PostgreSQL with deduplication by post_id
- Vector similarity search using pgvectorscale
- TimescaleDB time-series optimization

#### 4. SocialMediaService  
- Orchestrates collection pipeline: Reddit → Sentiment → Embeddings → Storage
- Provides ticker-specific social context
- Calculates aggregate sentiment metrics

#### 5. AgentToolkit Integration
```python
async def get_reddit_news(ticker: str, days: int = 7) -> str:
    # Returns formatted social media context with sentiment analysis
    
async def get_reddit_stock_info(ticker: str, query: Optional[str] = None) -> str:  
    # Returns semantic search results with sentiment aggregation
```

## Implementation Scope

### Complete Implementation ✅
- PostgreSQL migration from file storage
- Reddit API client (currently empty stub)
- SQLAlchemy entities with vector fields
- LLM sentiment analysis pipeline
- Vector embedding generation and search
- Dagster pipeline for scheduled collection
- Comprehensive test coverage (pytest-vcr for APIs)

### Current Status
**Basic stub implementation** - requires complete rebuild of all components

### Dependencies
- Reddit API credentials (PRAW)
- OpenRouter API access
- PostgreSQL with TimescaleDB + pgvectorscale
- Existing TradingAgentsConfig
- News domain patterns for consistency

## Data Flow
1. **Dagster pipeline** triggers daily collection
2. **RedditClient** fetches posts from financial subreddits  
3. **SentimentAnalyzer** processes posts via OpenRouter LLM
4. **EmbeddingGenerator** creates vector embeddings
5. **SocialRepository** stores in PostgreSQL with deduplication
6. **AI Agents** query via AgentToolkit with RAG-enhanced context

## Testing Strategy
- **pytest-vcr** for Reddit API mocking
- **Real PostgreSQL** for repository integration tests
- **Service mocks** for business logic testing
- **85%+ coverage** matching project standards

## Success Criteria
- Daily automated Reddit collection with sentiment analysis
- Sub-2-second agent queries with vector search
- Seamless RAG integration matching news domain patterns
- Production-ready reliability with comprehensive error handling