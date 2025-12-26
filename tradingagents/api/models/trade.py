"""Trade model for execution history with CGT tracking.

This module defines the Trade model for tracking buy/sell trade executions
with full capital gains tax (CGT) support for Australian tax compliance.
Each trade belongs to a portfolio and includes acquisition details,
cost basis, holding period, and CGT calculations.

Model Fields:
    Core Trade Fields:
    - id: Primary key
    - portfolio_id: Foreign key to portfolios table
    - symbol: Stock/asset symbol (uppercase)
    - side: Trade side (BUY, SELL)
    - quantity: Number of units traded
    - price: Price per unit
    - total_value: Total trade value (quantity * price)
    - order_type: Order type (MARKET, LIMIT, STOP, STOP_LIMIT)
    - status: Trade status (PENDING, FILLED, PARTIAL, CANCELLED, REJECTED)
    - executed_at: When trade was executed (nullable for pending)

    Signal Fields:
    - signal_source: Source of trading signal (e.g., "RSI_DIVERGENCE")
    - signal_confidence: Confidence score 0-100

    CGT Fields (Australian Tax):
    - acquisition_date: Date asset was acquired
    - cost_basis_per_unit: Purchase price per unit (for CGT)
    - cost_basis_total: Total purchase cost (for CGT)
    - holding_period_days: Days held (for 50% discount eligibility)
    - cgt_discount_eligible: Whether eligible for 50% CGT discount (>365 days)
    - cgt_gross_gain: Gross capital gain before discount
    - cgt_gross_loss: Gross capital loss
    - cgt_net_gain: Net capital gain after discount

    Currency Fields:
    - currency: 3-letter currency code (default: AUD)
    - fx_rate_to_aud: Foreign exchange rate to AUD
    - total_value_aud: Total value in AUD
    - created_at, updated_at: Automatic timestamps

Relationships:
    - portfolio: Many-to-one relationship with Portfolio model
    - Cascade delete when portfolio is deleted

Constraints:
    - quantity > 0
    - price > 0
    - total_value > 0
    - signal_confidence >= 0 AND signal_confidence <= 100
    - holding_period_days >= 0 OR NULL
    - fx_rate_to_aud > 0

Properties:
    - tax_year: Australian FY (July-June) in format "FY2024"
    - is_buy: True if BUY trade
    - is_sell: True if SELL trade
    - is_filled: True if FILLED status

Follows SQLAlchemy 2.0 patterns with Mapped[] and mapped_column().
"""

from enum import Enum as PyEnum
from typing import Optional
from decimal import Decimal
from datetime import datetime, date

