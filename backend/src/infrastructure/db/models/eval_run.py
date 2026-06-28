import uuid

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.db.models.base import Base, TimestampMixin


class EvalRunORM(Base, TimestampMixin):
    """One execution of the golden-set evaluation (F-08)."""

    __tablename__ = "eval_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id: Mapped[str] = mapped_column(String(100), nullable=False)
    total_prs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errored_prs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    overall_precision: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    overall_recall: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    overall_f1: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    false_positive_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    routing_accuracy: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # Per-category {category: {tp, fp, fn, precision, recall, f1}}
    per_category: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    notes: Mapped[str | None] = mapped_column(String(512))


class EvalResultORM(Base, TimestampMixin):
    """Per golden-PR score within an eval run (F-08)."""

    __tablename__ = "eval_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("eval_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    golden_id: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    expected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    true_positives: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    false_positives: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    false_negatives: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    routed_correctly: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
