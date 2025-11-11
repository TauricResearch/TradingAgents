# MarketData Domain: PostgreSQL Migration Technical Design

## Project Overview

**Project Type**: Migration Project (85% complete CSV → PostgreSQL + TimescaleDB + pgvectorscale)  
**Business Impact**: 10x performance improvement with sub-100ms query times and RAG capabilities  
**API Compatibility**: 100% preservation of existing MarketDataService, FundamentalDataService, InsiderDataService APIs  
**Data Volume**: 10 years OHLC, 5 years fundamentals, 3 years insider data for 500+ tickers  

## Architecture Overview

### Current State (85% Complete)
```
CSV File Storage (./data/market_data/)
├── OHLC data in CSV files
├── Fundamental data in CSV files  
├── Insider transaction data in CSV files
└── Manual file-based operations
```

### Target Architecture
```
PostgreSQL + TimescaleDB + pgvectorscale
├── TimescaleDB hypertables for time-series optimization
├── pgvectorscale for RAG vector embeddings
├── Async PostgreSQL operations for concurrent agent access
├── Dagster automation for daily data collection
└── 100% API-compatible service layer
```

### Component Relationships
```
External APIs (YFinance + FinnHub) → Dagster Pipeline → PostgreSQL Storage → Repository Layer → Service Layer → Agents
                                                                      ↓
                                                              pgvectorscale (RAG)
```

## Domain Model

### MarketDataEntity

**Purpose**: OHLC price data with TimescaleDB optimization and vector embeddings

```python
from sqlalchemy import Column, String, DateTime, Numeric, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy_utils import TSVectorType
from pgvectorscale import Vector

class MarketDataEntity(Base):
    __tablename__ = 'market_data'
    __table_args__ = {
        'timescaledb': {
            'time_column_name': 'timestamp',
            'chunk_time_interval': '1 day'
        }
    }
    
    id = Column(Integer, primary_key=True)
    symbol = Column(String(10), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    open_price = Column(Numeric(10, 2), nullable=False)
    high_price = Column(Numeric(10, 2), nullable=False)
    low_price = Column(Numeric(10, 2), nullable=False)
    close_price = Column(Numeric(10, 2), nullable=False)
    volume = Column(Integer, nullable=False)
    adjusted_close = Column(Numeric(10, 2), nullable=False)
    
    # Vector embeddings for RAG
    technical_pattern_embedding = Column(Vector(384))  # Technical analysis patterns
    price_movement_embedding = Column(Vector(384))     # Price movement patterns
    
    # Business rules
    @classmethod
    def from_csv_record(cls, csv_data: dict) -> 'MarketDataEntity':
        """Transform CSV data to entity"""
        return cls(
            symbol=csv_data['symbol'],
            timestamp=pd.to_datetime(csv_data['timestamp']),
            open_price=csv_data['open'],
            high_price=csv_data['high'],
            low_price=csv_data['low'],
            close_price=csv_data['close'],
            volume=csv_data['volume'],
            adjusted_close=csv_data['adj_close']
        )
    
    def to_service_response(self) -> dict:
        """Transform entity to service API format"""
        return {
            'symbol': self.symbol,
            'timestamp': self.timestamp.isoformat(),
            'open': float(self.open_price),
            'high': float(self.high_price),
            'low': float(self.low_price),
            'close': float(self.close_price),
            'volume': self.volume,
            'adj_close': float(self.adjusted_close)
        }
    
    def validate(self) -> bool:
        """Validate business rules"""
        return (
            self.high_price >= self.low_price and
            self.high_price >= self.open_price and
            self.high_price >= self.close_price and
            self.low_price <= self.open_price and
            self.low_price <= self.close_price and
            self.volume >= 0
        )
```

### FundamentalDataEntity

**Purpose**: Financial statement data with PostgreSQL storage

```python
class FundamentalDataEntity(Base):
    __tablename__ = 'fundamental_data'
    
    id = Column(Integer, primary_key=True)
    symbol = Column(String(10), nullable=False, index=True)
    report_date = Column(DateTime, nullable=False, index=True)
    period_type = Column(String(10), nullable=False)  # Q, Y
    
    # Balance Sheet
    total_assets = Column(Numeric(15, 2))
    total_liabilities = Column(Numeric(15, 2))
    shareholders_equity = Column(Numeric(15, 2))
    
    # Income Statement  
    total_revenue = Column(Numeric(15, 2))
    net_income = Column(Numeric(15, 2))
    earnings_per_share = Column(Numeric(8, 4))
    
    # Cash Flow
    operating_cash_flow = Column(Numeric(15, 2))
    capital_expenditures = Column(Numeric(15, 2))
    free_cash_flow = Column(Numeric(15, 2))
    
    # Ratios (calculated)
    pe_ratio = Column(Numeric(8, 2))
    pb_ratio = Column(Numeric(8, 2))
    roe = Column(Numeric(8, 4))
    roa = Column(Numeric(8, 4))
    debt_to_equity = Column(Numeric(8, 4))
    
    # Vector embeddings for RAG
    financial_health_embedding = Column(Vector(384))
    
    @classmethod
    def from_finnhub_response(cls, finnhub_data: dict) -> 'FundamentalDataEntity':
        """Transform FinnHub API response to entity"""
        return cls(
            symbol=finnhub_data['symbol'],
            report_date=pd.to_datetime(finnhub_data['reportedDate']),
            period_type=finnhub_data['period'],
            total_assets=finnhub_data.get('totalAssets'),
            total_revenue=finnhub_data.get('totalRevenue'),
            # ... map all fields
        )
    
    def calculate_ratios(self, current_price: float):
        """Calculate financial ratios"""
        if self.earnings_per_share and self.earnings_per_share > 0:
            self.pe_ratio = current_price / self.earnings_per_share
        
        if self.shareholders_equity and self.shareholders_equity > 0:
            self.pb_ratio = current_price / (self.shareholders_equity / 1_000_000)  # Book value per share
            
        if self.shareholders_equity and self.net_income:
            self.roe = self.net_income / self.shareholders_equity
            
        if self.total_assets and self.net_income:
            self.roa = self.net_income / self.total_assets
```

