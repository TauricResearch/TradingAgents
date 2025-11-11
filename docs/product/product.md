# TradingAgents Product Definition

## Product Overview

**TradingAgents** is a personal fork of the multi-agent LLM financial trading framework designed for individual trading research and data infrastructure development. This fork focuses on PostgreSQL + TimescaleDB + pgvectorscale architecture with RAG-powered agents for enhanced decision making through historical context and pattern recognition.

## Target User

### Primary User
- **Single Developer/Researcher**: Individual focused on personal trading research, strategy development, and building robust data infrastructure for financial analysis

### Use Cases
- **Personal Trading Research**: Developing and testing proprietary trading strategies with AI-powered analysis
- **Data Infrastructure Development**: Building scalable time-series and vector search capabilities for financial data
- **RAG Implementation**: Experimenting with retrieval-augmented generation for context-aware trading decisions
- **Academic Research**: Individual research projects exploring AI applications in financial markets

## Core Value Proposition

This personal fork transforms the original TradingAgents framework into a focused research and development platform that:
- **Enables Personal Research**: Provides a complete data infrastructure for individual trading research and strategy development
- **Implements Modern Architecture**: PostgreSQL + TimescaleDB + pgvectorscale stack for efficient time-series and vector operations
- **Supports RAG-Powered Decisions**: Agents leverage historical context through vector similarity search for informed decisions
- **Streamlines Data Collection**: Automated daily/twice-daily data pipelines with Dagster orchestration
- **Unifies LLM Access**: Single OpenRouter integration for consistent model access across all agents

## Key Features

### Enhanced Data Architecture
- **PostgreSQL Foundation**: Robust relational database for structured financial data
- **TimescaleDB Integration**: Optimized time-series storage and querying for market data
- **pgvectorscale Extension**: High-performance vector search for RAG and similarity matching
- **Automated Migrations**: Database schema versioning and management

### RAG-Powered Multi-Agent System
- **Context-Aware Analysis**: Agents use vector similarity search to find relevant historical patterns
- **Enhanced Decision Making**: Retrieval-augmented generation provides historical context for trading decisions
- **Pattern Recognition**: Semantic similarity matching for comparable market conditions
- **Learning from History**: Agents reference past decisions and outcomes for improved analysis

### Automated Data Collection
- **Dagster Orchestration**: Daily/twice-daily data collection pipelines with monitoring and alerting
- **Quality Assurance**: Automated data validation, gap detection, and backfill capabilities
- **Domain Coverage**: Comprehensive data collection for news (95% complete), market data, and social media domains
- **Scalable Processing**: Efficient batch processing with dependency management

### Unified LLM Provider
- **OpenRouter Integration**: Single provider for all model access, reducing API complexity
- **Cost Optimization**: Strategic model selection with clear separation between analysis and data processing models
- **Model Flexibility**: Easy switching between different models through OpenRouter's unified interface

## Business Context

### Research Focus Areas
- **Individual Strategy Development**: Personal trading algorithm research and backtesting
- **Data Infrastructure**: Building scalable financial data storage and retrieval systems
- **AI/ML in Finance**: Experimenting with RAG, vector search, and multi-agent systems
- **Time-Series Analysis**: Advanced market data analysis with TimescaleDB optimization

### Technical Advantages
- **Modern Data Stack**: PostgreSQL + TimescaleDB + pgvectorscale provides production-grade data infrastructure
- **RAG Implementation**: Real-world application of retrieval-augmented generation in financial decision making
- **Comprehensive Testing**: Maintains 85%+ test coverage with pragmatic TDD approach
- **Scalable Architecture**: Domain-driven design supports extensibility and maintainability

### Development Metrics
- **Code Quality**: 85%+ test coverage, comprehensive type checking, automated formatting
- **Data Pipeline Health**: Automated monitoring and alerting for data collection processes
- **Performance**: Optimized queries with TimescaleDB, fast vector search with pgvectorscale
- **Maintainability**: Clean architecture patterns, comprehensive documentation

## Technical Constraints

### Requirements
- **Database**: PostgreSQL with TimescaleDB and pgvectorscale extensions
- **Python Environment**: Python 3.13+ with comprehensive dependency management
- **API Access**: OpenRouter API key for LLM access, optional FinnHub for real-time data
- **Infrastructure**: Docker Compose for local development, Dagster for data orchestration

### Architectural Decisions
- **Single Developer Focus**: Optimized for individual use rather than multi-user collaboration
- **PostgreSQL-First**: All data persistence through PostgreSQL with appropriate extensions
- **OpenRouter Exclusive**: Unified LLM provider reduces complexity and improves consistency
- **Domain Completion**: Sequential domain development (news 95% → marketdata → socialmedia)

## Project Scope

### Current Implementation Status
- **News Domain**: 95% complete with comprehensive article scraping and sentiment analysis
- **Core Infrastructure**: PostgreSQL + TimescaleDB + pgvectorscale foundation established
- **Agent Framework**: RAG-powered agents with vector search capabilities
- **Data Pipelines**: Dagster orchestration for automated data collection

### Included Features
- Complete PostgreSQL-based data architecture with time-series and vector extensions
- RAG-enhanced multi-agent analysis framework with historical context
- Automated data collection pipelines with Dagster orchestration
- OpenRouter integration for unified LLM access
- Comprehensive test suite with domain-specific testing strategies
- CLI interface for interactive analysis and debugging

### Excluded Features
- Multi-user collaboration features
- Real money trading capabilities
- Production-grade risk management for live trading
- Multiple database backend support
- Legacy LLM provider integrations (focus on OpenRouter only)

## Development Phases

### Phase 1: News Domain Completion (Current - 95% Complete)
- Finalize news article scraping and processing
- Complete sentiment analysis pipeline
- Optimize news data storage and retrieval
- Implement comprehensive testing for news domain

### Phase 2: Market Data Domain + PostgreSQL Migration
- Complete market data collection and processing
- Implement TimescaleDB optimizations for price data
- Add technical analysis calculations
- Migrate all data persistence to PostgreSQL

### Phase 3: Social Media Domain
- Implement Reddit and Twitter data collection
- Add social sentiment analysis
- Complete the three-domain architecture
- Optimize cross-domain data relationships

### Phase 4: Dagster Pipeline Implementation
- Daily/twice-daily data collection automation
- Comprehensive monitoring and alerting
- Data quality validation and gap detection
- Performance optimization and scaling

### Phase 5: RAG Enhancement and OpenRouter Migration
- Complete RAG implementation for all agents
- Migrate to OpenRouter as sole LLM provider
- Optimize vector search performance
- Implement advanced pattern recognition

## Success Criteria

This personal fork is successful when it provides:
- **Robust Data Infrastructure**: PostgreSQL + TimescaleDB + pgvectorscale handling all financial data efficiently
- **Intelligent Decision Making**: RAG-powered agents making context-aware trading recommendations
- **Reliable Data Collection**: Automated pipelines collecting high-quality data consistently
- **Research Capability**: Complete platform for individual trading strategy research and development
- **Maintainable Codebase**: 85%+ test coverage with clear architecture and comprehensive documentation

The fork serves as both a practical trading research platform and a demonstration of modern data architecture patterns applied to financial AI systems.