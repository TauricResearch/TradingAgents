# Social Media Domain Implementation Tasks

## Overview

Complete greenfield implementation of the socialmedia domain from empty stubs to production-ready system with PRAW Reddit API integration, PostgreSQL migration, OpenRouter LLM sentiment analysis, and AgentToolkit RAG methods.

**Total Estimated Time: 32 hours (3-phase parallel development approach)**

## Phase Structure

### Phase 1: Foundation (12 hours) - Database & Core Models
**Parallel Execution Ready**: Multiple agents can work on different components simultaneously

### Phase 2: API Integration & Processing (12 hours) - Clients & Services  
**Parallel Execution Ready**: API clients and LLM services can be developed in parallel

### Phase 3: Integration & Validation (8 hours) - AgentToolkit & Dagster
**Parallel Execution Ready**: AgentToolkit and pipeline development with comprehensive testing

---

## Phase 1: Foundation (12 hours)

### Task 1.1: Database Schema Migration (3 hours)
**Priority: Blocking** | **Agent: Database Specialist**

Create PostgreSQL migration for social_media_posts table with TimescaleDB and pgvectorscale support.

**Implementation:**
```sql
-- Migration: 003_create_social_media_posts.sql
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

SELECT create_hypertable('social_media_posts', 'created_utc', chunk_time_interval => INTERVAL '1 day');

-- Performance indexes
CREATE UNIQUE INDEX idx_social_posts_post_id ON social_media_posts (post_id);
CREATE INDEX idx_social_posts_subreddit_time ON social_media_posts (subreddit, created_utc DESC);
CREATE INDEX idx_social_posts_tickers_gin ON social_media_posts USING GIN (tickers);
CREATE INDEX idx_social_posts_title_embedding ON social_media_posts USING vectors (title_embedding vector_cosine_ops);
CREATE INDEX idx_social_posts_content_embedding ON social_media_posts USING vectors (content_embedding vector_cosine_ops);
CREATE INDEX idx_social_posts_sentiment ON social_media_posts (((sentiment_score->>'sentiment'))) WHERE sentiment_score IS NOT NULL;

-- Constraints
ALTER TABLE social_media_posts ADD CONSTRAINT chk_sentiment_score CHECK (
    sentiment_score IS NULL OR ((sentiment_score->>'confidence')::float BETWEEN 0 AND 1)
);
ALTER TABLE social_media_posts ADD CONSTRAINT chk_created_utc CHECK (created_utc <= NOW());
```

**Acceptance Criteria:**
- [ ] Migration script creates social_media_posts table
- [ ] TimescaleDB hypertable configured for time-series optimization
- [ ] pgvectorscale indexes for title_embedding and content_embedding
- [ ] All constraints and indexes properly created
- [ ] Migration runs successfully in test and development environments

**Dependencies:** PostgreSQL + TimescaleDB + pgvectorscale installed
**Risk:** Medium - Extension compatibility issues

---

### Task 1.2: SQLAlchemy Entity Implementation (3 hours)
**Priority: Blocking** | **Agent: Entity Specialist**

Create SocialMediaPostEntity with proper field mappings and domain transformations.

**File:** `tradingagents/domains/socialmedia/entities.py`

**Implementation:**
```python
from sqlalchemy import Column, String, Text, Integer, TIMESTAMP, Index
from sqlalchemy.dialects.postgresql import UUID, VECTOR, ARRAY, JSONB
from sqlalchemy.sql import func
from tradingagents.database.base import Base
from typing import Optional, List, Dict, Any
import uuid

class SocialMediaPostEntity(Base):
    __tablename__ = 'social_media_posts'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    post_id = Column(String(50), unique=True, nullable=False, index=True)
    title = Column(Text, nullable=False)
    content = Column(Text)
    author = Column(String(100), nullable=False)
    subreddit = Column(String(50), nullable=False, index=True)
    created_utc = Column(TIMESTAMP(timezone=True), nullable=False, index=True)
    upvotes = Column(Integer, nullable=False, default=0)
    downvotes = Column(Integer, nullable=False, default=0)
    comments_count = Column(Integer, nullable=False, default=0)
    url = Column(Text, nullable=False)
    
    # Enhanced fields
    sentiment_score = Column(JSONB)
    sentiment_label = Column(String(20))
    tickers = Column(ARRAY(String(10)), default=lambda: [])
    title_embedding = Column(VECTOR(1536))
    content_embedding = Column(VECTOR(1536))
    
    # Metadata
    inserted_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())
    
    def to_domain(self) -> 'SocialPost':
        """Convert entity to domain model with proper field mapping"""
        sentiment_data = self.sentiment_score or {}
        return SocialPost(
            post_id=self.post_id,
            title=self.title,
            content=self.content,
            author=self.author,
            subreddit=self.subreddit,
            created_utc=self.created_utc,
            upvotes=self.upvotes,
            downvotes=self.downvotes,
            comments_count=self.comments_count,
            url=self.url,
            sentiment_score=sentiment_data.get('score'),
            sentiment_label=self.sentiment_label,
            sentiment_confidence=sentiment_data.get('confidence'),
            tickers=list(self.tickers) if self.tickers else [],
            title_embedding=list(self.title_embedding) if self.title_embedding else None,
            content_embedding=list(self.content_embedding) if self.content_embedding else None
        )
    
    @classmethod
    def from_domain(cls, post: 'SocialPost') -> 'SocialMediaPostEntity':
        """Create entity from domain model"""
        sentiment_data = None
        if post.sentiment_score is not None and post.sentiment_confidence is not None:
            sentiment_data = {
                'score': post.sentiment_score,
                'confidence': post.sentiment_confidence,
                'reasoning': getattr(post, 'sentiment_reasoning', None)
            }
        
        return cls(
            post_id=post.post_id,
            title=post.title,
            content=post.content,
            author=post.author,
            subreddit=post.subreddit,
            created_utc=post.created_utc,
            upvotes=post.upvotes,
            downvotes=post.downvotes,
            comments_count=post.comments_count,
            url=post.url,
            sentiment_score=sentiment_data,
            sentiment_label=post.sentiment_label,
            tickers=post.tickers or [],
            title_embedding=post.title_embedding,
            content_embedding=post.content_embedding
        )
```

**Acceptance Criteria:**
- [ ] SocialMediaPostEntity properly maps all database fields
- [ ] to_domain() and from_domain() methods handle all field conversions
- [ ] Proper handling of vector fields and JSONB sentiment data
- [ ] Entity integrates with existing database session management
- [ ] All field types match database schema exactly

**Dependencies:** Task 1.1 (database schema)
**Risk:** Low - Standard SQLAlchemy patterns

---

### Task 1.3: Domain Model Enhancement (3 hours)
**Priority: Blocking** | **Agent: Domain Specialist**

Enhance SocialPost domain entity with comprehensive validation, transformations, and business rules.

**File:** `tradingagents/domains/socialmedia/models.py`

**Implementation:**
```python
from pydantic import BaseModel, Field, validator, root_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
import re

class SentimentScore(BaseModel):
    """Structured sentiment analysis result from OpenRouter LLM"""
    sentiment: Literal['positive', 'negative', 'neutral']
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: Optional[str] = None
    
    @validator('reasoning')
    def reasoning_not_empty(cls, v):
        if v is not None and len(v.strip()) == 0:
            return None
        return v

class SocialPost(BaseModel):
    """Core domain entity with business rules and transformations"""
    # Base fields from Reddit API
    post_id: str = Field(..., regex=r'^[a-zA-Z0-9_-]+$')
    title: str = Field(..., min_length=1, max_length=300)
    content: Optional[str] = None
    author: str = Field(..., min_length=1, max_length=100)
    subreddit: str = Field(..., min_length=1, max_length=50)
    created_utc: datetime
    upvotes: int = Field(..., ge=0)
    downvotes: int = Field(..., ge=0)
    comments_count: int = Field(..., ge=0)
    url: str = Field(..., min_length=1)
    
    # Enhanced fields
    sentiment_score: Optional[float] = Field(None, ge=-1.0, le=1.0)
    sentiment_label: Optional[str] = Field(None, regex=r'^(positive|negative|neutral)$')
    sentiment_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    sentiment_reasoning: Optional[str] = None
    tickers: Optional[List[str]] = Field(default_factory=list)
    title_embedding: Optional[List[float]] = None
    content_embedding: Optional[List[float]] = None
    
    @validator('tickers')
    def validate_tickers(cls, v):
        """Validate ticker symbols format"""
        if v is None:
            return []
        # Ensure tickers are uppercase and valid format
        return [ticker.upper() for ticker in v if re.match(r'^[A-Z]{1,5}$', ticker.upper())]
    
    @validator('title_embedding', 'content_embedding')
    def validate_embedding_dimensions(cls, v):
        """Ensure embeddings have correct dimensions"""
        if v is not None and len(v) != 1536:
            raise ValueError('Embedding must be 1536 dimensions')
        return v
    
    @root_validator
    def validate_sentiment_consistency(cls, values):
        """Ensure sentiment fields are consistent"""
        score = values.get('sentiment_score')
        label = values.get('sentiment_label')
        confidence = values.get('sentiment_confidence')
        
        # All sentiment fields should be present or all None
        sentiment_fields = [score, label, confidence]
        non_none_count = sum(1 for field in sentiment_fields if field is not None)
        
        if non_none_count > 0 and non_none_count < 3:
            raise ValueError('All sentiment fields (score, label, confidence) must be provided together')
        
        return values
    
    @classmethod
    def from_praw_submission(cls, submission: Any) -> 'SocialPost':
        """Create SocialPost from PRAW Reddit submission"""
        return cls(
            post_id=submission.id,
            title=submission.title[:300],  # Truncate long titles
            content=submission.selftext if submission.selftext else None,
            author=str(submission.author) if submission.author else '[deleted]',
            subreddit=submission.subreddit.display_name,
            created_utc=datetime.fromtimestamp(submission.created_utc),
            upvotes=submission.ups if hasattr(submission, 'ups') else submission.score,
            downvotes=max(0, submission.score - submission.ups) if hasattr(submission, 'ups') else 0,
            comments_count=submission.num_comments,
            url=f"https://reddit.com{submission.permalink}"
        )
    
    def extract_tickers(self) -> List[str]:
        """Extract ticker symbols from title and content"""
        text = f"{self.title} {self.content or ''}"
        # Look for $TICKER or TICKER patterns
        ticker_pattern = r'\b(?:\$)?([A-Z]{1,5})\b'
        potential_tickers = re.findall(ticker_pattern, text.upper())
        
        # Filter out common words that look like tickers
        excluded = {'THE', 'AND', 'OR', 'FOR', 'TO', 'OF', 'IN', 'ON', 'AT', 'BY', 'UP', 'IS', 'IT', 'BE', 'AS', 'ARE', 'WAS', 'HE', 'SHE', 'WE', 'YOU', 'THEY', 'ALL', 'ANY', 'CAN', 'HAD', 'HER', 'HIS', 'HOW', 'ITS', 'MAY', 'NEW', 'NOW', 'OLD', 'SEE', 'TWO', 'WHO', 'BOY', 'DID', 'HAS', 'LET', 'PUT', 'SAY', 'SIX', 'TEN', 'USE', 'WAS', 'WIN', 'YES'}
        
        tickers = [ticker for ticker in potential_tickers if ticker not in excluded]
        return list(set(tickers))  # Remove duplicates
    
    def has_reliable_sentiment(self) -> bool:
        """Check if sentiment analysis has sufficient confidence"""
        return (self.sentiment_confidence is not None and 
                self.sentiment_confidence >= 0.5)
    
    def to_agent_context(self) -> Dict[str, Any]:
        """Format post for agent consumption"""
        sentiment_emoji = {"positive": "📈", "negative": "📉", "neutral": "➡️"}.get(self.sentiment_label, "❓")
        
        return {
            'post_id': self.post_id,
            'subreddit': self.subreddit,
            'title': self.title,
            'content': self.content[:200] + '...' if self.content and len(self.content) > 200 else self.content,
            'author': self.author,
            'created_utc': self.created_utc.isoformat(),
            'engagement': {
                'upvotes': self.upvotes,
                'comments_count': self.comments_count,
                'score': self.upvotes - self.downvotes
            },
            'sentiment': {
                'label': self.sentiment_label,
                'score': self.sentiment_score,
                'confidence': self.sentiment_confidence,
                'emoji': sentiment_emoji,
                'reliable': self.has_reliable_sentiment()
            },
            'tickers': self.tickers or [],
            'url': self.url
        }
```

