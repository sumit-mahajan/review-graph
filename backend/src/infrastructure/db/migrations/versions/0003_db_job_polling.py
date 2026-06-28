"""Add retry_after to review_jobs and embedding_cleanup_jobs table."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "review_jobs",
        sa.Column("retry_after", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_review_jobs_poll",
        "review_jobs",
        ["status", "retry_after", "enqueued_at"],
    )

    op.create_table(
        "embedding_cleanup_jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "repository_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("head_sha", sa.String(40), nullable=False),
        sa.Column("pr_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retry_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("enqueued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "repository_id",
            "head_sha",
            name="uq_embedding_cleanup_jobs_repo_head",
        ),
    )
    op.create_index(
        "idx_embedding_cleanup_jobs_poll",
        "embedding_cleanup_jobs",
        ["status", "retry_after", "enqueued_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_embedding_cleanup_jobs_poll", table_name="embedding_cleanup_jobs")
    op.drop_table("embedding_cleanup_jobs")
    op.drop_index("idx_review_jobs_poll", table_name="review_jobs")
    op.drop_column("review_jobs", "retry_after")
