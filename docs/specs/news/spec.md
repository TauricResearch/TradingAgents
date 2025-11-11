# News Domain Completion Specification

## Feature Overview

Complete the final 5% of the news domain by adding scheduled execution, LLM sentiment analysis, and vector embeddings to the existing 95% complete infrastructure. This enables automated daily news collection with advanced sentiment analysis and semantic search capabilities for News Analysts in the multi-agent trading framework.

## User Story

**Primary User**: Dagster Job (automated system)  
**Secondary Users**: News Analysts (LLM agents)

> As a Dagster Job, I want to automatically fetch Google News articles for tracked tickers, extract content, perform LLM sentiment analysis, and store with embeddings in the database, so that News Analysts can access comprehensive, up-to-date news data for trading decisions.

## Acceptance Criteria

### AC1: Scheduled Execution
**GIVEN** a scheduled job runs daily  
**WHEN** it executes  
**THEN** it fetches news for all configured tickers without manual intervention

**Validation**:
- Job executes at configured time (default: daily at 6 AM UTC)
- All tickers in configuration are processed
- Job completion status is logged with metrics

### AC2: Content Extraction Resilience  
**GIVEN** a news article is found  
**WHEN** content extraction fails due to paywall  
**THEN** a warning is logged and processing continues with available metadata

**Validation**:
- Paywall detection doesn't halt processing
- Warning messages include article URL and error reason
- Metadata (title, source, publish_date) is still stored

### AC3: Fast News Retrieval
**GIVEN** a ticker symbol  
**WHEN** a News Analyst requests news data  
**THEN** they receive articles with sentiment scores and embeddings within 2 seconds

**Validation**:
- Database queries return results in < 2 seconds
- Results include sentiment scores and vector embeddings
- Pagination supports large result sets

### AC4: LLM Sentiment Analysis
**GIVEN** news articles are processed  
**WHEN** LLM sentiment analysis runs  
**THEN** each article gets a structured sentiment score (positive/negative/neutral with confidence)

**Validation**:
- Sentiment scores use structured format: `{"sentiment": "positive|negative|neutral", "confidence": 0.0-1.0}`
- LLM integration uses OpenRouter unified provider
- Failed sentiment analysis doesn't prevent article storage

### AC5: Vector Embeddings Storage
**GIVEN** news articles are stored  
**WHEN** saved to database  
**THEN** they include vector embeddings for both title and content for semantic search

**Validation**:
- 1536-dimension embeddings generated for title and content
- Embeddings stored in pgvectorscale-optimized columns
- Semantic similarity search returns relevant results

## Business Rules

### BR1: Best Effort Processing
- Log warnings for paywalled/blocked content but continue processing
- Network failures don't halt entire job execution
- API rate limits are respected with exponential backoff

### BR2: Daily Schedule Execution
- Configurable ticker list supports adding/removing symbols
- Job execution time is configurable (default: daily at 6 AM UTC)
- Manual job execution available for testing and backfill

### BR3: Data Quality Standards
- URL-based deduplication prevents duplicate articles
- Article publish dates must be within last 30 days
- Source URLs must be valid and accessible

### BR4: LLM Integration Standards
- Use OpenRouter unified provider for sentiment analysis
- Quick-think LLM for sentiment processing (cost optimization)
- Structured prompts ensure consistent sentiment format

### BR5: Vector Search Optimization
- Embeddings enable semantic similarity search for agents
- Vector indexes optimize query performance
- Embedding generation uses consistent model for coherence

### BR6: Graceful Error Handling
- Individual article failures don't stop batch processing
- Comprehensive logging for monitoring and debugging
- Database transactions ensure data consistency

## Technical Implementation

### Architecture Alignment

Follows established **Router → Service → Repository → Entity → Database** pattern:

```
ScheduledNewsJob → NewsService → NewsRepository → NewsArticle → PostgreSQL+pgvectorscale
```

### Database Schema Integration

Leverages existing NewsRepository with vector extensions:

```sql
-- Existing news_articles table enhanced with:
ALTER TABLE news_articles 
ADD COLUMN IF NOT EXISTS sentiment_score JSONB,
ADD COLUMN IF NOT EXISTS title_embedding vector(1536),
ADD COLUMN IF NOT EXISTS content_embedding vector(1536);

-- Vector similarity indexes
CREATE INDEX IF NOT EXISTS idx_title_embedding 
ON news_articles USING ivfflat (title_embedding vector_cosine_ops);
```

### LLM Integration Pattern

```python
# OpenRouter sentiment analysis
sentiment_result = await llm_client.analyze_sentiment(
    text=article.content,
    model="anthropic/claude-3.5-haiku",  # quick_think_llm
    structured_output=True
)

# Expected response format
{
    "sentiment": "positive|negative|neutral",
    "confidence": 0.85,
    "reasoning": "Brief explanation"
}
```

### Vector Embedding Strategy

```python
# Generate embeddings for semantic search
title_embedding = await embedding_client.create_embedding(
    text=article.title,
    model="text-embedding-3-small"  # 1536 dimensions
)

content_embedding = await embedding_client.create_embedding(
    text=article.content[:8000],  # Truncate for token limits
    model="text-embedding-3-small"
)
```

### Scheduled Execution Framework