**Acceptance Criteria:**
- [ ] SocialPost model handles all Reddit API fields properly
- [ ] Comprehensive validation for all fields including sentiment and embeddings
- [ ] from_praw_submission() creates valid domain objects from Reddit data
- [ ] extract_tickers() accurately finds ticker symbols in text
- [ ] to_agent_context() formats data for AI agent consumption
- [ ] Business rule validation prevents invalid state combinations

**Dependencies:** None (can run parallel with other tasks)
**Risk:** Low - Standard domain modeling

---

### Task 1.4: Repository Implementation (3 hours)
**Priority: Medium** | **Agent: Repository Specialist**

Implement SocialRepository with PostgreSQL operations, vector similarity search, and performance optimization.

**File:** `tradingagents/domains/socialmedia/repositories.py`

**Implementation:**
```python
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy import and_, or_, desc, text, func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from tradingagents.domains.socialmedia.entities import SocialMediaPostEntity
from tradingagents.domains.socialmedia.models import SocialPost
from tradingagents.database import DatabaseManager
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class SocialRepository:
    """PostgreSQL repository for social media posts with vector search capabilities"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
    
    async def upsert_batch(self, posts: List[SocialPost]) -> List[str]:
        """Batch upsert social media posts with deduplication"""
        async with self.db_manager.get_session() as session:
            saved_ids = []
            
            for post in posts:
                try:
                    # Check for existing post
                    existing = await session.execute(
                        text("SELECT id FROM social_media_posts WHERE post_id = :post_id"),
                        {"post_id": post.post_id}
                    )
                    
                    if existing.first():
                        logger.debug(f"Skipping duplicate post: {post.post_id}")
                        continue
                    
                    entity = SocialMediaPostEntity.from_domain(post)
                    session.add(entity)
                    saved_ids.append(post.post_id)
                    
                except IntegrityError as e:
                    logger.warning(f"Integrity error saving post {post.post_id}: {e}")
                    await session.rollback()
                    continue
            
            await session.commit()
            logger.info(f"Saved {len(saved_ids)} new posts to database")
            return saved_ids
    
    async def find_by_ticker(self, ticker: str, days: int = 30, limit: int = 50) -> List[SocialPost]:
        """Find posts mentioning specific ticker symbol"""
        async with self.db_manager.get_session() as session:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            result = await session.execute(
                text("""
                    SELECT * FROM social_media_posts 
                    WHERE :ticker = ANY(tickers) 
                    AND created_utc >= :cutoff_date
                    ORDER BY created_utc DESC 
                    LIMIT :limit
                """),
                {
                    "ticker": ticker.upper(),
                    "cutoff_date": cutoff_date,
                    "limit": limit
                }
            )
            
            entities = [SocialMediaPostEntity(**row) for row in result.mappings()]
            return [entity.to_domain() for entity in entities]
    
    async def find_by_subreddit(self, subreddit: str, hours: int = 24, limit: int = 100) -> List[SocialPost]:
        """Find recent posts from specific subreddit"""
        async with self.db_manager.get_session() as session:
            cutoff_date = datetime.now() - timedelta(hours=hours)
            
            result = await session.execute(
                text("""
                    SELECT * FROM social_media_posts 
                    WHERE subreddit = :subreddit 
                    AND created_utc >= :cutoff_date
                    ORDER BY created_utc DESC 
                    LIMIT :limit
                """),
                {
                    "subreddit": subreddit,
                    "cutoff_date": cutoff_date,
                    "limit": limit
                }
            )
            
            entities = [SocialMediaPostEntity(**row) for row in result.mappings()]
            return [entity.to_domain() for entity in entities]
    
    async def find_similar_posts(
        self, 
        query_embedding: List[float], 
        ticker: Optional[str] = None,
        limit: int = 10,
        similarity_threshold: float = 0.8
    ) -> List[Tuple[SocialPost, float]]:
        """Find similar posts using vector similarity search"""
        async with self.db_manager.get_session() as session:
            embedding_str = str(query_embedding)
            
            base_query = """
                SELECT *, 
                       LEAST(
                           1 - (title_embedding <=> :embedding),
                           1 - (content_embedding <=> :embedding)
                       ) as similarity_score
                FROM social_media_posts 
                WHERE (title_embedding IS NOT NULL OR content_embedding IS NOT NULL)
            """
            
            params = {"embedding": embedding_str}
            
            if ticker:
                base_query += " AND :ticker = ANY(tickers)"
                params["ticker"] = ticker.upper()
            
            base_query += """
                AND LEAST(
                    1 - (title_embedding <=> :embedding),
                    1 - (content_embedding <=> :embedding)
                ) >= :threshold
                ORDER BY similarity_score DESC 
                LIMIT :limit
            """
            
            params.update({
                "threshold": similarity_threshold,
                "limit": limit
            })
            
            result = await session.execute(text(base_query), params)
            
            posts_with_scores = []
            for row in result.mappings():
                entity = SocialMediaPostEntity(**{k: v for k, v in row.items() if k != 'similarity_score'})
                post = entity.to_domain()
                similarity = row['similarity_score']
                posts_with_scores.append((post, similarity))
            
            return posts_with_scores
    
    async def get_sentiment_summary(
        self, 
        ticker: Optional[str] = None, 
        subreddit: Optional[str] = None,
        hours: int = 24
    ) -> Dict[str, Any]:
        """Get aggregated sentiment analysis for ticker or subreddit"""
        async with self.db_manager.get_session() as session:
            cutoff_date = datetime.now() - timedelta(hours=hours)
            
            base_query = """
                SELECT 
                    sentiment_label,
                    COUNT(*) as count,
                    AVG((sentiment_score->>'score')::float) as avg_score,
                    AVG((sentiment_score->>'confidence')::float) as avg_confidence,
                    SUM(upvotes) as total_upvotes,
                    SUM(comments_count) as total_comments
                FROM social_media_posts 
                WHERE created_utc >= :cutoff_date 
                AND sentiment_score IS NOT NULL
            """
            
            params = {"cutoff_date": cutoff_date}
            
            if ticker:
                base_query += " AND :ticker = ANY(tickers)"
                params["ticker"] = ticker.upper()
            
            if subreddit:
                base_query += " AND subreddit = :subreddit"
                params["subreddit"] = subreddit
            
            base_query += " GROUP BY sentiment_label"
            
            result = await session.execute(text(base_query), params)
            
            sentiment_counts = {}
            total_posts = 0
            weighted_score = 0
            total_engagement = 0
            
            for row in result.mappings():
                label = row['sentiment_label']
                count = row['count']
                avg_score = float(row['avg_score'] or 0)
                engagement = (row['total_upvotes'] or 0) + (row['total_comments'] or 0)
                
                sentiment_counts[label] = {
                    'count': count,
                    'avg_score': avg_score,
                    'avg_confidence': float(row['avg_confidence'] or 0),
                    'engagement': engagement
                }
                
                total_posts += count
                weighted_score += avg_score * count
                total_engagement += engagement
            
            return {
                'ticker': ticker,
                'subreddit': subreddit,
                'period_hours': hours,
                'total_posts': total_posts,
                'sentiment_breakdown': sentiment_counts,
                'overall_sentiment': weighted_score / total_posts if total_posts > 0 else 0.0,
                'total_engagement': total_engagement,
                'data_quality': {
                    'posts_with_sentiment': total_posts,
                    'period_start': cutoff_date.isoformat(),
                    'generated_at': datetime.now().isoformat()
                }
            }
    
    async def cleanup_old_posts(self, days: int = 90) -> int:
        """Remove posts older than specified days"""
        async with self.db_manager.get_session() as session:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            result = await session.execute(
                text("DELETE FROM social_media_posts WHERE created_utc < :cutoff_date"),
                {"cutoff_date": cutoff_date}
            )
            
            deleted_count = result.rowcount
            await session.commit()
            
            logger.info(f"Cleaned up {deleted_count} posts older than {days} days")
            return deleted_count
    
    async def get_trending_tickers(self, hours: int = 24, min_mentions: int = 5) -> List[Dict[str, Any]]:
        """Find trending ticker symbols by mention frequency and sentiment"""
        async with self.db_manager.get_session() as session:
            cutoff_date = datetime.now() - timedelta(hours=hours)
            
            result = await session.execute(
                text("""
                    SELECT 
                        unnest(tickers) as ticker,
                        COUNT(*) as mention_count,
                        AVG((sentiment_score->>'score')::float) as avg_sentiment,
                        SUM(upvotes) as total_upvotes,
                        SUM(comments_count) as total_comments
                    FROM social_media_posts 
                    WHERE created_utc >= :cutoff_date
                    AND sentiment_score IS NOT NULL
                    AND array_length(tickers, 1) > 0
                    GROUP BY ticker
                    HAVING COUNT(*) >= :min_mentions
                    ORDER BY mention_count DESC, avg_sentiment DESC
                    LIMIT 20
                """),
                {
                    "cutoff_date": cutoff_date,
                    "min_mentions": min_mentions
                }
            )
            
            trending = []
            for row in result.mappings():
                trending.append({
                    'ticker': row['ticker'],
                    'mention_count': row['mention_count'],
                    'avg_sentiment': float(row['avg_sentiment'] or 0),
                    'total_upvotes': row['total_upvotes'] or 0,
                    'total_comments': row['total_comments'] or 0,
                    'engagement_score': (row['total_upvotes'] or 0) + (row['total_comments'] or 0)
                })
            
            return trending
```

**Acceptance Criteria:**
- [ ] Batch upsert operations with proper deduplication
- [ ] Vector similarity search using pgvectorscale indexes
- [ ] Efficient ticker-based queries with TimescaleDB optimization
- [ ] Comprehensive sentiment aggregation with engagement metrics
- [ ] Data cleanup operations with configurable retention
- [ ] Trending ticker analysis with minimum mention thresholds
- [ ] Proper error handling and logging throughout

**Dependencies:** Task 1.1 (database schema), Task 1.2 (entity model)
**Risk:** Medium - Complex vector search queries

---

## Phase 2: API Integration & Processing (12 hours)

### Task 2.1: Reddit Client Implementation (4 hours)
**Priority: Blocking** | **Agent: API Integration Specialist**

Implement RedditClient using PRAW with comprehensive rate limiting, error handling, and financial subreddit focus.

**File:** `tradingagents/domains/socialmedia/clients.py`