### InsiderDataEntity

**Purpose**: SEC insider transaction records with sentiment analysis

```python
class InsiderDataEntity(Base):
    __tablename__ = 'insider_data'
    
    id = Column(Integer, primary_key=True)
    symbol = Column(String(10), nullable=False, index=True)
    transaction_date = Column(DateTime, nullable=False, index=True)
    
    # Insider information
    insider_name = Column(String(200), nullable=False)
    insider_position = Column(String(100))
    
    # Transaction details
    transaction_type = Column(String(20), nullable=False)  # Buy, Sell
    shares_traded = Column(Integer, nullable=False)
    transaction_price = Column(Numeric(10, 2))
    shares_owned_after = Column(Integer)
    
    # Derived fields
    transaction_value = Column(Numeric(15, 2))  # shares * price
    sentiment_score = Column(Numeric(3, 2))     # -1 to 1
    
    # Vector embeddings for RAG
    transaction_pattern_embedding = Column(Vector(384))
    
    @classmethod  
    def from_finnhub_response(cls, finnhub_data: dict) -> 'InsiderDataEntity':
        """Transform FinnHub insider data to entity"""
        entity = cls(
            symbol=finnhub_data['symbol'],
            transaction_date=pd.to_datetime(finnhub_data['transactionDate']),
            insider_name=finnhub_data['personName'],
            insider_position=finnhub_data.get('position'),
            transaction_type='Buy' if finnhub_data['change'] > 0 else 'Sell',
            shares_traded=abs(finnhub_data['change']),
            shares_owned_after=finnhub_data['currentShares']
        )
        entity.calculate_sentiment()
        return entity
    
    def calculate_sentiment(self):
        """Calculate sentiment score based on transaction type and insider position"""
        base_score = 0.7 if self.transaction_type == 'Buy' else -0.7
        
        # Adjust based on position
        if self.insider_position and 'ceo' in self.insider_position.lower():
            base_score *= 1.2
        elif self.insider_position and 'cfo' in self.insider_position.lower():
            base_score *= 1.1
            
        self.sentiment_score = max(-1.0, min(1.0, base_score))
```

### TechnicalIndicatorEntity

**Purpose**: Calculated TA-Lib indicator values with vector embeddings

```python
class TechnicalIndicatorEntity(Base):
    __tablename__ = 'technical_indicators'
    
    id = Column(Integer, primary_key=True)
    symbol = Column(String(10), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    
    # Moving Averages
    sma_20 = Column(Numeric(10, 2))
    sma_50 = Column(Numeric(10, 2))
    ema_12 = Column(Numeric(10, 2))
    ema_26 = Column(Numeric(10, 2))
    
    # Momentum Indicators
    rsi_14 = Column(Numeric(5, 2))
    macd = Column(Numeric(10, 4))
    macd_signal = Column(Numeric(10, 4))
    macd_histogram = Column(Numeric(10, 4))
    
    # Volatility Indicators  
    bollinger_upper = Column(Numeric(10, 2))
    bollinger_lower = Column(Numeric(10, 2))
    atr_14 = Column(Numeric(10, 4))
    
    # Volume Indicators
    obv = Column(Numeric(15, 0))
    volume_sma_20 = Column(Numeric(15, 0))
    
    # Pattern Recognition (0-100 scores)
    pattern_doji = Column(Integer)
    pattern_hammer = Column(Integer)
    pattern_engulfing = Column(Integer)
    
    # Vector embeddings for RAG pattern matching
    indicator_pattern_embedding = Column(Vector(384))
    
    @classmethod
    def calculate_from_ohlc(cls, symbol: str, ohlc_data: pd.DataFrame) -> List['TechnicalIndicatorEntity']:
        """Calculate all technical indicators from OHLC data"""
        import talib
        
        indicators = []
        
        # Calculate all indicators
        sma_20 = talib.SMA(ohlc_data['close'], timeperiod=20)
        rsi_14 = talib.RSI(ohlc_data['close'], timeperiod=14)
        macd, macd_signal, macd_hist = talib.MACD(ohlc_data['close'])
        # ... calculate all indicators
        
        for i, timestamp in enumerate(ohlc_data.index):
            if pd.notna(sma_20.iloc[i]):  # Only create records with valid data
                indicators.append(cls(
                    symbol=symbol,
                    timestamp=timestamp,
                    sma_20=sma_20.iloc[i],
                    rsi_14=rsi_14.iloc[i],
                    macd=macd.iloc[i],
                    macd_signal=macd_signal.iloc[i],
                    macd_histogram=macd_hist.iloc[i]
                    # ... set all calculated values
                ))
        
        return indicators
```

## Database Design

### PostgreSQL + TimescaleDB + pgvectorscale Schema

