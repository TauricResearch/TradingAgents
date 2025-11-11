# MarketData Domain - PostgreSQL Migration (Lite Spec)

## Migration Overview

**Project**: 85% complete MarketData domain → PostgreSQL + TimescaleDB + pgvectorscale  
**Objective**: 10x performance + RAG capabilities while preserving 100% API compatibility  
**Pattern**: Follow news domain PostgreSQL implementation for architectural consistency

## Key Requirements

### Performance Targets
- Sub-100ms market data queries (10x improvement from CSV)
- Sub-200ms RAG vector similarity search
- Support 500+ tickers with concurrent agent access

### API Preservation (Critical)
- **MarketDataService**: All existing methods preserved
- **FundamentalDataService**: Complete compatibility maintained  
- **InsiderDataService**: Zero breaking changes
- **20 TA-Lib indicators**: Full functionality preserved

### Data Sources & Collection
- **yfinance**: Daily OHLC data via Dagster pipelines
- **FinnHub**: Insider transactions + fundamental data
- **TimescaleDB hypertables**: market_data, fundamental_data, insider_data
- **Vector storage**: pgvectorscale for RAG pattern matching

## Technical Implementation

### Database Schema (TimescaleDB)
```sql
-- Hypertables for time-series optimization
market_data (symbol, date, ohlc, volume) - 10 year retention
fundamental_data (symbol, report_date, metrics) - 5 year retention  
insider_data (symbol, transaction_date, person, shares) - 3 year retention
technical_indicators (symbol, date, values, pattern_embedding) - RAG support
```

### Entity Models
- **MarketDataEntity**: OHLC + validation + database conversion
- **FundamentalDataEntity**: Financial statement data
- **InsiderDataEntity**: SEC transaction records
- **TechnicalIndicatorEntity**: Calculated values + vector embeddings

### Repository Pattern (Async PostgreSQL)
```python
class MarketDataRepository:
    async def get_ohlc_data(symbol, start, end) -> List[MarketDataEntity]
    async def bulk_upsert_market_data(entities) -> int  # Dagster ingestion
    async def find_similar_patterns(embedding, limit) -> List[Dict]  # RAG
```

### Service Layer (100% Compatible)
```python
class MarketDataService:
    async def get_stock_data(symbol, period) -> pd.DataFrame  # Preserved API
    async def calculate_technical_indicators(symbol, indicators) -> Dict  # 20 TA-Lib
    async def get_trading_style_preset(style) -> Dict  # Existing presets
```

## Migration Strategy

### Phase 1: Entities & Schema
1. Create SQLAlchemy entities following news domain patterns
2. Setup TimescaleDB hypertables with proper indexing
3. Configure pgvectorscale for vector embeddings

### Phase 2: Repository Migration  
1. Implement async PostgreSQL repositories (mirror NewsRepository pattern)
2. Create data migration scripts (CSV → PostgreSQL)
3. Add vector embedding generation for RAG

### Phase 3: Service Preservation
1. Update services to use PostgreSQL repositories
2. Maintain exact API signatures and return types
3. Add RAG-enhanced pattern analysis capabilities

### Phase 4: Integration & Testing
1. Real PostgreSQL tests for repositories
2. Preserve pytest-vcr for YFinanceClient/FinnhubClient
3. Validate 100% API compatibility with existing agents

## Ready Dependencies
- YFinanceClient + FinnhubClient (fully implemented)
- PostgreSQL + TimescaleDB + pgvectorscale (established)
- DatabaseManager async operations (available)
- News domain patterns for consistency (reference implementation)

## Success Metrics
- **Performance**: 10x query improvement, sub-100ms operations
- **Compatibility**: Zero API breaking changes, seamless agent migration  
- **Scalability**: 500+ concurrent tickers, efficient bulk ingestion
- **Quality**: 85%+ test coverage, comprehensive validation

## Implementation Approach
**Follow news domain patterns** → Create entities → Migrate repositories → Preserve service APIs → Enhance with vector RAG → Integrate Dagster pipelines

This migration provides the high-performance, RAG-enabled market data foundation essential for sophisticated multi-agent trading analysis while maintaining complete backward compatibility.