from sqlalchemy import (
    String,
    Boolean,
    Integer,
    Numeric,
    ForeignKey,
    Index,
    CheckConstraint,
    Enum,
    DateTime,
    Date,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates, Session

from tradingagents.api.models.base import Base, TimestampMixin
from tradingagents.api.models.portfolio import PreciseNumeric


class TradeSide(str, PyEnum):
    """Enum for trade side (buy/sell).

    BUY: Purchase of asset
    SELL: Sale of asset
    """

    BUY = "BUY"
    SELL = "SELL"


class TradeStatus(str, PyEnum):
    """Enum for trade execution status.

    PENDING: Trade submitted but not yet executed
    FILLED: Trade fully executed
    PARTIAL: Trade partially executed
    CANCELLED: Trade cancelled before full execution
    REJECTED: Trade rejected by broker/exchange
    """

    PENDING = "PENDING"
    FILLED = "FILLED"
    PARTIAL = "PARTIAL"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class TradeOrderType(str, PyEnum):
    """Enum for order types.

    MARKET: Execute at current market price
    LIMIT: Execute at specified price or better
    STOP: Trigger market order at stop price
    STOP_LIMIT: Trigger limit order at stop price
    """

    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class Trade(Base, TimestampMixin):
    """Trade model for execution history with CGT tracking.

    A trade represents a buy or sell execution with full capital gains tax
    tracking for Australian compliance. Includes acquisition details, cost basis,
    holding period calculations, and CGT discount eligibility.

    Attributes:
        Core Trade:
        id: Primary key, auto-increment
        portfolio_id: Foreign key to portfolios.id (cascade delete)
        symbol: Stock/asset symbol (uppercase)
        side: Trade side (BUY or SELL)
        quantity: Number of units traded (Decimal 19,4)
        price: Price per unit (Decimal 19,4)
        total_value: Total trade value (Decimal 19,4)
        order_type: Order type (MARKET, LIMIT, STOP, STOP_LIMIT)
        status: Trade status (PENDING, FILLED, etc.)
        executed_at: Timestamp when trade executed (nullable)

        Signal:
        signal_source: Source of trading signal (nullable)
        signal_confidence: Confidence score 0-100 (Decimal 5,2, nullable)

        CGT (Australian Tax):
        acquisition_date: Date asset acquired
        cost_basis_per_unit: Purchase price per unit (Decimal 19,4, nullable)
        cost_basis_total: Total purchase cost (Decimal 19,4, nullable)
        holding_period_days: Days held (nullable)
        cgt_discount_eligible: Eligible for 50% CGT discount (>365 days)
        cgt_gross_gain: Gross capital gain (Decimal 19,4, nullable)
        cgt_gross_loss: Gross capital loss (Decimal 19,4, nullable)
        cgt_net_gain: Net capital gain after discount (Decimal 19,4, nullable)

        Currency:
        currency: 3-letter currency code (e.g., AUD, USD)
        fx_rate_to_aud: FX rate to AUD (Decimal 19,8)
        total_value_aud: Total value in AUD (Decimal 19,4, nullable)

        Relationships:
        portfolio: Relationship to Portfolio model
        created_at: Timestamp when created (auto)
        updated_at: Timestamp when last updated (auto)

    Constraints:
        - quantity must be > 0
        - price must be > 0
        - total_value must be > 0
        - signal_confidence must be 0-100 (if set)
        - holding_period_days must be >= 0 (if set)
        - fx_rate_to_aud must be > 0

    Example:
        >>> from decimal import Decimal
        >>> from datetime import datetime, date
        >>> trade = Trade(
        ...     portfolio_id=1,
        ...     symbol="BHP",
        ...     side=TradeSide.BUY,
        ...     quantity=Decimal("100.0000"),
        ...     price=Decimal("45.5000"),
        ...     total_value=Decimal("4550.0000"),
        ...     order_type=TradeOrderType.MARKET,
        ...     status=TradeStatus.FILLED,
        ...     executed_at=datetime.now(),
        ...     acquisition_date=date.today(),
        ...     currency="AUD"
        ... )
        >>> session.add(trade)
        >>> await session.commit()
    """

    __tablename__ = "trades"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Foreign key to portfolio (cascade delete)
    portfolio_id: Mapped[int] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Portfolio this trade belongs to"
    )

    # Core trade fields
    symbol: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="Stock/asset symbol (uppercase)"
    )

    side: Mapped[TradeSide] = mapped_column(
        Enum(TradeSide, native_enum=False, length=10),
        nullable=False,
        index=True,
        comment="Trade side: BUY or SELL"
    )

    quantity: Mapped[Decimal] = mapped_column(
        PreciseNumeric,
        nullable=False,
        comment="Number of units traded"
    )

    price: Mapped[Decimal] = mapped_column(
        PreciseNumeric,
        nullable=False,
        comment="Price per unit"
    )

    total_value: Mapped[Decimal] = mapped_column(
        PreciseNumeric,
        nullable=False,
        default=lambda context: (
            context.get_current_parameters()['quantity'] *
            context.get_current_parameters()['price']
        ),
        comment="Total trade value (quantity * price)"
    )

    order_type: Mapped[TradeOrderType] = mapped_column(
        Enum(TradeOrderType, native_enum=False, length=20),
        nullable=False,
        comment="Order type: MARKET, LIMIT, STOP, STOP_LIMIT"
    )

    status: Mapped[TradeStatus] = mapped_column(
        Enum(TradeStatus, native_enum=False, length=20),
        nullable=False,
        default=TradeStatus.PENDING,
        index=True,
        comment="Trade status: PENDING, FILLED, PARTIAL, CANCELLED, REJECTED"
    )

    executed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when trade was executed (nullable for pending)"
    )

    # Signal fields
    signal_source: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Source of trading signal (e.g., RSI_DIVERGENCE)"
    )

    signal_confidence: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=5, scale=2),
        nullable=True,
        comment="Signal confidence score 0-100"
    )

    # CGT (Capital Gains Tax) fields for Australian tax compliance
    acquisition_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
        default=lambda context: (
            context.get_current_parameters().get('executed_at').date()
            if context.get_current_parameters().get('executed_at')
            else date.today()
        ),
        comment="Date asset was acquired (for CGT)"
    )

    cost_basis_per_unit: Mapped[Optional[Decimal]] = mapped_column(
        PreciseNumeric,
        nullable=True,
        comment="Purchase price per unit for CGT calculation"
    )

    cost_basis_total: Mapped[Optional[Decimal]] = mapped_column(
        PreciseNumeric,
        nullable=True,
        comment="Total purchase cost for CGT calculation"
    )

    holding_period_days: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Days held (for 50% CGT discount eligibility)"
    )

    cgt_discount_eligible: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Eligible for 50% CGT discount (held >365 days)"
    )

    cgt_gross_gain: Mapped[Optional[Decimal]] = mapped_column(
        PreciseNumeric,
        nullable=True,
        comment="Gross capital gain before discount"
    )

    cgt_gross_loss: Mapped[Optional[Decimal]] = mapped_column(
        PreciseNumeric,
        nullable=True,
        comment="Gross capital loss"
    )

    cgt_net_gain: Mapped[Optional[Decimal]] = mapped_column(
        PreciseNumeric,
        nullable=True,
        comment="Net capital gain after 50% discount"
    )

    # Currency fields
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="AUD",
        comment="Currency code (ISO 4217, e.g., AUD, USD)"
    )

    fx_rate_to_aud: Mapped[Decimal] = mapped_column(
        Numeric(precision=19, scale=8),
        nullable=False,
        default=Decimal("1.0"),
        comment="Foreign exchange rate to AUD"
    )

    total_value_aud: Mapped[Optional[Decimal]] = mapped_column(
        PreciseNumeric,
        nullable=True,
        comment="Total value in AUD (for multi-currency portfolios)"
    )

    # Relationships
    portfolio: Mapped["Portfolio"] = relationship(
        "Portfolio",
        back_populates="trades"
    )

    # Table-level constraints and indexes
    __table_args__ = (
        # Check constraints: positive values
        CheckConstraint(
            "quantity > 0",
            name="ck_trade_quantity_positive"
        ),
        CheckConstraint(
            "price > 0",
            name="ck_trade_price_positive"
        ),
        CheckConstraint(
            "total_value > 0",
            name="ck_trade_total_value_positive"
        ),
        # Check constraint: signal confidence range
        CheckConstraint(
            "signal_confidence >= 0 AND signal_confidence <= 100",
            name="ck_trade_signal_confidence_range"
        ),
        # Check constraint: holding period non-negative
        CheckConstraint(
            "holding_period_days >= 0 OR holding_period_days IS NULL",
            name="ck_trade_holding_period_positive"
        ),
        # Check constraint: FX rate positive
        CheckConstraint(
            "fx_rate_to_aud > 0",
            name="ck_trade_fx_rate_positive"
        ),
        # Composite indexes for common queries
        Index("ix_trade_portfolio_symbol", "portfolio_id", "symbol"),
        Index("ix_trade_portfolio_side", "portfolio_id", "side"),
        Index("ix_trade_status_executed", "status", "executed_at"),
    )

    @property
    def tax_year(self) -> str:
        """Calculate Australian financial year (July-June).

        Australian tax year runs from July 1 to June 30.
        Returns format "FY2024" for year ending June 30, 2024.

        Returns:
            String in format "FY2024" representing the Australian tax year
        """
        if not self.executed_at:
            # Use acquisition_date if no execution date
            ref_date = self.acquisition_date
        else:
            ref_date = self.executed_at.date()

        # Australian FY: July 1 to June 30
        # If month is Jan-Jun (1-6), FY is current year
        # If month is Jul-Dec (7-12), FY is next year
        if ref_date.month >= 7:
            fy_year = ref_date.year + 1
        else:
            fy_year = ref_date.year

        return f"FY{fy_year}"

    @property
    def is_buy(self) -> bool:
        """Check if trade is a BUY.

        Returns:
            True if trade side is BUY, False otherwise
        """
        return self.side == TradeSide.BUY

    @property
    def is_sell(self) -> bool:
        """Check if trade is a SELL.

        Returns:
            True if trade side is SELL, False otherwise
        """
        return self.side == TradeSide.SELL

    @property
    def is_filled(self) -> bool:
        """Check if trade is fully filled.

        Returns:
            True if trade status is FILLED, False otherwise
        """
        return self.status == TradeStatus.FILLED

    @validates("side")
    def validate_side(self, key: str, value) -> TradeSide:
        """Validate and convert trade side to TradeSide enum.

        Args:
            key: Field name (side)
            value: Trade side value (str or TradeSide)

        Returns:
            TradeSide enum value

        Raises:
            ValueError: If value is not a valid trade side
        """
        # If already a TradeSide, return it
        if isinstance(value, TradeSide):
            return value

        # Try to convert string to TradeSide
        if isinstance(value, str):
            try:
                return TradeSide[value.upper()]
            except KeyError:
                raise ValueError(
                    f"Invalid trade side '{value}'. "
                    f"Must be one of: {', '.join([s.value for s in TradeSide])}"
                )

        # Invalid type
        raise ValueError(
            f"Trade side must be string or TradeSide enum, got {type(value)}"
        )

    @validates("status")
    def validate_status(self, key: str, value) -> TradeStatus:
        """Validate and convert trade status to TradeStatus enum.

        Args:
            key: Field name (status)
            value: Trade status value (str or TradeStatus)

        Returns:
            TradeStatus enum value

        Raises:
            ValueError: If value is not a valid trade status
        """
        # If already a TradeStatus, return it
        if isinstance(value, TradeStatus):
            return value

        # Try to convert string to TradeStatus
        if isinstance(value, str):
            try:
                return TradeStatus[value.upper()]
            except KeyError:
                raise ValueError(
                    f"Invalid trade status '{value}'. "
                    f"Must be one of: {', '.join([s.value for s in TradeStatus])}"
                )

        # Invalid type
        raise ValueError(
            f"Trade status must be string or TradeStatus enum, got {type(value)}"
        )

    @validates("order_type")
    def validate_order_type(self, key: str, value) -> TradeOrderType:
        """Validate and convert order type to TradeOrderType enum.

        Args:
            key: Field name (order_type)
            value: Order type value (str or TradeOrderType)

        Returns:
            TradeOrderType enum value

        Raises:
            ValueError: If value is not a valid order type
        """
        # If already a TradeOrderType, return it
        if isinstance(value, TradeOrderType):
            return value

        # Try to convert string to TradeOrderType
        if isinstance(value, str):
            try:
                return TradeOrderType[value.upper()]
            except KeyError:
                raise ValueError(
                    f"Invalid order type '{value}'. "
                    f"Must be one of: {', '.join([t.value for t in TradeOrderType])}"
                )

        # Invalid type
        raise ValueError(
            f"Order type must be string or TradeOrderType enum, got {type(value)}"
        )

    @validates("currency")
    def validate_currency(self, key: str, value: str) -> str:
        """Normalize currency code to uppercase.

        Args:
            key: Field name (currency)
            value: Currency code to normalize

        Returns:
            Uppercase currency code
        """
        if value is None:
            return "AUD"  # Default currency

        # Convert to uppercase for consistency
        return value.upper()

    @validates("symbol")
    def validate_symbol(self, key: str, value: str) -> str:
        """Normalize symbol to uppercase.

        Args:
            key: Field name (symbol)
            value: Symbol to normalize

        Returns:
            Uppercase symbol
        """
        if value is None:
            raise ValueError("Symbol cannot be None")

        # Convert to uppercase for consistency
        return value.upper()

    def __repr__(self) -> str:
        """String representation of Trade.

        Returns:
            String showing trade ID, symbol, side, quantity, and status
        """
        return (
            f"<Trade(id={self.id}, "
            f"symbol='{self.symbol}', "
            f"side={self.side.value}, "
            f"quantity={self.quantity}, "
            f"price={self.price}, "
            f"status={self.status.value})>"
        )


