import uuid

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.db.models.base import Base, TimestampMixin


class CodeEmbeddingORM(Base, TimestampMixin):
    __tablename__ = "code_embeddings"
    __table_args__ = (
        UniqueConstraint(
            "repository_id",
            "commit_sha",
            "file_path",
            "chunk_index",
            name="uq_code_embeddings_repo_sha_file_chunk",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
    )
    commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    # embedding column added via Alembic migration with pgvector extension
    node_type: Mapped[str | None] = mapped_column(String(100))
    node_name: Mapped[str | None] = mapped_column(String(255))
    language: Mapped[str | None] = mapped_column(String(100))
