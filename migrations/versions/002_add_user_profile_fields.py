"""Add user profile fields - tax_jurisdiction, timezone, api_key_hash, is_verified

Revision ID: 002
Revises: 001
Create Date: 2025-12-26 13:00:00.000000

This migration adds four new fields to the users table:
- tax_jurisdiction: Tax jurisdiction code (default: AU)
- timezone: IANA timezone identifier (default: Australia/Sydney)
- api_key_hash: Bcrypt hash of API key for programmatic access (nullable)
- is_verified: Email verification status (default: False)

All existing users will get default values for the new required fields.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add tax_jurisdiction, timezone, api_key_hash, and is_verified columns to users table.

    For existing rows:
    - tax_jurisdiction defaults to "AU"
    - timezone defaults to "Australia/Sydney"
    - api_key_hash is NULL
    - is_verified is False
    """
    # Add tax_jurisdiction column
    op.add_column(
        'users',
        sa.Column(
            'tax_jurisdiction',
            sa.String(length=10),
            nullable=False,
            server_default='AU',
            comment='Tax jurisdiction code (e.g., US, US-CA, AU-NSW)'
        )
    )

    # Add timezone column
    op.add_column(
        'users',
        sa.Column(
            'timezone',
            sa.String(length=50),
            nullable=False,
            server_default='Australia/Sydney',
            comment='IANA timezone identifier (e.g., America/New_York, UTC)'
        )
    )

    # Add api_key_hash column with unique constraint and index
    op.add_column(
        'users',
        sa.Column(
            'api_key_hash',
            sa.String(length=255),
            nullable=True,
            comment='Bcrypt hash of API key for programmatic access'
        )
    )
    # Create unique constraint for api_key_hash
    op.create_unique_constraint(
        'uq_users_api_key_hash',
        'users',
        ['api_key_hash']
    )
    # Create index for fast lookups
    op.create_index(
        'ix_users_api_key_hash',
        'users',
        ['api_key_hash'],
        unique=False
    )

    # Add is_verified column
    op.add_column(
        'users',
        sa.Column(
            'is_verified',
            sa.Boolean(),
            nullable=False,
            server_default='0',
            comment='Whether user email has been verified'
        )
    )


def downgrade() -> None:
    """Remove tax_jurisdiction, timezone, api_key_hash, and is_verified columns from users table.

    WARNING: This will permanently delete data in these columns!
    """
    # Remove is_verified column
    op.drop_column('users', 'is_verified')

    # Remove api_key_hash column (drop index and constraint first)
    op.drop_index('ix_users_api_key_hash', 'users')
    op.drop_constraint('uq_users_api_key_hash', 'users', type_='unique')
    op.drop_column('users', 'api_key_hash')

    # Remove timezone column
    op.drop_column('users', 'timezone')

    # Remove tax_jurisdiction column
    op.drop_column('users', 'tax_jurisdiction')
