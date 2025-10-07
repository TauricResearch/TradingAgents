"""
Database Models and Persistence Layer
=====================================

SQLAlchemy models for persistent storage of trading data.
Uses PostgreSQL with TimescaleDB extension for time-series optimization.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, Dict, Any
import uuid

from sqlalchemy import (
    Column, String, Integer, Float, Decimal as SQLDecimal,
    DateTime, Boolean, JSON, Text, ForeignKey, Index,
    UniqueConstraint, CheckConstraint, create_engine
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker, Session
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func

Base = declarative_base()


class OrderStatus(str, Enum):
    """Order status enumeration"""
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    FAILED = "failed"


class SignalType(str, Enum):
    """Signal type enumeration"""
    CONGRESSIONAL = "congressional"
    INSIDER = "insider"
    TECHNICAL = "technical"
    FUNDAMENTAL = "fundamental"
    SENTIMENT = "sentiment"
    AI_GENERATED = "ai_generated"


class AlertPriority(str, Enum):
    """Alert priority levels"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


# === Portfolio Models ===

class Position(Base):
    """Current portfolio positions"""
    __tablename__ = "positions"
    __table_args__ = (
        Index('idx_position_ticker', 'ticker'),
        Index('idx_position_updated', 'last_updated'),
    )

    id = Column(Integer, primary_key=True)
    ticker = Column(String(10), nullable=False, unique=True)
    shares = Column(Integer, nullable=False)
    avg_cost = Column(SQLDecimal(12, 4), nullable=False)
    current_price = Column(SQLDecimal(12, 4))
    market_value = Column(SQLDecimal(12, 2))
    unrealized_pnl = Column(SQLDecimal(12, 2))
    realized_pnl = Column(SQLDecimal(12, 2))
    percent_change = Column(Float)
    last_updated = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    orders = relationship("Order", back_populates="position")
    snapshots = relationship("PortfolioSnapshot", back_populates="position")


class PortfolioSnapshot(Base):
    """Historical portfolio snapshots"""
    __tablename__ = "portfolio_snapshots"
    __table_args__ = (
        Index('idx_snapshot_timestamp', 'timestamp'),
        Index('idx_snapshot_ticker_time', 'ticker', 'timestamp'),
        # TimescaleDB hypertable on timestamp
        {'timescaledb_hypertable': {'time_column': 'timestamp'}}
    )

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=func.now())
    position_id = Column(Integer, ForeignKey('positions.id'))
    ticker = Column(String(10), nullable=False)
    shares = Column(Integer, nullable=False)
    price = Column(SQLDecimal(12, 4), nullable=False)
    value = Column(SQLDecimal(12, 2), nullable=False)
    daily_pnl = Column(SQLDecimal(12, 2))
    total_pnl = Column(SQLDecimal(12, 2))

    # Account level metrics
    total_value = Column(SQLDecimal(15, 2))
    cash_balance = Column(SQLDecimal(15, 2))
    buying_power = Column(SQLDecimal(15, 2))

    position = relationship("Position", back_populates="snapshots")


# === Trading Models ===

class Order(Base):
    """Order tracking with full lifecycle"""
    __tablename__ = "orders"
    __table_args__ = (
        Index('idx_order_ticker', 'ticker'),
        Index('idx_order_status', 'status'),
        Index('idx_order_created', 'created_at'),
        UniqueConstraint('idempotency_key', name='uq_order_idempotency'),
    )

    id = Column(Integer, primary_key=True)
    order_id = Column(String(50), unique=True)  # IBKR order ID
    idempotency_key = Column(UUID(as_uuid=True), default=uuid.uuid4)

    # Order details
    ticker = Column(String(10), nullable=False)
    position_id = Column(Integer, ForeignKey('positions.id'))
    action = Column(String(10), nullable=False)  # BUY/SELL
    order_type = Column(String(20), nullable=False)  # MARKET/LIMIT/STOP
    quantity = Column(Integer, nullable=False)
    limit_price = Column(SQLDecimal(12, 4))
    stop_price = Column(SQLDecimal(12, 4))

    # Status tracking
    status = Column(String(20), nullable=False, default=OrderStatus.PENDING)
    filled_quantity = Column(Integer, default=0)
    avg_fill_price = Column(SQLDecimal(12, 4))
    commission = Column(SQLDecimal(8, 2))

    # Risk management
    stop_loss_price = Column(SQLDecimal(12, 4))
    take_profit_price = Column(SQLDecimal(12, 4))
    parent_order_id = Column(Integer, ForeignKey('orders.id'))

    # Metadata
    signal_id = Column(Integer, ForeignKey('signals.id'))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    submitted_at = Column(DateTime(timezone=True))
    filled_at = Column(DateTime(timezone=True))
    cancelled_at = Column(DateTime(timezone=True))
    notes = Column(Text)

    # Relationships
    position = relationship("Position", back_populates="orders")
    signal = relationship("Signal", back_populates="orders")
    child_orders = relationship("Order", backref='parent_order')


