# MarketData Domain - PostgreSQL Migration Specification

## Feature Overview

**Feature**: MarketData Domain PostgreSQL Migration  
**Status**: Migration project (85% complete → PostgreSQL integration)  
**Priority**: High (foundational infrastructure for AI agents)

This specification defines the migration of the MarketData domain from CSV-based storage to PostgreSQL + TimescaleDB + pgvectorscale integration, while preserving 100% API compatibility and delivering 10x performance improvements for AI agent operations.

## User Stories

### Primary User Story
> As a Dagster pipeline and AI Agent, I want to collect daily OHLC data from yfinance, insider data from FinnHub, and fundamental data from FinnHub with PostgreSQL + TimescaleDB storage, so that agents have high-performance, RAG-enhanced market data access for comprehensive trading analysis.

### Supporting User Stories

**Agent Performance**
- As an AI Agent, I want market data queries to complete in under 100ms, so that real-time trading analysis is efficient
- As a Technical Analyst Agent, I want vector similarity search for historical patterns, so that pattern-based trading decisions are context-aware

**Data Pipeline Reliability**  
- As a Dagster pipeline, I want atomic data ingestion with PostgreSQL ACID transactions, so that data integrity is guaranteed during bulk operations
- As a Risk Management Agent, I want comprehensive audit trails for all market data access, so that trading decisions are fully traceable

## Acceptance Criteria

### Migration Compatibility
- **AC1**: GIVEN the MarketData domain migration WHEN PostgreSQL + TimescaleDB integration is complete THEN all existing MarketDataService APIs remain 100% compatible with 10x performance improvement

### Data Collection Pipeline
- **AC2**: GIVEN daily market data collection WHEN Dagster pipelines execute THEN OHLC data from yfinance and insider/fundamental data from FinnHub are stored in TimescaleDB hypertables

### Performance Requirements
- **AC3**: GIVEN historical market data queries WHEN AI agents request technical analysis THEN responses are delivered within 100ms using TimescaleDB time-series optimization
- **AC4**: GIVEN technical analysis requests WHEN agents query indicators THEN all 20 existing TA-Lib indicators are preserved with PostgreSQL-backed data access

### RAG Integration
- **AC5**: GIVEN RAG-powered analysis WHEN agents search for historical patterns THEN vector similarity search using pgvectorscale returns relevant market conditions within 200ms

### Scalability
- **AC6**: GIVEN concurrent agent operations WHEN multiple agents access market data THEN PostgreSQL async operations support concurrent reads without file system limitations

### Data Quality
- **AC7**: GIVEN data quality requirements WHEN market data is collected THEN comprehensive validation, audit trails, and error handling maintain data integrity with PostgreSQL ACID transactions

## Business Rules

### API Preservation
- **BR1**: Preserve 100% API compatibility with existing MarketDataService for seamless migration
- **BR2**: Maintain all existing method signatures in FundamentalDataService and InsiderDataService

### Data Collection Standards
- **BR3**: Daily automated collection from yfinance (OHLC) and FinnHub (insider + fundamentals) via Dagster pipelines
- **BR4**: FinnHub API rate limiting compliance with proper backoff strategies
- **BR5**: Graceful degradation when external APIs are unavailable

### Database Architecture
- **BR6**: TimescaleDB hypertables for market_data, fundamental_data, and insider_data tables
- **BR7**: Vector embeddings generation for technical analysis patterns using pgvectorscale

### Performance Standards
- **BR8**: Sub-100ms query performance for common market data operations
- **BR9**: Data retention policy: 10 years for OHLC, 5 years for fundamentals, 3 years for insider data

### Audit and Compliance
- **BR10**: Comprehensive audit logging for all data collection and agent queries

## Technical Implementation Details

### Architecture Pattern
**Router → Service → Repository → Entity → Database**

The migration preserves the existing service interfaces while upgrading the underlying data persistence layer.

### Database Schema Design

#### TimescaleDB Hypertables