```sql
-- Enable extensions
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
CREATE EXTENSION IF NOT EXISTS vectorscale CASCADE;

-- Market Data (TimescaleDB hypertable)
CREATE TABLE market_data (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    open_price DECIMAL(10,2) NOT NULL,
    high_price DECIMAL(10,2) NOT NULL,
    low_price DECIMAL(10,2) NOT NULL,
    close_price DECIMAL(10,2) NOT NULL,
    volume BIGINT NOT NULL,
    adjusted_close DECIMAL(10,2) NOT NULL,
    technical_pattern_embedding vector(384),
    price_movement_embedding vector(384),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Convert to TimescaleDB hypertable
SELECT create_hypertable('market_data', 'timestamp', chunk_time_interval => INTERVAL '1 day');

-- Indexes for performance
CREATE INDEX idx_market_data_symbol_time ON market_data (symbol, timestamp DESC);
CREATE INDEX idx_market_data_symbol ON market_data (symbol);

-- Vector indexes for RAG
CREATE INDEX idx_market_data_technical_embedding 
    ON market_data USING diskann (technical_pattern_embedding);
CREATE INDEX idx_market_data_price_embedding 
    ON market_data USING diskann (price_movement_embedding);

-- Fundamental Data
CREATE TABLE fundamental_data (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    report_date TIMESTAMPTZ NOT NULL,
    period_type VARCHAR(10) NOT NULL,
    
    -- Balance Sheet
    total_assets DECIMAL(15,2),
    total_liabilities DECIMAL(15,2),
    shareholders_equity DECIMAL(15,2),
    
    -- Income Statement
    total_revenue DECIMAL(15,2),
    net_income DECIMAL(15,2),
    earnings_per_share DECIMAL(8,4),
    
    -- Cash Flow
    operating_cash_flow DECIMAL(15,2),
    capital_expenditures DECIMAL(15,2),
    free_cash_flow DECIMAL(15,2),
    
    -- Ratios
    pe_ratio DECIMAL(8,2),
    pb_ratio DECIMAL(8,2),
    roe DECIMAL(8,4),
    roa DECIMAL(8,4),
    debt_to_equity DECIMAL(8,4),
    
    -- RAG embedding
    financial_health_embedding vector(384),
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(symbol, report_date, period_type)
);

CREATE INDEX idx_fundamental_symbol_date ON fundamental_data (symbol, report_date DESC);
CREATE INDEX idx_fundamental_embedding ON fundamental_data USING diskann (financial_health_embedding);

-- Insider Data  
CREATE TABLE insider_data (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    transaction_date TIMESTAMPTZ NOT NULL,
    insider_name VARCHAR(200) NOT NULL,
    insider_position VARCHAR(100),
    transaction_type VARCHAR(20) NOT NULL,
    shares_traded INTEGER NOT NULL,
    transaction_price DECIMAL(10,2),
    shares_owned_after INTEGER,
    transaction_value DECIMAL(15,2),
    sentiment_score DECIMAL(3,2),
    transaction_pattern_embedding vector(384),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_insider_symbol_date ON insider_data (symbol, transaction_date DESC);
CREATE INDEX idx_insider_embedding ON insider_data USING diskann (transaction_pattern_embedding);

-- Technical Indicators (TimescaleDB hypertable)
CREATE TABLE technical_indicators (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    
    -- Moving Averages
    sma_20 DECIMAL(10,2),
    sma_50 DECIMAL(10,2),
    ema_12 DECIMAL(10,2),
    ema_26 DECIMAL(10,2),
    
    -- Momentum
    rsi_14 DECIMAL(5,2),
    macd DECIMAL(10,4),
    macd_signal DECIMAL(10,4),
    macd_histogram DECIMAL(10,4),
    
    -- Volatility
    bollinger_upper DECIMAL(10,2),
    bollinger_lower DECIMAL(10,2),
    atr_14 DECIMAL(10,4),
    
    -- Volume
    obv DECIMAL(15,0),
    volume_sma_20 DECIMAL(15,0),
    
    -- Patterns
    pattern_doji INTEGER,
    pattern_hammer INTEGER,
    pattern_engulfing INTEGER,
    
    -- RAG embedding
    indicator_pattern_embedding vector(384),
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

SELECT create_hypertable('technical_indicators', 'timestamp', chunk_time_interval => INTERVAL '1 day');

CREATE INDEX idx_technical_symbol_time ON technical_indicators (symbol, timestamp DESC);
CREATE INDEX idx_technical_embedding ON technical_indicators USING diskann (indicator_pattern_embedding);
```

### Migration Strategy Scripts

```python
# migrations/001_create_market_data_tables.py

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    # Create market_data table
    op.create_table('market_data',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('symbol', sa.String(10), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('open_price', sa.Numeric(10, 2), nullable=False),
        sa.Column('high_price', sa.Numeric(10, 2), nullable=False),
        sa.Column('low_price', sa.Numeric(10, 2), nullable=False),
        sa.Column('close_price', sa.Numeric(10, 2), nullable=False),
        sa.Column('volume', sa.BigInteger(), nullable=False),
        sa.Column('adjusted_close', sa.Numeric(10, 2), nullable=False),
        sa.Column('technical_pattern_embedding', postgresql.ARRAY(sa.Float()), nullable=True),
        sa.Column('price_movement_embedding', postgresql.ARRAY(sa.Float()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Convert to hypertable
    op.execute("SELECT create_hypertable('market_data', 'timestamp', chunk_time_interval => INTERVAL '1 day');")
    
    # Create indexes
    op.create_index('idx_market_data_symbol_time', 'market_data', ['symbol', 'timestamp'])
    op.create_index('idx_market_data_symbol', 'market_data', ['symbol'])

def downgrade():
    op.drop_table('market_data')
```

## API Preservation

### 100% Compatible Service Layer

**MarketDataService**: Preserve all existing methods with PostgreSQL backend

