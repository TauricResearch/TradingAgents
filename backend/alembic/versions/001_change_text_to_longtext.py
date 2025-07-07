"""Change TEXT columns to LONGTEXT for analysis reports

Revision ID: 001
Revises: 
Create Date: 2025-07-07 16:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import LONGTEXT

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Change TEXT columns to LONGTEXT for better capacity."""
    # Change all report columns from TEXT to LONGTEXT
    op.alter_column('analyses', 'market_report',
                    existing_type=sa.TEXT(),
                    type_=LONGTEXT(),
                    existing_nullable=True)
    
    op.alter_column('analyses', 'sentiment_report',
                    existing_type=sa.TEXT(),
                    type_=LONGTEXT(),
                    existing_nullable=True)
    
    op.alter_column('analyses', 'news_report',
                    existing_type=sa.TEXT(),
                    type_=LONGTEXT(),
                    existing_nullable=True)
    
    op.alter_column('analyses', 'fundamentals_report',
                    existing_type=sa.TEXT(),
                    type_=LONGTEXT(),
                    existing_nullable=True)
    
    op.alter_column('analyses', 'trader_investment_plan',
                    existing_type=sa.TEXT(),
                    type_=LONGTEXT(),
                    existing_nullable=True)
    
    op.alter_column('analyses', 'final_trade_decision',
                    existing_type=sa.TEXT(),
                    type_=LONGTEXT(),
                    existing_nullable=True)
    
    op.alter_column('analyses', 'final_report',
                    existing_type=sa.TEXT(),
                    type_=LONGTEXT(),
                    existing_nullable=True)
    
    op.alter_column('analyses', 'error_message',
                    existing_type=sa.TEXT(),
                    type_=LONGTEXT(),
                    existing_nullable=True)


def downgrade() -> None:
    """Revert LONGTEXT columns back to TEXT."""
    # Revert all report columns from LONGTEXT back to TEXT
    op.alter_column('analyses', 'market_report',
                    existing_type=LONGTEXT(),
                    type_=sa.TEXT(),
                    existing_nullable=True)
    
    op.alter_column('analyses', 'sentiment_report',
                    existing_type=LONGTEXT(),
                    type_=sa.TEXT(),
                    existing_nullable=True)
    
    op.alter_column('analyses', 'news_report',
                    existing_type=LONGTEXT(),
                    type_=sa.TEXT(),
                    existing_nullable=True)
    
    op.alter_column('analyses', 'fundamentals_report',
                    existing_type=LONGTEXT(),
                    type_=sa.TEXT(),
                    existing_nullable=True)
    
    op.alter_column('analyses', 'trader_investment_plan',
                    existing_type=LONGTEXT(),
                    type_=sa.TEXT(),
                    existing_nullable=True)
    
    op.alter_column('analyses', 'final_trade_decision',
                    existing_type=LONGTEXT(),
                    type_=sa.TEXT(),
                    existing_nullable=True)
    
    op.alter_column('analyses', 'final_report',
                    existing_type=LONGTEXT(),
                    type_=sa.TEXT(),
                    existing_nullable=True)
    
    op.alter_column('analyses', 'error_message',
                    existing_type=LONGTEXT(),
                    type_=sa.TEXT(),
                    existing_nullable=True)