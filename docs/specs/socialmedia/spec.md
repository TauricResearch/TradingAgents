# Social Media Domain Specification

## Feature Overview

**Complete implementation of social media data collection and analysis** - Transform the current stub implementation into a production-ready social media domain that provides comprehensive Reddit sentiment analysis for trading agents.

### User Story

As a Dagster pipeline, I want to collect Reddit posts from financial subreddits with LLM sentiment analysis and vector embeddings, so that AI Agents can access comprehensive social media context for ticker-specific trading decisions through RAG-powered queries.

## Acceptance Criteria

### Daily Data Collection
- **GIVEN** a scheduled Dagster pipeline **WHEN** it executes daily **THEN** it collects Reddit posts from configured financial subreddits without manual intervention
- **GIVEN** Reddit posts are collected **WHEN** processed **THEN** they are stored in PostgreSQL with TimescaleDB optimization and vector embeddings for semantic search

### LLM Sentiment Analysis  
- **GIVEN** social media posts **WHEN** processed **THEN** each post receives OpenRouter LLM sentiment analysis with structured scores (positive/negative/neutral with confidence)

### Agent Integration
- **GIVEN** a ticker symbol **WHEN** AI agents request social context **THEN** they receive relevant Reddit posts with sentiment scores and vector similarity ranking within 2 seconds
- **GIVEN** social media data **WHEN** agents query **THEN** AgentToolkit provides RAG-enhanced context including post content, sentiment trends, and engagement metrics

## Business Rules and Constraints

### Data Collection Rules
1. **Daily automated collection** from configured financial subreddits (wallstreetbets, investing, stocks, SecurityAnalysis)
2. **OpenRouter LLM sentiment analysis** for all posts with confidence scoring
3. **Vector embeddings generation** for semantic similarity search
4. **Post deduplication** by Reddit post ID to prevent duplicates
5. **Rate limiting compliance** with Reddit API terms of service

### Data Management
1. **Data retention policy**: 90 days for social media posts
2. **Best effort processing**: API failures or rate limits don't block other posts

## Scope Definition

### Included Features ✅
- Complete socialmedia domain implementation from stub to production
- PostgreSQL migration from current file-based storage
- Reddit API integration using PRAW or Reddit API client
- OpenRouter LLM sentiment analysis integration
- Vector embeddings generation and similarity search
- AgentToolkit integration with `get_reddit_news` and `get_reddit_stock_info` methods
- Dagster pipeline for scheduled daily collection
- SQLAlchemy entities with TimescaleDB and pgvectorscale support
- Comprehensive test coverage with pytest-vcr for API mocking

### Excluded Features ❌
- Other social media platforms beyond Reddit (Twitter, LinkedIn, etc.)
- Real-time social media streaming (batch processing only)
- Custom sentiment models (use OpenRouter LLMs only)
- Social media influence scoring or user reputation tracking
- Multi-language post support (English only)
- Historical Reddit data backfilling beyond 30 days

## Technical Implementation Details

### Architecture Pattern
**Router → Service → Repository → Entity → Database** (matching news domain)

### Current Implementation Status
**Basic stub implementation - requires complete rebuild**

### Missing Components
1. PostgreSQL database migration from file storage
2. Reddit API client implementation (RedditClient is empty stub)
3. SQLAlchemy entity models for social posts with vector fields
4. LLM sentiment analysis integration via OpenRouter
5. Vector embedding generation and similarity search
6. AgentToolkit RAG methods (`get_reddit_news`, `get_reddit_stock_info`)
7. Dagster pipeline for scheduled data collection
8. Comprehensive test suite with domain-specific patterns

### Existing Stub Components
- SocialMediaService with empty method stubs
- SocialRepository with file-based JSON storage
- Basic data models: SocialPost, PostData, SocialContext
- Empty RedditClient class requiring full implementation
- Agent references to social methods (not yet implemented)

## Database Integration