```python
from typing import List, Dict, Any, Optional
import pandas as pd
from datetime import datetime, timedelta

class MarketDataService:
    """API-compatible service with PostgreSQL backend"""
    
    def __init__(self, repository: MarketDataRepository):
        self.repository = repository
    
    async def get_ohlc_data(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """Get OHLC data - 100% API compatible"""
        entities = await self.repository.get_ohlc_data(symbol, start_date, end_date)
        
        # Transform to same DataFrame format as CSV version
        return pd.DataFrame([
            {
                'timestamp': entity.timestamp,
                'open': float(entity.open_price),
                'high': float(entity.high_price),
                'low': float(entity.low_price),
                'close': float(entity.close_price),
                'volume': entity.volume,
                'adj_close': float(entity.adjusted_close)
            }
            for entity in entities
        ]).set_index('timestamp')
    
    async def get_technical_indicators(self, symbol: str, start_date: str, end_date: str) -> Dict[str, List[float]]:
        """Get all technical indicators - 100% API compatible"""
        indicators = await self.repository.get_technical_indicators(symbol, start_date, end_date)
        
        return {
            'sma_20': [float(ind.sma_20) if ind.sma_20 else None for ind in indicators],
            'rsi_14': [float(ind.rsi_14) if ind.rsi_14 else None for ind in indicators],
            'macd': [float(ind.macd) if ind.macd else None for ind in indicators],
            'macd_signal': [float(ind.macd_signal) if ind.macd_signal else None for ind in indicators],
            # ... all indicators
        }
    
    async def get_trading_style_preset(self, style: str, symbol: str, lookback_days: int = 30) -> Dict[str, Any]:
        """Get trading style analysis - 100% API compatible"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=lookback_days)
        
        ohlc_data = await self.get_ohlc_data(symbol, start_date.isoformat(), end_date.isoformat())
        indicators = await self.get_technical_indicators(symbol, start_date.isoformat(), end_date.isoformat())
        
        if style == 'momentum':
            return await self._analyze_momentum(ohlc_data, indicators)
        elif style == 'mean_reversion':
            return await self._analyze_mean_reversion(ohlc_data, indicators)
        elif style == 'breakout':
            return await self._analyze_breakout(ohlc_data, indicators)
        # ... all trading styles
    
    async def _analyze_momentum(self, ohlc_data: pd.DataFrame, indicators: Dict) -> Dict[str, Any]:
        """Momentum analysis with RAG enhancement"""
        latest_rsi = indicators['rsi_14'][-1] if indicators['rsi_14'] else 50
        latest_macd = indicators['macd'][-1] if indicators['macd'] else 0
        
        # RAG: Find similar momentum patterns
        similar_patterns = await self.repository.find_similar_momentum_patterns(
            latest_rsi, latest_macd, limit=10
        )
        
        return {
            'signal': 'BUY' if latest_rsi > 70 and latest_macd > 0 else 'HOLD',
            'confidence': 0.85,
            'indicators': {
                'rsi': latest_rsi,
                'macd': latest_macd
            },
            'similar_patterns': [p.to_dict() for p in similar_patterns],
            'rag_enhanced': True
        }
```

**FundamentalDataService**: Complete API preservation

```python
class FundamentalDataService:
    """API-compatible fundamental analysis with PostgreSQL backend"""
    
    def __init__(self, repository: FundamentalDataRepository):
        self.repository = repository
        
    async def get_financial_ratios(self, symbol: str, period_type: str = 'Q') -> Dict[str, float]:
        """Get latest financial ratios - 100% API compatible"""
        latest_data = await self.repository.get_latest_fundamental_data(symbol, period_type)
        
        if not latest_data:
            return {}
            
        return {
            'pe_ratio': float(latest_data.pe_ratio) if latest_data.pe_ratio else None,
            'pb_ratio': float(latest_data.pb_ratio) if latest_data.pb_ratio else None,
            'roe': float(latest_data.roe) if latest_data.roe else None,
            'roa': float(latest_data.roa) if latest_data.roa else None,
            'debt_to_equity': float(latest_data.debt_to_equity) if latest_data.debt_to_equity else None
        }
    
    async def analyze_financial_health(self, symbol: str) -> Dict[str, Any]:
        """Financial health analysis with RAG - 100% API compatible"""
        latest_data = await self.repository.get_latest_fundamental_data(symbol)
        historical_data = await self.repository.get_fundamental_history(symbol, quarters=8)
        
        # RAG: Find companies with similar financial profiles
        similar_companies = await self.repository.find_similar_financial_profiles(
            latest_data.financial_health_embedding, limit=10
        )
        
        return {
            'health_score': self._calculate_health_score(latest_data, historical_data),
            'trend_analysis': self._analyze_trends(historical_data),
            'peer_comparison': [comp.to_dict() for comp in similar_companies],
            'rag_enhanced': True
        }
```

**InsiderDataService**: Complete API preservation

```python  
class InsiderDataService:
    """API-compatible insider analysis with PostgreSQL backend"""
    
    def __init__(self, repository: InsiderDataRepository):
        self.repository = repository
        
    async def get_recent_insider_activity(self, symbol: str, days: int = 90) -> List[Dict[str, Any]]:
        """Get recent insider transactions - 100% API compatible"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        transactions = await self.repository.get_insider_transactions(symbol, start_date, end_date)
        
        return [
            {
                'insider_name': trans.insider_name,
                'position': trans.insider_position,
                'transaction_date': trans.transaction_date.isoformat(),
                'transaction_type': trans.transaction_type,
                'shares_traded': trans.shares_traded,
                'transaction_price': float(trans.transaction_price) if trans.transaction_price else None,
                'transaction_value': float(trans.transaction_value) if trans.transaction_value else None,
                'sentiment_score': float(trans.sentiment_score) if trans.sentiment_score else None
            }
            for trans in transactions
        ]
    
    async def analyze_insider_sentiment(self, symbol: str, days: int = 180) -> Dict[str, Any]:
        """Insider sentiment analysis with RAG - 100% API compatible"""
        transactions = await self.get_recent_insider_activity(symbol, days)
        
        # RAG: Find similar insider activity patterns
        similar_patterns = await self.repository.find_similar_insider_patterns(
            symbol, days, limit=10
        )
        
        buy_volume = sum(t['shares_traded'] for t in transactions if t['transaction_type'] == 'Buy')
        sell_volume = sum(t['shares_traded'] for t in transactions if t['transaction_type'] == 'Sell')
        
        net_sentiment = buy_volume - sell_volume
        
        return {
            'net_sentiment': net_sentiment,
            'buy_transactions': len([t for t in transactions if t['transaction_type'] == 'Buy']),
            'sell_transactions': len([t for t in transactions if t['transaction_type'] == 'Sell']),
            'average_sentiment_score': sum(t['sentiment_score'] for t in transactions if t['sentiment_score']) / len(transactions) if transactions else 0,
            'similar_patterns': [p.to_dict() for p in similar_patterns],
            'rag_enhanced': True
        }
```

## Component Architecture

### Repository Migration Pattern

**AsyncRepository with PostgreSQL Operations**

