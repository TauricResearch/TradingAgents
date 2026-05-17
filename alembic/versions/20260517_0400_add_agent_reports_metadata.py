"""add agent_reports.metadata jsonb

Revision ID: 20260517_0400
Revises: 20260516_2300
Create Date: 2026-05-17

TT-295: per-agent structured-data extraction. After each agent finishes,
a gpt-4o-mini extractor pulls quantitative findings (RSI, P/E, sentiment
score, etc.) into a JSON object stored here. The dashboard renders these
as gauges/sparklines/cards.

Null when extraction fails or no schema is defined for the agent. The
GIN index supports future "filter runs where market_analyst.rsi > 70"
queries via JSONB containment.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "20260517_0400"
down_revision: Union[str, None] = "20260516_2300"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_reports",
        sa.Column("metadata", JSONB(), nullable=True),
    )
    op.create_index(
        "ix_agent_reports_metadata",
        "agent_reports",
        ["metadata"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_agent_reports_metadata", table_name="agent_reports")
    op.drop_column("agent_reports", "metadata")
