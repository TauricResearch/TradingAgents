"""Portfolio model for managing trading portfolios.

This module defines the Portfolio model for tracking live, paper trading,
and backtesting portfolios. Each portfolio belongs to a user and tracks
monetary values with high precision using Decimal.

Model Fields:
    - id: Primary key
    - user_id: Foreign key to users table
    - name: Portfolio name (unique per user)
    - portfolio_type: Type of portfolio (LIVE, PAPER, BACKTEST)
    - initial_capital: Starting capital with Decimal(19,4) precision
    - current_value: Current portfolio value with Decimal(19,4) precision
    - currency: 3-letter currency code (default: AUD)
    - is_active: Whether portfolio is active
    - created_at, updated_at: Automatic timestamps

Relationships:
    - user: Many-to-one relationship with User model
    - Cascade delete when user is deleted

Constraints:
    - Unique constraint on (user_id, name)
    - Check constraint: initial_capital >= 0
    - Check constraint: current_value >= 0

Follows SQLAlchemy 2.0 patterns with Mapped[] and mapped_column().
"""

from enum import Enum as PyEnum
from typing import Optional
from decimal import Decimal

from sqlalchemy import (
    String,
    Boolean,
    Numeric,
    ForeignKey,
    Index,
    UniqueConstraint,
    CheckConstraint,
    Enum,
    event,
    TypeDecorator,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates, Session

from tradingagents.api.models.base import Base, TimestampMixin


class PreciseNumeric(TypeDecorator):
    """Custom type for high-precision numeric values.

    Stores Decimal with proper precision in all databases.
    For SQLite, uses NUMERIC (stored as REAL) but processes to/from Decimal
    to maintain Python-side precision even though DB storage is approximate.
    For PostgreSQL, uses true NUMERIC(19,4) type.

    Note: SQLite stores NUMERIC as REAL (float) which has precision limits.
    Very large values (>15 significant digits) will lose precision in SQLite.
    For production, use PostgreSQL which has true arbitrary precision NUMERIC.
    """

    impl = Numeric(19, 4)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Ensure value is Decimal before storing."""
        if value is None:
            return value
        if not isinstance(value, Decimal):
            return Decimal(str(value))
        return value

    def process_result_value(self, value, dialect):
        """Convert result to Decimal with proper precision."""
        if value is None:
            return value
        if isinstance(value, Decimal):
            return value
        # Convert from float/int to Decimal
        return Decimal(str(value))


class PortfolioType(str, PyEnum):
    """Enum for portfolio types.

    LIVE: Real money trading portfolio
    PAPER: Virtual/simulated trading portfolio
    BACKTEST: Historical backtesting portfolio
    """

    LIVE = "LIVE"
    PAPER = "PAPER"
    BACKTEST = "BACKTEST"


class Portfolio(Base, TimestampMixin):
    """Portfolio model for managing trading portfolios.

    A portfolio represents a collection of positions and tracks capital
    allocation. Users can have multiple portfolios of different types.

    Attributes:
        id: Primary key, auto-increment
        user_id: Foreign key to users.id (cascade delete)
        name: Portfolio name, unique per user
        portfolio_type: Type of portfolio (LIVE, PAPER, BACKTEST)
        initial_capital: Starting capital amount (Decimal 19,4)
        current_value: Current portfolio value (Decimal 19,4)
        currency: 3-letter currency code (e.g., AUD, USD)
        is_active: Whether portfolio is actively trading
        user: Relationship to User model
        created_at: Timestamp when created (auto)
        updated_at: Timestamp when last updated (auto)

    Constraints:
        - (user_id, name) must be unique
        - initial_capital must be >= 0
        - current_value must be >= 0
        - currency must be exactly 3 uppercase characters

    Example:
        >>> from decimal import Decimal
        >>> portfolio = Portfolio(
        ...     user_id=1,
        ...     name="My Trading Portfolio",
        ...     portfolio_type=PortfolioType.PAPER,
        ...     initial_capital=Decimal("10000.0000")
        ... )
        >>> session.add(portfolio)
        >>> await session.commit()
    """

    __tablename__ = "portfolios"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Foreign key to user (cascade delete)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User who owns this portfolio"
    )

    # Portfolio identification
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Portfolio name (unique per user)"
    )

    # Portfolio type (enum)
    portfolio_type: Mapped[PortfolioType] = mapped_column(
        Enum(PortfolioType, native_enum=False, length=20),
        nullable=False,
        comment="Portfolio type: LIVE, PAPER, or BACKTEST"
    )

    # Monetary values with high precision (19 total digits, 4 after decimal)
    # Using PreciseNumeric to preserve decimal precision in SQLite
    initial_capital: Mapped[Decimal] = mapped_column(
        PreciseNumeric,
        nullable=False,
        comment="Initial capital amount"
    )

    current_value: Mapped[Decimal] = mapped_column(
        PreciseNumeric,
        nullable=False,
        default=lambda context: context.get_current_parameters()['initial_capital'],
        comment="Current portfolio value"
    )

    # Currency code (ISO 4217 - 3 letters)
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="AUD",
        comment="Currency code (ISO 4217, e.g., AUD, USD)"
    )

    # Portfolio status
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
        comment="Whether portfolio is actively trading"
    )

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="portfolios"
    )

    trades: Mapped[list["Trade"]] = relationship(
        "Trade",
        back_populates="portfolio",
        cascade="all, delete-orphan"
    )

    # Table-level constraints and indexes
    __table_args__ = (
        # Unique constraint: user can't have duplicate portfolio names
        UniqueConstraint(
            "user_id",
            "name",
            name="uq_portfolio_user_name"
        ),
        # Check constraints: non-negative monetary values
        CheckConstraint(
            "initial_capital >= 0",
            name="ck_portfolio_initial_capital_positive"
        ),
        CheckConstraint(
            "current_value >= 0",
            name="ck_portfolio_current_value_positive"
        ),
        # Composite index for common queries
        Index("ix_portfolio_user_active", "user_id", "is_active"),
        Index("ix_portfolio_user_type", "user_id", "portfolio_type"),
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

    @validates("portfolio_type")
    def validate_portfolio_type(self, key: str, value) -> PortfolioType:
        """Validate and convert portfolio type to PortfolioType enum.

        Args:
            key: Field name (portfolio_type)
            value: Portfolio type value (str or PortfolioType)

        Returns:
            PortfolioType enum value

        Raises:
            ValueError: If value is not a valid portfolio type
        """
        # If already a PortfolioType, return it
        if isinstance(value, PortfolioType):
            return value

        # Try to convert string to PortfolioType
        if isinstance(value, str):
            try:
                return PortfolioType[value.upper()]
            except KeyError:
                raise ValueError(
                    f"Invalid portfolio type '{value}'. "
                    f"Must be one of: {', '.join([t.value for t in PortfolioType])}"
                )

        # Invalid type
        raise ValueError(
            f"Portfolio type must be string or PortfolioType enum, got {type(value)}"
        )

    def __repr__(self) -> str:
        """String representation of Portfolio.

        Returns:
            String showing portfolio ID, name, type, and value
        """
        return (
            f"<Portfolio(id={self.id}, "
            f"name='{self.name}', "
            f"type={self.portfolio_type.value}, "
            f"value={self.current_value} {self.currency})>"
        )


# Event listener for before_flush validation
# This ensures constraints are checked before database commit
@event.listens_for(Session, "before_flush")
def validate_portfolio_before_flush(session, flush_context, instances):
    """Validate Portfolio objects before flushing to database.

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
        if isinstance(obj, Portfolio):
            # Validate portfolio name
            if not obj.name or not obj.name.strip():
                raise ValueError("Portfolio name cannot be empty")

            if len(obj.name) > 255:
                raise ValueError(
                    f"Portfolio name too long: {len(obj.name)} characters (max 255)"
                )

            # Validate currency code length
            if obj.currency and len(obj.currency) != 3:
                raise ValueError(
                    f"Currency code must be exactly 3 characters, got {len(obj.currency)}"
                )

            # Validate monetary values are non-negative
            if obj.initial_capital is not None and obj.initial_capital < 0:
                raise ValueError(
                    f"initial_capital cannot be negative, got {obj.initial_capital}"
                )

            if obj.current_value is not None and obj.current_value < 0:
                raise ValueError(
                    f"current_value cannot be negative, got {obj.current_value}"
                )
