"""Tests for PostReviewToGithubUseCase."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from application.use_cases.post_review_to_github import (
    PostReviewToGithubUseCase,
    build_summary_body,
    format_finding_comment,
)
from domain.entities.github_installation import GithubInstallation
from domain.entities.repository import Repository
from domain.entities.review import Finding, Review
from domain.services.i_github_comment_poster import PostedReviewResult
from domain.services.i_pr_fetcher import FilePatch, PullRequestDiff
from domain.value_objects.agent_type import AgentType
from domain.value_objects.severity import Severity
from tests.support.memory_repositories import InMemoryInstallationRepository, InMemoryRepoRepository
from tests.unit.test_review_persistence import InMemoryReviewRepository


def _make_review(*, posted: bool = False) -> tuple[Review, Repository, GithubInstallation]:
    now = datetime.now(UTC)
    installation = GithubInstallation(
        id=uuid4(),
        installation_id=12345,
        account_login="org",
        account_type="org",
        account_avatar_url=None,
        access_token_encrypted=None,
        access_token_expires_at=None,
        created_at=now,
        updated_at=now,
    )
    repository = Repository(
        id=uuid4(),
        github_id=99,
        installation_id=installation.id,
        owner="org",
        name="repo",
        full_name="org/repo",
        default_branch="main",
        is_active=True,
        language="python",
        created_at=now,
        updated_at=now,
    )
    review_id = uuid4()
    finding = Finding(
        id=uuid4(),
        review_id=review_id,
        severity=Severity.HIGH,
        category="security",
        agent_source="security",
        file_path="src/auth.py",
        line_start=42,
        line_end=44,
        title="SQL injection",
        description="Unsanitised query.",
        fix_suggestion="Use parameters.",
        github_comment_id=None,
        created_at=now,
    )
    review = Review(
        id=review_id,
        job_id=uuid4(),
        repository_id=repository.id,
        pr_number=3,
        head_sha="c" * 40,
        pr_url="https://github.com/org/repo/pull/3",
        summary="Security issue found.",
        total_findings=1,
        critical_count=0,
        high_count=1,
        medium_count=0,
        low_count=0,
        info_count=0,
        agents_run=[AgentType.SECURITY],
        langfuse_trace_id=None,
        posted_to_github=posted,
        created_at=now,
        updated_at=now,
        findings=[finding],
    )
    return review, repository, installation


@pytest.mark.asyncio
async def test_post_review_calls_github_and_marks_posted() -> None:
    review, repository, installation = _make_review()
    review_repo = InMemoryReviewRepository()
    review_repo._reviews[review.id] = review

    repo_repo = InMemoryRepoRepository()
    repo_repo._repos[repository.github_id] = repository

    inst_repo = InMemoryInstallationRepository()
    inst_repo._installations[installation.installation_id] = installation

    poster = AsyncMock()
    poster.post_pull_request_review.return_value = PostedReviewResult(
        github_review_id=999,
        comment_ids=(111,),
    )

    use_case = PostReviewToGithubUseCase(
        review_repo, repo_repo, inst_repo, poster, min_severity=Severity.MEDIUM
    )
    updated = await use_case.execute(review)

    assert updated.posted_to_github is True
    poster.post_pull_request_review.assert_awaited_once()
    call_kwargs = poster.post_pull_request_review.await_args.kwargs
    assert call_kwargs["owner"] == "org"
    assert call_kwargs["repo"] == "repo"
    assert call_kwargs["pr_number"] == 3
    assert len(call_kwargs["comments"]) == 1
    assert call_kwargs["comments"][0].line == 42


@pytest.mark.asyncio
async def test_post_review_skips_when_already_posted() -> None:
    review, repository, installation = _make_review(posted=True)
    review_repo = InMemoryReviewRepository()
    review_repo._reviews[review.id] = review

    repo_repo = InMemoryRepoRepository()
    repo_repo._repos[repository.github_id] = repository
    inst_repo = InMemoryInstallationRepository()
    inst_repo._installations[installation.installation_id] = installation

    poster = AsyncMock()
    use_case = PostReviewToGithubUseCase(review_repo, repo_repo, inst_repo, poster)
    updated = await use_case.execute(review)
    assert updated.posted_to_github is True
    poster.post_pull_request_review.assert_not_awaited()


@pytest.mark.asyncio
async def test_post_review_filters_below_min_severity() -> None:
    review, repository, installation = _make_review()
    review.findings[0] = Finding(
        id=review.findings[0].id,
        review_id=review.id,
        severity=Severity.LOW,
        category="security",
        agent_source="security",
        file_path="src/auth.py",
        line_start=42,
        line_end=None,
        title="Minor nit",
        description="Style issue.",
        fix_suggestion=None,
        github_comment_id=None,
        created_at=review.findings[0].created_at,
    )
    review_repo = InMemoryReviewRepository()
    review_repo._reviews[review.id] = review
    repo_repo = InMemoryRepoRepository()
    repo_repo._repos[repository.github_id] = repository
    inst_repo = InMemoryInstallationRepository()
    inst_repo._installations[installation.installation_id] = installation

    poster = AsyncMock()
    poster.post_pull_request_review.return_value = PostedReviewResult(
        github_review_id=1,
        comment_ids=(),
    )

    use_case = PostReviewToGithubUseCase(
        review_repo, repo_repo, inst_repo, poster, min_severity=Severity.MEDIUM
    )
    await use_case.execute(review)

    call_kwargs = poster.post_pull_request_review.await_args.kwargs
    assert call_kwargs["comments"] == []


@pytest.mark.asyncio
async def test_post_review_drops_inline_comments_not_on_diff() -> None:
    review, repository, installation = _make_review()
    review.findings[0] = Finding(
        id=review.findings[0].id,
        review_id=review.id,
        severity=Severity.HIGH,
        category="security",
        agent_source="security",
        file_path="src/auth.py",
        line_start=99,
        line_end=None,
        title="Off-diff line",
        description="Not on changed lines.",
        fix_suggestion=None,
        github_comment_id=None,
        created_at=review.findings[0].created_at,
    )
    review_repo = InMemoryReviewRepository()
    review_repo._reviews[review.id] = review
    repo_repo = InMemoryRepoRepository()
    repo_repo._repos[repository.github_id] = repository
    inst_repo = InMemoryInstallationRepository()
    inst_repo._installations[installation.installation_id] = installation

    pr_fetcher = AsyncMock()
    pr_fetcher.fetch_diff_for_pr.return_value = PullRequestDiff(
        pr_number=3,
        base_sha="b" * 40,
        head_sha=review.head_sha,
        base_branch="main",
        head_branch="feature",
        file_patches=[
            FilePatch(
                path="src/auth.py",
                status="modified",
                patch="@@ -40,3 +40,4 @@\n unchanged\n+added\n",
                additions=1,
                deletions=0,
            )
        ],
    )

    poster = AsyncMock()
    poster.post_pull_request_review.return_value = PostedReviewResult(
        github_review_id=999,
        comment_ids=(),
    )

    use_case = PostReviewToGithubUseCase(
        review_repo,
        repo_repo,
        inst_repo,
        poster,
        pr_fetcher=pr_fetcher,
        min_severity=Severity.MEDIUM,
    )
    await use_case.execute(review)

    call_kwargs = poster.post_pull_request_review.await_args.kwargs
    assert call_kwargs["comments"] == []


def test_format_finding_comment_includes_fix() -> None:
    now = datetime.now(UTC)
    finding = Finding(
        id=uuid4(),
        review_id=uuid4(),
        severity=Severity.HIGH,
        category="security",
        agent_source="security",
        file_path="a.py",
        line_start=1,
        line_end=None,
        title="Issue",
        description="Bad code.",
        fix_suggestion="Fix it.",
        github_comment_id=None,
        created_at=now,
    )
    body = format_finding_comment(finding)
    assert "Issue" in body
    assert "Fix it." in body


def test_build_summary_body_lists_findings() -> None:
    now = datetime.now(UTC)
    finding = Finding(
        id=uuid4(),
        review_id=uuid4(),
        severity=Severity.HIGH,
        category="security",
        agent_source="security",
        file_path="a.py",
        line_start=5,
        line_end=7,
        title="Bug",
        description="x",
        fix_suggestion=None,
        github_comment_id=None,
        created_at=now,
    )
    body = build_summary_body("Summary text.", [finding])
    assert "Summary text." in body
    assert "Bug" in body
    assert "lines 5–7" in body
