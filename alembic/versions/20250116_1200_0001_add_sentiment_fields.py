"""Add sentiment fields to news_articles

Revision ID: 20250116_1200_0001_add_sentiment_fields
Revises: 
Create Date: 2025-01-16 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20250116_1200_0001_add_sentiment_fields'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add sentiment confidence and label fields to news_articles table."""
    # Add sentiment_confidence FLOAT column (nullable)
    op.add_column('news_articles', sa.Column('sentiment_confidence', sa.Float(), nullable=True))
    
    # Add sentiment_label VARCHAR(20) column (nullable)
    op.add_column('news_articles', sa.Column('sentiment_label', sa.String(20), nullable=True))
    
    # Create index on sentiment_label for efficient filtering
    op.create_index('idx_news_sentiment_label', 'news_articles', ['sentiment_label'])


def downgrade() -> None:
    """Remove sentiment fields and index from news_articles table."""
    # Drop index first (foreign key dependency order)
    op.drop_index('idx_news_sentiment_label', table_name='news_articles')
    
    # Drop columns
    op.drop_column('news_articles', 'sentiment_label')
    op.drop_column('news_articles', 'sentiment_confidence')