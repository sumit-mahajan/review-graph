"""Tests for PersistReviewUseCase."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from application.use_cases.persist_review import PersistReviewUseCase
from domain.entities.job import ReviewJob
from domain.services.i_agent_orchestrator import OrchestratorResult
from domain.value_objects.agent_type import AgentType
from domain.value_objects.job_status import JobStatus
from domain.value_objects.review_finding import ReviewFinding
from tests.unit.test_review_persistence import InMemoryReviewRepository


def _make_job() -> ReviewJob:
    now = datetime.now(UTC)
    return ReviewJob(
        id=uuid4(),
        repository_id=uuid4(),
        pr_number=7,
        pr_title="Add auth",
        pr_author="dev",
        pr_url="https://github.com/org/repo/pull/7",
        base_sha="a" * 40,
        head_sha="b" * 40,
        status=JobStatus.RUNNING,
        attempt_count=1,
        retry_after=None,
        error_message=None,
        enqueued_at=now,
        started_at=now,
        completed_at=None,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_persist_review_creates_record() -> None:
    repo = InMemoryReviewRepository()
    use_case = PersistReviewUseCase(repo)
    job = _make_job()

    result = OrchestratorResult(
        job_id=job.id,
        agents_run=[AgentType.SECURITY],
        total_findings=1,
        summary="One security issue found.",
        findings=(
            ReviewFinding(
                severity="high",
                category="security",
                agent_source="security",
                file_path="src/auth.py",
                line_start=10,
                line_end=12,
                title="Missing validation",
                description="User input is not validated.",
                fix_suggestion="Add input validation.",
            ),
        ),
    )

    review = await use_case.execute(job, result)
    assert review.total_findings == 1
    assert review.high_count == 1
    assert review.summary == "One security issue found."
    assert review.findings[0].title == "Missing validation"


@pytest.mark.asyncio
async def test_persist_review_is_idempotent_per_job() -> None:
    repo = InMemoryReviewRepository()
    use_case = PersistReviewUseCase(repo)
    job = _make_job()
    result = OrchestratorResult(
        job_id=job.id,
        agents_run=[],
        total_findings=0,
        summary="Clean",
        findings=(),
    )

    first = await use_case.execute(job, result)
    second = await use_case.execute(job, result)
    assert first.id == second.id