class Trade(Base):
    """Executed trades (fills)"""
    __tablename__ = "trades"
    __table_args__ = (
        Index('idx_trade_ticker', 'ticker'),
        Index('idx_trade_executed', 'executed_at'),
    )

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey('orders.id'), nullable=False)
    ticker = Column(String(10), nullable=False)
    action = Column(String(10), nullable=False)
    quantity = Column(Integer, nullable=False)
    price = Column(SQLDecimal(12, 4), nullable=False)
    commission = Column(SQLDecimal(8, 2))
    executed_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    pnl = Column(SQLDecimal(12, 2))


# === Signal Models ===

class Signal(Base):
    """Trading signals generated by the system"""
    __tablename__ = "signals"
    __table_args__ = (
        Index('idx_signal_ticker', 'ticker'),
        Index('idx_signal_type', 'signal_type'),
        Index('idx_signal_created', 'created_at'),
        Index('idx_signal_confidence', 'confidence'),
    )

    id = Column(Integer, primary_key=True)
    ticker = Column(String(10), nullable=False)
    signal_type = Column(String(20), nullable=False)
    action = Column(String(10), nullable=False)  # BUY/SELL/HOLD
    confidence = Column(Float, nullable=False)

    # Price targets
    current_price = Column(SQLDecimal(12, 4))
    entry_price_min = Column(SQLDecimal(12, 4))
    entry_price_max = Column(SQLDecimal(12, 4))
    target_price_1 = Column(SQLDecimal(12, 4))
    target_price_2 = Column(SQLDecimal(12, 4))
    stop_loss = Column(SQLDecimal(12, 4))

    # Sizing
    position_size = Column(Float)  # Percentage of portfolio
    risk_level = Column(String(10))  # LOW/MEDIUM/HIGH

    # Metadata
    reasoning = Column(Text)
    data_sources = Column(JSONB)  # JSON array of sources
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True))

    # Tracking
    acted_upon = Column(Boolean, default=False)
    acted_at = Column(DateTime(timezone=True))
    performance = Column(JSONB)  # Track signal accuracy

    # Relationships
    orders = relationship("Order", back_populates="signal")


# === Alternative Data Models ===

class CongressionalTrade(Base):
    """Congressional trading activity"""
    __tablename__ = "congressional_trades"
    __table_args__ = (
        Index('idx_congress_ticker', 'ticker'),
        Index('idx_congress_politician', 'politician'),
        Index('idx_congress_filed', 'filing_date'),
        UniqueConstraint('politician', 'ticker', 'transaction_date',
                        name='uq_congress_trade'),
    )

    id = Column(Integer, primary_key=True)
    politician = Column(String(100), nullable=False)
    ticker = Column(String(10), nullable=False)
    action = Column(String(20), nullable=False)  # purchase/sale
    amount_range = Column(String(50))
    transaction_date = Column(DateTime(timezone=True), nullable=False)
    filing_date = Column(DateTime(timezone=True), nullable=False)
    party = Column(String(20))
    state = Column(String(5))
    chamber = Column(String(10))  # house/senate
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class InsiderTrade(Base):
    """Insider trading activity"""
    __tablename__ = "insider_trades"
    __table_args__ = (
        Index('idx_insider_ticker', 'ticker'),
        Index('idx_insider_name', 'insider_name'),
        Index('idx_insider_date', 'transaction_date'),
    )

    id = Column(Integer, primary_key=True)
    insider_name = Column(String(100), nullable=False)
    ticker = Column(String(10), nullable=False)
    action = Column(String(10), nullable=False)  # Buy/Sell
    shares = Column(Integer)
    value = Column(SQLDecimal(15, 2))
    transaction_date = Column(DateTime(timezone=True), nullable=False)
    position = Column(String(50))  # CEO/CFO/Director
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# === Alert Models ===

class Alert(Base):
    """Alert history and tracking"""
    __tablename__ = "alerts"
    __table_args__ = (
        Index('idx_alert_type', 'alert_type'),
        Index('idx_alert_priority', 'priority'),
        Index('idx_alert_created', 'created_at'),
    )

    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    alert_type = Column(String(30), nullable=False)
    priority = Column(String(10), nullable=False)

    # Delivery tracking
    channels = Column(JSONB)  # ['discord', 'telegram', 'email']
    sent_successfully = Column(Boolean, default=False)
    send_attempts = Column(Integer, default=0)
    error_message = Column(Text)

    # Metadata
    data = Column(JSONB)
    ticker = Column(String(10))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    sent_at = Column(DateTime(timezone=True))

    # Deduplication
    hash = Column(String(64), index=True)