### PostgreSQL Schema Design
```sql
-- Social media posts table with TimescaleDB optimization
CREATE TABLE social_media_posts (
    id SERIAL PRIMARY KEY,
    post_id VARCHAR(50) UNIQUE NOT NULL,           -- Reddit post ID
    ticker VARCHAR(10),                            -- Associated ticker
    subreddit VARCHAR(50) NOT NULL,                -- Source subreddit
    title TEXT NOT NULL,                           -- Post title
    content TEXT,                                  -- Post content
    author VARCHAR(50),                            -- Reddit username
    created_at TIMESTAMPTZ NOT NULL,               -- Post creation time
    collected_at TIMESTAMPTZ DEFAULT NOW(),        -- Data collection time
    upvotes INTEGER DEFAULT 0,                     -- Reddit upvotes
    downvotes INTEGER DEFAULT 0,                   -- Reddit downvotes
    comment_count INTEGER DEFAULT 0,               -- Number of comments
    url TEXT,                                      -- Reddit URL
    permalink TEXT,                                -- Reddit permalink
    
    -- Sentiment analysis fields
    sentiment_score DECIMAL(3,2),                  -- -1.0 to +1.0
    sentiment_label VARCHAR(20),                   -- positive/negative/neutral
    sentiment_confidence DECIMAL(3,2),             -- 0.0 to 1.0
    
    -- Vector embeddings
    embedding vector(1536),                        -- pgvectorscale embedding
    
    -- Metadata
    data_quality_score DECIMAL(3,2) DEFAULT 1.0,
    processing_status VARCHAR(20) DEFAULT 'pending',
    error_message TEXT
);

-- TimescaleDB hypertable for time-series optimization
SELECT create_hypertable('social_media_posts', 'created_at');

-- Vector similarity index
CREATE INDEX idx_social_posts_embedding ON social_media_posts USING vectors (embedding vector_cosine_ops);

-- Performance indexes
CREATE INDEX idx_social_posts_ticker ON social_media_posts (ticker, created_at DESC);
CREATE INDEX idx_social_posts_subreddit ON social_media_posts (subreddit, created_at DESC);
CREATE INDEX idx_social_posts_sentiment ON social_media_posts (sentiment_label, sentiment_score);
```

### Entity Model
```python
# tradingagents/domains/socialmedia/entities.py
from sqlalchemy import Column, Integer, String, Text, DECIMAL, TIMESTAMP, Index
from sqlalchemy.dialects.postgresql import VECTOR
from tradingagents.database import Base
from typing import Optional, Dict, Any
import json

class SocialMediaPostEntity(Base):
    __tablename__ = 'social_media_posts'
    
    id = Column(Integer, primary_key=True)
    post_id = Column(String(50), unique=True, nullable=False)
    ticker = Column(String(10), index=True)
    subreddit = Column(String(50), nullable=False, index=True)
    title = Column(Text, nullable=False)
    content = Column(Text)
    author = Column(String(50))
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, index=True)
    collected_at = Column(TIMESTAMP(timezone=True), server_default='NOW()')
    upvotes = Column(Integer, default=0)
    downvotes = Column(Integer, default=0)
    comment_count = Column(Integer, default=0)
    url = Column(Text)
    permalink = Column(Text)
    
    # Sentiment analysis
    sentiment_score = Column(DECIMAL(3,2))
    sentiment_label = Column(String(20))
    sentiment_confidence = Column(DECIMAL(3,2))
    
    # Vector embeddings
    embedding = Column(VECTOR(1536))
    
    # Metadata
    data_quality_score = Column(DECIMAL(3,2), default=1.0)
    processing_status = Column(String(20), default='pending')
    error_message = Column(Text)
    
    def to_domain(self) -> 'SocialPost':
        """Convert entity to domain model"""
        return SocialPost(
            post_id=self.post_id,
            ticker=self.ticker,
            subreddit=self.subreddit,
            title=self.title,
            content=self.content,
            author=self.author,
            created_at=self.created_at,
            upvotes=self.upvotes,
            downvotes=self.downvotes,
            comment_count=self.comment_count,
            url=self.url,
            sentiment_score=float(self.sentiment_score) if self.sentiment_score else None,
            sentiment_label=self.sentiment_label,
            sentiment_confidence=float(self.sentiment_confidence) if self.sentiment_confidence else None
        )
    
    @classmethod
    def from_domain(cls, post: 'SocialPost', embedding: Optional[list] = None) -> 'SocialMediaPostEntity':
        """Create entity from domain model"""
        return cls(
            post_id=post.post_id,
            ticker=post.ticker,
            subreddit=post.subreddit,
            title=post.title,
            content=post.content,
            author=post.author,
            created_at=post.created_at,
            upvotes=post.upvotes,
            downvotes=post.downvotes,
            comment_count=post.comment_count,
            url=post.url,
            sentiment_score=post.sentiment_score,
            sentiment_label=post.sentiment_label,
            sentiment_confidence=post.sentiment_confidence,
            embedding=embedding
        )
```