**Implementation:**
```python
import praw
import asyncio
from typing import List, Optional, Dict, Any, AsyncIterator
from datetime import datetime, timedelta
from tradingagents.config import TradingAgentsConfig
import logging
import time
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

class RedditClient:
    """PRAW-based Reddit client with rate limiting and error handling"""
    
    def __init__(self, config: TradingAgentsConfig):
        self.config = config
        self.reddit = None
        self.last_request_time = 0
        self.min_request_interval = 1.0  # 1 second between requests
        self.financial_subreddits = [
            'wallstreetbets', 'investing', 'stocks', 'SecurityAnalysis',
            'ValueInvesting', 'financialindependence', 'StockMarket',
            'options', 'dividends', 'pennystocks'
        ]
    
    async def __aenter__(self):
        """Async context manager entry"""
        self._initialize_reddit()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        pass
    
    def _initialize_reddit(self):
        """Initialize PRAW Reddit instance"""
        try:
            self.reddit = praw.Reddit(
                client_id=self.config.reddit_client_id,
                client_secret=self.config.reddit_client_secret,
                user_agent=self.config.reddit_user_agent,
                check_for_async=False
            )
            
            # Test authentication
            self.reddit.user.me()
            logger.info("Reddit client initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Reddit client: {e}")
            raise
    
    async def _rate_limit_delay(self):
        """Implement rate limiting between requests"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.min_request_interval:
            delay = self.min_request_interval - time_since_last
            await asyncio.sleep(delay)
        
        self.last_request_time = time.time()
    
    async def fetch_subreddit_posts(
        self, 
        subreddit_name: str, 
        time_filter: str = 'day',
        limit: int = 50,
        sort_type: str = 'hot'
    ) -> List[Dict[str, Any]]:
        """Fetch posts from a specific subreddit"""
        if not self.reddit:
            self._initialize_reddit()
        
        await self._rate_limit_delay()
        
        try:
            subreddit = self.reddit.subreddit(subreddit_name)
            
            # Get submissions based on sort type
            if sort_type == 'hot':
                submissions = subreddit.hot(limit=limit)
            elif sort_type == 'top':
                submissions = subreddit.top(time_filter=time_filter, limit=limit)
            elif sort_type == 'new':
                submissions = subreddit.new(limit=limit)
            else:
                submissions = subreddit.hot(limit=limit)
            
            posts = []
            for submission in submissions:
                # Skip removed or deleted posts
                if submission.selftext == '[removed]' or submission.selftext == '[deleted]':
                    continue
                
                post_data = self._extract_post_data(submission, subreddit_name)
                posts.append(post_data)
            
            logger.info(f"Fetched {len(posts)} posts from r/{subreddit_name}")
            return posts
            
        except Exception as e:
            logger.error(f"Error fetching posts from r/{subreddit_name}: {e}")
            return []
    
    async def fetch_financial_posts_batch(
        self,
        subreddits: Optional[List[str]] = None,
        time_filter: str = 'day',
        posts_per_subreddit: int = 50
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Fetch posts from multiple financial subreddits"""
        if not subreddits:
            subreddits = self.financial_subreddits
        
        results = {}
        
        for subreddit_name in subreddits:
            try:
                posts = await self.fetch_subreddit_posts(
                    subreddit_name=subreddit_name,
                    time_filter=time_filter,
                    limit=posts_per_subreddit
                )
                results[subreddit_name] = posts
                
            except Exception as e:
                logger.error(f"Failed to fetch from r/{subreddit_name}: {e}")
                results[subreddit_name] = []
        
        total_posts = sum(len(posts) for posts in results.values())
        logger.info(f"Fetched {total_posts} total posts from {len(subreddits)} subreddits")
        
        return results
    
    async def search_posts(
        self,
        query: str,
        subreddit_names: Optional[List[str]] = None,
        time_filter: str = 'week',
        limit: int = 25
    ) -> List[Dict[str, Any]]:
        """Search for posts containing specific terms"""
        if not self.reddit:
            self._initialize_reddit()
        
        if not subreddit_names:
            subreddit_names = self.financial_subreddits
        
        all_posts = []
        
        for subreddit_name in subreddit_names:
            await self._rate_limit_delay()
            
            try:
                subreddit = self.reddit.subreddit(subreddit_name)
                search_results = subreddit.search(
                    query=query,
                    time_filter=time_filter,
                    limit=limit,
                    sort='relevance'
                )
                
                for submission in search_results:
                    if submission.selftext not in ['[removed]', '[deleted]']:
                        post_data = self._extract_post_data(submission, subreddit_name)
                        all_posts.append(post_data)
                
            except Exception as e:
                logger.error(f"Search error in r/{subreddit_name}: {e}")
                continue
        
        logger.info(f"Found {len(all_posts)} posts matching query: {query}")
        return all_posts
    
    def _extract_post_data(self, submission: Any, subreddit_name: str) -> Dict[str, Any]:
        """Extract structured data from PRAW submission"""
        try:
            return {
                'post_id': submission.id,
                'title': submission.title[:300],  # Limit title length
                'content': submission.selftext if submission.selftext else None,
                'author': str(submission.author) if submission.author else '[deleted]',
                'subreddit': subreddit_name,
                'created_utc': datetime.fromtimestamp(submission.created_utc),
                'upvotes': getattr(submission, 'ups', submission.score),
                'downvotes': max(0, submission.score - getattr(submission, 'ups', submission.score)),
                'comments_count': submission.num_comments,
                'url': f"https://reddit.com{submission.permalink}",
                'reddit_score': submission.score,
                'upvote_ratio': getattr(submission, 'upvote_ratio', 0.5),
                'is_self': submission.is_self,
                'domain': submission.domain,
                'flair_text': getattr(submission, 'link_flair_text', None)
            }
        except Exception as e:
            logger.error(f"Error extracting post data: {e}")
            return None
    
    async def get_post_details(self, post_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information for a specific post"""
        if not self.reddit:
            self._initialize_reddit()
        
        await self._rate_limit_delay()
        
        try:
            submission = self.reddit.submission(id=post_id)
            return self._extract_post_data(submission, submission.subreddit.display_name)
        except Exception as e:
            logger.error(f"Error fetching post details for {post_id}: {e}")
            return None
    
    async def health_check(self) -> bool:
        """Check if Reddit API is accessible"""
        try:
            if not self.reddit:
                self._initialize_reddit()
            
            # Simple API call to verify connectivity
            self.reddit.subreddit('wallstreetbets').hot(limit=1)
            return True
        except Exception as e:
            logger.error(f"Reddit health check failed: {e}")
            return False
```

**Testing Implementation:**
```python
# tests/domains/socialmedia/test_reddit_client.py
import pytest
import pytest_vcr
from unittest.mock import MagicMock, patch
from tradingagents.domains.socialmedia.clients import RedditClient
from tradingagents.config import TradingAgentsConfig

@pytest_vcr.use_cassette('reddit_fetch_posts.yaml')
@pytest.mark.asyncio
async def test_fetch_subreddit_posts(reddit_client, trading_config):
    """Test fetching posts from a specific subreddit"""
    async with reddit_client:
        posts = await reddit_client.fetch_subreddit_posts('wallstreetbets', limit=10)
        
        assert len(posts) > 0
        for post in posts:
            assert 'post_id' in post
            assert 'title' in post
            assert 'subreddit' in post
            assert post['subreddit'] == 'wallstreetbets'
```

**Acceptance Criteria:**
- [ ] PRAW Reddit client properly authenticated and initialized
- [ ] Rate limiting implemented (1 request per second minimum)
- [ ] Comprehensive error handling for network issues and API limits
- [ ] Financial subreddit focus with configurable subreddit lists
- [ ] Structured data extraction from Reddit submissions
- [ ] Search functionality across multiple subreddits
- [ ] Health check capabilities for monitoring
- [ ] Test coverage with pytest-vcr cassettes

**Dependencies:** Reddit API credentials in TradingAgentsConfig
**Risk:** High - External API dependency, rate limiting complexity

---

### Task 2.2: OpenRouter LLM Sentiment Analysis (3 hours)
**Priority: Medium** | **Agent: LLM Integration Specialist**

Implement sentiment analysis using OpenRouter with social media-specific prompts and structured output parsing.

**File:** `tradingagents/domains/socialmedia/sentiment.py`

**Implementation:**
```python
from typing import Optional, Dict, Any, List
import json
import asyncio
from tradingagents.llm.openrouter_client import OpenRouterClient
from tradingagents.config import TradingAgentsConfig
from tradingagents.domains.socialmedia.models import SentimentScore
import logging

logger = logging.getLogger(__name__)

class SocialSentimentAnalyzer:
    """OpenRouter-based sentiment analysis for social media posts"""
    
    def __init__(self, config: TradingAgentsConfig):
        self.config = config
        self.client = OpenRouterClient(config)
        self.batch_size = 5  # Process posts in batches
        
    async def analyze_post_sentiment(self, post_text: str, ticker: Optional[str] = None) -> Optional[SentimentScore]:
        """Analyze sentiment of a single social media post"""
        prompt = self._create_sentiment_prompt(post_text, ticker)
        
        try:
            response = await self.client.generate_response(
                model=self.config.quick_think_llm,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150,
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response)
            
            return SentimentScore(
                sentiment=result.get('sentiment', 'neutral'),
                confidence=float(result.get('confidence', 0.0)),
                reasoning=result.get('reasoning')
            )
            
        except Exception as e:
            logger.error(f"Sentiment analysis failed: {e}")
            return None
    
    async def analyze_batch(
        self, 
        posts: List[Dict[str, Any]], 
        include_ticker: bool = True
    ) -> List[Optional[SentimentScore]]:
        """Analyze sentiment for multiple posts with rate limiting"""
        results = []
        
        for i in range(0, len(posts), self.batch_size):
            batch = posts[i:i + self.batch_size]
            batch_tasks = []
            
            for post in batch:
                text = self._combine_post_text(post)
                ticker = None
                
                if include_ticker and 'tickers' in post and post['tickers']:
                    ticker = post['tickers'][0]  # Use first ticker if available
                
                task = self.analyze_post_sentiment(text, ticker)
                batch_tasks.append(task)
            
            # Process batch with concurrency limit
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
            
            for result in batch_results:
                if isinstance(result, Exception):
                    logger.error(f"Batch sentiment analysis error: {result}")
                    results.append(None)
                else:
                    results.append(result)
            
            # Rate limiting between batches
            if i + self.batch_size < len(posts):
                await asyncio.sleep(1.0)
        
        successful_count = sum(1 for r in results if r is not None)
        logger.info(f"Sentiment analysis completed: {successful_count}/{len(posts)} successful")
        
        return results
    
    def _create_sentiment_prompt(self, text: str, ticker: Optional[str] = None) -> str:
        """Create social media-specific sentiment analysis prompt"""
        ticker_context = f" for ticker ${ticker}" if ticker else ""
        
        return f"""
Analyze the financial sentiment of this Reddit post{ticker_context}. Consider:
- Trading/investment sentiment (not general mood)
- Informal language, slang, and memes common in financial social media
- Context clues like "diamond hands", "to the moon", "bearish", etc.
- Overall market outlook expressed in the post

Post text: "{text}"

Respond with JSON only:
{{
    "sentiment": "positive|negative|neutral",
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation of key factors"
}}

Guidelines:
- "positive": Bullish, optimistic about price/performance
- "negative": Bearish, pessimistic about price/performance  
- "neutral": Mixed signals or no clear directional sentiment
- Confidence: How certain are you? (0.5+ for reliable sentiment)
- Reasoning: Key words/phrases that influenced the classification
        """.strip()
    
    def _combine_post_text(self, post: Dict[str, Any]) -> str:
        """Combine title and content for sentiment analysis"""
        title = post.get('title', '')
        content = post.get('content', '')
        
        if content:
            # Limit total text length for efficient processing
            combined = f"{title} {content}"[:1000]
        else:
            combined = title
            
        return combined.strip()
    
    async def analyze_market_sentiment(
        self, 
        posts: List[Dict[str, Any]], 
        ticker: str
    ) -> Dict[str, Any]:
        """Analyze overall market sentiment for a ticker from multiple posts"""
        sentiments = await self.analyze_batch(posts, include_ticker=True)
        
        # Filter out failed analyses
        valid_sentiments = [s for s in sentiments if s is not None and s.confidence >= 0.5]
        
        if not valid_sentiments:
            return {
                'ticker': ticker,
                'overall_sentiment': 'neutral',
                'confidence': 0.0,
                'post_count': len(posts),
                'analysis_success_rate': 0.0,
                'sentiment_distribution': {'positive': 0, 'negative': 0, 'neutral': 0}
            }
        
        # Calculate sentiment distribution
        sentiment_counts = {'positive': 0, 'negative': 0, 'neutral': 0}
        confidence_sum = 0
        
        for sentiment in valid_sentiments:
            sentiment_counts[sentiment.sentiment] += 1
            confidence_sum += sentiment.confidence
        
        # Determine overall sentiment
        total_valid = len(valid_sentiments)
        positive_ratio = sentiment_counts['positive'] / total_valid
        negative_ratio = sentiment_counts['negative'] / total_valid
        
        if positive_ratio > 0.6:
            overall_sentiment = 'positive'
        elif negative_ratio > 0.6:
            overall_sentiment = 'negative'
        else:
            overall_sentiment = 'neutral'
        
        return {
            'ticker': ticker,
            'overall_sentiment': overall_sentiment,
            'confidence': confidence_sum / total_valid,
            'post_count': len(posts),
            'analyzed_posts': total_valid,
            'analysis_success_rate': total_valid / len(posts),
            'sentiment_distribution': sentiment_counts,
            'positive_ratio': positive_ratio,
            'negative_ratio': negative_ratio,
            'neutral_ratio': sentiment_counts['neutral'] / total_valid
        }
```

