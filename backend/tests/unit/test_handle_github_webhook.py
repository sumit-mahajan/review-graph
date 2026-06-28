import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from application.use_cases.handle_github_webhook import HandleGithubWebhookUseCase
from domain.entities.job import ReviewJob
from domain.entities.repository import Repository
from domain.value_objects.job_status import JobStatus

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _repo() -> Repository:
    now = datetime.now(UTC)
    return Repository(
        id=uuid4(),
        github_id=987654321,
        installation_id=uuid4(),
        owner="acme-corp",
        name="backend",
        full_name="acme-corp/backend",
        default_branch="main",
        is_active=True,
        language="Python",
        created_at=now,
        updated_at=now,
    )


def _job(repo: Repository) -> ReviewJob:
    now = datetime.now(UTC)
    return ReviewJob(
        id=uuid4(),
        repository_id=repo.id,
        pr_number=42,
        pr_title="Fix auth handler",
        pr_author="john",
        pr_url="https://github.com/acme-corp/backend/pull/42",
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


@pytest.mark.asyncio
async def test_pull_request_opened_enqueues_review() -> None:
    payload = json.loads((FIXTURES / "pull_request_opened.json").read_text())
    repo = _repo()
    job = _job(repo)

    start_review = AsyncMock()
    start_review.execute.return_value = (job, True)

    enqueue_cleanup = AsyncMock()
    sync_installation = AsyncMock()

    use_case = HandleGithubWebhookUseCase(start_review, enqueue_cleanup, sync_installation)
    result = await use_case.execute("pull_request", payload)

    assert result.accepted is True
    assert result.job_enqueued is True
    start_review.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_pull_request_closed_enqueues_cleanup() -> None:
    payload = json.loads((FIXTURES / "pull_request_opened.json").read_text())
    payload["action"] = "closed"

    start_review = AsyncMock()
    enqueue_cleanup = AsyncMock()
    enqueue_cleanup.execute.return_value = True
    sync_installation = AsyncMock()

    use_case = HandleGithubWebhookUseCase(start_review, enqueue_cleanup, sync_installation)
    result = await use_case.execute("pull_request", payload)

    assert result.accepted is True
    assert result.job_enqueued is True
    enqueue_cleanup.execute.assert_awaited_once()
    start_review.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_ping_returns_accepted_without_enqueue() -> None:
    start_review = AsyncMock()
    enqueue_cleanup = AsyncMock()
    sync_installation = AsyncMock()

    use_case = HandleGithubWebhookUseCase(start_review, enqueue_cleanup, sync_installation)
    result = await use_case.execute("ping", {"zen": "Keep it logically awesome."})

    assert result.accepted is True
    assert result.job_enqueued is False
    assert result.message == "pong"