```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy import select, and_, desc
from typing import List, Optional
from datetime import datetime

class MarketDataRepository:
    """Async PostgreSQL repository with RAG capabilities"""
    
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory
    
    async def get_ohlc_data(self, symbol: str, start_date: str, end_date: str) -> List[MarketDataEntity]:
        """Get OHLC data with sub-100ms performance"""
        async with self.session_factory() as session:
            stmt = select(MarketDataEntity).where(
                and_(
                    MarketDataEntity.symbol == symbol,
                    MarketDataEntity.timestamp >= datetime.fromisoformat(start_date),
                    MarketDataEntity.timestamp <= datetime.fromisoformat(end_date)
                )
            ).order_by(MarketDataEntity.timestamp)
            
            result = await session.execute(stmt)
            return result.scalars().all()
    
    async def save_ohlc_batch(self, entities: List[MarketDataEntity]) -> None:
        """Batch insert with conflict resolution"""
        async with self.session_factory() as session:
            session.add_all(entities)
            await session.commit()
    
    async def find_similar_momentum_patterns(self, rsi: float, macd: float, limit: int = 10) -> List[TechnicalIndicatorEntity]:
        """RAG: Find similar technical patterns using vector similarity"""
        target_embedding = self._encode_momentum_pattern(rsi, macd)
        
        async with self.session_factory() as session:
            # Using pgvectorscale cosine similarity
            stmt = select(TechnicalIndicatorEntity).order_by(
                TechnicalIndicatorEntity.indicator_pattern_embedding.cosine_distance(target_embedding)
            ).limit(limit)
            
            result = await session.execute(stmt)
            return result.scalars().all()
    
    def _encode_momentum_pattern(self, rsi: float, macd: float) -> List[float]:
        """Encode momentum indicators to vector for similarity search"""
        from sentence_transformers import SentenceTransformer
        
        model = SentenceTransformer('all-MiniLM-L6-v2')
        pattern_text = f"RSI: {rsi:.2f}, MACD: {macd:.4f}, momentum pattern"
        return model.encode(pattern_text).tolist()
```

### Migration Data Processing

**4-Phase Migration Strategy**

```python
class MarketDataMigrator:
    """Migrate from CSV files to PostgreSQL with data validation"""
    
    def __init__(self, csv_data_path: str, repository: MarketDataRepository):
        self.csv_data_path = csv_data_path
        self.repository = repository
    
    async def migrate_all_data(self) -> Dict[str, int]:
        """Execute 4-phase migration strategy"""
        results = {}
        
        # Phase 1: Market Data (OHLC)
        results['market_data'] = await self._migrate_market_data()
        
        # Phase 2: Fundamental Data  
        results['fundamental_data'] = await self._migrate_fundamental_data()
        
        # Phase 3: Insider Data
        results['insider_data'] = await self._migrate_insider_data()
        
        # Phase 4: Calculate Technical Indicators
        results['technical_indicators'] = await self._calculate_technical_indicators()
        
        return results
    
    async def _migrate_market_data(self) -> int:
        """Migrate OHLC data from CSV files"""
        csv_files = glob.glob(f"{self.csv_data_path}/market_data/*.csv")
        total_records = 0
        
        for csv_file in csv_files:
            symbol = self._extract_symbol_from_filename(csv_file)
            df = pd.read_csv(csv_file)
            
            # Transform to entities
            entities = []
            for _, row in df.iterrows():
                entity = MarketDataEntity.from_csv_record({
                    'symbol': symbol,
                    'timestamp': row['Date'],
                    'open': row['Open'],
                    'high': row['High'],
                    'low': row['Low'],
                    'close': row['Close'],
                    'volume': row['Volume'],
                    'adj_close': row['Adj Close']
                })
                
                if entity.validate():
                    entities.append(entity)
            
            # Batch insert
            await self.repository.save_ohlc_batch(entities)
            total_records += len(entities)
            
            print(f"Migrated {len(entities)} records for {symbol}")
        
        return total_records
    
    async def _calculate_technical_indicators(self) -> int:
        """Calculate and store technical indicators for all symbols"""
        symbols = await self.repository.get_all_symbols()
        total_indicators = 0
        
        for symbol in symbols:
            # Get OHLC data
            ohlc_data = await self.repository.get_ohlc_data(
                symbol, "2020-01-01", datetime.now().isoformat()
            )
            
            # Convert to DataFrame
            df = pd.DataFrame([{
                'timestamp': entity.timestamp,
                'close': float(entity.close_price),
                'high': float(entity.high_price),
                'low': float(entity.low_price),
                'volume': entity.volume
            } for entity in ohlc_data])
            df.set_index('timestamp', inplace=True)
            
            # Calculate indicators
            indicators = TechnicalIndicatorEntity.calculate_from_ohlc(symbol, df)
            
            # Generate embeddings
            for indicator in indicators:
                indicator.indicator_pattern_embedding = self._generate_indicator_embedding(indicator)
            
            # Save indicators
            await self.repository.save_technical_indicators(indicators)
            total_indicators += len(indicators)
            
            print(f"Calculated {len(indicators)} indicators for {symbol}")
        
        return total_indicators
```

## RAG Integration

### Vector Embeddings for Historical Pattern Matching

**Embedding Generation Strategy**