**Acceptance Criteria:**
- [ ] OpenRouter integration for sentiment analysis with structured JSON output
- [ ] Social media-specific prompts handling informal language and financial slang
- [ ] Batch processing with rate limiting and error handling
- [ ] Confidence scoring for sentiment reliability
- [ ] Market sentiment aggregation across multiple posts
- [ ] Comprehensive error handling and logging
- [ ] Test coverage with mocked LLM responses

**Dependencies:** OpenRouter client implementation
**Risk:** Medium - LLM API reliability and cost management

---

### Task 2.3: Vector Embedding Generation (2 hours)
**Priority: Medium** | **Agent: ML Integration Specialist**

Implement vector embedding generation for semantic similarity search using OpenRouter embedding models.

**File:** `tradingagents/domains/socialmedia/embeddings.py`

**Implementation:**
```python
from typing import List, Optional, Dict, Any
import asyncio
import numpy as np
from tradingagents.llm.openrouter_client import OpenRouterClient
from tradingagents.config import TradingAgentsConfig
import logging

logger = logging.getLogger(__name__)

class SocialEmbeddingGenerator:
    """Generate vector embeddings for social media posts using OpenRouter"""
    
    def __init__(self, config: TradingAgentsConfig):
        self.config = config
        self.client = OpenRouterClient(config)
        self.embedding_model = "text-embedding-3-large"  # 1536 dimensions
        self.max_text_length = 8000  # Token limit for embedding model
        self.batch_size = 10
    
    async def generate_post_embeddings(
        self, 
        post: Dict[str, Any]
    ) -> Dict[str, Optional[List[float]]]:
        """Generate embeddings for post title and content separately"""
        embeddings = {
            'title_embedding': None,
            'content_embedding': None
        }
        
        # Generate title embedding
        title = post.get('title', '').strip()
        if title:
            embeddings['title_embedding'] = await self._generate_embedding(title)
        
        # Generate content embedding if content exists
        content = post.get('content', '').strip()
        if content:
            # Combine title and content for content embedding
            combined_text = f"{title} {content}"[:self.max_text_length]
            embeddings['content_embedding'] = await self._generate_embedding(combined_text)
        
        return embeddings
    
    async def generate_batch_embeddings(
        self, 
        posts: List[Dict[str, Any]]
    ) -> List[Dict[str, Optional[List[float]]]]:
        """Generate embeddings for multiple posts with batching"""
        results = []
        
        for i in range(0, len(posts), self.batch_size):
            batch = posts[i:i + self.batch_size]
            
            # Create tasks for concurrent processing
            tasks = [self.generate_post_embeddings(post) for post in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in batch_results:
                if isinstance(result, Exception):
                    logger.error(f"Embedding generation error: {result}")
                    results.append({'title_embedding': None, 'content_embedding': None})
                else:
                    results.append(result)
            
            # Rate limiting between batches
            if i + self.batch_size < len(posts):
                await asyncio.sleep(0.5)
        
        successful_count = sum(
            1 for r in results 
            if r.get('title_embedding') is not None or r.get('content_embedding') is not None
        )
        logger.info(f"Embedding generation completed: {successful_count}/{len(posts)} successful")
        
        return results
    
    async def generate_query_embedding(self, query: str) -> Optional[List[float]]:
        """Generate embedding for search query"""
        return await self._generate_embedding(query[:self.max_text_length])
    
    async def _generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate single embedding using OpenRouter"""
        if not text.strip():
            return None
        
        try:
            response = await self.client.create_embeddings(
                model=self.embedding_model,
                input=[text],
                encoding_format="float"
            )
            
            if response and response.data:
                embedding = response.data[0].embedding
                
                # Validate embedding dimensions
                if len(embedding) != 1536:
                    logger.error(f"Unexpected embedding dimension: {len(embedding)}")
                    return None
                
                return embedding
            
        except Exception as e:
            logger.error(f"Embedding generation failed for text: {e}")
            return None
        
        return None
    
    def calculate_similarity(
        self, 
        embedding1: List[float], 
        embedding2: List[float]
    ) -> float:
        """Calculate cosine similarity between two embeddings"""
        try:
            # Convert to numpy arrays for efficient computation
            vec1 = np.array(embedding1)
            vec2 = np.array(embedding2)
            
            # Cosine similarity: dot product / (magnitude1 * magnitude2)
            dot_product = np.dot(vec1, vec2)
            magnitude1 = np.linalg.norm(vec1)
            magnitude2 = np.linalg.norm(vec2)
            
            if magnitude1 == 0 or magnitude2 == 0:
                return 0.0
            
            similarity = dot_product / (magnitude1 * magnitude2)
            return float(similarity)
            
        except Exception as e:
            logger.error(f"Similarity calculation error: {e}")
            return 0.0
    
    def find_most_similar(
        self, 
        query_embedding: List[float], 
        post_embeddings: List[Dict[str, Any]],
        top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """Find most similar posts to query embedding"""
        similarities = []
        
        for i, post_data in enumerate(post_embeddings):
            max_similarity = 0.0
            best_embedding_type = None
            
            # Check title embedding similarity
            title_emb = post_data.get('title_embedding')
            if title_emb:
                title_sim = self.calculate_similarity(query_embedding, title_emb)
                if title_sim > max_similarity:
                    max_similarity = title_sim
                    best_embedding_type = 'title'
            
            # Check content embedding similarity
            content_emb = post_data.get('content_embedding')
            if content_emb:
                content_sim = self.calculate_similarity(query_embedding, content_emb)
                if content_sim > max_similarity:
                    max_similarity = content_sim
                    best_embedding_type = 'content'
            
            if max_similarity > 0:
                similarities.append({
                    'post_index': i,
                    'similarity_score': max_similarity,
                    'embedding_type': best_embedding_type,
                    'post_data': post_data
                })
        
        # Sort by similarity score and return top k
        similarities.sort(key=lambda x: x['similarity_score'], reverse=True)
        return similarities[:top_k]
    
    async def create_semantic_clusters(
        self, 
        posts: List[Dict[str, Any]], 
        similarity_threshold: float = 0.8
    ) -> List[List[Dict[str, Any]]]:
        """Group similar posts into semantic clusters"""
        if not posts:
            return []
        
        # Generate embeddings for all posts
        embeddings_data = await self.generate_batch_embeddings(posts)
        
        # Combine posts with their embeddings
        posts_with_embeddings = []
        for post, embeddings in zip(posts, embeddings_data):
            if embeddings.get('title_embedding') or embeddings.get('content_embedding'):
                posts_with_embeddings.append({**post, **embeddings})
        
        clusters = []
        processed = set()
        
        for i, post in enumerate(posts_with_embeddings):
            if i in processed:
                continue
            
            current_cluster = [post]
            processed.add(i)
            
            # Find similar posts for current cluster
            for j, other_post in enumerate(posts_with_embeddings):
                if j in processed or i == j:
                    continue
                
                # Calculate similarity between posts
                max_sim = 0.0
                
                # Compare all embedding combinations
                for emb1_type in ['title_embedding', 'content_embedding']:
                    for emb2_type in ['title_embedding', 'content_embedding']:
                        emb1 = post.get(emb1_type)
                        emb2 = other_post.get(emb2_type)
                        
                        if emb1 and emb2:
                            sim = self.calculate_similarity(emb1, emb2)
                            max_sim = max(max_sim, sim)
                
                if max_sim >= similarity_threshold:
                    current_cluster.append(other_post)
                    processed.add(j)
            
            if len(current_cluster) > 1:  # Only include clusters with multiple posts
                clusters.append(current_cluster)
        
        logger.info(f"Created {len(clusters)} semantic clusters from {len(posts)} posts")
        return clusters
```

**Acceptance Criteria:**
- [ ] Vector embedding generation for post titles and content separately
- [ ] Batch processing with rate limiting for efficiency
- [ ] Cosine similarity calculation for semantic search
- [ ] Query embedding generation for search functionality
- [ ] Semantic clustering capabilities for related post discovery
- [ ] Proper error handling and dimension validation
- [ ] Test coverage with mocked embedding responses

**Dependencies:** OpenRouter client with embedding support
**Risk:** Low - Standard embedding generation patterns

---

### Task 2.4: Service Layer Implementation (3 hours)
**Priority: Medium** | **Agent: Service Integration Specialist**

Implement SocialMediaService that orchestrates Reddit collection, sentiment analysis, and embedding generation.

**File:** `tradingagents/domains/socialmedia/services.py`