## Reddit API Integration

### RedditClient Implementation
```python
# tradingagents/domains/socialmedia/clients.py
import praw
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import asyncio
import aiohttp
from tradingagents.config import TradingAgentsConfig

class RedditClient:
    def __init__(self, config: TradingAgentsConfig):
        self.config = config
        self.reddit = praw.Reddit(
            client_id=config.reddit_client_id,
            client_secret=config.reddit_client_secret,
            user_agent=config.reddit_user_agent
        )
        
    async def fetch_financial_posts(
        self,
        subreddits: List[str],
        ticker: Optional[str] = None,
        limit: int = 100,
        time_filter: str = "day"
    ) -> List[Dict[str, Any]]:
        """Fetch financial posts from specified subreddits"""
        posts = []
        
        for subreddit_name in subreddits:
            try:
                subreddit = self.reddit.subreddit(subreddit_name)
                submissions = subreddit.hot(limit=limit)
                
                for submission in submissions:
                    # Filter by ticker if specified
                    if ticker and ticker.upper() not in submission.title.upper():
                        continue
                        
                    post_data = {
                        'post_id': submission.id,
                        'subreddit': subreddit_name,
                        'title': submission.title,
                        'content': submission.selftext,
                        'author': str(submission.author),
                        'created_at': datetime.fromtimestamp(submission.created_utc),
                        'upvotes': submission.ups,
                        'downvotes': submission.downs,
                        'comment_count': submission.num_comments,
                        'url': submission.url,
                        'permalink': submission.permalink
                    }
                    posts.append(post_data)
                    
            except Exception as e:
                # Log error but continue processing other subreddits
                print(f"Error fetching from {subreddit_name}: {e}")
                continue
                
        return posts
```

## LLM Sentiment Analysis

### OpenRouter Integration
```python
# tradingagents/domains/socialmedia/services.py
from typing import Dict, Any, Optional, Tuple
import openai
from tradingagents.config import TradingAgentsConfig

class SentimentAnalyzer:
    def __init__(self, config: TradingAgentsConfig):
        self.config = config
        self.client = openai.OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=config.openrouter_api_key
        )
    
    async def analyze_sentiment(self, text: str) -> Tuple[float, str, float]:
        """
        Analyze sentiment of social media post
        Returns: (score, label, confidence)
        """
        prompt = f"""
        Analyze the financial sentiment of this social media post.
        
        Post: "{text}"
        
        Return sentiment as JSON with:
        - score: float from -1.0 (very negative) to +1.0 (very positive)
        - label: "positive", "negative", or "neutral"  
        - confidence: float from 0.0 to 1.0 indicating confidence
        
        Focus on financial and trading sentiment, not general sentiment.
        """
        
        try:
            response = await self.client.chat.completions.create(
                model=self.config.quick_think_llm,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100,
                temperature=0.1
            )
            
            result = json.loads(response.choices[0].message.content)
            return result['score'], result['label'], result['confidence']
            
        except Exception as e:
            # Return neutral sentiment on error
            return 0.0, "neutral", 0.0
```

## Vector Embeddings and Search

### Embedding Generation
```python
# tradingagents/domains/socialmedia/embeddings.py
import openai
from typing import List, Optional
from tradingagents.config import TradingAgentsConfig

class EmbeddingGenerator:
    def __init__(self, config: TradingAgentsConfig):
        self.config = config
        self.client = openai.OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=config.openrouter_api_key
        )
    
    async def generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate vector embedding for text"""
        try:
            response = await self.client.embeddings.create(
                model="text-embedding-3-small",
                input=text,
                encoding_format="float"
            )
            return response.data[0].embedding
        except Exception as e:
            print(f"Embedding generation failed: {e}")
            return None
    
    def prepare_text_for_embedding(self, post: Dict[str, Any]) -> str:
        """Combine title and content for embedding"""
        title = post.get('title', '')
        content = post.get('content', '')
        return f"{title} {content}".strip()
```

