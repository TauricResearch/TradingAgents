"""create shadow run precedents

Revision ID: 20260505_0003
Revises: 20260501_0002
Create Date: 2026-05-05 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260505_0003"
down_revision: Union[str, Sequence[str], None] = "20260501_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shadow_run_precedents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticker", sa.String(length=32), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("selected_analysts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("embedding_model", sa.String(length=64), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("embedding_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["shadow_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id"),
    )
    op.create_index(
        "ix_shadow_run_precedents_ticker_trade_date",
        "shadow_run_precedents",
        ["ticker", "trade_date"],
        unique=False,
    )
    op.create_index(
        "ix_shadow_run_precedents_provider_model",
        "shadow_run_precedents",
        ["provider", "model"],
        unique=False,
    )
    op.create_index(
        "ix_shadow_run_precedents_content_hash",
        "shadow_run_precedents",
        ["content_hash"],
        unique=False,
    )
    op.create_index(
        "ix_shadow_run_precedents_selected_analysts",
        "shadow_run_precedents",
        ["selected_analysts"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_shadow_run_precedents_selected_analysts", table_name="shadow_run_precedents")
    op.drop_index("ix_shadow_run_precedents_content_hash", table_name="shadow_run_precedents")
    op.drop_index("ix_shadow_run_precedents_provider_model", table_name="shadow_run_precedents")
    op.drop_index("ix_shadow_run_precedents_ticker_trade_date", table_name="shadow_run_precedents")
    op.drop_table("shadow_run_precedents")
