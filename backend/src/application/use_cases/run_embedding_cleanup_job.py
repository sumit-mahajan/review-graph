"""
RunEmbeddingCleanupJobUseCase — deletes pgvector rows for a closed PR job row.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog

from application.use_cases.cleanup_embeddings import CleanupEmbeddingsUseCase
from domain.repositories.i_embedding_cleanup_job_repository import IEmbeddingCleanupJobRepository
from domain.value_objects.job_poll import MAX_JOB_ATTEMPTS, RETRY_BACKOFF_SECONDS
from domain.value_objects.job_status import JobStatus

logger = structlog.get_logger()


class RunEmbeddingCleanupJobUseCase:
    def __init__(
        self,
        job_repo: IEmbeddingCleanupJobRepository,
        cleanup: CleanupEmbeddingsUseCase,
    ) -> None:
        self._job_repo = job_repo
        self._cleanup = cleanup

    async def execute(self, job_id: UUID) -> None:
        job = await self._job_repo.get_by_id(job_id)
        if job is None:
            await logger.awarning("cleanup_job_not_found", job_id=str(job_id))
            return

        log = logger.bind(job_id=str(job_id), head_sha=job.head_sha, attempt=job.attempt_count + 1)

        if job.attempt_count >= MAX_JOB_ATTEMPTS:
            await log.awarning("cleanup_job_max_attempts_exceeded")
            return

        await self._job_repo.update_attempt_count(job_id, job.attempt_count + 1)
        await self._job_repo.update_status(job_id, JobStatus.RUNNING)
        await log.ainfo("cleanup_job_started")

        try:
            await self._cleanup.cleanup_for_pr(job.repository_id, job.head_sha)
            await self._job_repo.update_status(job_id, JobStatus.COMPLETED)
            await log.ainfo("cleanup_job_completed")
        except Exception as exc:  # noqa: BLE001
            error_msg = f"{type(exc).__name__}: {exc}"
            updated = await self._job_repo.get_by_id(job_id)
            if updated is not None and updated.attempt_count >= MAX_JOB_ATTEMPTS:
                await self._job_repo.update_status(
                    job_id, JobStatus.FAILED, error_message=error_msg
                )
            elif updated is not None:
                delay_index = min(updated.attempt_count - 1, len(RETRY_BACKOFF_SECONDS) - 1)
                retry_after = datetime.now(UTC) + timedelta(
                    seconds=RETRY_BACKOFF_SECONDS[delay_index]
                )
                await self._job_repo.schedule_retry(
                    job_id, retry_after=retry_after, error_message=error_msg
                )
            await log.aerror("cleanup_job_failed", error=error_msg)
