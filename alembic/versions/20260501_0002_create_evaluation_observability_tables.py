"""create evaluation observability tables

Revision ID: 20260501_0002
Revises: 20260430_0001
Create Date: 2026-05-01 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260501_0002"
down_revision: Union[str, Sequence[str], None] = "20260430_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    evaluation_run_status = postgresql.ENUM(
        "queued",
        "running",
        "succeeded",
        "failed",
        "cancelled",
        name="evaluation_run_status",
        create_type=False,
    )
    evaluation_run_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "evaluation_rubrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("scope_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("definition_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "version", name="uq_evaluation_rubrics_name_version"),
    )
    op.create_index("ix_evaluation_rubrics_scope_type", "evaluation_rubrics", ["scope_type"], unique=False)
    op.create_index("ix_evaluation_rubrics_status", "evaluation_rubrics", ["status"], unique=False)

    op.create_table(
        "evaluation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evaluation_rubric_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("shadow_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("evaluator_type", sa.String(length=32), nullable=False),
        sa.Column("evaluator_model", sa.String(length=128), nullable=True),
        sa.Column("status", evaluation_run_status, nullable=False),
        sa.Column("trace_id", sa.String(length=128), nullable=True),
        sa.Column("input_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["evaluation_rubric_id"], ["evaluation_rubrics.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["shadow_run_id"], ["shadow_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evaluation_runs_created_at", "evaluation_runs", ["created_at"], unique=False)
    op.create_index("ix_evaluation_runs_shadow_run_id", "evaluation_runs", ["shadow_run_id"], unique=False)
    op.create_index("ix_evaluation_runs_status", "evaluation_runs", ["status"], unique=False)
    op.create_index("ix_evaluation_runs_target", "evaluation_runs", ["target_type", "target_id"], unique=False)

    op.create_table(
        "evaluation_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evaluation_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dimension", sa.String(length=128), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("pass_fail", sa.Boolean(), nullable=False),
        sa.Column("basis", sa.String(length=32), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("evidence_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["evaluation_run_id"], ["evaluation_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("evaluation_run_id", "dimension", name="uq_evaluation_scores_run_dimension"),
    )
    op.create_index("ix_evaluation_scores_basis", "evaluation_scores", ["basis"], unique=False)
    op.create_index("ix_evaluation_scores_dimension", "evaluation_scores", ["dimension"], unique=False)

    op.create_table(
        "human_annotations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("shadow_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("evaluation_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("annotator_actor_type", sa.String(length=32), nullable=False),
        sa.Column("annotator_actor_id", sa.String(length=128), nullable=False),
        sa.Column("annotator_role", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("basis", sa.String(length=32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("evidence_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["evaluation_run_id"], ["evaluation_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["shadow_run_id"], ["shadow_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_human_annotations_evaluation_run_id", "human_annotations", ["evaluation_run_id"], unique=False)
    op.create_index("ix_human_annotations_label", "human_annotations", ["label"], unique=False)
    op.create_index("ix_human_annotations_shadow_run_id", "human_annotations", ["shadow_run_id"], unique=False)
    op.create_index("ix_human_annotations_target", "human_annotations", ["target_type", "target_id"], unique=False)

    op.create_table(
        "evaluation_datasets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("scope_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("selection_rule_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("basis", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_evaluation_datasets_scope_type", "evaluation_datasets", ["scope_type"], unique=False)
    op.create_index("ix_evaluation_datasets_status", "evaluation_datasets", ["status"], unique=False)

    op.create_table(
        "evaluation_dataset_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("shadow_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("evaluation_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("gold_label", sa.String(length=64), nullable=True),
        sa.Column("gold_score", sa.Float(), nullable=True),
        sa.Column("basis", sa.String(length=32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["dataset_id"], ["evaluation_datasets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evaluation_run_id"], ["evaluation_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["shadow_run_id"], ["shadow_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_id", "target_type", "target_id", name="uq_evaluation_dataset_items_target"),
    )
    op.create_index("ix_evaluation_dataset_items_dataset_id", "evaluation_dataset_items", ["dataset_id"], unique=False)
    op.create_index("ix_evaluation_dataset_items_target", "evaluation_dataset_items", ["target_type", "target_id"], unique=False)

    op.create_table(
        "evaluation_queue_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("shadow_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("assigned_actor_type", sa.String(length=32), nullable=True),
        sa.Column("assigned_actor_id", sa.String(length=128), nullable=True),
        sa.Column("assigned_by_actor_type", sa.String(length=32), nullable=True),
        sa.Column("assigned_by_actor_id", sa.String(length=128), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["shadow_run_id"], ["shadow_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("target_type", "target_id", name="uq_evaluation_queue_assignments_target"),
    )
    op.create_index(
        "ix_evaluation_queue_assignments_assignee",
        "evaluation_queue_assignments",
        ["assigned_actor_type", "assigned_actor_id"],
        unique=False,
    )
    op.create_index(
        "ix_evaluation_queue_assignments_shadow_run_id",
        "evaluation_queue_assignments",
        ["shadow_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_evaluation_queue_assignments_shadow_run_id", table_name="evaluation_queue_assignments")
    op.drop_index("ix_evaluation_queue_assignments_assignee", table_name="evaluation_queue_assignments")
    op.drop_table("evaluation_queue_assignments")
    op.drop_index("ix_evaluation_dataset_items_target", table_name="evaluation_dataset_items")
    op.drop_index("ix_evaluation_dataset_items_dataset_id", table_name="evaluation_dataset_items")
    op.drop_table("evaluation_dataset_items")
    op.drop_index("ix_evaluation_datasets_status", table_name="evaluation_datasets")
    op.drop_index("ix_evaluation_datasets_scope_type", table_name="evaluation_datasets")
    op.drop_table("evaluation_datasets")
    op.drop_index("ix_human_annotations_target", table_name="human_annotations")
    op.drop_index("ix_human_annotations_shadow_run_id", table_name="human_annotations")
    op.drop_index("ix_human_annotations_label", table_name="human_annotations")
    op.drop_index("ix_human_annotations_evaluation_run_id", table_name="human_annotations")
    op.drop_table("human_annotations")
    op.drop_index("ix_evaluation_scores_dimension", table_name="evaluation_scores")
    op.drop_index("ix_evaluation_scores_basis", table_name="evaluation_scores")
    op.drop_table("evaluation_scores")
    op.drop_index("ix_evaluation_runs_target", table_name="evaluation_runs")
    op.drop_index("ix_evaluation_runs_status", table_name="evaluation_runs")
    op.drop_index("ix_evaluation_runs_shadow_run_id", table_name="evaluation_runs")
    op.drop_index("ix_evaluation_runs_created_at", table_name="evaluation_runs")
    op.drop_table("evaluation_runs")
    op.drop_index("ix_evaluation_rubrics_status", table_name="evaluation_rubrics")
    op.drop_index("ix_evaluation_rubrics_scope_type", table_name="evaluation_rubrics")
    op.drop_table("evaluation_rubrics")
    sa.Enum(name="evaluation_run_status").drop(op.get_bind(), checkfirst=True)
