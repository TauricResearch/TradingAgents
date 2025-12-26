"""Add Portfolio model for managing trading portfolios

Revision ID: 003
Revises: 002
Create Date: 2025-12-26 14:00:00.000000

This migration adds the portfolios table for managing user trading portfolios.
Each portfolio belongs to a user and tracks capital with high precision.

Table: portfolios
Columns:
- id: Primary key, auto-increment
- user_id: Foreign key to users.id (cascade delete)
- name: Portfolio name (VARCHAR 255, indexed)
- portfolio_type: Type of portfolio (ENUM: LIVE, PAPER, BACKTEST)
- initial_capital: Starting capital (NUMERIC 19,4)
- current_value: Current portfolio value (NUMERIC 19,4)
- currency: 3-letter currency code (VARCHAR 3, default: AUD)
- is_active: Whether portfolio is active (BOOLEAN, default: TRUE, indexed)
- created_at: Timestamp when created (auto)
- updated_at: Timestamp when last updated (auto)

Constraints:
- UNIQUE (user_id, name): User can't have duplicate portfolio names
- CHECK initial_capital >= 0: Capital must be non-negative
- CHECK current_value >= 0: Value must be non-negative

Indexes:
- ix_portfolios_user_id: Foreign key lookup
- ix_portfolios_name: Name search
- ix_portfolios_is_active: Active/inactive filtering
- ix_portfolios_user_active: Composite (user_id, is_active)
- ix_portfolios_user_type: Composite (user_id, portfolio_type)

Relationships:
- portfolios.user_id -> users.id (CASCADE DELETE)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create portfolios table with all constraints and indexes.

    Creates the portfolios table for managing user trading portfolios
    with proper foreign keys, constraints, and indexes.
    """
    # Create portfolios table
    op.create_table(
        'portfolios',
        # Primary key
        sa.Column(
            'id',
            sa.Integer(),
            nullable=False,
            primary_key=True,
            autoincrement=True
        ),

        # Foreign key to users (cascade delete)
        sa.Column(
            'user_id',
            sa.Integer(),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
            comment='User who owns this portfolio'
        ),

        # Portfolio identification
        sa.Column(
            'name',
            sa.String(length=255),
            nullable=False,
            comment='Portfolio name (unique per user)'
        ),

        # Portfolio type enum
        sa.Column(
            'portfolio_type',
            sa.String(length=20),
            nullable=False,
            comment='Portfolio type: LIVE, PAPER, or BACKTEST'
        ),

        # Monetary values with high precision (19 total digits, 4 after decimal)
        sa.Column(
            'initial_capital',
            sa.Numeric(precision=19, scale=4),
            nullable=False,
            comment='Initial capital amount'
        ),

        sa.Column(
            'current_value',
            sa.Numeric(precision=19, scale=4),
            nullable=False,
            comment='Current portfolio value'
        ),

        # Currency code (ISO 4217 - 3 letters)
        sa.Column(
            'currency',
            sa.String(length=3),
            nullable=False,
            server_default='AUD',
            comment='Currency code (ISO 4217, e.g., AUD, USD)'
        ),

        # Portfolio status
        sa.Column(
            'is_active',
            sa.Boolean(),
            nullable=False,
            server_default='1',
            comment='Whether portfolio is actively trading'
        ),

        # Timestamps (from TimestampMixin)
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('CURRENT_TIMESTAMP'),
            comment='Timestamp when portfolio was created'
        ),

        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('CURRENT_TIMESTAMP'),
            comment='Timestamp when portfolio was last updated'
        ),

        # Table-level constraints
        # Unique constraint: user can't have duplicate portfolio names
        sa.UniqueConstraint(
            'user_id',
            'name',
            name='uq_portfolio_user_name'
        ),

        # Check constraints: non-negative monetary values
        sa.CheckConstraint(
            'initial_capital >= 0',
            name='ck_portfolio_initial_capital_positive'
        ),

        sa.CheckConstraint(
            'current_value >= 0',
            name='ck_portfolio_current_value_positive'
        ),
    )

    # Create indexes for efficient queries
    # Index on user_id for foreign key lookups
    op.create_index(
        'ix_portfolios_user_id',
        'portfolios',
        ['user_id'],
        unique=False
    )

    # Index on name for searching
    op.create_index(
        'ix_portfolios_name',
        'portfolios',
        ['name'],
        unique=False
    )

    # Index on is_active for filtering active/inactive portfolios
    op.create_index(
        'ix_portfolios_is_active',
        'portfolios',
        ['is_active'],
        unique=False
    )

    # Composite index for querying user's active portfolios
    op.create_index(
        'ix_portfolio_user_active',
        'portfolios',
        ['user_id', 'is_active'],
        unique=False
    )

    # Composite index for querying user's portfolios by type
    op.create_index(
        'ix_portfolio_user_type',
        'portfolios',
        ['user_id', 'portfolio_type'],
        unique=False
    )


def downgrade() -> None:
    """Drop portfolios table and all associated indexes and constraints.

    WARNING: This will permanently delete all portfolio data!
    """
    # Drop all indexes
    op.drop_index('ix_portfolio_user_type', 'portfolios')
    op.drop_index('ix_portfolio_user_active', 'portfolios')
    op.drop_index('ix_portfolios_is_active', 'portfolios')
    op.drop_index('ix_portfolios_name', 'portfolios')
    op.drop_index('ix_portfolios_user_id', 'portfolios')

    # Drop the table (constraints are dropped automatically)
    op.drop_table('portfolios')
