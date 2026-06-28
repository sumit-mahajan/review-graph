"""Initial schema — all tables

Revision ID: 0001
Revises:
Create Date: 2026-06-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Enable pgvector extension (required for VECTOR column in code_embeddings)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "github_installations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("installation_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("account_login", sa.String(255), nullable=False),
        sa.Column("account_type", sa.String(50), nullable=False),
        sa.Column("account_avatar_url", sa.String(512), nullable=True),
        sa.Column("access_token_encrypted", sa.Text(), nullable=True),
        sa.Column("access_token_expires_at", sa.DateTime(timezone=True), nullable=True),
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
    )

    op.create_table(
        "repositories",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("github_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column(
            "installation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("github_installations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("owner", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(512), nullable=False),
        sa.Column("default_branch", sa.String(255), nullable=False, server_default="main"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("language", sa.String(100), nullable=True),
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
    )

    op.create_table(
        "agent_configs",
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
            unique=True,
        ),
        sa.Column("security_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("perf_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("arch_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("test_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("min_severity", sa.String(50), nullable=False, server_default="medium"),
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
    )

    op.create_table(
        "review_jobs",
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
        sa.Column("pr_number", sa.Integer(), nullable=False),
        sa.Column("pr_title", sa.String(512), nullable=False),
        sa.Column("pr_author", sa.String(255), nullable=False),
        sa.Column("pr_url", sa.String(512), nullable=False),
        sa.Column("base_sha", sa.String(40), nullable=False),
        sa.Column("head_sha", sa.String(40), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
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
        sa.UniqueConstraint("repository_id", "head_sha", name="uq_review_jobs_repo_head"),
    )

    op.create_table(
        "reviews",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("review_jobs.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "repository_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("pr_number", sa.Integer(), nullable=False),
        sa.Column("head_sha", sa.String(40), nullable=False),
        sa.Column("pr_url", sa.String(512), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("total_findings", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("critical_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("high_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("medium_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("low_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("info_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "agents_run", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("langfuse_trace_id", sa.String(255), nullable=True),
        sa.Column("posted_to_github", sa.Boolean(), nullable=False, server_default="false"),
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
    )

    op.create_table(
        "findings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "review_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("reviews.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("severity", sa.String(50), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("agent_source", sa.String(50), nullable=False),
        sa.Column("file_path", sa.String(512), nullable=False),
        sa.Column("line_start", sa.Integer(), nullable=True),
        sa.Column("line_end", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("fix_suggestion", sa.Text(), nullable=True),
        sa.Column("github_comment_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "code_embeddings",
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
        sa.Column("commit_sha", sa.String(40), nullable=False),
        sa.Column("file_path", sa.String(512), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", sa.Text(), nullable=True),  # VECTOR(768) applied below
        sa.Column("node_type", sa.String(100), nullable=True),
        sa.Column("node_name", sa.String(255), nullable=True),
        sa.Column("language", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "repository_id",
            "commit_sha",
            "file_path",
            "chunk_index",
            name="uq_code_embeddings_repo_sha_file_chunk",
        ),
    )

    # Convert embedding column to VECTOR(768) now that pgvector is enabled
    op.execute(
        "ALTER TABLE code_embeddings ALTER COLUMN embedding TYPE vector(768) USING NULL::vector(768)"
    )

    # Indexes
    op.create_index("idx_review_jobs_repo", "review_jobs", ["repository_id"])
    op.create_index("idx_review_jobs_status", "review_jobs", ["status"])
    op.create_index("idx_reviews_repo", "reviews", ["repository_id"])
    op.create_index("idx_reviews_pr", "reviews", ["repository_id", "pr_number"])
    op.create_index("idx_findings_review", "findings", ["review_id"])
    op.create_index("idx_findings_severity", "findings", ["severity"])
    op.create_index("idx_embeddings_repo", "code_embeddings", ["repository_id", "commit_sha"])
    op.execute(
        "CREATE INDEX idx_embeddings_vector ON code_embeddings "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )


def downgrade() -> None:
    op.drop_table("code_embeddings")
    op.drop_table("findings")
    op.drop_table("reviews")
    op.drop_table("review_jobs")
    op.drop_table("agent_configs")
    op.drop_table("repositories")
    op.drop_table("github_installations")
    op.execute("DROP EXTENSION IF EXISTS vector")
