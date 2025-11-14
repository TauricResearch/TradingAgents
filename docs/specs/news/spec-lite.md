# News Domain Completion - Implementation Summary

## Core Requirement
Complete final 5% of news domain: add scheduled execution, LLM sentiment analysis, and vector embeddings to existing 95% complete infrastructure.

## User Story
**Dagster Job** automatically fetches Google News articles for tracked tickers, extracts content, performs LLM sentiment analysis, and stores with embeddings → **News Analysts** get comprehensive, up-to-date news data for trading decisions.

## Essential Requirements

### 1. Scheduled Execution
- Daily job at 6 AM UTC for all configured tickers
- Dagster orchestration with partitioned schedules
- Graceful error handling with Dagster sensors and alerting

### 2. LLM Sentiment Analysis
- OpenRouter integration using `quick_think_llm` (claude-3.5-haiku)
- Structured output: `{"sentiment": "positive|negative|neutral", "confidence": 0.0-1.0, "label": "positive|negative|neutral"}`
- Best-effort processing - failures don't stop pipeline

### 3. Vector Embeddings
- 1536-dimension embeddings for title and content
- pgvectorscale storage with similarity indexes
- Semantic search capability for News Analysts

## Technical Implementation

### Architecture Pattern
```
Dagster Job → Dagster Op → NewsService → NewsRepository → NewsArticle → PostgreSQL+pgvectorscale
```

### Database Changes
```sql
ALTER TABLE news_articles
ADD COLUMN sentiment_confidence FLOAT,
ADD COLUMN sentiment_label VARCHAR(20);

-- Vector columns already exist from 95% complete infrastructure
-- title_embedding vector(1536)
-- content_embedding vector(1536)
```

### Key Integration Points
- **Existing NewsService**: Enhance `update_company_news` method
- **LLM Integration**: OpenRouter unified provider for sentiment and embeddings
- **Vector Generation**: OpenAI text-embedding-ada-002 via OpenRouter (1536 dims)
- **Job Scheduling**: Dagster jobs with daily partitioned schedules

## Implementation Phases
1. **Entity Layer** (2-3h): Enhance NewsArticle dataclass + migration
2. **Repository Layer** (2-3h): RAG vector similarity search methods
3. **LLM Integration** (4-5h): OpenRouter sentiment + embeddings clients
4. **Service Enhancement** (2-3h): Integrate LLM clients into NewsService
5. **Dagster Orchestration** (3-4h): Jobs, ops, and schedules
6. **Testing & Monitoring** (2-3h): Coverage + performance validation

**Total: 15-20 hours**

## Success Criteria
- ✅ Daily automated news collection via Dagster without manual intervention
- ✅ News retrieval with sentiment scores < 2 seconds response time
- ✅ Vector embeddings enable semantic search for News Analysts
- ✅ >95% article processing success rate despite paywall/blocking
- ✅ Maintain >85% test coverage including new components
- ✅ Dagster UI provides monitoring and alerting for job failures

## Dependencies
- **APIs**: OpenRouter (sentiment + embeddings via unified provider)
- **Infrastructure**: PostgreSQL + TimescaleDB + pgvectorscale
- **Orchestration**: Dagster for job scheduling and monitoring
- **Existing**: 95% complete news domain components (clients, repository, service)

## Configuration
```yaml
# Dagster workspace.yaml
schedules:
  news_collection_daily:
    cron_schedule: "0 6 * * *"  # Daily at 6 AM UTC
    execution_timezone: "UTC"

# Dagster run config
ops:
  collect_news:
    config:
      symbols: ["AAPL", "GOOGL", "MSFT", "TSLA"]
      lookback_days: 1
```

```bash
# Environment variables
OPENROUTER_API_KEY="sk-or-..."  # Unified LLM provider
DATABASE_URL="postgresql+asyncpg://..."
```

## Risk Mitigation
- **API Rate Limits**: Exponential backoff + batch processing
- **Paywall Blocking**: Metadata-only storage with warnings
- **Job Failures**: Dagster sensors + alerting for operational visibility
- **Performance**: Vector indexes + query optimization for <2s target
- **LLM Failures**: Keyword-based fallback for sentiment, zero-vector fallback for embeddings
