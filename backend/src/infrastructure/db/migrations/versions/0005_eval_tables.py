"""Add eval_runs and eval_results tables for F-08 evaluation system."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "eval_runs",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("model_id", sa.String(100), nullable=False),
        sa.Column("total_prs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errored_prs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("overall_precision", sa.Float(), nullable=False, server_default="0"),
        sa.Column("overall_recall", sa.Float(), nullable=False, server_default="0"),
        sa.Column("overall_f1", sa.Float(), nullable=False, server_default="0"),
        sa.Column("false_positive_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("routing_accuracy", sa.Float(), nullable=False, server_default="0"),
        sa.Column("per_category", JSONB(), nullable=False, server_default="{}"),
        sa.Column("notes", sa.String(512), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "eval_results",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("golden_id", sa.String(100), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("expected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("true_positives", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("false_positives", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("false_negatives", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("routed_correctly", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["run_id"], ["eval_runs.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_eval_results_run", "eval_results", ["run_id"])


def downgrade() -> None:
    op.drop_index("idx_eval_results_run", table_name="eval_results")
    op.drop_table("eval_results")
    op.drop_table("eval_runs")