# Event listener for before_flush validation
# This ensures constraints are checked before database commit
@event.listens_for(Session, "before_flush")
def validate_trade_before_flush(session, flush_context, instances):
    """Validate Trade objects before flushing to database.

    This event listener checks business rules that may not be enforced
    by the database (especially in SQLite which is permissive).

    Args:
        session: SQLAlchemy session
        flush_context: Flush context
        instances: Instances being flushed

    Raises:
        ValueError: If validation fails
    """
    for obj in session.new | session.dirty:
        if isinstance(obj, Trade):
            # Validate symbol
            if not obj.symbol or not obj.symbol.strip():
                raise ValueError("Trade symbol cannot be empty")

            if len(obj.symbol) > 20:
                raise ValueError(
                    f"Trade symbol too long: {len(obj.symbol)} characters (max 20)"
                )

            # Validate currency code length
            if obj.currency and len(obj.currency) != 3:
                raise ValueError(
                    f"Currency code must be exactly 3 characters, got {len(obj.currency)}"
                )

            # Validate signal_source length
            if obj.signal_source and len(obj.signal_source) > 100:
                raise ValueError(
                    f"Signal source too long: {len(obj.signal_source)} characters (max 100)"
                )

            # Validate positive values
            if obj.quantity is not None and obj.quantity <= 0:
                raise ValueError(
                    f"quantity must be positive, got {obj.quantity}"
                )

            if obj.price is not None and obj.price <= 0:
                raise ValueError(
                    f"price must be positive, got {obj.price}"
                )

            if obj.total_value is not None and obj.total_value <= 0:
                raise ValueError(
                    f"total_value must be positive, got {obj.total_value}"
                )

            if obj.fx_rate_to_aud is not None and obj.fx_rate_to_aud <= 0:
                raise ValueError(
                    f"fx_rate_to_aud must be positive, got {obj.fx_rate_to_aud}"
                )
