"""
WorkerDispatcher — routes dequeued messages to the correct use case.

Called by the worker main loop for each message popped from Redis.
Pure dispatch logic; no queue concerns here.
"""
import asyncio
import json
from uuid import UUID

import structlog

from application.use_cases.cleanup_embeddings import CleanupEmbeddingsUseCase
from application.use_cases.run_review_pipeline import RunReviewPipelineUseCase
from domain.value_objects.job_type import JobType

logger = structlog.get_logger()

# Exponential backoff delays in seconds for failed review jobs: 2s, 8s, 32s
BACKOFF_DELAYS = [2, 8, 32]


def _parse_uuid(value: object, *, field: str) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(str(value))
    except ValueError:
        return None


class WorkerDispatcher:
    def __init__(
        self,
        run_review: RunReviewPipelineUseCase,
        cleanup_embeddings: CleanupEmbeddingsUseCase,
    ) -> None:
        self._run_review = run_review
        self._cleanup = cleanup_embeddings

    async def dispatch(self, raw_payload: str) -> bool:
        """Parse and dispatch a single queue message.

        Returns True to acknowledge (remove from queue), False to requeue.
        """
        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError:
            await logger.aerror("worker_invalid_payload", raw=raw_payload[:200])
            return True  # Ack malformed messages; they will never succeed.

        job_type_raw = payload.get("job_type", "")
        try:
            job_type = JobType(job_type_raw)
        except ValueError:
            await logger.aerror("worker_unknown_job_type", job_type=job_type_raw)
            return True

        if job_type == JobType.REVIEW:
            return await self._dispatch_review(payload)

        if job_type == JobType.EMBEDDING_CLEANUP:
            return await self._dispatch_cleanup(payload)

        await logger.awarning("worker_unhandled_job_type", job_type=job_type_raw)
        return True

    async def _dispatch_review(self, payload: dict[str, object]) -> bool:
        job_id_raw = payload.get("job_id")
        if not job_id_raw:
            await logger.aerror("worker_review_missing_job_id")
            return True

        job_id = _parse_uuid(job_id_raw, field="job_id")
        if job_id is None:
            await logger.aerror("worker_review_invalid_job_id", job_id=job_id_raw)
            return True
        attempt = int(payload.get("attempt", 0))

        # Backoff before retry (skip on first attempt)
        if attempt > 0 and attempt <= len(BACKOFF_DELAYS):
            delay = BACKOFF_DELAYS[attempt - 1]
            await logger.ainfo("worker_backoff", job_id=str(job_id), delay=delay, attempt=attempt)
            await asyncio.sleep(delay)

        completed = await self._run_review.execute(job_id)
        return completed

    async def _dispatch_cleanup(self, payload: dict[str, object]) -> bool:
        repo_id_raw = payload.get("repository_id")
        head_sha = str(payload.get("head_sha", ""))

        if not repo_id_raw or not head_sha:
            await logger.aerror("worker_cleanup_missing_fields", payload=payload)
            return True

        repository_id = _parse_uuid(repo_id_raw, field="repository_id")
        if repository_id is None:
            await logger.aerror("worker_cleanup_invalid_repository_id", repository_id=repo_id_raw)
            return True
        await self._cleanup.cleanup_for_pr(repository_id, head_sha)
        return True
