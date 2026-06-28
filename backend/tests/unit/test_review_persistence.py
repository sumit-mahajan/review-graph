"""Tests for review + finding persistence using in-memory repo."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from domain.entities.review import Finding, Review
from domain.errors import EntityNotFoundError
from domain.repositories.i_review_repository import (
    CreateFindingParams,
    CreateReviewParams,
    IReviewRepository,
)
from domain.value_objects.agent_type import AgentType
from domain.value_objects.severity import Severity


class InMemoryReviewRepository(IReviewRepository):
    """Simple in-memory implementation for unit tests."""

    def __init__(self) -> None:
        self._reviews: dict[object, Review] = {}

    async def create(self, params: CreateReviewParams) -> Review:
        now = datetime.now(UTC)
        severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
        findings: list[Finding] = []

        for fp in params.findings:
            severity_counts[fp.severity.value] += 1
            findings.append(
                Finding(
                    id=uuid4(),
                    review_id=uuid4(),  # will be fixed below
                    severity=fp.severity,
                    category=fp.category,
                    agent_source=fp.agent_source,
                    file_path=fp.file_path,
                    line_start=fp.line_start,
                    line_end=fp.line_end,
                    title=fp.title,
                    description=fp.description,
                    fix_suggestion=fp.fix_suggestion,
                    github_comment_id=None,
                    created_at=now,
                )
            )

        review = Review(
            id=uuid4(),
            job_id=params.job_id,
            repository_id=params.repository_id,
            pr_number=params.pr_number,
            head_sha=params.head_sha,
            pr_url=params.pr_url,
            summary=params.summary,
            total_findings=len(findings),
            critical_count=severity_counts["critical"],
            high_count=severity_counts["high"],
            medium_count=severity_counts["medium"],
            low_count=severity_counts["low"],
            info_count=severity_counts["info"],
            agents_run=params.agents_run,
            langfuse_trace_id=params.langfuse_trace_id,
            posted_to_github=False,
            created_at=now,
            updated_at=now,
            findings=findings,
        )
        self._reviews[review.id] = review
        return review

    async def get_by_id(self, review_id: object) -> Review | None:
        return self._reviews.get(review_id)

    async def get_by_job_id(self, job_id: object) -> Review | None:
        for r in self._reviews.values():
            if r.job_id == job_id:
                return r
        return None

    async def list_by_repo(
        self, repository_id: object, *, page: int = 1, limit: int = 20
    ) -> tuple[list[Review], int]:
        items = [r for r in self._reviews.values() if r.repository_id == repository_id]
        total = len(items)
        offset = (page - 1) * limit
        return items[offset : offset + limit], total

    async def mark_posted_to_github(self, review_id: object) -> Review:
        review = self._reviews.get(review_id)
        if review is None:
            raise EntityNotFoundError(f"Review {review_id} not found")
        updated = Review(
            id=review.id,
            job_id=review.job_id,
            repository_id=review.repository_id,
            pr_number=review.pr_number,
            head_sha=review.head_sha,
            pr_url=review.pr_url,
            summary=review.summary,
            total_findings=review.total_findings,
            critical_count=review.critical_count,
            high_count=review.high_count,
            medium_count=review.medium_count,
            low_count=review.low_count,
            info_count=review.info_count,
            agents_run=review.agents_run,
            langfuse_trace_id=review.langfuse_trace_id,
            posted_to_github=True,
            created_at=review.created_at,
            updated_at=datetime.now(UTC),
            findings=review.findings,
        )
        self._reviews[review_id] = updated
        return updated

    async def update_finding_comment_ids(self, updates: list[tuple[object, int]]) -> None:
        for finding_id, comment_id in updates:
            for review in self._reviews.values():
                for i, finding in enumerate(review.findings):
                    if finding.id == finding_id:
                        review.findings[i] = Finding(
                            id=finding.id,
                            review_id=finding.review_id,
                            severity=finding.severity,
                            category=finding.category,
                            agent_source=finding.agent_source,
                            file_path=finding.file_path,
                            line_start=finding.line_start,
                            line_end=finding.line_end,
                            title=finding.title,
                            description=finding.description,
                            fix_suggestion=finding.fix_suggestion,
                            github_comment_id=comment_id,
                            created_at=finding.created_at,
                        )


@pytest.mark.asyncio
async def test_create_review_persists_findings() -> None:
    repo = InMemoryReviewRepository()
    job_id = uuid4()
    repo_id = uuid4()

    params = CreateReviewParams(
        job_id=job_id,
        repository_id=repo_id,
        pr_number=42,
        head_sha="b" * 40,
        pr_url="https://github.com/org/repo/pull/42",
        summary="LGTM with notes",
        agents_run=[AgentType.SECURITY, AgentType.PERF],
        langfuse_trace_id="trace-abc",
        findings=[
            CreateFindingParams(
                review_id=uuid4(),
                severity=Severity.HIGH,
                category="security",
                agent_source="security",
                file_path="src/auth.py",
                line_start=45,
                line_end=47,
                title="SQL injection risk",
                description="Unsanitised input passed directly to query.",
                fix_suggestion="Use parameterised queries.",
            )
        ],
    )

    review = await repo.create(params)
    assert review.total_findings == 1
    assert review.high_count == 1
    assert review.critical_count == 0
    assert len(review.findings) == 1
    assert review.findings[0].severity == Severity.HIGH


@pytest.mark.asyncio
async def test_mark_posted_to_github() -> None:
    repo = InMemoryReviewRepository()
    params = CreateReviewParams(
        job_id=uuid4(),
        repository_id=uuid4(),
        pr_number=1,
        head_sha="a" * 40,
        pr_url="u",
        summary=None,
        agents_run=[],
        langfuse_trace_id=None,
        findings=[],
    )
    review = await repo.create(params)
    assert review.posted_to_github is False

    updated = await repo.mark_posted_to_github(review.id)
    assert updated.posted_to_github is True


@pytest.mark.asyncio
async def test_list_by_repo_paginates() -> None:
    repo = InMemoryReviewRepository()
    repo_id = uuid4()

    for i in range(5):
        await repo.create(
            CreateReviewParams(
                job_id=uuid4(),
                repository_id=repo_id,
                pr_number=i,
                head_sha="a" * 40,
                pr_url="u",
                summary=None,
                agents_run=[],
                langfuse_trace_id=None,
                findings=[],
            )
        )

    page1, total = await repo.list_by_repo(repo_id, page=1, limit=3)
    assert total == 5
    assert len(page1) == 3

    page2, _ = await repo.list_by_repo(repo_id, page=2, limit=3)
    assert len(page2) == 2