```sql
-- Market Data (OHLC)
CREATE TABLE market_data (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date TIMESTAMPTZ NOT NULL,
    open DECIMAL(12,4),
    high DECIMAL(12,4), 
    low DECIMAL(12,4),
    close DECIMAL(12,4),
    adj_close DECIMAL(12,4),
    volume BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

SELECT create_hypertable('market_data', 'date', chunk_time_interval => INTERVAL '1 month');

-- Fundamental Data
CREATE TABLE fundamental_data (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    report_date TIMESTAMPTZ NOT NULL,
    period_type VARCHAR(20), -- annual, quarterly
    metric_name VARCHAR(100),
    metric_value DECIMAL(20,4),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

SELECT create_hypertable('fundamental_data', 'report_date', chunk_time_interval => INTERVAL '3 months');

-- Insider Data
CREATE TABLE insider_data (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    transaction_date TIMESTAMPTZ NOT NULL,
    person_name VARCHAR(200),
    position VARCHAR(100),
    transaction_type VARCHAR(50),
    shares BIGINT,
    price DECIMAL(12,4),
    value DECIMAL(20,4),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

SELECT create_hypertable('insider_data', 'transaction_date', chunk_time_interval => INTERVAL '1 month');
```

#### Vector Storage for RAG

```sql
-- Technical Indicators with Vector Embeddings
CREATE TABLE technical_indicators (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date TIMESTAMPTZ NOT NULL,
    indicator_name VARCHAR(50),
    indicator_value DECIMAL(12,6),
    pattern_embedding vector(384), -- OpenRouter embeddings
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ON technical_indicators USING hnsw (pattern_embedding vector_cosine_ops);
```

### SQLAlchemy Entity Models

```python
# MarketDataEntity
@dataclass
class MarketDataEntity:
    symbol: str
    date: datetime
    open: Optional[Decimal] = None
    high: Optional[Decimal] = None
    low: Optional[Decimal] = None
    close: Optional[Decimal] = None
    adj_close: Optional[Decimal] = None
    volume: Optional[int] = None
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_yfinance_data(cls, symbol: str, row: pd.Series) -> "MarketDataEntity":
        """Convert yfinance data to entity"""
        
    def to_database_record(self) -> dict:
        """Convert entity to database record"""
        
    def validate(self) -> None:
        """Validate entity data integrity"""
```

### Repository Migration

```python
class MarketDataRepository:
    """PostgreSQL + TimescaleDB repository with async operations"""
    
    def __init__(self, database_manager: DatabaseManager):
        self.db = database_manager
    
    async def get_ohlc_data(
        self, 
        symbol: str, 
        start_date: datetime, 
        end_date: datetime
    ) -> List[MarketDataEntity]:
        """Retrieve OHLC data with TimescaleDB optimization"""
        query = """
        SELECT * FROM market_data 
        WHERE symbol = $1 AND date BETWEEN $2 AND $3
        ORDER BY date DESC
        """
        rows = await self.db.fetch(query, symbol, start_date, end_date)
        return [MarketDataEntity.from_database_record(row) for row in rows]
    
    async def bulk_upsert_market_data(
        self, 
        entities: List[MarketDataEntity]
    ) -> int:
        """Atomic bulk upsert for Dagster pipelines"""
        
    async def find_similar_patterns(
        self, 
        pattern_embedding: List[float], 
        limit: int = 10
    ) -> List[Dict]:
        """RAG-powered pattern matching using pgvectorscale"""
        query = """
        SELECT symbol, date, indicator_name, indicator_value,
               pattern_embedding <=> $1 as similarity
        FROM technical_indicators
        ORDER BY pattern_embedding <=> $1
        LIMIT $2
        """
        return await self.db.fetch(query, pattern_embedding, limit)
```

### Service Compatibility Layer