## Repository Implementation

### SocialRepository with PostgreSQL
```python
# tradingagents/domains/socialmedia/repositories.py
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, text
from tradingagents.domains.socialmedia.entities import SocialMediaPostEntity
from tradingagents.domains.socialmedia.models import SocialPost, SocialContext
from tradingagents.database import get_db_session
from datetime import datetime, timedelta

class SocialRepository:
    def __init__(self):
        self.session = get_db_session()
    
    async def save_posts(self, posts: List[SocialPost]) -> List[str]:
        """Save social media posts with deduplication"""
        saved_ids = []
        
        for post in posts:
            # Check for existing post
            existing = self.session.query(SocialMediaPostEntity).filter(
                SocialMediaPostEntity.post_id == post.post_id
            ).first()
            
            if existing:
                continue  # Skip duplicates
                
            entity = SocialMediaPostEntity.from_domain(post)
            self.session.add(entity)
            saved_ids.append(post.post_id)
        
        self.session.commit()
        return saved_ids
    
    async def get_posts_for_ticker(
        self, 
        ticker: str, 
        days: int = 7,
        limit: int = 50
    ) -> List[SocialPost]:
        """Get social media posts for specific ticker"""
        cutoff_date = datetime.now() - timedelta(days=days)
        
        results = self.session.query(SocialMediaPostEntity).filter(
            and_(
                SocialMediaPostEntity.ticker == ticker,
                SocialMediaPostEntity.created_at >= cutoff_date
            )
        ).order_by(desc(SocialMediaPostEntity.created_at)).limit(limit).all()
        
        return [entity.to_domain() for entity in results]
    
    async def vector_similarity_search(
        self, 
        query_embedding: List[float], 
        ticker: Optional[str] = None,
        limit: int = 10
    ) -> List[SocialPost]:
        """Find similar posts using vector search"""
        query = self.session.query(SocialMediaPostEntity)
        
        if ticker:
            query = query.filter(SocialMediaPostEntity.ticker == ticker)
        
        # Vector similarity search using pgvectorscale
        query = query.order_by(
            text(f"embedding <-> '{query_embedding}'")
        ).limit(limit)
        
        results = query.all()
        return [entity.to_domain() for entity in results]
```

## Service Layer

### SocialMediaService
```python
# tradingagents/domains/socialmedia/services.py
from typing import List, Optional, Dict, Any
from tradingagents.domains.socialmedia.repositories import SocialRepository
from tradingagents.domains.socialmedia.clients import RedditClient
from tradingagents.domains.socialmedia.models import SocialPost, SocialContext
from tradingagents.config import TradingAgentsConfig

class SocialMediaService:
    def __init__(self, config: TradingAgentsConfig):
        self.config = config
        self.repository = SocialRepository()
        self.reddit_client = RedditClient(config)
        self.sentiment_analyzer = SentimentAnalyzer(config)
        self.embedding_generator = EmbeddingGenerator(config)
    
    async def collect_social_data(
        self, 
        ticker: Optional[str] = None,
        subreddits: Optional[List[str]] = None
    ) -> SocialContext:
        """Main entry point for social media data collection"""
        
        if not subreddits:
            subreddits = ['wallstreetbets', 'investing', 'stocks', 'SecurityAnalysis']
        
        # Fetch posts from Reddit
        raw_posts = await self.reddit_client.fetch_financial_posts(
            subreddits=subreddits,
            ticker=ticker,
            limit=100
        )
        
        # Process posts: sentiment analysis + embeddings
        processed_posts = []
        for raw_post in raw_posts:
            # Generate sentiment
            text = f"{raw_post['title']} {raw_post['content']}"
            score, label, confidence = await self.sentiment_analyzer.analyze_sentiment(text)
            
            # Generate embedding
            embedding = await self.embedding_generator.generate_embedding(text)
            
            post = SocialPost(
                **raw_post,
                sentiment_score=score,
                sentiment_label=label,
                sentiment_confidence=confidence
            )
            processed_posts.append(post)
        
        # Save to database
        await self.repository.save_posts(processed_posts)
        
        # Return context
        return SocialContext(
            posts=processed_posts,
            ticker=ticker,
            total_posts=len(processed_posts),
            sentiment_summary=self._calculate_sentiment_summary(processed_posts)
        )
    
    def _calculate_sentiment_summary(self, posts: List[SocialPost]) -> Dict[str, Any]:
        """Calculate aggregate sentiment metrics"""
        if not posts:
            return {}
        
        scores = [p.sentiment_score for p in posts if p.sentiment_score is not None]
        labels = [p.sentiment_label for p in posts if p.sentiment_label]
        
        return {
            'avg_sentiment': sum(scores) / len(scores) if scores else 0.0,
            'positive_count': labels.count('positive'),
            'negative_count': labels.count('negative'),
            'neutral_count': labels.count('neutral'),
            'total_posts': len(posts)
        }
```

