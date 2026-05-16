"""initial — runs, decisions, agent_reports

Revision ID: 20260516_2300
Revises:
Create Date: 2026-05-16

Creates the Python-owned half of the shared Lyceum Fund database. The
Prisma-owned half (User, Role, App, etc.) is untouched — Alembic's
include_name filter in env.py keeps autogenerate blind to it.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260516_2300"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "runs",
        sa.Column("id",           sa.String(), nullable=False),
        sa.Column("user_id",      sa.String(), nullable=False),
        sa.Column("ticker",       sa.String(), nullable=False),
        sa.Column("trade_date",   sa.String(), nullable=False),
        sa.Column("status",       sa.String(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("created_at",   sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_runs_user_id_created_at", "runs", ["user_id", "created_at"])
    op.create_index("ix_runs_status",             "runs", ["status"])

    op.create_table(
        "decisions",
        sa.Column("id",         sa.String(), nullable=False),
        sa.Column("run_id",     sa.String(), nullable=False),
        sa.Column("decision",   sa.String(), nullable=False),
        sa.Column("rationale",  sa.Text(),   nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_decisions_run_id", "decisions", ["run_id"])

    op.create_table(
        "agent_reports",
        sa.Column("id",         sa.String(), nullable=False),
        sa.Column("run_id",     sa.String(), nullable=False),
        sa.Column("agent_name", sa.String(), nullable=False),
        sa.Column("content",    sa.Text(),   nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_agent_reports_run_id",       "agent_reports", ["run_id"])
    op.create_index("ix_agent_reports_run_id_agent", "agent_reports", ["run_id", "agent_name"])


def downgrade() -> None:
    op.drop_index("ix_agent_reports_run_id_agent", table_name="agent_reports")
    op.drop_index("ix_agent_reports_run_id",       table_name="agent_reports")
    op.drop_table("agent_reports")

    op.drop_index("ix_decisions_run_id", table_name="decisions")
    op.drop_table("decisions")

    op.drop_index("ix_runs_status",             table_name="runs")
    op.drop_index("ix_runs_user_id_created_at", table_name="runs")
    op.drop_table("runs")