```python
class MarketDataService:
    """Preserved API with PostgreSQL backend"""
    
    def __init__(self, repository: MarketDataRepository, yfinance_client: YFinanceClient):
        self.repository = repository
        self.yfinance_client = yfinance_client
    
    async def get_stock_data(self, symbol: str, period: str = "1y") -> pd.DataFrame:
        """100% compatible with existing API signature"""
        # Implementation using PostgreSQL repository
        
    async def calculate_technical_indicators(
        self, 
        symbol: str, 
        indicators: List[str]
    ) -> Dict[str, np.ndarray]:
        """Preserve all 20 TA-Lib indicators with PostgreSQL data"""
        
    async def get_trading_style_preset(self, style: str) -> Dict:
        """Preserved trading style presets with enhanced performance"""
```

### Vector RAG Enhancement

```python
class MarketDataRAGService:
    """RAG-powered market analysis enhancement"""
    
    async def find_historical_patterns(
        self, 
        current_indicators: Dict[str, float],
        lookback_days: int = 30
    ) -> List[Dict]:
        """Vector similarity search for historical patterns"""
        
    async def generate_pattern_embedding(
        self, 
        indicator_values: Dict[str, float]
    ) -> List[float]:
        """Generate embeddings using OpenRouter for pattern matching"""
```

## Migration Components

### Phase 1: Database Schema & Entities
1. **SQLAlchemy Entity Models**
   - MarketDataEntity for OHLC data
   - FundamentalDataEntity for financial statements  
   - InsiderDataEntity for SEC transactions
   - TechnicalIndicatorEntity for calculated values

2. **TimescaleDB Setup**
   - Hypertable creation for time-series optimization
   - Proper indexing strategy
   - Vector extension configuration

### Phase 2: Repository Migration
1. **Async PostgreSQL Operations**
   - Follow news domain patterns for consistency
   - Connection pooling and transaction management
   - Error handling and retry logic

2. **Data Migration Scripts**
   - CSV to PostgreSQL data transfer
   - Data validation and integrity checks
   - Performance optimization

### Phase 3: Service Preservation
1. **API Compatibility**
   - Maintain all existing method signatures
   - Preserve return types and data formats
   - Performance optimization through PostgreSQL

2. **Vector RAG Integration**
   - Pattern embedding generation
   - Similarity search capabilities
   - Historical context enhancement

### Phase 4: Testing & Integration
1. **Comprehensive Testing**
   - Real PostgreSQL database for repository tests
   - Preserved pytest-vcr for API clients
   - Service compatibility validation

2. **Agent Integration**
   - AgentToolkit RAG capabilities
   - Performance benchmarking
   - Concurrent access testing

## Dependencies

### Ready Dependencies
- **YFinanceClient and FinnhubClient**: Fully implemented and tested
- **PostgreSQL + TimescaleDB + pgvectorscale**: Database infrastructure established
- **News domain PostgreSQL patterns**: Migration templates available
- **DatabaseManager**: Async operations and connection management ready
- **OpenRouter configuration**: Vector embeddings generation available

### Planned Dependencies
- **Dagster orchestration**: Framework for daily data collection pipelines

## Success Criteria

### Performance Metrics
- **10x query performance improvement** over CSV-based storage
- **Sub-100ms market data operations** for common agent queries
- **Sub-200ms RAG queries** for vector similarity search
- **Support for 500+ tickers** with concurrent agent access

### Compatibility Standards  
- **100% existing API preservation** without breaking changes
- **Seamless migration** without agent disruption
- **Efficient bulk data ingestion** for Dagster pipelines

### Quality Assurance
- **85%+ test coverage maintained** across all components
- **Comprehensive data validation** and audit trails
- **PostgreSQL ACID transactions** for data integrity

## Architecture Alignment

This migration aligns with the multi-agent trading framework vision by providing:

1. **High-performance market data foundation** for sophisticated agent analysis
2. **RAG-powered historical context** for pattern-based trading decisions  
3. **Scalable concurrent access** supporting multiple agents simultaneously
4. **Comprehensive audit trails** for regulatory compliance and risk management
5. **Time-series optimization** for efficient technical analysis operations

The migration follows established news domain patterns to ensure architectural consistency across the entire TradingAgents framework.