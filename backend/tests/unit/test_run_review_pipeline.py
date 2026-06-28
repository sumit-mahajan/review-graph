"""Tests for RunReviewPipelineUseCase — job lifecycle and retry logic."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from application.use_cases.persist_review import PersistReviewUseCase
from application.use_cases.post_review_to_github import PostReviewToGithubUseCase
from application.use_cases.run_review_pipeline import MAX_ATTEMPTS, RunReviewPipelineUseCase
from domain.entities.job import ReviewJob
from domain.entities.review import Review
from domain.services.i_agent_orchestrator import OrchestratorResult
from domain.value_objects.job_status import JobStatus
from tests.support.memory_repositories import InMemoryJobRepository
from tests.unit.test_review_persistence import InMemoryReviewRepository


def _make_job(attempt_count: int = 0, status: JobStatus = JobStatus.PENDING) -> ReviewJob:
    now = datetime.now(UTC)
    return ReviewJob(
        id=uuid4(),
        repository_id=uuid4(),
        pr_number=1,
        pr_title="Test PR",
        pr_author="dev",
        pr_url="https://github.com/org/repo/pull/1",
        base_sha="a" * 40,
        head_sha="b" * 40,
        status=status,
        attempt_count=attempt_count,
        retry_after=None,
        error_message=None,
        enqueued_at=now,
        started_at=None,
        completed_at=None,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_pipeline_completes_successfully() -> None:
    job = _make_job()
    repo = InMemoryJobRepository()
    repo._jobs[(job.repository_id, job.head_sha)] = job

    orchestrator = AsyncMock()
    orchestrator.run.return_value = OrchestratorResult(
        job_id=job.id, agents_run=[], total_findings=3
    )

    use_case = RunReviewPipelineUseCase(repo, orchestrator)
    result = await use_case.execute(job.id)

    assert result is True
    stored = await repo.get_by_id(job.id)
    assert stored is not None
    assert stored.status == JobStatus.COMPLETED
    assert stored.attempt_count == 1


@pytest.mark.asyncio
async def test_pipeline_schedules_retry_on_first_failure() -> None:
    job = _make_job()
    repo = InMemoryJobRepository()
    repo._jobs[(job.repository_id, job.head_sha)] = job

    orchestrator = AsyncMock()
    orchestrator.run.side_effect = RuntimeError("Gemini unavailable")

    use_case = RunReviewPipelineUseCase(repo, orchestrator)
    result = await use_case.execute(job.id)

    assert result is True
    stored = await repo.get_by_id(job.id)
    assert stored is not None
    assert stored.status == JobStatus.PENDING
    assert stored.retry_after is not None
    assert stored.error_message is not None
    assert "Gemini unavailable" in stored.error_message
    assert stored.attempt_count == 1


@pytest.mark.asyncio
async def test_pipeline_marks_failed_after_max_attempts() -> None:
    job = _make_job(attempt_count=2)
    repo = InMemoryJobRepository()
    repo._jobs[(job.repository_id, job.head_sha)] = job

    orchestrator = AsyncMock()
    orchestrator.run.side_effect = RuntimeError("Gemini unavailable")

    use_case = RunReviewPipelineUseCase(repo, orchestrator)
    result = await use_case.execute(job.id)

    assert result is True
    stored = await repo.get_by_id(job.id)
    assert stored is not None
    assert stored.status == JobStatus.FAILED
    assert stored.attempt_count == 3


@pytest.mark.asyncio
async def test_pipeline_acks_queue_when_job_at_max_attempts() -> None:
    """Terminal jobs must return True so Redis messages are not poison pills."""
    job = _make_job(attempt_count=MAX_ATTEMPTS, status=JobStatus.FAILED)
    job.error_message = "Gemini unavailable"
    repo = InMemoryJobRepository()
    repo._jobs[(job.repository_id, job.head_sha)] = job

    orchestrator = AsyncMock()
    use_case = RunReviewPipelineUseCase(repo, orchestrator)

    result = await use_case.execute(job.id)
    assert result is True
    orchestrator.run.assert_not_awaited()


@pytest.mark.asyncio
async def test_pipeline_returns_true_for_unknown_job() -> None:
    """Worker should ack an unknown job rather than crash."""
    repo = InMemoryJobRepository()
    orchestrator = AsyncMock()
    use_case = RunReviewPipelineUseCase(repo, orchestrator)

    result = await use_case.execute(uuid4())
    assert result is True
    orchestrator.run.assert_not_awaited()


@pytest.mark.asyncio
async def test_pipeline_skips_orchestrator_when_review_already_posted() -> None:
    job = _make_job()
    job_repo = InMemoryJobRepository()
    job_repo._jobs[(job.repository_id, job.head_sha)] = job

    review_repo = InMemoryReviewRepository()
    review_repo._reviews[job.id] = Review(
        id=uuid4(),
        job_id=job.id,
        repository_id=job.repository_id,
        pr_number=job.pr_number,
        head_sha=job.head_sha,
        pr_url=job.pr_url,
        summary="done",
        total_findings=0,
        critical_count=0,
        high_count=0,
        medium_count=0,
        low_count=0,
        info_count=0,
        agents_run=[],
        langfuse_trace_id=None,
        posted_to_github=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        findings=[],
    )

    orchestrator = AsyncMock()
    persist = PersistReviewUseCase(review_repo)
    use_case = RunReviewPipelineUseCase(job_repo, orchestrator, persist_review=persist)

    result = await use_case.execute(job.id)
    assert result is True
    orchestrator.run.assert_not_awaited()
    stored = await job_repo.get_by_id(job.id)
    assert stored is not None
    assert stored.status == JobStatus.COMPLETED


@pytest.mark.asyncio
async def test_pipeline_persists_and_posts_after_orchestrator() -> None:
    job = _make_job()
    job_repo = InMemoryJobRepository()
    job_repo._jobs[(job.repository_id, job.head_sha)] = job

    orchestrator = AsyncMock()
    orchestrator.run.return_value = OrchestratorResult(
        job_id=job.id,
        agents_run=[],
        total_findings=0,
        summary="All good",
        findings=(),
    )

    review_repo = InMemoryReviewRepository()
    persist = PersistReviewUseCase(review_repo)
    post = AsyncMock(spec=PostReviewToGithubUseCase)
    post.execute = AsyncMock(side_effect=lambda review: review)

    use_case = RunReviewPipelineUseCase(
        job_repo,
        orchestrator,
        persist_review=persist,
        post_to_github=post,  # type: ignore[arg-type]
    )
    result = await use_case.execute(job.id)

    assert result is True
    orchestrator.run.assert_awaited_once()
    post.execute.assert_awaited_once()