# === Performance Models ===

class PerformanceMetric(Base):
    """Strategy performance tracking"""
    __tablename__ = "performance_metrics"
    __table_args__ = (
        Index('idx_perf_date', 'date'),
        {'timescaledb_hypertable': {'time_column': 'date'}}
    )

    id = Column(Integer, primary_key=True)
    date = Column(DateTime(timezone=True), nullable=False, default=func.now())

    # Daily metrics
    total_pnl = Column(SQLDecimal(12, 2))
    realized_pnl = Column(SQLDecimal(12, 2))
    unrealized_pnl = Column(SQLDecimal(12, 2))
    win_rate = Column(Float)
    sharpe_ratio = Column(Float)
    max_drawdown = Column(Float)

    # Trade statistics
    total_trades = Column(Integer)
    winning_trades = Column(Integer)
    losing_trades = Column(Integer)
    avg_win = Column(SQLDecimal(10, 2))
    avg_loss = Column(SQLDecimal(10, 2))

    # Signal statistics
    signals_generated = Column(Integer)
    signals_acted = Column(Integer)
    signal_accuracy = Column(Float)

    # Risk metrics
    portfolio_beta = Column(Float)
    portfolio_volatility = Column(Float)
    value_at_risk = Column(SQLDecimal(12, 2))


# === Database Manager ===

class DatabaseManager:
    """Database connection and session management"""

    def __init__(self, connection_string: str):
        """
        Initialize database manager

        Args:
            connection_string: PostgreSQL connection string
        """
        self.engine = create_engine(
            connection_string,
            pool_size=20,
            max_overflow=40,
            pool_pre_ping=True,  # Check connections before using
            echo=False
        )
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )

    def init_database(self):
        """Create all tables and indexes"""
        Base.metadata.create_all(bind=self.engine)

        # Create TimescaleDB hypertables
        with self.engine.connect() as conn:
            # Convert tables to hypertables for time-series optimization
            conn.execute("""
                SELECT create_hypertable('portfolio_snapshots', 'timestamp',
                                        if_not_exists => TRUE);
            """)
            conn.execute("""
                SELECT create_hypertable('performance_metrics', 'date',
                                        if_not_exists => TRUE);
            """)

    def get_session(self) -> Session:
        """Get a new database session"""
        return self.SessionLocal()

    def save_position(self, position_data: Dict[str, Any]) -> Position:
        """Save or update a position"""
        with self.get_session() as session:
            position = session.query(Position).filter_by(
                ticker=position_data['ticker']
            ).first()

            if position:
                # Update existing
                for key, value in position_data.items():
                    setattr(position, key, value)
            else:
                # Create new
                position = Position(**position_data)
                session.add(position)

            session.commit()
            session.refresh(position)
            return position

    def save_signal(self, signal_data: Dict[str, Any]) -> Signal:
        """Save a new signal"""
        with self.get_session() as session:
            signal = Signal(**signal_data)
            session.add(signal)
            session.commit()
            session.refresh(signal)
            return signal

    def save_order(self, order_data: Dict[str, Any]) -> Order:
        """Save a new order with idempotency"""
        with self.get_session() as session:
            # Check idempotency
            if 'idempotency_key' in order_data:
                existing = session.query(Order).filter_by(
                    idempotency_key=order_data['idempotency_key']
                ).first()
                if existing:
                    return existing

            order = Order(**order_data)
            session.add(order)
            session.commit()
            session.refresh(order)
            return order

    def update_order_status(self, order_id: str, status: OrderStatus,
                          **kwargs) -> Optional[Order]:
        """Update order status"""
        with self.get_session() as session:
            order = session.query(Order).filter_by(order_id=order_id).first()
            if order:
                order.status = status
                for key, value in kwargs.items():
                    setattr(order, key, value)
                session.commit()
                session.refresh(order)
            return order

    def get_active_positions(self) -> list[Position]:
        """Get all active positions"""
        with self.get_session() as session:
            return session.query(Position).filter(
                Position.shares > 0
            ).all()

    def get_recent_signals(self, ticker: Optional[str] = None,
                          hours: int = 24) -> list[Signal]:
        """Get recent signals"""
        with self.get_session() as session:
            query = session.query(Signal).filter(
                Signal.created_at >= func.now() - timedelta(hours=hours)
            )
            if ticker:
                query = query.filter(Signal.ticker == ticker)
            return query.order_by(Signal.confidence.desc()).all()


# Example usage
if __name__ == "__main__":
    # Initialize database
    db = DatabaseManager("postgresql://trader:password@localhost/trading_db")
    db.init_database()

    print("✅ Database initialized successfully")