```python
from sentence_transformers import SentenceTransformer
import numpy as np

class MarketDataEmbeddingService:
    """Generate vector embeddings for RAG pattern matching"""
    
    def __init__(self):
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
    
    def generate_technical_pattern_embedding(self, indicator_data: TechnicalIndicatorEntity) -> List[float]:
        """Generate embedding for technical analysis patterns"""
        pattern_description = f"""
        Technical Analysis Pattern:
        RSI: {indicator_data.rsi_14:.2f}
        MACD: {indicator_data.macd:.4f}, Signal: {indicator_data.macd_signal:.4f}
        SMA 20: {indicator_data.sma_20:.2f}, SMA 50: {indicator_data.sma_50:.2f}
        Bollinger Bands: Upper {indicator_data.bollinger_upper:.2f}, Lower {indicator_data.bollinger_lower:.2f}
        Volume: Above average {indicator_data.volume_sma_20 > 0}
        Pattern: {'Bullish' if indicator_data.rsi_14 > 50 and indicator_data.macd > indicator_data.macd_signal else 'Bearish'}
        """
        
        return self.model.encode(pattern_description.strip()).tolist()
    
    def generate_price_movement_embedding(self, market_data: MarketDataEntity) -> List[float]:
        """Generate embedding for price movement patterns"""
        price_change = (market_data.close_price - market_data.open_price) / market_data.open_price * 100
        volatility = (market_data.high_price - market_data.low_price) / market_data.open_price * 100
        
        movement_description = f"""
        Price Movement Pattern:
        Price Change: {price_change:.2f}%
        Intraday Volatility: {volatility:.2f}%
        Volume Profile: {'High' if market_data.volume > 1000000 else 'Normal'}
        Price Level: {'Above' if market_data.close_price > market_data.open_price else 'Below'} opening
        Candle Type: {'Green' if market_data.close_price >= market_data.open_price else 'Red'}
        """
        
        return self.model.encode(movement_description.strip()).tolist()
    
    def generate_financial_health_embedding(self, fundamental_data: FundamentalDataEntity) -> List[float]:
        """Generate embedding for financial health patterns"""
        health_description = f"""
        Financial Health Profile:
        PE Ratio: {fundamental_data.pe_ratio:.2f if fundamental_data.pe_ratio else 'N/A'}
        ROE: {fundamental_data.roe * 100:.2f}% if fundamental_data.roe else 'N/A'}
        Debt to Equity: {fundamental_data.debt_to_equity:.2f if fundamental_data.debt_to_equity else 'N/A'}
        Revenue Growth: {'Positive' if fundamental_data.total_revenue and fundamental_data.total_revenue > 0 else 'Unknown'}
        Profitability: {'Profitable' if fundamental_data.net_income and fundamental_data.net_income > 0 else 'Loss'}
        Financial Strength: {'Strong' if fundamental_data.pe_ratio and fundamental_data.pe_ratio < 20 else 'Average'}
        """
        
        return self.model.encode(health_description.strip()).tolist()
```

**RAG Query Service**

```python
class MarketDataRAGService:
    """RAG-powered market analysis with vector similarity search"""
    
    def __init__(self, repository: MarketDataRepository):
        self.repository = repository
        self.embedding_service = MarketDataEmbeddingService()
    
    async def find_similar_market_conditions(
        self, 
        symbol: str, 
        current_date: datetime, 
        similarity_threshold: float = 0.8,
        limit: int = 10
    ) -> Dict[str, Any]:
        """Find historically similar market conditions for decision support"""
        
        # Get current market state
        current_ohlc = await self.repository.get_latest_ohlc(symbol, current_date)
        current_indicators = await self.repository.get_latest_indicators(symbol, current_date)
        current_fundamentals = await self.repository.get_latest_fundamentals(symbol)
        
        # Generate query embeddings
        current_pattern_embedding = self.embedding_service.generate_technical_pattern_embedding(current_indicators)
        
        # Find similar patterns
        similar_patterns = await self.repository.find_similar_patterns(
            current_pattern_embedding, 
            similarity_threshold,
            limit
        )
        
        # Analyze outcomes of similar patterns
        pattern_outcomes = []
        for pattern in similar_patterns:
            # Get price movement 5-10 days after similar pattern
            future_price = await self.repository.get_price_after_date(
                pattern.symbol, 
                pattern.timestamp, 
                days=7
            )
            
            if future_price:
                price_change = (future_price.close_price - pattern.close_price) / pattern.close_price
                pattern_outcomes.append({
                    'symbol': pattern.symbol,
                    'date': pattern.timestamp,
                    'similarity_score': pattern.similarity_score,
                    'future_return': float(price_change),
                    'pattern_type': self._classify_pattern(pattern)
                })
        
        return {
            'current_symbol': symbol,
            'analysis_date': current_date,
            'similar_patterns_found': len(similar_patterns),
            'historical_outcomes': pattern_outcomes,
            'average_return': np.mean([p['future_return'] for p in pattern_outcomes]) if pattern_outcomes else 0,
            'success_rate': len([p for p in pattern_outcomes if p['future_return'] > 0]) / len(pattern_outcomes) if pattern_outcomes else 0,
            'confidence_score': self._calculate_confidence(pattern_outcomes)
        }
    
    async def get_peer_analysis(self, symbol: str) -> Dict[str, Any]:
        """Find peer companies with similar financial profiles"""
        fundamentals = await self.repository.get_latest_fundamentals(symbol)
        
        if not fundamentals:
            return {'error': 'No fundamental data available'}
        
        # Find companies with similar financial health embeddings
        similar_companies = await self.repository.find_similar_financial_profiles(
            fundamentals.financial_health_embedding,
            exclude_symbol=symbol,
            limit=10
        )
        
        # Get recent performance comparison
        peer_performance = []
        for peer in similar_companies:
            recent_performance = await self.repository.get_recent_performance(peer.symbol, days=30)
            peer_performance.append({
                'symbol': peer.symbol,
                'similarity_score': peer.similarity_score,
                'recent_return': recent_performance.get('return', 0),
                'volatility': recent_performance.get('volatility', 0),
                'pe_ratio': float(peer.pe_ratio) if peer.pe_ratio else None
            })
        
        return {
            'target_symbol': symbol,
            'peer_companies': peer_performance,
            'peer_average_return': np.mean([p['recent_return'] for p in peer_performance]),
            'relative_performance': 'Above average' if recent_performance.get('return', 0) > np.mean([p['recent_return'] for p in peer_performance]) else 'Below average'
        }
```

## Migration Strategy

### 4-Phase Migration Approach

**Phase 1: Database Infrastructure Setup**
```bash
# 1. Set up PostgreSQL with extensions
docker-compose up -d postgres

# 2. Run database migrations
alembic upgrade head

# 3. Verify TimescaleDB and pgvectorscale extensions
psql $DATABASE_URL -c "SELECT * FROM pg_extension WHERE extname IN ('timescaledb', 'vectorscale');"
```

