"""Tests for AssembleReviewPackageUseCase with mocked fetcher."""
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from application.use_cases.assemble_review_package import (
    AssembleReviewPackageUseCase,
    _extract_changed_lines,
)
from domain.entities.github_installation import GithubInstallation
from domain.entities.repository import Repository
from domain.services.i_pr_fetcher import FilePatch, PullRequestDiff
from tests.fixtures.python_sample import PYTHON_PATCH, PYTHON_SOURCE


def _repo() -> Repository:
    now = datetime.now(UTC)
    inst_id = uuid4()
    return Repository(
        id=uuid4(),
        github_id=123,
        installation_id=inst_id,
        owner="acme",
        name="backend",
        full_name="acme/backend",
        default_branch="main",
        is_active=True,
        language="Python",
        created_at=now,
        updated_at=now,
    )


def _installation(installation_id: object) -> GithubInstallation:
    now = datetime.now(UTC)
    return GithubInstallation(
        id=installation_id,  # type: ignore[arg-type]
        installation_id=99001,
        account_login="acme",
        account_type="org",
        account_avatar_url=None,
        access_token_encrypted=None,
        access_token_expires_at=None,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_assembly_produces_context_units() -> None:
    repo = _repo()
    installation = _installation(repo.installation_id)

    repo_repo = AsyncMock()
    repo_repo.get_by_id.return_value = repo

    installation_repo = AsyncMock()
    installation_repo.get_by_id.return_value = installation

    pr_fetcher = AsyncMock()
    pr_fetcher.fetch_diff.return_value = PullRequestDiff(
        pr_number=42,
        base_sha="a" * 40,
        head_sha="b" * 40,
        base_branch="main",
        head_branch="fix/auth",
        file_patches=[
            FilePatch(
                path="src/auth/handlers.py",
                status="modified",
                additions=2,
                deletions=2,
                patch=PYTHON_PATCH,
            )
        ],
    )
    pr_fetcher.fetch_file_content.return_value = PYTHON_SOURCE

    use_case = AssembleReviewPackageUseCase(repo_repo, installation_repo, pr_fetcher)
    pr_metadata, context_units, raw_diff_chunks = await use_case.execute(
        repository_id=repo.id,
        pr_number=42,
        pr_title="Fix auth handler",
        pr_author="john",
        pr_url="https://github.com/acme/backend/pull/42",
        base_sha="a" * 40,
        head_sha="b" * 40,
    )

    assert pr_metadata.pr_number == 42
    assert pr_metadata.base_sha == "a" * 40
    assert len(raw_diff_chunks) == 1
    assert raw_diff_chunks[0].file_path == "src/auth/handlers.py"

    # authenticate_user is in the diff → should be a context unit
    names = {u.node_name for u in context_units}
    assert "authenticate_user" in names


@pytest.mark.asyncio
async def test_assembly_uses_raw_diff_when_parser_unavailable() -> None:
    """For unsupported file types, raw_diff_chunks should still be populated."""
    repo = _repo()
    installation = _installation(repo.installation_id)

    repo_repo = AsyncMock()
    repo_repo.get_by_id.return_value = repo

    installation_repo = AsyncMock()
    installation_repo.get_by_id.return_value = installation

    pr_fetcher = AsyncMock()
    pr_fetcher.fetch_diff.return_value = PullRequestDiff(
        pr_number=1,
        base_sha="a" * 40,
        head_sha="b" * 40,
        base_branch="main",
        head_branch="fix/config",
        file_patches=[
            FilePatch(
                path="config/app.yaml",
                status="modified",
                additions=1,
                deletions=1,
                patch="@@ -1 +1 @@\n-debug: false\n+debug: true\n",
            )
        ],
    )

    use_case = AssembleReviewPackageUseCase(repo_repo, installation_repo, pr_fetcher)
    _, context_units, raw_diff_chunks = await use_case.execute(
        repository_id=repo.id,
        pr_number=1,
        pr_title="Toggle debug",
        pr_author="alice",
        pr_url="u",
        base_sha="a" * 40,
        head_sha="b" * 40,
    )

    assert len(raw_diff_chunks) == 1
    assert context_units == []  # YAML has no parser; graceful fallback


def test_extract_changed_lines_from_patch() -> None:
    lines = _extract_changed_lines(PYTHON_PATCH)
    assert len(lines) > 0
    assert isinstance(list(lines)[0], int)
