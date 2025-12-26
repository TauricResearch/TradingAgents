"""Add Trade model for execution history with CGT tracking

Revision ID: 005
Revises: 004
Create Date: 2025-12-26 15:00:00.000000

This migration adds the trades table for tracking buy/sell trade executions
with full capital gains tax (CGT) support for Australian tax compliance.
Each trade belongs to a portfolio and includes acquisition details, cost basis,
holding period calculations, and CGT discount eligibility.

Table: trades
Columns:
    Core Trade:
    - id: Primary key, auto-increment
    - portfolio_id: Foreign key to portfolios.id (cascade delete)
    - symbol: Stock/asset symbol (STRING 20, uppercase)
    - side: Trade side (ENUM: BUY, SELL)
    - quantity: Number of units traded (NUMERIC 19,4)
    - price: Price per unit (NUMERIC 19,4)
    - total_value: Total trade value (NUMERIC 19,4)
    - order_type: Order type (ENUM: MARKET, LIMIT, STOP, STOP_LIMIT)
    - status: Trade status (ENUM: PENDING, FILLED, PARTIAL, CANCELLED, REJECTED)
    - executed_at: Timestamp when executed (DATETIME, nullable)

    Signal:
    - signal_source: Source of trading signal (STRING 100, nullable)
    - signal_confidence: Confidence score 0-100 (NUMERIC 5,2, nullable)

    CGT (Australian Tax):
    - acquisition_date: Date asset acquired (DATE)
    - cost_basis_per_unit: Purchase price per unit (NUMERIC 19,4, nullable)
    - cost_basis_total: Total purchase cost (NUMERIC 19,4, nullable)
    - holding_period_days: Days held (INTEGER, nullable)
    - cgt_discount_eligible: Eligible for 50% CGT discount (BOOLEAN, default: false)
    - cgt_gross_gain: Gross capital gain (NUMERIC 19,4, nullable)
    - cgt_gross_loss: Gross capital loss (NUMERIC 19,4, nullable)
    - cgt_net_gain: Net capital gain after discount (NUMERIC 19,4, nullable)

    Currency:
    - currency: 3-letter currency code (STRING 3, default: AUD)
    - fx_rate_to_aud: FX rate to AUD (NUMERIC 19,8, default: 1.0)
    - total_value_aud: Total value in AUD (NUMERIC 19,4, nullable)

    Timestamps:
    - created_at: Timestamp when created (auto)
    - updated_at: Timestamp when last updated (auto)

Constraints:
- CHECK quantity > 0
- CHECK price > 0
- CHECK total_value > 0
- CHECK signal_confidence >= 0 AND signal_confidence <= 100
- CHECK holding_period_days >= 0 OR holding_period_days IS NULL
- CHECK fx_rate_to_aud > 0

Indexes:
- ix_trades_portfolio_id: Index on portfolio_id
- ix_trades_symbol: Index on symbol
- ix_trades_side: Index on side
- ix_trades_status: Index on status
- ix_trades_acquisition_date: Index on acquisition_date
- ix_trade_portfolio_symbol: Composite index on (portfolio_id, symbol)
- ix_trade_portfolio_side: Composite index on (portfolio_id, side)
- ix_trade_status_executed: Composite index on (status, executed_at)

Relationships:
- trades.portfolio_id -> portfolios.id (CASCADE DELETE)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '005'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create trades table with all constraints and indexes.

    Creates the trades table for tracking trade executions with CGT support
    and proper foreign keys, constraints, and indexes.
    """
    # Create trades table
    op.create_table(
        'trades',
        # Primary key
        sa.Column(
            'id',
            sa.Integer(),
            nullable=False,
            primary_key=True,
            autoincrement=True
        ),

        # Foreign key to portfolios (cascade delete)
        sa.Column(
            'portfolio_id',
            sa.Integer(),
            sa.ForeignKey('portfolios.id', ondelete='CASCADE'),
            nullable=False,
            comment='Portfolio this trade belongs to'
        ),

        # Core trade fields
        sa.Column(
            'symbol',
            sa.String(length=20),
            nullable=False,
            comment='Stock/asset symbol (uppercase)'
        ),

        sa.Column(
            'side',
            sa.String(length=10),
            nullable=False,
            comment='Trade side: BUY or SELL'
        ),

        sa.Column(
            'quantity',
            sa.Numeric(precision=19, scale=4),
            nullable=False,
            comment='Number of units traded'
        ),

        sa.Column(
            'price',
            sa.Numeric(precision=19, scale=4),
            nullable=False,
            comment='Price per unit'
        ),

        sa.Column(
            'total_value',
            sa.Numeric(precision=19, scale=4),
            nullable=False,
            comment='Total trade value (quantity * price)'
        ),

        sa.Column(
            'order_type',
            sa.String(length=20),
            nullable=False,
            comment='Order type: MARKET, LIMIT, STOP, STOP_LIMIT'
        ),

        sa.Column(
            'status',
            sa.String(length=20),
            nullable=False,
            server_default='PENDING',
            comment='Trade status: PENDING, FILLED, PARTIAL, CANCELLED, REJECTED'
        ),

        sa.Column(
            'executed_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='Timestamp when trade was executed (nullable for pending)'
        ),

        # Signal fields
        sa.Column(
            'signal_source',
            sa.String(length=100),
            nullable=True,
            comment='Source of trading signal (e.g., RSI_DIVERGENCE)'
        ),

        sa.Column(
            'signal_confidence',
            sa.Numeric(precision=5, scale=2),
            nullable=True,
            comment='Signal confidence score 0-100'
        ),

        # CGT (Capital Gains Tax) fields
        sa.Column(
            'acquisition_date',
            sa.Date(),
            nullable=False,
            comment='Date asset was acquired (for CGT)'
        ),

        sa.Column(
            'cost_basis_per_unit',
            sa.Numeric(precision=19, scale=4),
            nullable=True,
            comment='Purchase price per unit for CGT calculation'
        ),

        sa.Column(
            'cost_basis_total',
            sa.Numeric(precision=19, scale=4),
            nullable=True,
            comment='Total purchase cost for CGT calculation'
        ),

        sa.Column(
            'holding_period_days',
            sa.Integer(),
            nullable=True,
            comment='Days held (for 50% CGT discount eligibility)'
        ),

        sa.Column(
            'cgt_discount_eligible',
            sa.Boolean(),
            nullable=False,
            server_default='false',
            comment='Eligible for 50% CGT discount (held >365 days)'
        ),

        sa.Column(
            'cgt_gross_gain',
            sa.Numeric(precision=19, scale=4),
            nullable=True,
            comment='Gross capital gain before discount'
        ),

        sa.Column(
            'cgt_gross_loss',
            sa.Numeric(precision=19, scale=4),
            nullable=True,
            comment='Gross capital loss'
        ),

        sa.Column(
            'cgt_net_gain',
            sa.Numeric(precision=19, scale=4),
            nullable=True,
            comment='Net capital gain after 50% discount'
        ),

        # Currency fields
        sa.Column(
            'currency',
            sa.String(length=3),
            nullable=False,
            server_default='AUD',
            comment='Currency code (ISO 4217, e.g., AUD, USD)'
        ),

        sa.Column(
            'fx_rate_to_aud',
            sa.Numeric(precision=19, scale=8),
            nullable=False,
            server_default='1.0',
            comment='Foreign exchange rate to AUD'
        ),

        sa.Column(
            'total_value_aud',
            sa.Numeric(precision=19, scale=4),
            nullable=True,
            comment='Total value in AUD (for multi-currency portfolios)'
        ),

        # Timestamps (from TimestampMixin)
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('CURRENT_TIMESTAMP'),
            comment='Timestamp when trade was created'
        ),

        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('CURRENT_TIMESTAMP'),
            comment='Timestamp when trade was last updated'
        ),

        # Check constraints: positive values
        sa.CheckConstraint(
            'quantity > 0',
            name='ck_trade_quantity_positive'
        ),

        sa.CheckConstraint(
            'price > 0',
            name='ck_trade_price_positive'
        ),

        sa.CheckConstraint(
            'total_value > 0',
            name='ck_trade_total_value_positive'
        ),

        # Check constraint: signal confidence range
        sa.CheckConstraint(
            'signal_confidence >= 0 AND signal_confidence <= 100',
            name='ck_trade_signal_confidence_range'
        ),

        # Check constraint: holding period non-negative
        sa.CheckConstraint(
            'holding_period_days >= 0 OR holding_period_days IS NULL',
            name='ck_trade_holding_period_positive'
        ),

        # Check constraint: FX rate positive
        sa.CheckConstraint(
            'fx_rate_to_aud > 0',
            name='ck_trade_fx_rate_positive'
        ),
    )

    # Create indexes for efficient queries
    # Single column indexes
    op.create_index(
        'ix_trades_portfolio_id',
        'trades',
        ['portfolio_id']
    )

    op.create_index(
        'ix_trades_symbol',
        'trades',
        ['symbol']
    )

    op.create_index(
        'ix_trades_side',
        'trades',
        ['side']
    )

    op.create_index(
        'ix_trades_status',
        'trades',
        ['status']
    )

    op.create_index(
        'ix_trades_acquisition_date',
        'trades',
        ['acquisition_date']
    )

    # Composite indexes for common query patterns
    op.create_index(
        'ix_trade_portfolio_symbol',
        'trades',
        ['portfolio_id', 'symbol']
    )

    op.create_index(
        'ix_trade_portfolio_side',
        'trades',
        ['portfolio_id', 'side']
    )

    op.create_index(
        'ix_trade_status_executed',
        'trades',
        ['status', 'executed_at']
    )


def downgrade() -> None:
    """Drop trades table and all associated indexes and constraints.

    WARNING: This will permanently delete all trade execution data!
    """
    # Drop all indexes
    op.drop_index('ix_trade_status_executed', 'trades')
    op.drop_index('ix_trade_portfolio_side', 'trades')
    op.drop_index('ix_trade_portfolio_symbol', 'trades')
    op.drop_index('ix_trades_acquisition_date', 'trades')
    op.drop_index('ix_trades_status', 'trades')
    op.drop_index('ix_trades_side', 'trades')
    op.drop_index('ix_trades_symbol', 'trades')
    op.drop_index('ix_trades_portfolio_id', 'trades')

    # Drop the table (constraints are dropped automatically)
    op.drop_table('trades')