Use APScheduler for job orchestration (Dagster not in current dependencies):

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()
scheduler.add_job(
    run_news_collection,
    'cron',
    hour=6,  # 6 AM UTC
    minute=0,
    timezone=timezone.utc,
    id='daily_news_collection'
)
```

## Implementation Approach

### Phase 1: Scheduled Execution (2-3 hours)
1. Configure APScheduler for daily news collection
2. Create job configuration management for ticker lists
3. Implement job monitoring and status tracking
4. Add manual execution capability for testing

### Phase 2: LLM Sentiment Integration (3-4 hours)
1. Integrate OpenRouter LLM for sentiment analysis  
2. Create structured sentiment analysis prompts
3. Update NewsService to include sentiment processing
4. Add sentiment data to NewsArticle domain model

### Phase 3: Vector Embeddings (2-3 hours)
1. Add embedding generation to article processing
2. Update database schema for vector storage
3. Implement semantic search capabilities in NewsRepository
4. Create vector similarity query methods

### Phase 4: Testing & Monitoring (2 hours)
1. Add comprehensive test coverage for new components
2. Implement job monitoring and alerting
3. Create configuration validation
4. Performance testing for 2-second query requirement

### Total Estimated Effort: 9-12 hours

## Dependencies

### Required APIs
- **OpenRouter API**: LLM sentiment analysis (`OPENROUTER_API_KEY`)
- **OpenAI API**: Vector embeddings (`OPENAI_API_KEY` for embeddings)

### Database Requirements  
- **PostgreSQL**: Base storage with async support
- **TimescaleDB**: Time-series optimization for news data
- **pgvectorscale**: Vector storage and similarity search

### Existing Infrastructure (95% Complete)
- `NewsService` with `update_news_for_symbol` method
- `GoogleNewsClient` for RSS feed parsing
- `ArticleScraperClient` with newspaper4k integration
- `NewsRepository` with async PostgreSQL operations
- `NewsArticle` domain model with validation
- Comprehensive test coverage with pytest-vcr

### New Dependencies
- `apscheduler` for job scheduling
- Enhanced vector embedding capabilities
- LLM client integration for sentiment analysis

## Configuration Management

### Environment Variables
```bash
# Existing
OPENROUTER_API_KEY="sk-or-..."
DATABASE_URL="postgresql://..."

# New requirements
OPENAI_API_KEY="sk-..."  # For embeddings
NEWS_SCHEDULE_HOUR=6     # UTC hour for daily execution
NEWS_TICKERS="AAPL,GOOGL,MSFT,TSLA"  # Comma-separated ticker list
```

### Configuration File Support
```yaml
# config/news_collection.yaml
schedule:
  hour: 6
  minute: 0
  timezone: "UTC"

tickers:
  - "AAPL"
  - "GOOGL" 
  - "MSFT"
  - "TSLA"

sentiment:
  llm_model: "anthropic/claude-3.5-haiku"
  confidence_threshold: 0.5

embeddings:
  model: "text-embedding-3-small"
  dimensions: 1536
  content_max_length: 8000
```

## Success Metrics

### Performance Targets
- **Query Response Time**: < 2 seconds for news retrieval with sentiment
- **Job Execution Time**: < 30 minutes for daily collection (4 tickers)
- **Success Rate**: > 95% article processing success rate
- **Test Coverage**: Maintain > 85% coverage including new components

### Operational Metrics
- Daily job completion status and execution time
- Article processing success/failure rates per ticker
- LLM sentiment analysis success rates
- Vector embedding generation performance
- Database query performance monitoring

## Risk Mitigation

### Technical Risks
1. **LLM API Rate Limits**: Implement exponential backoff and batch processing
2. **Vector Storage Performance**: Monitor query times and optimize indexes
3. **Paywall Content Blocking**: Graceful degradation with metadata-only storage
4. **Database Migration Complexity**: Test schema changes thoroughly

### Operational Risks  
1. **Scheduled Job Failures**: Implement monitoring and alerting
2. **API Key Management**: Secure configuration management
3. **Data Quality Issues**: Validation at multiple pipeline stages
4. **Performance Degradation**: Regular performance monitoring and optimization

## Testing Strategy

### Unit Testing (pytest with pytest-vcr)
- Scheduled job execution logic
- LLM sentiment analysis integration  
- Vector embedding generation
- Configuration management

### Integration Testing
- End-to-end news collection pipeline
- Database vector operations
- LLM API integration
- Job scheduling functionality

### Performance Testing
- Query response time validation (< 2 seconds)
- Batch processing performance
- Vector similarity search optimization
- Concurrent job execution handling

## Monitoring and Observability

### Logging Strategy
- Job execution start/completion with metrics
- Individual article processing success/failure
- LLM API call status and timing
- Database operation performance

### Health Checks
- Daily job completion status
- Database connectivity and performance
- LLM API availability and response times
- Vector search functionality

### Alerting Triggers
- Failed daily news collection jobs
- API rate limit violations
- Database query performance degradation
- Sentiment analysis failure rates > 10%

This specification completes the news domain infrastructure to support advanced news analysis for the multi-agent trading framework, providing News Analysts with comprehensive, sentiment-analyzed, and semantically searchable news data for informed trading decisions.