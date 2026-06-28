"""
Shared pytest fixtures for all test layers.

Unit tests:        tests/unit/      — mock all infrastructure interfaces
Integration tests: tests/integration/ — real DB (test schema), mocked external APIs
E2E tests:         tests/e2e/        — full stack, real DB + Redis
"""

from unittest.mock import AsyncMock

import pytest

# ── Domain / Application mocks ────────────────────────────────────────────────


@pytest.fixture
def mock_review_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_job_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_repo_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_queue_client() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_github_client() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_gemini_client() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_embedding_service() -> AsyncMock:
    return AsyncMock()
