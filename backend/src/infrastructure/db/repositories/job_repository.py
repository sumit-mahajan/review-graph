from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.job import ReviewJob
from domain.errors import EntityNotFoundError
from domain.repositories.i_job_repository import CreateReviewJobParams, IJobRepository
from domain.value_objects.job_status import JobStatus
from infrastructure.db.models.review_job import ReviewJobORM
from infrastructure.db.repositories.job_poll_helpers import (
    claim_next_pending_job,
    release_stale_running_jobs,
)
from infrastructure.db.repositories.mappers import to_job_entity


class PostgresJobRepository(IJobRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_repo_and_head_sha(
        self, repository_id: UUID, head_sha: str
    ) -> ReviewJob | None:
        result = await self._session.execute(
            select(ReviewJobORM).where(
                ReviewJobORM.repository_id == repository_id,
                ReviewJobORM.head_sha == head_sha,
            )
        )
        orm = result.scalar_one_or_none()
        return to_job_entity(orm) if orm else None

    async def create(self, params: CreateReviewJobParams) -> ReviewJob:
        now = datetime.now(UTC)
        orm = ReviewJobORM(
            repository_id=params.repository_id,
            pr_number=params.pr_number,
            pr_title=params.pr_title,
            pr_author=params.pr_author,
            pr_url=params.pr_url,
            base_sha=params.base_sha,
            head_sha=params.head_sha,
            status=JobStatus.PENDING.value,
            attempt_count=0,
            enqueued_at=now,
        )
        self._session.add(orm)
        await self._session.commit()
        await self._session.refresh(orm)
        return to_job_entity(orm)

    async def get_by_id(self, job_id: UUID) -> ReviewJob | None:
        orm = await self._session.get(ReviewJobORM, job_id)
        return to_job_entity(orm) if orm else None

    async def update_attempt_count(self, job_id: UUID, attempt_count: int) -> ReviewJob:
        orm = await self._session.get(ReviewJobORM, job_id)
        if orm is None:
            raise EntityNotFoundError(f"Review job {job_id} not found")
        orm.attempt_count = attempt_count
        await self._session.commit()
        await self._session.refresh(orm)
        return to_job_entity(orm)

    async def update_status(
        self,
        job_id: UUID,
        status: JobStatus,
        *,
        error_message: str | None = None,
    ) -> ReviewJob:
        orm = await self._session.get(ReviewJobORM, job_id)
        if orm is None:
            raise EntityNotFoundError(f"Review job {job_id} not found")

        orm.status = status.value
        orm.error_message = error_message
        if status == JobStatus.RUNNING and orm.started_at is None:
            orm.started_at = datetime.now(UTC)
        if status in {JobStatus.COMPLETED, JobStatus.FAILED}:
            orm.completed_at = datetime.now(UTC)

        await self._session.commit()
        await self._session.refresh(orm)
        return to_job_entity(orm)

    async def claim_next_pending(self, max_attempts: int) -> ReviewJob | None:
        orm = await claim_next_pending_job(self._session, ReviewJobORM, max_attempts=max_attempts)
        return to_job_entity(orm) if orm is not None else None  # type: ignore[arg-type]

    async def release_stale_running(self, stale_minutes: int, max_attempts: int) -> int:
        return await release_stale_running_jobs(
            self._session,
            ReviewJobORM,
            stale_minutes=stale_minutes,
            max_attempts=max_attempts,
        )

    async def schedule_retry(
        self,
        job_id: UUID,
        *,
        retry_after: datetime,
        error_message: str,
    ) -> ReviewJob:
        orm = await self._session.get(ReviewJobORM, job_id)
        if orm is None:
            raise EntityNotFoundError(f"Review job {job_id} not found")
        orm.status = JobStatus.PENDING.value
        orm.retry_after = retry_after
        orm.error_message = error_message
        orm.started_at = None
        orm.completed_at = None
        await self._session.commit()
        await self._session.refresh(orm)
        return to_job_entity(orm)