## AgentToolkit Integration

### RAG-Enhanced Methods
```python
# tradingagents/agents/libs/agent_toolkit.py (additions)

async def get_reddit_news(self, ticker: str, days: int = 7) -> str:
    """Get Reddit posts related to a ticker with RAG context"""
    try:
        # Get recent posts for ticker
        posts = await self.social_service.repository.get_posts_for_ticker(
            ticker=ticker,
            days=days,
            limit=20
        )
        
        if not posts:
            return f"No Reddit posts found for {ticker} in the last {days} days."
        
        # Format for agent consumption
        context = f"Reddit Social Media Context for {ticker} ({len(posts)} posts):\n\n"
        
        for post in posts[:10]:  # Limit to top 10
            sentiment_emoji = {"positive": "📈", "negative": "📉", "neutral": "➡️"}.get(post.sentiment_label, "")
            context += f"{sentiment_emoji} r/{post.subreddit} - {post.title}\n"
            context += f"   Sentiment: {post.sentiment_label} ({post.sentiment_score:.2f})\n"
            context += f"   Engagement: {post.upvotes} upvotes, {post.comment_count} comments\n"
            if post.content:
                context += f"   Content: {post.content[:200]}...\n"
            context += "\n"
        
        return context
        
    except Exception as e:
        return f"Error fetching Reddit data for {ticker}: {str(e)}"

async def get_reddit_stock_info(self, ticker: str, query: Optional[str] = None) -> str:
    """Get Reddit stock information with semantic search"""
    try:
        if query:
            # Generate embedding for semantic search
            query_embedding = await self.social_service.embedding_generator.generate_embedding(query)
            if query_embedding:
                posts = await self.social_service.repository.vector_similarity_search(
                    query_embedding=query_embedding,
                    ticker=ticker,
                    limit=10
                )
            else:
                posts = await self.social_service.repository.get_posts_for_ticker(ticker, days=7)
        else:
            posts = await self.social_service.repository.get_posts_for_ticker(ticker, days=7)
        
        if not posts:
            return f"No relevant Reddit discussions found for {ticker}."
        
        # Aggregate sentiment and key insights
        sentiment_summary = self.social_service._calculate_sentiment_summary(posts)
        
        context = f"Reddit Stock Analysis for {ticker}:\n\n"
        context += f"Overall Sentiment: {sentiment_summary.get('avg_sentiment', 0):.2f}/1.0\n"
        context += f"Posts: {sentiment_summary.get('positive_count', 0)} positive, "
        context += f"{sentiment_summary.get('negative_count', 0)} negative, "
        context += f"{sentiment_summary.get('neutral_count', 0)} neutral\n\n"
        
        context += "Key Discussions:\n"
        for post in posts[:5]:
            context += f"• {post.title} (r/{post.subreddit})\n"
            context += f"  Sentiment: {post.sentiment_label} ({post.sentiment_score:.2f})\n"
        
        return context
        
    except Exception as e:
        return f"Error analyzing Reddit stock info for {ticker}: {str(e)}"
```

## Dagster Pipeline

