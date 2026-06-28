"""Add content_hash to code_embeddings for cross-SHA deduplication."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "code_embeddings",
        sa.Column("content_hash", sa.String(64), nullable=True),
    )
    op.create_index(
        "idx_embeddings_content_hash",
        "code_embeddings",
        ["repository_id", "file_path", "content_hash"],
    )


def downgrade() -> None:
    op.drop_index("idx_embeddings_content_hash", table_name="code_embeddings")
    op.drop_column("code_embeddings", "content_hash")
