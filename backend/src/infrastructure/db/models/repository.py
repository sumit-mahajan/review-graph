import uuid

from sqlalchemy import BigInteger, Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.db.models.base import Base, TimestampMixin


class RepositoryORM(Base, TimestampMixin):
    __tablename__ = "repositories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    github_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    installation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("github_installations.id", ondelete="CASCADE"),
        nullable=False,
    )
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(512), nullable=False)
    default_branch: Mapped[str] = mapped_column(String(255), nullable=False, default="main")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    language: Mapped[str | None] = mapped_column(String(100))