### Social Media Collection Asset
```python
# tradingagents/data/assets/social_media.py
from dagster import asset, AssetExecutionContext
from tradingagents.domains.socialmedia.services import SocialMediaService
from tradingagents.config import TradingAgentsConfig

@asset(
    group_name="social_media",
    description="Collect Reddit posts from financial subreddits with sentiment analysis"
)
async def reddit_financial_posts(context: AssetExecutionContext) -> Dict[str, Any]:
    """Daily collection of Reddit financial posts"""
    
    config = TradingAgentsConfig.from_env()
    social_service = SocialMediaService(config)
    
    # Collect from financial subreddits
    subreddits = ['wallstreetbets', 'investing', 'stocks', 'SecurityAnalysis']
    
    total_collected = 0
    results = {}
    
    for subreddit in subreddits:
        try:
            social_context = await social_service.collect_social_data(
                subreddits=[subreddit]
            )
            
            results[subreddit] = {
                'posts_collected': len(social_context.posts),
                'sentiment_summary': social_context.sentiment_summary
            }
            total_collected += len(social_context.posts)
            
            context.log.info(f"Collected {len(social_context.posts)} posts from r/{subreddit}")
            
        except Exception as e:
            context.log.error(f"Failed to collect from r/{subreddit}: {e}")
            results[subreddit] = {'error': str(e)}
    
    context.log.info(f"Total posts collected: {total_collected}")
    return results
```

## Testing Strategy

### Test Structure
```
tests/domains/socialmedia/
├── conftest.py                    # Fixtures and test setup
├── test_reddit_client.py          # API integration tests with VCR
├── test_social_repository.py      # PostgreSQL database tests  
├── test_social_service.py         # Business logic with mocks
├── test_sentiment_analyzer.py     # LLM sentiment analysis tests
├── test_embedding_generator.py    # Vector embedding tests
└── fixtures/                      # VCR cassettes and test data
    └── reddit_api_responses.yaml
```

### Key Test Patterns
```python
# tests/domains/socialmedia/test_social_service.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from tradingagents.domains.socialmedia.services import SocialMediaService

@pytest.mark.asyncio
async def test_collect_social_data_success(mock_social_service):
    """Test successful social media data collection"""
    # Mock Reddit API response
    mock_posts = [
        {
            'post_id': 'abc123',
            'title': 'AAPL to the moon!',
            'subreddit': 'wallstreetbets',
            # ... other fields
        }
    ]
    
    mock_social_service.reddit_client.fetch_financial_posts.return_value = mock_posts
    mock_social_service.sentiment_analyzer.analyze_sentiment.return_value = (0.8, 'positive', 0.9)
    
    result = await mock_social_service.collect_social_data(ticker='AAPL')
    
    assert len(result.posts) == 1
    assert result.posts[0].sentiment_label == 'positive'
    assert result.sentiment_summary['positive_count'] == 1
```

## Dependencies

### Technical Dependencies
- **Reddit API access** (PRAW or Reddit API client)
- **OpenRouter API** for LLM sentiment analysis
- **PostgreSQL** with TimescaleDB and pgvectorscale extensions
- **Existing database infrastructure** from news domain
- **OpenRouter configuration** in TradingAgentsConfig
- **Dagster orchestration framework** for scheduled execution

### Reference Implementations
- **News domain patterns**: Follow NewsService, NewsRepository, NewsArticleEntity patterns for consistency
- **Database schema**: Mirror NewsArticleEntity vector embedding approach for social posts
- **Agent integration**: Follow existing AgentToolkit get_news() pattern for social media methods
- **Testing approach**: Apply news domain testing patterns: VCR for API, real DB for repositories

## Success Criteria

### Functionality
- Daily Reddit collection with sentiment analysis and vector search
- Seamless integration with existing multi-agent trading framework
- RAG-enhanced social context for AI agents

### Performance  
- < 2 second social context queries
- < 100ms repository operations
- Efficient vector similarity search

### Quality
- 85%+ test coverage matching project standards
- Comprehensive error handling and resilience
- Data quality monitoring and validation

### Integration
- Seamless AgentToolkit RAG integration for AI agents
- Architecture and patterns match successful news domain implementation
- Consistent with existing TradingAgents configuration and conventions

## Implementation Approach

**Complete domain implementation following successful news domain patterns:**

1. **Database migration** from file storage to PostgreSQL
2. **Entity models** with TimescaleDB and vector support
3. **Reddit client** implementation with rate limiting
4. **Repository layer** with vector search capabilities
5. **Service layer** with sentiment analysis and embedding generation
6. **AgentToolkit integration** with RAG-enhanced methods
7. **Dagster pipeline** for automated daily collection
8. **Comprehensive testing** with VCR mocking and real database tests

This comprehensive implementation transforms the social media domain from basic stubs into a production-ready system that seamlessly integrates with the existing TradingAgents framework.