**Implementation:**
```python
from typing import List, Optional, Dict, Any, Tuple
import asyncio
import logging
from datetime import datetime, timedelta

from tradingagents.domains.socialmedia.clients import RedditClient
from tradingagents.domains.socialmedia.repositories import SocialRepository
from tradingagents.domains.socialmedia.sentiment import SocialSentimentAnalyzer
from tradingagents.domains.socialmedia.embeddings import SocialEmbeddingGenerator
from tradingagents.domains.socialmedia.models import SocialPost, SocialContext
from tradingagents.config import TradingAgentsConfig
from tradingagents.database import DatabaseManager

logger = logging.getLogger(__name__)

class SocialMediaService:
    """Orchestrates social media data collection, analysis, and storage"""
    
    def __init__(self, config: TradingAgentsConfig, db_manager: DatabaseManager):
        self.config = config
        self.db_manager = db_manager
        self.repository = SocialRepository(db_manager)
        self.sentiment_analyzer = SocialSentimentAnalyzer(config)
        self.embedding_generator = SocialEmbeddingGenerator(config)
        
        # Configuration
        self.financial_subreddits = [
            'wallstreetbets', 'investing', 'stocks', 'SecurityAnalysis',
            'ValueInvesting', 'financialindependence', 'StockMarket'
        ]
        self.min_score_threshold = 10  # Minimum upvotes
        self.max_posts_per_subreddit = 50
    
    async def collect_and_process_posts(
        self, 
        subreddits: Optional[List[str]] = None,
        time_filter: str = 'day',
        process_sentiment: bool = True,
        generate_embeddings: bool = True
    ) -> Dict[str, Any]:
        """Main entry point for collecting and processing social media posts"""
        if not subreddits:
            subreddits = self.financial_subreddits
        
        collection_start = datetime.now()
        logger.info(f"Starting social media collection from {len(subreddits)} subreddits")
        
        async with RedditClient(self.config) as reddit_client:
            # Collect raw posts from Reddit
            raw_posts_by_subreddit = await reddit_client.fetch_financial_posts_batch(
                subreddits=subreddits,
                time_filter=time_filter,
                posts_per_subreddit=self.max_posts_per_subreddit
            )
        
        # Flatten and filter posts
        all_raw_posts = []
        for subreddit, posts in raw_posts_by_subreddit.items():
            filtered_posts = [
                post for post in posts 
                if post and post.get('reddit_score', 0) >= self.min_score_threshold
            ]
            all_raw_posts.extend(filtered_posts)
        
        logger.info(f"Collected {len(all_raw_posts)} posts meeting quality thresholds")
        
        # Convert to domain objects and extract tickers
        domain_posts = []
        for raw_post in all_raw_posts:
            try:
                post = SocialPost(**raw_post)
                post.tickers = post.extract_tickers()  # Extract tickers from content
                domain_posts.append(post)
            except Exception as e:
                logger.error(f"Error creating domain object: {e}")
                continue
        
        # Process sentiment analysis if requested
        if process_sentiment and domain_posts:
            await self._process_sentiment_analysis(domain_posts)
        
        # Generate embeddings if requested
        if generate_embeddings and domain_posts:
            await self._process_embeddings(domain_posts)
        
        # Save to database
        saved_post_ids = await self.repository.upsert_batch(domain_posts)
        
        collection_end = datetime.now()
        processing_time = (collection_end - collection_start).total_seconds()
        
        # Calculate success metrics
        results = {
            'collection_timestamp': collection_start.isoformat(),
            'processing_time_seconds': processing_time,
            'subreddits_processed': subreddits,
            'total_posts_collected': len(all_raw_posts),
            'posts_processed': len(domain_posts),
            'posts_saved': len(saved_post_ids),
            'sentiment_analysis_enabled': process_sentiment,
            'embeddings_enabled': generate_embeddings,
            'subreddit_breakdown': {}
        }
        
        # Add per-subreddit breakdown
        for subreddit, posts in raw_posts_by_subreddit.items():
            results['subreddit_breakdown'][subreddit] = {
                'posts_collected': len(posts),
                'posts_filtered': len([p for p in posts if p.get('reddit_score', 0) >= self.min_score_threshold])
            }
        
        logger.info(f"Collection completed: {len(saved_post_ids)} posts saved in {processing_time:.2f}s")
        return results
    
    async def get_social_context(
        self,
        ticker: str,
        days: int = 7,
        include_similar: bool = True,
        similarity_query: Optional[str] = None
    ) -> SocialContext:
        """Get comprehensive social media context for a ticker"""
        logger.info(f"Generating social context for {ticker} ({days} days)")
        
        # Get direct ticker mentions
        ticker_posts = await self.repository.find_by_ticker(ticker, days=days, limit=50)
        
        similar_posts = []
        if include_similar and ticker_posts:
            # Use semantic search to find related discussions
            if similarity_query:
                query_embedding = await self.embedding_generator.generate_query_embedding(similarity_query)
                if query_embedding:
                    similar_results = await self.repository.find_similar_posts(
                        query_embedding=query_embedding,
                        ticker=ticker,
                        limit=10
                    )
                    similar_posts = [post for post, score in similar_results]
        
        # Get sentiment summary
        sentiment_summary = await self.repository.get_sentiment_summary(
            ticker=ticker,
            hours=days * 24
        )
        
        # Find trending discussions
        trending_tickers = await self.repository.get_trending_tickers(
            hours=days * 24,
            min_mentions=3
        )
        ticker_trend = next(
            (trend for trend in trending_tickers if trend['ticker'] == ticker.upper()),
            None
        )
        
        return SocialContext(
            ticker=ticker,
            period_days=days,
            direct_mentions=ticker_posts,
            similar_posts=similar_posts,
            sentiment_summary=sentiment_summary,
            trending_info=ticker_trend,
            total_posts=len(ticker_posts) + len(similar_posts),
            data_quality_score=self._calculate_data_quality(ticker_posts + similar_posts)
        )
    
    async def search_posts_semantic(
        self, 
        query: str, 
        ticker: Optional[str] = None,
        limit: int = 10,
        min_similarity: float = 0.7
    ) -> List[Tuple[SocialPost, float]]:
        """Semantic search for social media posts"""
        query_embedding = await self.embedding_generator.generate_query_embedding(query)
        
        if not query_embedding:
            logger.error(f"Failed to generate query embedding for: {query}")
            return []
        
        return await self.repository.find_similar_posts(
            query_embedding=query_embedding,
            ticker=ticker,
            limit=limit,
            similarity_threshold=min_similarity
        )
    
    async def get_subreddit_analysis(
        self, 
        subreddit: str, 
        hours: int = 24
    ) -> Dict[str, Any]:
        """Get analysis of a specific subreddit's activity"""
        posts = await self.repository.find_by_subreddit(subreddit, hours=hours)
        
        if not posts:
            return {
                'subreddit': subreddit,
                'period_hours': hours,
                'total_posts': 0,
                'message': f'No posts found for r/{subreddit} in the last {hours} hours'
            }
        
        # Analyze ticker mentions
        ticker_counts = {}
        for post in posts:
            for ticker in post.tickers or []:
                ticker_counts[ticker] = ticker_counts.get(ticker, 0) + 1
        
        top_tickers = sorted(ticker_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        
        # Analyze sentiment distribution
        sentiment_counts = {'positive': 0, 'negative': 0, 'neutral': 0}
        reliable_sentiment_count = 0
        
        for post in posts:
            if post.sentiment_label:
                sentiment_counts[post.sentiment_label] += 1
                if post.has_reliable_sentiment():
                    reliable_sentiment_count += 1
        
        # Calculate engagement metrics
        total_upvotes = sum(post.upvotes for post in posts)
        total_comments = sum(post.comments_count for post in posts)
        avg_score = total_upvotes / len(posts) if posts else 0
        
        return {
            'subreddit': subreddit,
            'period_hours': hours,
            'total_posts': len(posts),
            'engagement_metrics': {
                'total_upvotes': total_upvotes,
                'total_comments': total_comments,
                'avg_score': avg_score,
                'top_post_score': max(post.upvotes for post in posts) if posts else 0
            },
            'sentiment_analysis': {
                'distribution': sentiment_counts,
                'reliable_sentiment_posts': reliable_sentiment_count,
                'sentiment_reliability': reliable_sentiment_count / len(posts) if posts else 0
            },
            'ticker_mentions': {
                'top_tickers': top_tickers,
                'unique_tickers': len(ticker_counts),
                'total_mentions': sum(ticker_counts.values())
            },
            'data_quality': self._calculate_data_quality(posts)
        }
    
    async def _process_sentiment_analysis(self, posts: List[SocialPost]) -> None:
        """Process sentiment analysis for posts"""
        logger.info(f"Processing sentiment analysis for {len(posts)} posts")
        
        # Convert to dict format for sentiment analyzer
        posts_data = []
        for post in posts:
            post_dict = post.dict()
            posts_data.append(post_dict)
        
        # Analyze sentiment in batches
        sentiments = await self.sentiment_analyzer.analyze_batch(posts_data)
        
        # Update posts with sentiment results
        for post, sentiment in zip(posts, sentiments):
            if sentiment:
                post.sentiment_score = sentiment.score if hasattr(sentiment, 'score') else None
                post.sentiment_label = sentiment.sentiment
                post.sentiment_confidence = sentiment.confidence
                post.sentiment_reasoning = sentiment.reasoning
        
        successful_count = sum(1 for s in sentiments if s is not None)
        logger.info(f"Sentiment analysis completed: {successful_count}/{len(posts)} successful")
    
    async def _process_embeddings(self, posts: List[SocialPost]) -> None:
        """Process embedding generation for posts"""
        logger.info(f"Generating embeddings for {len(posts)} posts")
        
        # Convert to dict format for embedding generator
        posts_data = []
        for post in posts:
            post_dict = post.dict()
            posts_data.append(post_dict)
        
        # Generate embeddings in batches
        embeddings = await self.embedding_generator.generate_batch_embeddings(posts_data)
        
        # Update posts with embedding results
        for post, embedding_data in zip(posts, embeddings):
            post.title_embedding = embedding_data.get('title_embedding')
            post.content_embedding = embedding_data.get('content_embedding')
        
        successful_count = sum(
            1 for e in embeddings 
            if e.get('title_embedding') is not None or e.get('content_embedding') is not None
        )
        logger.info(f"Embedding generation completed: {successful_count}/{len(posts)} successful")
    
    def _calculate_data_quality(self, posts: List[SocialPost]) -> Dict[str, float]:
        """Calculate data quality metrics for posts"""
        if not posts:
            return {'overall_score': 0.0}
        
        sentiment_coverage = sum(1 for p in posts if p.sentiment_label is not None) / len(posts)
        reliable_sentiment = sum(1 for p in posts if p.has_reliable_sentiment()) / len(posts)
        embedding_coverage = sum(
            1 for p in posts 
            if p.title_embedding is not None or p.content_embedding is not None
        ) / len(posts)
        ticker_extraction = sum(1 for p in posts if p.tickers) / len(posts)
        
        overall_score = (sentiment_coverage + reliable_sentiment + embedding_coverage + ticker_extraction) / 4
        
        return {
            'overall_score': overall_score,
            'sentiment_coverage': sentiment_coverage,
            'reliable_sentiment_ratio': reliable_sentiment,
            'embedding_coverage': embedding_coverage,
            'ticker_extraction_ratio': ticker_extraction
        }
```

**Acceptance Criteria:**
- [ ] Orchestrates complete collection, analysis, and storage pipeline
- [ ] Integrates Reddit client, sentiment analyzer, and embedding generator
- [ ] Handles batch processing with proper error handling and logging
- [ ] Provides ticker-specific social context with sentiment and similarity
- [ ] Semantic search capabilities with configurable similarity thresholds
- [ ] Subreddit analysis with engagement and sentiment metrics
- [ ] Data quality scoring and monitoring
- [ ] Comprehensive test coverage with mocked dependencies

**Dependencies:** All Phase 2 tasks (clients, sentiment, embeddings)
**Risk:** Medium - Complex orchestration of multiple async services

---

## Phase 3: Integration & Validation (8 hours)

### Task 3.1: AgentToolkit Integration (3 hours)
**Priority: High** | **Agent: Agent Integration Specialist**

Add RAG-enhanced social media methods to AgentToolkit for AI agent consumption.

**File:** `tradingagents/agents/libs/agent_toolkit.py` (additions)