**Phase 2: Data Migration with Validation**
```python
# Migration script: migrate_market_data.py

import asyncio
from tradingagents.domains.marketdata.migration.migrator import MarketDataMigrator
from tradingagents.domains.marketdata.repository import MarketDataRepository

async def main():
    # Initialize components
    repository = MarketDataRepository(session_factory)
    migrator = MarketDataMigrator("./data/market_data", repository)
    
    # Execute migration
    print("Starting MarketData migration...")
    results = await migrator.migrate_all_data()
    
    print(f"Migration completed:")
    print(f"  Market Data: {results['market_data']} records")
    print(f"  Fundamental Data: {results['fundamental_data']} records")
    print(f"  Insider Data: {results['insider_data']} records")
    print(f"  Technical Indicators: {results['technical_indicators']} records")
    
    # Validate migration
    validation_results = await migrator.validate_migration()
    print(f"Validation: {validation_results}")

if __name__ == "__main__":
    asyncio.run(main())
```

**Phase 3: Service Layer Migration**
```python
# Switch services to PostgreSQL repositories
# Update dependency injection in service factory

class ServiceFactory:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory
    
    def create_market_data_service(self) -> MarketDataService:
        repository = MarketDataRepository(self.session_factory)
        return MarketDataService(repository)
    
    def create_fundamental_data_service(self) -> FundamentalDataService:
        repository = FundamentalDataRepository(self.session_factory)
        return FundamentalDataService(repository)
    
    def create_insider_data_service(self) -> InsiderDataService:
        repository = InsiderDataRepository(self.session_factory)
        return InsiderDataService(repository)
```

**Phase 4: RAG Enhancement and Testing**
```python
# Generate embeddings for existing data
async def enhance_with_rag():
    embedding_service = MarketDataEmbeddingService()
    
    # Generate embeddings for all technical indicators
    indicators = await repository.get_all_technical_indicators()
    
    for indicator in indicators:
        embedding = embedding_service.generate_technical_pattern_embedding(indicator)
        await repository.update_indicator_embedding(indicator.id, embedding)
    
    print(f"Generated embeddings for {len(indicators)} technical indicators")
    
    # Test RAG functionality
    rag_service = MarketDataRAGService(repository)
    test_results = await rag_service.find_similar_market_conditions("AAPL", datetime.now())
    
    print(f"RAG test completed: {test_results}")
```

## Testing Strategy

### Migration Testing

**Data Integrity Tests**
```python
class TestMarketDataMigration:
    """Validate PostgreSQL migration maintains data integrity"""
    
    async def test_ohlc_data_accuracy(self):
        """Verify OHLC data matches CSV files exactly"""
        # Load original CSV data
        original_df = pd.read_csv("./data/market_data/AAPL.csv")
        
        # Get PostgreSQL data  
        postgres_entities = await self.repository.get_ohlc_data("AAPL", "2020-01-01", "2024-01-01")
        postgres_df = pd.DataFrame([entity.to_dict() for entity in postgres_entities])
        
        # Compare datasets
        assert len(original_df) == len(postgres_df)
        assert np.allclose(original_df['Close'].values, postgres_df['close_price'].values)
        assert np.allclose(original_df['Volume'].values, postgres_df['volume'].values)
    
    async def test_performance_improvement(self):
        """Verify 10x performance improvement"""
        import time
        
        # Test PostgreSQL query time
        start = time.time()
        postgres_data = await self.repository.get_ohlc_data("AAPL", "2023-01-01", "2024-01-01")
        postgres_time = time.time() - start
        
        # Historical CSV time (from benchmarks)
        csv_baseline_time = 0.500  # 500ms baseline
        
        assert postgres_time < 0.100  # Sub-100ms requirement
        assert postgres_time < csv_baseline_time / 10  # 10x improvement
    
    async def test_rag_functionality(self):
        """Verify RAG vector similarity search works"""
        rag_service = MarketDataRAGService(self.repository)
        
        # Test pattern matching
        results = await rag_service.find_similar_market_conditions("AAPL", datetime(2023, 6, 1))
        
        assert len(results['historical_outcomes']) > 0
        assert 'confidence_score' in results
        assert results['average_return'] is not None
```

**API Compatibility Tests**
```python
class TestAPICompatibility:
    """Ensure 100% API compatibility after migration"""
    
    async def test_market_data_service_api(self):
        """Verify MarketDataService API unchanged"""
        service = MarketDataService(self.repository)
        
        # Test all existing methods
        ohlc_data = await service.get_ohlc_data("AAPL", "2023-01-01", "2023-12-31")
        assert isinstance(ohlc_data, pd.DataFrame)
        assert list(ohlc_data.columns) == ['open', 'high', 'low', 'close', 'volume', 'adj_close']
        
        indicators = await service.get_technical_indicators("AAPL", "2023-01-01", "2023-12-31")
        assert isinstance(indicators, dict)
        assert 'sma_20' in indicators
        assert 'rsi_14' in indicators
        
        momentum_analysis = await service.get_trading_style_preset("momentum", "AAPL")
        assert 'signal' in momentum_analysis
        assert 'confidence' in momentum_analysis
    
    async def test_fundamental_service_api(self):
        """Verify FundamentalDataService API unchanged"""
        service = FundamentalDataService(self.repository)
        
        ratios = await service.get_financial_ratios("AAPL")
        assert isinstance(ratios, dict)
        assert 'pe_ratio' in ratios
        
        health = await service.analyze_financial_health("AAPL")
        assert 'health_score' in health
        assert 'trend_analysis' in health
```

