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

Uses batch mode for SQLite compatibility.
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

    Uses batch mode for SQLite compatibility with constraints.
    """
    # Use batch_alter_table for SQLite compatibility
    with op.batch_alter_table('users', schema=None) as batch_op:
        # Add tax_jurisdiction column
        batch_op.add_column(
            sa.Column(
                'tax_jurisdiction',
                sa.String(length=10),
                nullable=False,
                server_default='AU',
            )
        )

        # Add timezone column
        batch_op.add_column(
            sa.Column(
                'timezone',
                sa.String(length=50),
                nullable=False,
                server_default='Australia/Sydney',
            )
        )

        # Add api_key_hash column
        batch_op.add_column(
            sa.Column(
                'api_key_hash',
                sa.String(length=255),
                nullable=True,
            )
        )

        # Add is_verified column
        batch_op.add_column(
            sa.Column(
                'is_verified',
                sa.Boolean(),
                nullable=False,
                server_default='0',
            )
        )

        # Create unique constraint for api_key_hash
        batch_op.create_unique_constraint(
            'uq_users_api_key_hash',
            ['api_key_hash']
        )

    # Create index for fast lookups (can be done outside batch)
    op.create_index(
        'ix_users_api_key_hash',
        'users',
        ['api_key_hash'],
        unique=False
    )


def downgrade() -> None:
    """Remove tax_jurisdiction, timezone, api_key_hash, and is_verified columns from users table.

    WARNING: This will permanently delete data in these columns!

    Uses batch mode for SQLite compatibility.
    """
    # Drop index first (outside batch)
    op.drop_index('ix_users_api_key_hash', 'users')

    # Use batch_alter_table for SQLite compatibility
    with op.batch_alter_table('users', schema=None) as batch_op:
        # Drop unique constraint
        batch_op.drop_constraint('uq_users_api_key_hash', type_='unique')

        # Remove columns
        batch_op.drop_column('is_verified')
        batch_op.drop_column('api_key_hash')
        batch_op.drop_column('timezone')
        batch_op.drop_column('tax_jurisdiction')
