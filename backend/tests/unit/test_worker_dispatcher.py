"""Tests for WorkerDispatcher — routing and error handling."""

import json
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import pytest

from application.use_cases.cleanup_embeddings import CleanupEmbeddingsUseCase
from application.use_cases.run_review_pipeline import RunReviewPipelineUseCase
from domain.entities.job import ReviewJob
from domain.value_objects.job_status import JobStatus
from infrastructure.ai.stub_orchestrator import StubAgentOrchestrator
from infrastructure.worker.dispatcher import WorkerDispatcher
from tests.support.memory_repositories import (
    InMemoryEmbeddingCleanupRepository,
    InMemoryJobRepository,
)


def _make_dispatcher() -> tuple[
    WorkerDispatcher, InMemoryJobRepository, InMemoryEmbeddingCleanupRepository
]:
    job_repo = InMemoryJobRepository()
    orchestrator = StubAgentOrchestrator()
    run_review = RunReviewPipelineUseCase(job_repo, orchestrator)

    cleanup_repo = InMemoryEmbeddingCleanupRepository()
    cleanup = CleanupEmbeddingsUseCase(cleanup_repo)

    return WorkerDispatcher(run_review, cleanup), job_repo, cleanup_repo


def _make_job(job_repo: InMemoryJobRepository) -> ReviewJob:
    now = datetime.now(UTC)
    job = ReviewJob(
        id=uuid4(),
        repository_id=uuid4(),
        pr_number=5,
        pr_title="t",
        pr_author="dev",
        pr_url="u",
        base_sha="a" * 40,
        head_sha="b" * 40,
        status=JobStatus.PENDING,
        attempt_count=0,
        retry_after=None,
        error_message=None,
        enqueued_at=now,
        started_at=None,
        completed_at=None,
        created_at=now,
        updated_at=now,
    )
    job_repo._jobs[(job.repository_id, job.head_sha)] = job
    return job


@pytest.mark.asyncio
async def test_dispatcher_routes_review_job() -> None:
    dispatcher, job_repo, _ = _make_dispatcher()
    job = _make_job(job_repo)

    payload = json.dumps(
        {
            "job_type": "review",
            "job_id": str(job.id),
            "repository_id": str(job.repository_id),
            "head_sha": job.head_sha,
            "pr_number": job.pr_number,
        }
    )

    result = await dispatcher.dispatch(payload)
    assert result is True

    stored = await job_repo.get_by_id(job.id)
    assert stored is not None
    assert stored.status == JobStatus.COMPLETED


@pytest.mark.asyncio
async def test_dispatcher_routes_cleanup_job() -> None:
    dispatcher, _, cleanup_repo = _make_dispatcher()
    repo_id = uuid4()

    payload = json.dumps(
        {
            "job_type": "embedding_cleanup",
            "job_id": None,
            "repository_id": str(repo_id),
            "head_sha": "c" * 40,
            "pr_number": 7,
        }
    )

    result = await dispatcher.dispatch(payload)
    assert result is True
    assert len(cleanup_repo.deleted_shas) == 1
    assert cleanup_repo.deleted_shas[0] == (repo_id, "c" * 40)


@pytest.mark.asyncio
async def test_dispatcher_acks_invalid_json() -> None:
    dispatcher, _, _ = _make_dispatcher()
    result = await dispatcher.dispatch("not-json{{{")
    assert result is True  # Ack so it doesn't block the queue.


@pytest.mark.asyncio
async def test_dispatcher_acks_unknown_job_type() -> None:
    dispatcher, _, _ = _make_dispatcher()
    payload = json.dumps({"job_type": "does_not_exist"})
    result = await dispatcher.dispatch(payload)
    assert result is True


@pytest.mark.asyncio
async def test_dispatcher_acks_invalid_job_id_uuid() -> None:
    dispatcher, _, _ = _make_dispatcher()
    payload = json.dumps(
        {
            "job_type": "review",
            "job_id": "test",
            "repository_id": str(uuid4()),
            "head_sha": "b" * 40,
            "pr_number": 1,
        }
    )
    result = await dispatcher.dispatch(payload)
    assert result is True


@pytest.mark.asyncio
async def test_dispatcher_backoff_skipped_on_first_attempt() -> None:
    dispatcher, job_repo, _ = _make_dispatcher()
    job = _make_job(job_repo)

    payload = json.dumps(
        {
            "job_type": "review",
            "job_id": str(job.id),
            "repository_id": str(job.repository_id),
            "head_sha": job.head_sha,
            "pr_number": job.pr_number,
            "attempt": 0,  # first attempt — no sleep
        }
    )

    with patch("infrastructure.worker.dispatcher.asyncio.sleep") as mock_sleep:
        await dispatcher.dispatch(payload)
        mock_sleep.assert_not_awaited()
