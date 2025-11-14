# TradingAgents Personal Fork Roadmap

## Overview

This roadmap outlines the technical development path for the personal fork of TradingAgents, focusing on building a robust data infrastructure with PostgreSQL + TimescaleDB + pgvectorscale, implementing RAG-powered agents, and establishing automated data collection pipelines with Dagster.

**Last Updated**: 2025-11-11

### Key Roadmap Changes
- **Pragmatic Dagster Integration**: Dagster jobs built incrementally per domain (not separate phase)
- **Accurate Timeline**: 10-14 weeks total (vs original 16-22 weeks) based on actual progress
- **Incremental Automation**: Each domain gets automated collection as it completes
- **Earlier Production Readiness**: Automated data collection starts Week 1 (not Month 4)

### Development Velocity
- **Observed Completion Rate**: News clients 85-90% complete with 600+ lines of quality tests
- **AI-Assisted Multiplier**: 3-4x faster development with spec-driven workflow
- **Target Task Velocity**: 15-20 tasks/week with AI assistance
- **Test Coverage**: Maintained 85%+ with pytest-vcr pattern

## Current Status: Phase 1 - News Domain + Dagster Integration (85% Complete)

The foundation has been established with core domain architecture, comprehensive testing framework, and the news domain clients complete.

### Completed Infrastructure
- **Domain Architecture**: Clean separation of news, marketdata, and socialmedia domains
- **Testing Framework**: Pragmatic TDD with 85%+ coverage, pytest-vcr for HTTP mocking
- **News Clients**: Google News RSS + Article Scraper with comprehensive tests (600+ lines)
- **Database Stack**: PostgreSQL + TimescaleDB + pgvectorscale ready
- **Basic Agent System**: Multi-agent trading analysis framework with LangGraph

### Current Priorities (Next 5-7 Days)
1. **Complete News Domain Foundation** - Repository, Service, Entity layers
2. **LLM Integration** - OpenRouter sentiment analysis + vector embeddings
3. **Basic Dagster Job** - Automated daily news collection
4. **Spec Documentation** - Create status.md and tasks.md for progress tracking

## Development Phases

### Phase 1: News Domain + Basic Dagster (Current - 85% Complete)
**Timeline**: 5-7 days remaining
**Status**: 🔄 In Progress

#### Remaining Work (5-7 days)
- **News Repository Layer**: PostgreSQL async operations with TimescaleDB (1-2 days)
- **News Service Layer**: Business logic with LLM integration (1-2 days)
- **NewsArticle Entity**: Domain models with sentiment and embeddings (1 day)
- **OpenRouter Integration**: Sentiment analysis via LLM (1-2 days)
- **Vector Embeddings**: OpenAI embeddings via OpenRouter for semantic search (1 day)
- **Basic Dagster Job**: Daily news collection automation (1-2 days)
- **Integration Testing**: End-to-end workflow validation (1 day)

#### Key Deliverables
- News domain following Router → Service → Repository → Entity → Database pattern
- OpenRouter LLM sentiment analysis operational
- pgvectorscale vector embeddings for semantic search
- Automated Dagster job for daily news collection
- 85%+ test coverage maintained

#### Success Criteria
- ✅ Complete layered architecture implemented
- ✅ LLM sentiment scores with confidence ratings
- ✅ Vector embeddings enabling semantic search
- ✅ Dagster job running daily news collection
- ✅ Query performance < 2 seconds
- ✅ News domain ready for agent integration

### Phase 2: Market Data Domain + Dagster Integration (Next Priority)
**Timeline**: 4-5 weeks
**Status**: 📋 Planned

#### Core Objectives
- **TimescaleDB Hypertables**: Efficient time-series storage for price/volume data
- **Market Data Collection**: FinnHub/yfinance integration with retry logic
- **PostgreSQL Migration**: Move from file-based to database storage
- **Technical Indicators**: MACD, RSI, Bollinger Bands calculations
- **Dagster Market Data Job**: Twice-daily price data collection automation
- **Performance Optimization**: Sub-100ms queries with proper indexing

#### Key Deliverables
- MarketDataRepository with TimescaleDB optimization
- MarketDataService with technical analysis calculations
- MarketData entities (Price, OHLCV, TechnicalIndicators)
- Dagster job for automated twice-daily collection
- pytest-vcr tests for API clients
- Performance benchmarks for time-series queries

#### Success Criteria
- ✅ TimescaleDB hypertables storing historical price data
- ✅ Sub-100ms queries for price lookups and indicators
- ✅ Technical indicators calculating accurately
- ✅ Dagster job running twice daily (market open/close)
- ✅ Complete migration from file-based storage
- ✅ Market data domain ready for agent integration

### Phase 3: Social Media Domain + Dagster Integration
**Timeline**: 2-3 weeks
**Status**: 📋 Planned

#### Core Objectives
- **Reddit Integration**: PRAW library for financial subreddits (r/wallstreetbets, r/stocks)
- **Twitter/X Alternative**: Evaluate Reddit-only approach or alternative sources
- **Social Sentiment Analysis**: OpenRouter LLM sentiment across posts
- **Cross-Domain Relations**: Link social sentiment to market data and news
- **Dagster Social Media Job**: Daily social sentiment collection
- **Vector Embeddings**: Semantic search across social discussions

