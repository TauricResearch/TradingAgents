# News Domain Completion - Implementation Summary

## Core Requirement
Complete final 5% of news domain: add scheduled execution, LLM sentiment analysis, and vector embeddings to existing 95% complete infrastructure.

## User Story
**Dagster Job** automatically fetches Google News articles for tracked tickers, extracts content, performs LLM sentiment analysis, and stores with embeddings → **News Analysts** get comprehensive, up-to-date news data for trading decisions.

## Essential Requirements

### 1. Scheduled Execution
- Daily job at 6 AM UTC for all configured tickers
- APScheduler integration (no Dagster dependency)
- Graceful error handling with comprehensive logging

### 2. LLM Sentiment Analysis  
- OpenRouter integration using `quick_think_llm` (claude-3.5-haiku)
- Structured output: `{"sentiment": "positive|negative|neutral", "confidence": 0.0-1.0}`
- Best-effort processing - failures don't stop pipeline

### 3. Vector Embeddings
- 1536-dimension embeddings for title and content
- pgvectorscale storage with similarity indexes
- Semantic search capability for News Analysts

## Technical Implementation

### Architecture Pattern
```
ScheduledNewsJob → NewsService → NewsRepository → NewsArticle → PostgreSQL+pgvectorscale
```

### Database Changes
```sql
ALTER TABLE news_articles 
ADD COLUMN sentiment_score JSONB,
ADD COLUMN title_embedding vector(1536),
ADD COLUMN content_embedding vector(1536);
```

### Key Integration Points
- **Existing NewsService**: Enhance `update_news_for_symbol` method
- **LLM Integration**: OpenRouter unified provider for sentiment
- **Vector Generation**: text-embedding-3-small model (1536 dims)  
- **Job Scheduling**: APScheduler with cron trigger

## Implementation Phases
1. **Scheduled Execution** (2-3h): APScheduler + config management
2. **LLM Sentiment** (3-4h): OpenRouter integration + structured prompts
3. **Vector Embeddings** (2-3h): Embedding generation + database schema
4. **Testing & Monitoring** (2h): Coverage + performance validation

**Total: 9-12 hours**

## Success Criteria
- ✅ Daily automated news collection without manual intervention
- ✅ News retrieval with sentiment scores < 2 seconds response time
- ✅ Vector embeddings enable semantic search for News Analysts
- ✅ >95% article processing success rate despite paywall/blocking
- ✅ Maintain >85% test coverage including new components

## Dependencies
- **APIs**: OpenRouter (sentiment), OpenAI (embeddings)
- **Infrastructure**: PostgreSQL + TimescaleDB + pgvectorscale
- **New Package**: `apscheduler` for job scheduling
- **Existing**: 95% complete news domain components

## Configuration
```bash
OPENROUTER_API_KEY="sk-or-..."
OPENAI_API_KEY="sk-..."
NEWS_SCHEDULE_HOUR=6
NEWS_TICKERS="AAPL,GOOGL,MSFT,TSLA"
```

## Risk Mitigation
- **API Rate Limits**: Exponential backoff + batch processing
- **Paywall Blocking**: Metadata-only storage with warnings  
- **Job Failures**: Monitoring + alerting for operational visibility
- **Performance**: Vector indexes + query optimization for <2s target