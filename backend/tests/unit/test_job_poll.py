from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from domain.repositories.i_job_repository import CreateReviewJobParams
from domain.value_objects.job_poll import MAX_JOB_ATTEMPTS
from domain.value_objects.job_status import JobStatus
from tests.support.memory_repositories import InMemoryJobRepository


@pytest.mark.asyncio
async def test_claim_next_pending_skips_future_retry_after() -> None:
    repo = InMemoryJobRepository()
    await repo.create(
        CreateReviewJobParams(
            repository_id=uuid4(),
            pr_number=1,
            pr_title="t",
            pr_author="a",
            pr_url="u",
            base_sha="a" * 40,
            head_sha="b" * 40,
        )
    )
    job = next(iter(repo._jobs.values()))
    future = datetime.now(UTC) + timedelta(minutes=5)
    await repo.schedule_retry(job.id, retry_after=future, error_message="transient")

    claimed = await repo.claim_next_pending(MAX_JOB_ATTEMPTS)
    assert claimed is None


@pytest.mark.asyncio
async def test_claim_next_pending_picks_eligible_job() -> None:
    repo = InMemoryJobRepository()
    await repo.create(
        CreateReviewJobParams(
            repository_id=uuid4(),
            pr_number=1,
            pr_title="t",
            pr_author="a",
            pr_url="u",
            base_sha="a" * 40,
            head_sha="b" * 40,
        )
    )

    claimed = await repo.claim_next_pending(MAX_JOB_ATTEMPTS)
    assert claimed is not None
    assert claimed.status == JobStatus.RUNNING


@pytest.mark.asyncio
async def test_claim_next_pending_skips_terminal_failed_jobs() -> None:
    repo = InMemoryJobRepository()
    await repo.create(
        CreateReviewJobParams(
            repository_id=uuid4(),
            pr_number=1,
            pr_title="t",
            pr_author="a",
            pr_url="u",
            base_sha="a" * 40,
            head_sha="b" * 40,
        )
    )
    next(iter(repo._jobs.values()))
    for key, stored in list(repo._jobs.items()):
        repo._jobs[key] = type(stored)(
            id=stored.id,
            repository_id=stored.repository_id,
            pr_number=stored.pr_number,
            pr_title=stored.pr_title,
            pr_author=stored.pr_author,
            pr_url=stored.pr_url,
            base_sha=stored.base_sha,
            head_sha=stored.head_sha,
            status=JobStatus.FAILED,
            attempt_count=MAX_JOB_ATTEMPTS,
            retry_after=None,
            error_message="done",
            enqueued_at=stored.enqueued_at,
            started_at=stored.started_at,
            completed_at=datetime.now(UTC),
            created_at=stored.created_at,
            updated_at=stored.updated_at,
        )

    claimed = await repo.claim_next_pending(MAX_JOB_ATTEMPTS)
    assert claimed is None