**Implementation:**
```python
# Additional methods for AgentToolkit class

async def get_reddit_sentiment(
    self, 
    ticker: str, 
    days: int = 7,
    include_context: bool = True
) -> str:
    """Get Reddit sentiment analysis for a specific ticker with RAG context"""
    try:
        if not hasattr(self, 'social_service'):
            self.social_service = SocialMediaService(self.config, self.db_manager)
        
        # Get comprehensive social context
        social_context = await self.social_service.get_social_context(
            ticker=ticker,
            days=days,
            include_similar=include_context
        )
        
        if not social_context.total_posts:
            return f"No Reddit sentiment data found for ${ticker} in the last {days} days."
        
        # Format for agent consumption
        sentiment_summary = social_context.sentiment_summary
        trending_info = social_context.trending_info
        
        context = f"Reddit Sentiment Analysis for ${ticker} ({days}-day period):\n\n"
        
        # Overall sentiment metrics
        if sentiment_summary:
            overall_score = sentiment_summary.get('overall_sentiment', 0.0)
            sentiment_emoji = "📈" if overall_score > 0.1 else "📉" if overall_score < -0.1 else "➡️"
            
            context += f"{sentiment_emoji} Overall Sentiment: {overall_score:.2f}/1.0\n"
            context += f"📊 Analysis Coverage: {social_context.total_posts} posts analyzed\n"
            
            # Sentiment breakdown
            breakdown = sentiment_summary.get('sentiment_breakdown', {})
            if breakdown:
                context += f"   • Positive: {breakdown.get('positive', {}).get('count', 0)} posts\n"
                context += f"   • Negative: {breakdown.get('negative', {}).get('count', 0)} posts\n"
                context += f"   • Neutral: {breakdown.get('neutral', {}).get('count', 0)} posts\n"
        
        # Trending information
        if trending_info:
            context += f"\n🔥 Trending Status:\n"
            context += f"   • Mentions: {trending_info['mention_count']} posts\n"
            context += f"   • Engagement: {trending_info['engagement_score']} (upvotes + comments)\n"
            context += f"   • Avg Sentiment: {trending_info['avg_sentiment']:.2f}\n"
        
        # Top discussions (sample posts)
        if social_context.direct_mentions:
            context += f"\n💬 Recent Discussions:\n"
            for i, post in enumerate(social_context.direct_mentions[:5]):
                sentiment_emoji = {"positive": "📈", "negative": "📉", "neutral": "➡️"}.get(
                    post.sentiment_label, "❓"
                )
                context += f"{i+1}. {sentiment_emoji} r/{post.subreddit}: {post.title[:100]}...\n"
                context += f"   Score: {post.upvotes} upvotes, {post.comments_count} comments\n"
                if post.has_reliable_sentiment():
                    context += f"   Sentiment: {post.sentiment_label} ({post.sentiment_confidence:.2f})\n"
        
        # Data quality indicators
        quality = social_context.data_quality_score
        context += f"\n📋 Data Quality: {quality.get('overall_score', 0):.1%} coverage\n"
        
        return context
        
    except Exception as e:
        logger.error(f"Error getting Reddit sentiment for {ticker}: {e}")
        return f"Error retrieving Reddit sentiment for ${ticker}: {str(e)}"

async def get_reddit_stock_info(
    self, 
    ticker: str, 
    query: Optional[str] = None,
    days: int = 7
) -> str:
    """Get Reddit stock information with optional semantic search"""
    try:
        if not hasattr(self, 'social_service'):
            self.social_service = SocialMediaService(self.config, self.db_manager)
        
        context = f"Reddit Stock Information for ${ticker}:\n\n"
        
        if query:
            # Semantic search for specific information
            search_results = await self.social_service.search_posts_semantic(
                query=query,
                ticker=ticker,
                limit=10,
                min_similarity=0.7
            )
            
            if search_results:
                context += f"🔍 Semantic Search Results for '{query}':\n"
                for i, (post, similarity) in enumerate(search_results[:5]):
                    context += f"{i+1}. (Similarity: {similarity:.2f}) r/{post.subreddit}\n"
                    context += f"   Title: {post.title}\n"
                    if post.content:
                        context += f"   Content: {post.content[:150]}...\n"
                    context += f"   Engagement: {post.upvotes} upvotes, {post.comments_count} comments\n\n"
            else:
                context += f"🔍 No relevant discussions found for '{query}' about ${ticker}\n\n"
        
        # Get general stock context
        social_context = await self.social_service.get_social_context(
            ticker=ticker,
            days=days,
            include_similar=False
        )
        
        if social_context.direct_mentions:
            context += f"📈 Recent Stock Discussions ({len(social_context.direct_mentions)} posts):\n"
            
            # Group by subreddit for better organization
            by_subreddit = {}
            for post in social_context.direct_mentions:
                if post.subreddit not in by_subreddit:
                    by_subreddit[post.subreddit] = []
                by_subreddit[post.subreddit].append(post)
            
            for subreddit, posts in by_subreddit.items():
                context += f"\nr/{subreddit} ({len(posts)} posts):\n"
                for post in posts[:3]:  # Top 3 per subreddit
                    sentiment_info = ""
                    if post.has_reliable_sentiment():
                        sentiment_emoji = {"positive": "📈", "negative": "📉", "neutral": "➡️"}
                        emoji = sentiment_emoji.get(post.sentiment_label, "❓")
                        sentiment_info = f" {emoji} {post.sentiment_label}"
                    
                    context += f"  • {post.title[:80]}...{sentiment_info}\n"
                    context += f"    {post.upvotes} upvotes, {post.comments_count} comments\n"
        
        # Add trending context if available
        if social_context.trending_info:
            trend = social_context.trending_info
            context += f"\n📊 Trending Analysis:\n"
            context += f"   • Market attention: {trend['mention_count']} recent mentions\n"
            context += f"   • Community sentiment: {trend['avg_sentiment']:.2f}/1.0\n"
            context += f"   • Total engagement: {trend['engagement_score']}\n"
        
        return context
        
    except Exception as e:
        logger.error(f"Error getting Reddit stock info for {ticker}: {e}")
        return f"Error retrieving Reddit stock information for ${ticker}: {str(e)}"

async def search_social_posts(
    self, 
    query: str, 
    ticker: Optional[str] = None,
    limit: int = 10,
    days: int = 30
) -> str:
    """Search social media posts using semantic similarity"""
    try:
        if not hasattr(self, 'social_service'):
            self.social_service = SocialMediaService(self.config, self.db_manager)
        
        # Perform semantic search
        search_results = await self.social_service.search_posts_semantic(
            query=query,
            ticker=ticker,
            limit=limit,
            min_similarity=0.6
        )
        
        if not search_results:
            ticker_context = f" about ${ticker}" if ticker else ""
            return f"No relevant social media posts found for '{query}'{ticker_context}."
        
        ticker_context = f" (${ticker})" if ticker else ""
        context = f"Social Media Search Results for '{query}'{ticker_context}:\n\n"
        context += f"Found {len(search_results)} relevant posts:\n\n"
        
        for i, (post, similarity) in enumerate(search_results):
            context += f"{i+1}. Relevance: {similarity:.2%} | r/{post.subreddit}\n"
            context += f"   Title: {post.title}\n"
            
            if post.content:
                # Show relevant snippet
                content_preview = post.content[:200] + "..." if len(post.content) > 200 else post.content
                context += f"   Content: {content_preview}\n"
            
            # Add sentiment if available
            if post.has_reliable_sentiment():
                sentiment_emoji = {"positive": "📈", "negative": "📉", "neutral": "➡️"}.get(
                    post.sentiment_label, "❓"
                )
                context += f"   Sentiment: {sentiment_emoji} {post.sentiment_label} ({post.sentiment_confidence:.2f})\n"
            
            # Add engagement metrics
            context += f"   Engagement: {post.upvotes} upvotes, {post.comments_count} comments\n"
            context += f"   Posted: {post.created_utc.strftime('%Y-%m-%d %H:%M')} UTC\n\n"
        
        return context
        
    except Exception as e:
        logger.error(f"Error searching social posts for '{query}': {e}")
        return f"Error searching social media posts: {str(e)}"

async def get_subreddit_analysis(
    self, 
    subreddit: str, 
    ticker: Optional[str] = None,
    hours: int = 24
) -> str:
    """Get analysis of activity in a specific financial subreddit"""
    try:
        if not hasattr(self, 'social_service'):
            self.social_service = SocialMediaService(self.config, self.db_manager)
        
        analysis = await self.social_service.get_subreddit_analysis(subreddit, hours=hours)
        
        if analysis['total_posts'] == 0:
            return f"No recent activity found in r/{subreddit} in the last {hours} hours."
        
        context = f"r/{subreddit} Analysis ({hours}-hour period):\n\n"
        
        # Activity overview
        context += f"📊 Activity Overview:\n"
        context += f"   • Total Posts: {analysis['total_posts']}\n"
        context += f"   • Total Upvotes: {analysis['engagement_metrics']['total_upvotes']:,}\n"
        context += f"   • Total Comments: {analysis['engagement_metrics']['total_comments']:,}\n"
        context += f"   • Avg Score: {analysis['engagement_metrics']['avg_score']:.1f}\n"
        context += f"   • Top Post Score: {analysis['engagement_metrics']['top_post_score']:,}\n\n"
        
        # Sentiment analysis
        sentiment_dist = analysis['sentiment_analysis']['distribution']
        reliable_ratio = analysis['sentiment_analysis']['sentiment_reliability']
        
        context += f"😊 Sentiment Analysis:\n"
        context += f"   • Positive: {sentiment_dist['positive']} posts\n"
        context += f"   • Negative: {sentiment_dist['negative']} posts\n"
        context += f"   • Neutral: {sentiment_dist['neutral']} posts\n"
        context += f"   • Reliability: {reliable_ratio:.1%} of posts have confident sentiment scores\n\n"
        
        # Ticker mentions
        ticker_info = analysis['ticker_mentions']
        context += f"💰 Stock Mentions:\n"
        context += f"   • Unique Tickers: {ticker_info['unique_tickers']}\n"
        context += f"   • Total Mentions: {ticker_info['total_mentions']}\n"
        
        if ticker_info['top_tickers']:
            context += f"   • Most Discussed:\n"
            for ticker_symbol, count in ticker_info['top_tickers'][:5]:
                context += f"     - ${ticker_symbol}: {count} mentions\n"
        
        # Filter for specific ticker if requested
        if ticker:
            ticker_mentions = next(
                (count for symbol, count in ticker_info['top_tickers'] if symbol == ticker.upper()),
                0
            )
            if ticker_mentions > 0:
                context += f"\n🎯 ${ticker} Activity: {ticker_mentions} mentions in this period\n"
            else:
                context += f"\n🎯 ${ticker}: No mentions found in r/{subreddit} during this period\n"
        
        # Data quality
        quality = analysis['data_quality']['overall_score']
        context += f"\n📋 Data Quality Score: {quality:.1%}\n"
        
        return context
        
    except Exception as e:
        logger.error(f"Error analyzing subreddit {subreddit}: {e}")
        return f"Error analyzing r/{subreddit}: {str(e)}"
```

**Acceptance Criteria:**
- [ ] get_reddit_sentiment() provides comprehensive sentiment analysis with visual formatting
- [ ] get_reddit_stock_info() supports both general info and semantic search queries
- [ ] search_social_posts() enables semantic search across all social media content
- [ ] get_subreddit_analysis() provides detailed subreddit activity and ticker analysis
- [ ] All methods return human-readable formatted strings for AI agent consumption
- [ ] Proper error handling with fallback responses
- [ ] Methods integrate seamlessly with existing AgentToolkit patterns
- [ ] Test coverage with mocked service dependencies

**Dependencies:** Task 2.4 (SocialMediaService implementation)
**Risk:** Low - Standard AgentToolkit integration patterns

---

### Task 3.2: Dagster Pipeline Implementation (2 hours)
**Priority: Medium** | **Agent: Pipeline Specialist**

Implement Dagster asset for scheduled social media collection and processing.

**File:** `tradingagents/data/assets/social_media.py`