**Performance Validation**
```python
class TestPerformanceRequirements:
    """Validate performance requirements are met"""
    
    async def test_sub_100ms_queries(self):
        """Verify sub-100ms query performance"""
        import time
        
        queries = [
            lambda: self.repository.get_ohlc_data("AAPL", "2023-12-01", "2023-12-31"),
            lambda: self.repository.get_technical_indicators("AAPL", "2023-12-01", "2023-12-31"),
            lambda: self.repository.get_latest_fundamentals("AAPL")
        ]
        
        for query in queries:
            start = time.time()
            await query()
            elapsed = time.time() - start
            
            assert elapsed < 0.100, f"Query took {elapsed:.3f}s, exceeds 100ms requirement"
    
    async def test_rag_query_performance(self):
        """Verify sub-200ms RAG query performance"""
        rag_service = MarketDataRAGService(self.repository)
        
        start = time.time()
        results = await rag_service.find_similar_market_conditions("AAPL", datetime.now())
        elapsed = time.time() - start
        
        assert elapsed < 0.200, f"RAG query took {elapsed:.3f}s, exceeds 200ms requirement"
    
    async def test_concurrent_access(self):
        """Verify concurrent agent access performance"""
        import asyncio
        
        async def concurrent_query(symbol: str):
            return await self.repository.get_ohlc_data(symbol, "2023-12-01", "2023-12-31")
        
        # Simulate 10 concurrent agents
        tasks = [concurrent_query(f"SYMBOL_{i}") for i in range(10)]
        
        start = time.time()
        results = await asyncio.gather(*tasks)
        elapsed = time.time() - start
        
        assert elapsed < 1.0, f"Concurrent queries took {elapsed:.3f}s, too slow for agent workload"
        assert len(results) == 10
```

## Implementation Guidance

### Step-by-Step Implementation

**Week 1: Database Setup and Schema Migration**
1. Set up PostgreSQL with TimescaleDB and pgvectorscale extensions
2. Create database schemas with proper indexing
3. Run Alembic migrations to create all tables
4. Test hypertable creation and vector index performance

**Week 2: Entity Models and Repository Layer**
1. Implement all SQLAlchemy entity models with business logic
2. Create async repository classes with PostgreSQL operations
3. Implement batch operations for high-performance data loading
4. Add vector similarity search capabilities

**Week 3: Data Migration and Validation**
1. Build CSV-to-PostgreSQL migration scripts
2. Migrate all historical data with integrity validation
3. Generate vector embeddings for all existing data
4. Validate data accuracy and performance benchmarks

**Week 4: Service Layer and API Preservation**
1. Update service layer to use PostgreSQL repositories
2. Ensure 100% API compatibility with existing interfaces
3. Implement RAG-enhanced analysis features
4. Complete integration testing and performance validation

### Code Organization

```
tradingagents/domains/marketdata/
├── entities/
│   ├── __init__.py
│   ├── market_data_entity.py
│   ├── fundamental_data_entity.py
│   ├── insider_data_entity.py
│   └── technical_indicator_entity.py
├── repositories/
│   ├── __init__.py
│   ├── market_data_repository.py
│   ├── fundamental_data_repository.py
│   └── insider_data_repository.py
├── services/
│   ├── __init__.py
│   ├── market_data_service.py
│   ├── fundamental_data_service.py
│   ├── insider_data_service.py
│   └── embedding_service.py
├── migration/
│   ├── __init__.py
│   ├── migrator.py
│   └── validation.py
├── rag/
│   ├── __init__.py
│   ├── rag_service.py
│   └── pattern_matcher.py
└── clients/
    ├── __init__.py
    ├── yfinance_client.py  # Already implemented
    └── finnhub_client.py   # Already implemented
```

### Configuration Updates

**Database Configuration**
```python
# config/database.py

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import QueuePool

class DatabaseConfig:
    def __init__(self, database_url: str):
        self.engine = create_async_engine(
            database_url,
            poolclass=QueuePool,
            pool_size=20,
            max_overflow=30,
            pool_pre_ping=True,
            echo=False  # Set True for SQL debugging
        )
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
            autoflush=True,
            autocommit=False
        )
    
    async def health_check(self) -> bool:
        """Verify database connectivity and extensions"""
        async with self.session_factory() as session:
            result = await session.execute(
                "SELECT extname FROM pg_extension WHERE extname IN ('timescaledb', 'vectorscale')"
            )
            extensions = result.fetchall()
            return len(extensions) == 2
```

### Monitoring and Observability

**Performance Monitoring**
```python
class MarketDataMetrics:
    """Monitor PostgreSQL migration performance"""
    
    def __init__(self):
        self.query_times = []
        self.rag_query_times = []
    
    async def track_query_performance(self, operation: str, execution_time: float):
        """Track query performance metrics"""
        self.query_times.append({
            'operation': operation,
            'time': execution_time,
            'timestamp': datetime.now()
        })
        
        # Alert if performance degrades
        if execution_time > 0.100:
            print(f"WARNING: {operation} took {execution_time:.3f}s, exceeds 100ms SLA")
    
    def generate_performance_report(self) -> Dict[str, Any]:
        """Generate performance analytics report"""
        recent_queries = [q for q in self.query_times if q['timestamp'] > datetime.now() - timedelta(hours=1)]
        
        return {
            'total_queries': len(recent_queries),
            'average_query_time': np.mean([q['time'] for q in recent_queries]),
            'p95_query_time': np.percentile([q['time'] for q in recent_queries], 95),
            'sla_violations': len([q for q in recent_queries if q['time'] > 0.100]),
            'performance_trend': 'stable'  # Could implement trending analysis
        }
```

This technical design provides a comprehensive migration strategy from the 85% complete CSV-based system to a high-performance PostgreSQL + TimescaleDB + pgvectorscale architecture while preserving 100% API compatibility and adding powerful RAG capabilities for historical pattern matching.

The design emphasizes:
- **Performance**: Sub-100ms queries with TimescaleDB optimization
- **Compatibility**: Zero API changes for existing services
- **Intelligence**: RAG-enhanced analysis with vector similarity search
- **Scalability**: Async PostgreSQL operations for concurrent agent access
- **Quality**: Comprehensive testing strategy for migration validation

Implementation should follow the 4-phase approach with weekly milestones to ensure smooth migration and immediate performance benefits.
