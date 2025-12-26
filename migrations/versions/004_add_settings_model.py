"""Add Settings model for user preferences and risk management

Revision ID: 004
Revises: 003
Create Date: 2025-12-26 14:30:00.000000

This migration adds the settings table for managing user trading preferences,
risk profiles, and alert configurations. Each user has exactly one Settings
record (one-to-one relationship).

Table: settings
Columns:
- id: Primary key, auto-increment
- user_id: Foreign key to users.id (cascade delete, unique)
- risk_profile: Risk tolerance profile (ENUM: CONSERVATIVE, MODERATE, AGGRESSIVE)
- risk_score: Numeric risk score 0-10 (NUMERIC 5,2, default: 5.0)
- max_position_pct: Max % of portfolio for single position (NUMERIC 5,2, default: 10.0)
- max_portfolio_risk_pct: Max portfolio-wide risk % (NUMERIC 5,2, default: 2.0)
- investment_horizon_years: Investment time horizon in years (INTEGER, default: 5)
- alert_preferences: JSON config for notifications (TEXT/JSON, default: '{}')
- created_at: Timestamp when created (auto)
- updated_at: Timestamp when last updated (auto)

Constraints:
- UNIQUE (user_id): One settings per user (one-to-one)
- CHECK risk_score >= 0 AND risk_score <= 10
- CHECK max_position_pct >= 0 AND max_position_pct <= 100
- CHECK max_portfolio_risk_pct >= 0 AND max_portfolio_risk_pct <= 100
- CHECK investment_horizon_years >= 0

Indexes:
- ix_settings_user_id: Unique index on user_id (one-to-one lookup)

Relationships:
- settings.user_id -> users.id (CASCADE DELETE)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create settings table with all constraints and indexes.

    Creates the settings table for managing user trading preferences
    with proper foreign keys, constraints, and indexes.
    """
    # Create settings table
    op.create_table(
        'settings',
        # Primary key
        sa.Column(
            'id',
            sa.Integer(),
            nullable=False,
            primary_key=True,
            autoincrement=True
        ),

        # Foreign key to users (cascade delete, unique for one-to-one)
        sa.Column(
            'user_id',
            sa.Integer(),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
            unique=True,
            comment='User who owns these settings (one-to-one)'
        ),

        # Risk profile enum
        sa.Column(
            'risk_profile',
            sa.String(length=20),
            nullable=False,
            server_default='MODERATE',
            comment='Risk tolerance: CONSERVATIVE, MODERATE, or AGGRESSIVE'
        ),

        # Risk score (0-10 scale with 2 decimal places)
        sa.Column(
            'risk_score',
            sa.Numeric(precision=5, scale=2),
            nullable=False,
            server_default='5.0',
            comment='Numeric risk score from 0 (conservative) to 10 (aggressive)'
        ),

        # Position sizing limits (percentages with 2 decimal places)
        sa.Column(
            'max_position_pct',
            sa.Numeric(precision=5, scale=2),
            nullable=False,
            server_default='10.0',
            comment='Maximum percentage of portfolio for single position (0-100)'
        ),

        sa.Column(
            'max_portfolio_risk_pct',
            sa.Numeric(precision=5, scale=2),
            nullable=False,
            server_default='2.0',
            comment='Maximum portfolio-wide risk percentage (0-100)'
        ),

        # Investment horizon
        sa.Column(
            'investment_horizon_years',
            sa.Integer(),
            nullable=False,
            server_default='5',
            comment='Investment time horizon in years'
        ),

        # Alert preferences (JSON)
        # Use TEXT for SQLite compatibility, PostgreSQL will handle as JSON
        sa.Column(
            'alert_preferences',
            sa.Text(),
            nullable=False,
            server_default='{}',
            comment='JSON configuration for email/SMS/push notifications'
        ),

        # Timestamps (from TimestampMixin)
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('CURRENT_TIMESTAMP'),
            comment='Timestamp when settings were created'
        ),

        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('CURRENT_TIMESTAMP'),
            comment='Timestamp when settings were last updated'
        ),

        # Table-level constraints
        # Unique constraint: one settings per user
        sa.UniqueConstraint(
            'user_id',
            name='uq_settings_user_id'
        ),

        # Check constraints: valid numeric ranges
        sa.CheckConstraint(
            'risk_score >= 0 AND risk_score <= 10',
            name='ck_settings_risk_score_range'
        ),

        sa.CheckConstraint(
            'max_position_pct >= 0 AND max_position_pct <= 100',
            name='ck_settings_max_position_pct_range'
        ),

        sa.CheckConstraint(
            'max_portfolio_risk_pct >= 0 AND max_portfolio_risk_pct <= 100',
            name='ck_settings_max_portfolio_risk_pct_range'
        ),

        sa.CheckConstraint(
            'investment_horizon_years >= 0',
            name='ck_settings_investment_horizon_positive'
        ),
    )

    # Create unique index on user_id for efficient one-to-one lookups
    op.create_index(
        'ix_settings_user_id',
        'settings',
        ['user_id'],
        unique=True
    )


def downgrade() -> None:
    """Drop settings table and all associated indexes and constraints.

    WARNING: This will permanently delete all settings data!
    """
    # Drop index
    op.drop_index('ix_settings_user_id', 'settings')

    # Drop the table (constraints are dropped automatically)
    op.drop_table('settings')