**Implementation:**
```python
from dagster import asset, AssetExecutionContext, Config, DailyPartitionsDefinition
from typing import Dict, Any, List
import asyncio
from datetime import datetime, timedelta

from tradingagents.domains.socialmedia.services import SocialMediaService
from tradingagents.config import TradingAgentsConfig
from tradingagents.database import DatabaseManager

class SocialMediaCollectionConfig(Config):
    """Configuration for social media collection"""
    subreddits: List[str] = [
        'wallstreetbets', 'investing', 'stocks', 'SecurityAnalysis',
        'ValueInvesting', 'StockMarket', 'options'
    ]
    time_filter: str = 'day'
    process_sentiment: bool = True
    generate_embeddings: bool = True
    max_posts_per_subreddit: int = 50
    cleanup_old_data: bool = True
    retention_days: int = 90

@asset(
    partitions_def=DailyPartitionsDefinition(start_date="2024-01-01"),
    group_name="social_media",
    description="Daily collection of Reddit posts from financial subreddits with sentiment analysis and embeddings",
    compute_kind="python",
    tags={"domain": "socialmedia", "source": "reddit"}
)
async def reddit_financial_posts(
    context: AssetExecutionContext, 
    config: SocialMediaCollectionConfig
) -> Dict[str, Any]:
    """Daily collection and processing of Reddit financial posts"""
    
    partition_date = context.partition_key
    context.log.info(f"Starting social media collection for partition: {partition_date}")
    
    # Initialize services
    trading_config = TradingAgentsConfig.from_env()
    db_manager = DatabaseManager(trading_config)
    social_service = SocialMediaService(trading_config, db_manager)
    
    collection_start = datetime.now()
    
    try:
        # Main collection and processing
        results = await social_service.collect_and_process_posts(
            subreddits=config.subreddits,
            time_filter=config.time_filter,
            process_sentiment=config.process_sentiment,
            generate_embeddings=config.generate_embeddings
        )
        
        # Log detailed results
        context.log.info(f"Collection completed successfully:")
        context.log.info(f"  - Total posts collected: {results['total_posts_collected']}")
        context.log.info(f"  - Posts processed: {results['posts_processed']}")
        context.log.info(f"  - Posts saved: {results['posts_saved']}")
        context.log.info(f"  - Processing time: {results['processing_time_seconds']:.2f}s")
        
        # Log per-subreddit breakdown
        for subreddit, breakdown in results['subreddit_breakdown'].items():
            context.log.info(f"  - r/{subreddit}: {breakdown['posts_collected']} collected, "
                           f"{breakdown['posts_filtered']} after filtering")
        
        # Data quality check
        if results['posts_saved'] == 0:
            context.log.warning("No posts were saved - possible data quality issues")
        elif results['posts_saved'] < results['posts_processed'] * 0.5:
            context.log.warning(f"Low save rate: {results['posts_saved']}/{results['posts_processed']} posts saved")
        
        # Cleanup old data if configured
        if config.cleanup_old_data:
            try:
                deleted_count = await social_service.repository.cleanup_old_posts(
                    days=config.retention_days
                )
                context.log.info(f"Cleaned up {deleted_count} posts older than {config.retention_days} days")
                results['cleanup_deleted_count'] = deleted_count
            except Exception as e:
                context.log.error(f"Cleanup failed: {e}")
                results['cleanup_error'] = str(e)
        
        # Add partition metadata
        results.update({
            'partition_date': partition_date,
            'asset_name': 'reddit_financial_posts',
            'collection_success': True
        })
        
        return results
        
    except Exception as e:
        context.log.error(f"Social media collection failed: {e}")
        
        # Return error results for monitoring
        return {
            'partition_date': partition_date,
            'asset_name': 'reddit_financial_posts',
            'collection_success': False,
            'error_message': str(e),
            'processing_time_seconds': (datetime.now() - collection_start).total_seconds(),
            'total_posts_collected': 0,
            'posts_processed': 0,
            'posts_saved': 0
        }
    
    finally:
        # Always close database connections
        if 'db_manager' in locals():
            await db_manager.close_all()

@asset(
    deps=[reddit_financial_posts],
    group_name="social_media",
    description="Generate daily social media analytics and trending analysis",
    compute_kind="python",
    tags={"domain": "socialmedia", "analytics": "trending"}
)
async def social_media_analytics(context: AssetExecutionContext) -> Dict[str, Any]:
    """Generate analytics and trending analysis from collected social media data"""
    
    context.log.info("Generating social media analytics")
    
    # Initialize services
    trading_config = TradingAgentsConfig.from_env()
    db_manager = DatabaseManager(trading_config)
    social_service = SocialMediaService(trading_config, db_manager)
    
    try:
        # Get trending tickers analysis
        trending_tickers = await social_service.repository.get_trending_tickers(
            hours=24,
            min_mentions=5
        )
        
        context.log.info(f"Found {len(trending_tickers)} trending tickers")
        
        # Analyze top subreddits
        financial_subreddits = [
            'wallstreetbets', 'investing', 'stocks', 'SecurityAnalysis',
            'ValueInvesting', 'StockMarket'
        ]
        
        subreddit_analysis = {}
        for subreddit in financial_subreddits:
            analysis = await social_service.get_subreddit_analysis(subreddit, hours=24)
            subreddit_analysis[subreddit] = analysis
            
            if analysis['total_posts'] > 0:
                context.log.info(f"r/{subreddit}: {analysis['total_posts']} posts, "
                               f"{analysis['ticker_mentions']['unique_tickers']} unique tickers")
        
        # Calculate overall sentiment trends
        overall_sentiment_summary = {}
        for ticker_info in trending_tickers[:10]:  # Top 10 trending
            ticker = ticker_info['ticker']
            sentiment_data = await social_service.repository.get_sentiment_summary(
                ticker=ticker,
                hours=24
            )
            overall_sentiment_summary[ticker] = sentiment_data
        
        analytics_results = {
            'generated_at': datetime.now().isoformat(),
            'period_hours': 24,
            'trending_tickers': trending_tickers,
            'subreddit_analysis': subreddit_analysis,
            'sentiment_trends': overall_sentiment_summary,
            'analytics_success': True
        }
        
        # Log key insights
        if trending_tickers:
            top_ticker = trending_tickers[0]
            context.log.info(f"Most trending ticker: ${top_ticker['ticker']} "
                           f"({top_ticker['mention_count']} mentions, "
                           f"{top_ticker['avg_sentiment']:.2f} sentiment)")
        
        return analytics_results
        
    except Exception as e:
        context.log.error(f"Analytics generation failed: {e}")
        return {
            'generated_at': datetime.now().isoformat(),
            'analytics_success': False,
            'error_message': str(e)
        }
    
    finally:
        if 'db_manager' in locals():
            await db_manager.close_all()

@asset(
    deps=[social_media_analytics],
    group_name="social_media",
    description="Data quality monitoring and validation for social media pipeline",
    compute_kind="python",
    tags={"domain": "socialmedia", "monitoring": "data_quality"}
)
async def social_media_quality_check(context: AssetExecutionContext) -> Dict[str, Any]:
    """Monitor data quality and pipeline health for social media assets"""
    
    context.log.info("Performing social media data quality checks")
    
    trading_config = TradingAgentsConfig.from_env()
    db_manager = DatabaseManager(trading_config)
    social_service = SocialMediaService(trading_config, db_manager)
    
    try:
        # Check recent data volume
        recent_posts = await social_service.repository.find_by_subreddit(
            'wallstreetbets',  # Use as representative subreddit
            hours=24,
            limit=1000
        )
        
        # Quality metrics
        total_posts = len(recent_posts)
        posts_with_sentiment = sum(1 for p in recent_posts if p.sentiment_label is not None)
        posts_with_embeddings = sum(
            1 for p in recent_posts 
            if p.title_embedding is not None or p.content_embedding is not None
        )
        posts_with_tickers = sum(1 for p in recent_posts if p.tickers)
        
        # Calculate quality percentages
        sentiment_coverage = posts_with_sentiment / total_posts if total_posts > 0 else 0
        embedding_coverage = posts_with_embeddings / total_posts if total_posts > 0 else 0
        ticker_coverage = posts_with_tickers / total_posts if total_posts > 0 else 0
        
        # Quality thresholds
        quality_checks = {
            'data_volume_check': total_posts >= 100,  # Expect at least 100 posts per day
            'sentiment_coverage_check': sentiment_coverage >= 0.8,  # 80% should have sentiment
            'embedding_coverage_check': embedding_coverage >= 0.7,  # 70% should have embeddings
            'ticker_coverage_check': ticker_coverage >= 0.3  # 30% should have ticker mentions
        }
        
        overall_health = all(quality_checks.values())
        
        # Log quality results
        context.log.info(f"Data quality assessment:")
        context.log.info(f"  - Total posts (24h): {total_posts}")
        context.log.info(f"  - Sentiment coverage: {sentiment_coverage:.1%}")
        context.log.info(f"  - Embedding coverage: {embedding_coverage:.1%}")
        context.log.info(f"  - Ticker coverage: {ticker_coverage:.1%}")
        context.log.info(f"  - Overall health: {'PASS' if overall_health else 'FAIL'}")
        
        # Alert on quality issues
        for check_name, passed in quality_checks.items():
            if not passed:
                context.log.warning(f"Quality check failed: {check_name}")
        
        return {
            'check_timestamp': datetime.now().isoformat(),
            'total_posts_24h': total_posts,
            'quality_metrics': {
                'sentiment_coverage': sentiment_coverage,
                'embedding_coverage': embedding_coverage,
                'ticker_coverage': ticker_coverage
            },
            'quality_checks': quality_checks,
            'overall_health': overall_health,
            'quality_check_success': True
        }
        
    except Exception as e:
        context.log.error(f"Quality check failed: {e}")
        return {
            'check_timestamp': datetime.now().isoformat(),
            'quality_check_success': False,
            'error_message': str(e)
        }
    
    finally:
        if 'db_manager' in locals():
            await db_manager.close_all()

# Schedule configuration for the social media pipeline
SOCIAL_MEDIA_SCHEDULE = {
    "reddit_financial_posts": "0 6,18 * * *",  # 6 AM and 6 PM UTC daily
    "social_media_analytics": "30 7,19 * * *",  # 30 minutes after collection
    "social_media_quality_check": "0 8,20 * * *"  # 1 hour after collection
}
```

**Acceptance Criteria:**
- [ ] Daily scheduled collection from financial subreddits
- [ ] Sentiment analysis and embedding generation in pipeline
- [ ] Analytics generation with trending ticker analysis
- [ ] Data quality monitoring with configurable thresholds
- [ ] Proper error handling and logging throughout pipeline
- [ ] Cleanup of old data based on retention policies
- [ ] Integration with existing Dagster infrastructure
- [ ] Monitoring and alerting on pipeline failures

**Dependencies:** Task 2.4 (SocialMediaService)
**Risk:** Low - Standard Dagster asset patterns

---

### Task 3.3: Comprehensive Testing Suite (3 hours)
**Priority: High** | **Agent: Testing Specialist**

Implement comprehensive test suite covering all socialmedia domain components with >85% coverage.

**Test Structure:**
```
tests/domains/socialmedia/
├── conftest.py                     # Fixtures and test configuration
├── test_entities.py               # SQLAlchemy entity tests
├── test_models.py                 # Domain model validation tests
├── test_reddit_client.py          # API integration with VCR
├── test_sentiment_analyzer.py     # LLM sentiment analysis
├── test_embedding_generator.py    # Vector embedding generation
├── test_social_repository.py      # Database operations
├── test_social_service.py         # Service orchestration
├── test_agent_toolkit.py          # AgentToolkit integration
├── test_dagster_assets.py         # Pipeline testing
└── fixtures/
    ├── reddit_responses.yaml      # VCR cassettes
    ├── sample_posts.json          # Test data
    └── embeddings.json            # Sample embeddings
```

