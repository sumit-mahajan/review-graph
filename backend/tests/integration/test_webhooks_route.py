"""Integration tests for POST /api/v1/webhooks/github."""

import hashlib
import hmac
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api.dependencies.container import build_container
from api.main import create_app
from application.use_cases.enqueue_embedding_cleanup import EnqueueEmbeddingCleanupUseCase
from application.use_cases.handle_github_webhook import HandleGithubWebhookUseCase
from application.use_cases.start_review import StartReviewUseCase
from application.use_cases.sync_installation import SyncInstallationUseCase
from domain.repositories.i_repo_repository import UpsertRepositoryParams
from infrastructure.github.webhook_signature import GithubWebhookSignatureValidator
from tests.support.memory_repositories import (
    InMemoryEmbeddingCleanupJobRepository,
    InMemoryJobRepository,
    InMemoryRepoRepository,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
WEBHOOK_SECRET = "integration-test-secret"


def _sign(body: bytes) -> str:
    digest = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


class _TestContainer:
    def __init__(
        self,
        use_case: HandleGithubWebhookUseCase,
        signature_validator: GithubWebhookSignatureValidator,
        job_repo: InMemoryJobRepository,
    ) -> None:
        self._use_case = use_case
        self.signature_validator = signature_validator
        self.session_factory = _fake_session_factory
        self._job_repo = job_repo

    def webhook_use_case(self, _session: object) -> HandleGithubWebhookUseCase:
        return self._use_case


@asynccontextmanager
async def _fake_session_factory() -> AsyncIterator[object]:
    yield object()


@pytest.fixture
def webhook_setup() -> tuple[TestClient, InMemoryJobRepository, InMemoryRepoRepository]:
    build_container.cache_clear()

    job_repo = InMemoryJobRepository()
    repo_repo = InMemoryRepoRepository()
    cleanup_job_repo = InMemoryEmbeddingCleanupJobRepository()

    start_review = StartReviewUseCase(job_repo, repo_repo)
    enqueue_cleanup = EnqueueEmbeddingCleanupUseCase(repo_repo, cleanup_job_repo)
    sync_installation = AsyncMock(spec=SyncInstallationUseCase)

    use_case = HandleGithubWebhookUseCase(start_review, enqueue_cleanup, sync_installation)
    container = _TestContainer(
        use_case=use_case,
        signature_validator=GithubWebhookSignatureValidator(WEBHOOK_SECRET),
        job_repo=job_repo,
    )

    app = create_app()
    app.dependency_overrides[build_container] = lambda: container  # type: ignore[return-value]

    return TestClient(app), job_repo, repo_repo


@pytest.mark.asyncio
async def test_webhook_pull_request_opened_returns_202_and_persists_job(
    webhook_setup: tuple[TestClient, InMemoryJobRepository, InMemoryRepoRepository],
) -> None:
    client, job_repo, repo_repo = webhook_setup

    await repo_repo.upsert(
        UpsertRepositoryParams(
            github_id=987654321,
            installation_id=uuid4(),
            owner="acme-corp",
            name="backend",
            full_name="acme-corp/backend",
            default_branch="main",
            language="Python",
        )
    )

    payload = (FIXTURES / "pull_request_opened.json").read_bytes()
    response = client.post(
        "/api/v1/webhooks/github",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": _sign(payload),
        },
    )

    assert response.status_code == 202
    assert response.json()["status"] == "accepted"
    assert len(job_repo._jobs) == 1


def test_webhook_rejects_invalid_signature(
    webhook_setup: tuple[TestClient, InMemoryJobRepository, InMemoryRepoRepository],
) -> None:
    client, _, _ = webhook_setup
    body = b'{"action":"opened"}'
    response = client.post(
        "/api/v1/webhooks/github",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": "sha256=invalid",
        },
    )
    assert response.status_code == 401


def test_webhook_rejects_missing_event_header(
    webhook_setup: tuple[TestClient, InMemoryJobRepository, InMemoryRepoRepository],
) -> None:
    client, _, _ = webhook_setup
    body = b'{"action":"opened"}'
    response = client.post(
        "/api/v1/webhooks/github",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": _sign(body),
        },
    )
    assert response.status_code == 400