#### Key Deliverables
- RedditClient with pytest-vcr tests
- SocialMediaRepository with PostgreSQL + pgvectorscale
- SocialMediaService with sentiment aggregation
- Dagster job for daily Reddit data collection
- Cross-domain correlation queries (social ↔ news ↔ price)
- Vector embeddings for semantic post search

#### Success Criteria
- ✅ Reddit data collected daily from financial subreddits
- ✅ Sentiment scores integrated with market events
- ✅ Cross-domain relationships queryable in database
- ✅ Dagster job running daily social collection
- ✅ Vector embeddings enabling semantic social search
- ✅ Three-domain architecture complete

#### Blockers to Resolve
- **Reddit API Access**: Obtain REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET
- **Twitter/X Alternative**: Evaluate API costs or alternative data sources

### Phase 4: RAG Enhancement + Advanced Orchestration
**Timeline**: 3-4 weeks
**Status**: 📋 Planned

#### Core Objectives
- **RAG Agent Enhancement**: All agents use vector similarity search for context
- **Historical Pattern Matching**: Semantic search for comparable market scenarios
- **Cross-Domain RAG**: Agents query across news, price, and social data
- **Advanced Dagster Features**: Data quality monitoring, gap detection, backfill
- **Performance Optimization**: Vector query tuning, database optimization
- **Monitoring & Alerting**: Pipeline health tracking and failure notifications

#### Key Deliverables
- RAG-enhanced agents with similarity-based context retrieval
- Cross-domain vector search (find similar market conditions)
- Dagster data quality checks and validation
- Automated backfill for missing historical data
- Monitoring dashboard for pipeline health
- Performance benchmarks for vector queries (< 50ms target)

#### Success Criteria
- ✅ All agents using RAG for contextual decisions
- ✅ Vector similarity search < 50ms across all domains
- ✅ Cross-domain queries enabling holistic analysis
- ✅ Dagster monitoring with automated alerts
- ✅ Data quality metrics tracked and reported
- ✅ Historical gaps detected and auto-filled
- ✅ Production-ready data infrastructure complete

## Technical Milestones

### Revised Timeline: 10-14 weeks (vs original 16-22 weeks)

**Phase Breakdown:**
- Phase 1 (News + Dagster): 5-7 days
- Phase 2 (Market Data + Dagster): 4-5 weeks
- Phase 3 (Social Media + Dagster): 2-3 weeks
- Phase 4 (RAG + Advanced Orchestration): 3-4 weeks

### Database Architecture
- **Week 1**: PostgreSQL + TimescaleDB + pgvectorscale operational (News domain)
- **Week 6**: TimescaleDB hypertables optimized for market data time-series
- **Week 9**: Three-domain database architecture complete with vector embeddings
- **Week 12**: Full RAG implementation with cross-domain similarity search

### Agent Capabilities
- **Week 1**: News Analysts accessing news with LLM sentiment
- **Week 6**: Technical Analysts using market data with indicators
- **Week 9**: Sentiment Analysts using social media data
- **Week 12**: All agents RAG-enhanced with historical context

### Data Pipeline Maturity (Incremental Dagster)
- **Week 1**: Daily news collection automated via Dagster
- **Week 6**: Twice-daily market data collection automated
- **Week 9**: Daily social media collection automated
- **Week 12**: Production-grade orchestration with monitoring, backfill, and alerting

## Success Metrics

### Technical Excellence
- **Test Coverage**: Maintain 85%+ across all domains
- **Query Performance**: < 100ms for common database operations
- **Pipeline Reliability**: 99%+ uptime for data collection
- **Data Quality**: < 0.1% missing data points across all domains

### Feature Completeness
- **Domain Coverage**: 100% implementation across news, marketdata, socialmedia
- **Agent Capabilities**: RAG-enhanced decision making operational
- **Data Infrastructure**: Complete PostgreSQL + TimescaleDB + pgvectorscale stack
- **Automation**: Fully automated data collection and processing

### Development Velocity
- **Code Quality**: Consistent formatting, type checking, and documentation
- **Testing Strategy**: Comprehensive test suite with domain-specific approaches
- **Architecture Consistency**: Clean domain separation and layered architecture
- **Performance Optimization**: Regular profiling and optimization cycles

## Risk Management

### Technical Risks
- **Database Performance**: Mitigate with proper indexing and query optimization
- **API Rate Limits**: Implement intelligent backoff and caching strategies  
- **Data Quality**: Establish comprehensive validation and monitoring
- **Vector Search Performance**: Optimize pgvectorscale configuration and queries

### Development Risks
- **Scope Creep**: Maintain focus on sequential domain completion
- **Technical Debt**: Regular refactoring and code quality maintenance
- **Testing Coverage**: Continuous integration with coverage enforcement
- **Documentation**: Maintain comprehensive documentation throughout development

## Long-Term Vision (6+ Months)

### Advanced Capabilities
- **Strategy Backtesting**: Historical strategy validation with complete data
- **Real-Time Analysis**: Live market analysis with sub-second agent responses
- **Advanced RAG**: Multi-modal RAG with charts, documents, and audio data
- **Performance Analytics**: Comprehensive analysis of agent decision accuracy

### Research Applications
- **Academic Research**: Platform for publishing trading AI research
- **Strategy Development**: Complete environment for developing proprietary strategies
- **Data Science**: Advanced analytics and machine learning on financial data
- **Educational Use**: Comprehensive learning platform for financial AI

This roadmap prioritizes building a solid data foundation before enhancing agent capabilities, ensuring each phase delivers measurable value while maintaining high code quality and comprehensive testing.