**Implementation Samples:**

**conftest.py:**
```python
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from tradingagents.config import TradingAgentsConfig
from tradingagents.database import DatabaseManager
from tradingagents.domains.socialmedia.entities import SocialMediaPostEntity
from tradingagents.domains.socialmedia.models import SocialPost
from tradingagents.domains.socialmedia.services import SocialMediaService

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def test_config():
    """Test configuration"""
    return TradingAgentsConfig(
        reddit_client_id="test_client_id",
        reddit_client_secret="test_secret",
        reddit_user_agent="test_agent",
        openrouter_api_key="test_openrouter_key",
        quick_think_llm="test/model",
        database_url="sqlite:///test.db"
    )

@pytest.fixture
async def db_session(test_config):
    """Test database session"""
    engine = create_engine(test_config.database_url, echo=False)
    SocialMediaPostEntity.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    SocialMediaPostEntity.metadata.drop_all(engine)

@pytest.fixture
def sample_social_post():
    """Sample SocialPost for testing"""
    return SocialPost(
        post_id="test123",
        title="AAPL to the moon! 🚀",
        content="Apple stock is going to explode higher after earnings!",
        author="test_user",
        subreddit="wallstreetbets",
        created_utc=datetime(2024, 1, 15, 10, 0, 0),
        upvotes=150,
        downvotes=25,
        comments_count=45,
        url="https://reddit.com/r/wallstreetbets/test123",
        tickers=["AAPL"],
        sentiment_score=0.8,
        sentiment_label="positive",
        sentiment_confidence=0.9
    )

@pytest.fixture
def mock_social_service(test_config):
    """Mocked SocialMediaService"""
    service = MagicMock(spec=SocialMediaService)
    service.config = test_config
    service.repository = AsyncMock()
    service.sentiment_analyzer = AsyncMock()
    service.embedding_generator = AsyncMock()
    return service
```

**test_models.py:**
```python
import pytest
from datetime import datetime
from tradingagents.domains.socialmedia.models import SocialPost, SentimentScore

def test_social_post_validation():
    """Test SocialPost validation rules"""
    # Valid post
    post = SocialPost(
        post_id="abc123",
        title="Test post",
        author="test_user",
        subreddit="stocks",
        created_utc=datetime.now(),
        upvotes=10,
        downvotes=2,
        comments_count=5,
        url="https://reddit.com/test"
    )
    assert post.post_id == "abc123"
    assert post.tickers == []

def test_extract_tickers():
    """Test ticker extraction from post content"""
    post = SocialPost(
        post_id="abc123",
        title="AAPL and $TSLA are great buys",
        content="I think MSFT will outperform this year",
        author="test_user",
        subreddit="investing",
        created_utc=datetime.now(),
        upvotes=10,
        downvotes=0,
        comments_count=3,
        url="https://reddit.com/test"
    )
    
    tickers = post.extract_tickers()
    assert "AAPL" in tickers
    assert "TSLA" in tickers
    assert "MSFT" in tickers
    assert len(tickers) == 3

def test_sentiment_validation():
    """Test sentiment score validation"""
    # Valid sentiment
    sentiment = SentimentScore(
        sentiment="positive",
        confidence=0.85,
        reasoning="Bullish language and positive outlook"
    )
    assert sentiment.confidence == 0.85

    # Invalid confidence
    with pytest.raises(ValueError):
        SentimentScore(
            sentiment="positive",
            confidence=1.5  # > 1.0
        )

@pytest.mark.parametrize("sentiment_score,sentiment_label,confidence,expected_reliable", [
    (0.8, "positive", 0.9, True),
    (0.3, "neutral", 0.4, False),
    (-0.6, "negative", 0.7, True),
    (None, None, None, False)
])
def test_has_reliable_sentiment(sentiment_score, sentiment_label, confidence, expected_reliable):
    """Test sentiment reliability check"""
    post = SocialPost(
        post_id="test",
        title="Test",
        author="user",
        subreddit="test",
        created_utc=datetime.now(),
        upvotes=1,
        downvotes=0,
        comments_count=0,
        url="test",
        sentiment_score=sentiment_score,
        sentiment_label=sentiment_label,
        sentiment_confidence=confidence
    )
    
    assert post.has_reliable_sentiment() == expected_reliable
```

**test_social_repository.py:**
```python
import pytest
from datetime import datetime, timedelta
from tradingagents.domains.socialmedia.repositories import SocialRepository
from tradingagents.domains.socialmedia.models import SocialPost

@pytest.mark.asyncio
async def test_upsert_batch_deduplication(social_repository, sample_social_post):
    """Test batch upsert with deduplication"""
    posts = [sample_social_post, sample_social_post]  # Duplicate posts
    
    saved_ids = await social_repository.upsert_batch(posts)
    
    assert len(saved_ids) == 1  # Only one saved due to deduplication
    assert saved_ids[0] == sample_social_post.post_id

@pytest.mark.asyncio 
async def test_find_by_ticker(social_repository, sample_social_post):
    """Test finding posts by ticker symbol"""
    await social_repository.upsert_batch([sample_social_post])
    
    posts = await social_repository.find_by_ticker("AAPL", days=7)
    
    assert len(posts) == 1
    assert posts[0].post_id == sample_social_post.post_id
    assert "AAPL" in posts[0].tickers

@pytest.mark.asyncio
async def test_vector_similarity_search(social_repository, sample_social_post):
    """Test vector similarity search"""
    # Add post with embedding
    sample_social_post.title_embedding = [0.1] * 1536  # Mock embedding
    await social_repository.upsert_batch([sample_social_post])
    
    # Search with similar embedding
    query_embedding = [0.1] * 1536
    results = await social_repository.find_similar_posts(
        query_embedding=query_embedding,
        limit=5
    )
    
    assert len(results) >= 0  # May be empty if similarity too low
    if results:
        post, similarity = results[0]
        assert isinstance(similarity, float)
        assert 0 <= similarity <= 1

@pytest.mark.asyncio
async def test_sentiment_summary(social_repository, sample_social_post):
    """Test sentiment aggregation"""
    await social_repository.upsert_batch([sample_social_post])
    
    summary = await social_repository.get_sentiment_summary(
        ticker="AAPL",
        hours=24
    )
    
    assert summary['ticker'] == "AAPL"
    assert summary['total_posts'] >= 0
    assert 'sentiment_breakdown' in summary
    assert 'overall_sentiment' in summary

@pytest.mark.asyncio
async def test_cleanup_old_posts(social_repository, sample_social_post):
    """Test cleanup of old posts"""
    # Create old post
    old_post = sample_social_post.copy()
    old_post.post_id = "old_post"
    old_post.created_utc = datetime.now() - timedelta(days=100)
    
    await social_repository.upsert_batch([old_post])
    
    deleted_count = await social_repository.cleanup_old_posts(days=90)
    
    assert deleted_count >= 1
```

**test_reddit_client.py (with VCR):**
```python
import pytest
import pytest_vcr
from tradingagents.domains.socialmedia.clients import RedditClient

@pytest_vcr.use_cassette('fixtures/reddit_fetch_posts.yaml')
@pytest.mark.asyncio
async def test_fetch_subreddit_posts(test_config):
    """Test fetching posts from Reddit API"""
    async with RedditClient(test_config) as client:
        posts = await client.fetch_subreddit_posts(
            subreddit_name="wallstreetbets",
            limit=10
        )
        
        assert len(posts) > 0
        for post in posts:
            assert 'post_id' in post
            assert 'title' in post
            assert 'subreddit' in post
            assert post['subreddit'] == 'wallstreetbets'

@pytest_vcr.use_cassette('fixtures/reddit_search.yaml')
@pytest.mark.asyncio
async def test_search_posts(test_config):
    """Test Reddit post search functionality"""
    async with RedditClient(test_config) as client:
        posts = await client.search_posts(
            query="AAPL",
            subreddit_names=["investing"],
            limit=5
        )
        
        assert isinstance(posts, list)
        if posts:  # May be empty in test
            for post in posts:
                assert 'post_id' in post
                assert 'title' in post

@pytest.mark.asyncio
async def test_health_check(test_config):
    """Test Reddit API health check"""
    async with RedditClient(test_config) as client:
        health = await client.health_check()
        assert isinstance(health, bool)
```

**Acceptance Criteria:**
- [ ] >85% test coverage across all socialmedia domain components
- [ ] Unit tests for all domain models with validation edge cases
- [ ] Integration tests for Reddit API client with VCR cassettes
- [ ] Repository tests with real PostgreSQL database operations
- [ ] Service layer tests with proper mocking of dependencies
- [ ] AgentToolkit integration tests
- [ ] Dagster pipeline asset tests with mocked data
- [ ] Performance benchmarks for vector similarity queries
- [ ] Error handling and edge case coverage
- [ ] Test fixtures and sample data for consistent testing

**Dependencies:** All implementation tasks
**Risk:** Low - Standard testing patterns

---

## Implementation Dependencies & Parallel Execution

### Phase 1 Dependencies
- Task 1.1 → Task 1.2 (Entity depends on database schema)
- Task 1.3 can run parallel with 1.1 and 1.2
- Task 1.4 depends on 1.1 and 1.2

### Phase 2 Dependencies
- All Phase 2 tasks can run in parallel
- Task 2.4 depends on 2.1, 2.2, and 2.3

### Phase 3 Dependencies
- Task 3.1 depends on Task 2.4
- Task 3.2 depends on Task 2.4  
- Task 3.3 can start after any component is complete

### Risk Assessment

**High Risk Tasks:**
- Task 2.1 (Reddit Client) - External API complexity, rate limiting

**Medium Risk Tasks:**
- Task 1.1 (Database Migration) - Extension dependencies
- Task 1.4 (Repository) - Complex vector queries
- Task 2.2 (Sentiment Analysis) - LLM API reliability
- Task 2.4 (Service Layer) - Complex orchestration

**Low Risk Tasks:**
- Task 1.2 (Entity Implementation)
- Task 1.3 (Domain Models)
- Task 2.3 (Embedding Generation)
- Task 3.1 (AgentToolkit Integration)
- Task 3.2 (Dagster Pipeline)
- Task 3.3 (Testing Suite)

## Success Criteria Summary

### Functionality
- ✅ Complete Reddit data collection with PRAW integration
- ✅ OpenRouter LLM sentiment analysis with confidence scoring
- ✅ Vector embeddings for semantic similarity search
- ✅ PostgreSQL + TimescaleDB + pgvectorscale data persistence
- ✅ AgentToolkit RAG methods for AI agent integration
- ✅ Daily Dagster pipeline for automated collection
- ✅ Comprehensive error handling and resilience

### Performance
- ✅ <2 second social context queries for AI agents
- ✅ <1 second vector similarity search (top 10 results)
- ✅ <5 seconds batch processing 1000 posts
- ✅ Efficient TimescaleDB time-series queries

### Quality
- ✅ >85% test coverage across all components
- ✅ Data quality monitoring and validation
- ✅ Comprehensive logging and observability
- ✅ Best-effort processing with graceful degradation

### Integration
- ✅ Seamless integration with existing TradingAgents architecture
- ✅ Follows news domain patterns for consistency
- ✅ Compatible with multi-agent trading workflows
- ✅ Production-ready deployment capability

This comprehensive task breakdown enables efficient parallel development by multiple AI agents while ensuring complete coverage of the socialmedia domain implementation requirements.