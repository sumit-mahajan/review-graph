import uuid

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.db.models.base import Base, TimestampMixin


class AgentConfigORM(Base, TimestampMixin):
    __tablename__ = "agent_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    security_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    perf_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    arch_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    test_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    min_severity: Mapped[str] = mapped_column(String(50), nullable=False, default="medium")
