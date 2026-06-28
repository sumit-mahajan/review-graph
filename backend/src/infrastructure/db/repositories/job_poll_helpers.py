"""Shared SQLAlchemy helpers for DB job polling."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import or_, select, update

from domain.value_objects.job_status import JobStatus

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import DeclarativeBase


async def claim_next_pending_job(
    session: AsyncSession,
    orm_model: type[DeclarativeBase],
    *,
    max_attempts: int,
) -> object | None:
    """Claim the oldest pending job row using FOR UPDATE SKIP LOCKED."""
    now = datetime.now(UTC)
    result = await session.execute(
        select(orm_model)
        .where(
            orm_model.status == JobStatus.PENDING.value,  # type: ignore[attr-defined]
            orm_model.attempt_count < max_attempts,  # type: ignore[attr-defined]
            or_(
                orm_model.retry_after.is_(None),  # type: ignore[attr-defined]
                orm_model.retry_after <= now,  # type: ignore[attr-defined]
            ),
        )
        .order_by(orm_model.enqueued_at)  # type: ignore[attr-defined]
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    orm = result.scalar_one_or_none()
    if orm is None:
        return None

    orm.status = JobStatus.RUNNING.value  # type: ignore[attr-defined]
    orm.started_at = now  # type: ignore[attr-defined]
    await session.commit()
    await session.refresh(orm)
    return orm


async def release_stale_running_jobs(
    session: AsyncSession,
    orm_model: type[DeclarativeBase],
    *,
    stale_minutes: int,
    max_attempts: int,
) -> int:
    """Reset running jobs stuck longer than stale_minutes back to pending."""
    cutoff = datetime.now(UTC) - timedelta(minutes=stale_minutes)
    result = await session.execute(
        update(orm_model)
        .where(
            orm_model.status == JobStatus.RUNNING.value,  # type: ignore[attr-defined]
            orm_model.started_at.is_not(None),  # type: ignore[attr-defined]
            orm_model.started_at < cutoff,  # type: ignore[attr-defined]
            orm_model.attempt_count < max_attempts,  # type: ignore[attr-defined]
        )
        .values(status=JobStatus.PENDING.value, started_at=None)
    )
    await session.commit()
    return int(getattr(result, "rowcount", 0) or 0)
