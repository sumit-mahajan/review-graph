from datetime import UTC
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.review import Finding, Review
from domain.errors import EntityNotFoundError
from domain.repositories.i_review_repository import (
    CreateReviewParams,
    IReviewRepository,
)
from domain.value_objects.agent_type import AgentType
from domain.value_objects.severity import Severity
from infrastructure.db.models.finding import FindingORM
from infrastructure.db.models.review import ReviewORM


class PostgresReviewRepository(IReviewRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, params: CreateReviewParams) -> Review:
        severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
        for f in params.findings:
            key = f.severity.value
            if key in severity_counts:
                severity_counts[key] += 1

        review_orm = ReviewORM(
            job_id=params.job_id,
            repository_id=params.repository_id,
            pr_number=params.pr_number,
            head_sha=params.head_sha,
            pr_url=params.pr_url,
            summary=params.summary,
            total_findings=len(params.findings),
            critical_count=severity_counts["critical"],
            high_count=severity_counts["high"],
            medium_count=severity_counts["medium"],
            low_count=severity_counts["low"],
            info_count=severity_counts["info"],
            agents_run=[a.value for a in params.agents_run],
            langfuse_trace_id=params.langfuse_trace_id,
            posted_to_github=False,
        )
        self._session.add(review_orm)
        await self._session.flush()  # Get review_orm.id before inserting findings.

        finding_orms: list[FindingORM] = []
        for fp in params.findings:
            f_orm = FindingORM(
                review_id=review_orm.id,
                severity=fp.severity.value,
                category=fp.category,
                agent_source=fp.agent_source,
                file_path=fp.file_path,
                line_start=fp.line_start,
                line_end=fp.line_end,
                title=fp.title,
                description=fp.description,
                fix_suggestion=fp.fix_suggestion,
            )
            self._session.add(f_orm)
            finding_orms.append(f_orm)

        await self._session.commit()
        await self._session.refresh(review_orm)
        for f_orm in finding_orms:
            await self._session.refresh(f_orm)

        return _to_review_entity(review_orm, finding_orms)

    async def get_by_id(self, review_id: UUID) -> Review | None:
        orm = await self._session.get(ReviewORM, review_id)
        if orm is None:
            return None
        findings = await self._load_findings(review_id)
        return _to_review_entity(orm, findings)

    async def get_by_job_id(self, job_id: UUID) -> Review | None:
        result = await self._session.execute(select(ReviewORM).where(ReviewORM.job_id == job_id))
        orm = result.scalar_one_or_none()
        if orm is None:
            return None
        findings = await self._load_findings(orm.id)
        return _to_review_entity(orm, findings)

    async def list_by_repo(
        self, repository_id: UUID, *, page: int = 1, limit: int = 20
    ) -> tuple[list[Review], int]:
        offset = (page - 1) * limit

        count_result = await self._session.execute(
            select(func.count()).where(ReviewORM.repository_id == repository_id)
        )
        total: int = count_result.scalar_one()

        result = await self._session.execute(
            select(ReviewORM)
            .where(ReviewORM.repository_id == repository_id)
            .order_by(ReviewORM.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        orms = list(result.scalars().all())
        reviews = [_to_review_entity(orm, []) for orm in orms]
        return reviews, total

    async def mark_posted_to_github(self, review_id: UUID) -> Review:
        orm = await self._session.get(ReviewORM, review_id)
        if orm is None:
            raise EntityNotFoundError(f"Review {review_id} not found")
        orm.posted_to_github = True
        await self._session.commit()
        await self._session.refresh(orm)
        findings = await self._load_findings(review_id)
        return _to_review_entity(orm, findings)

    async def update_finding_comment_ids(self, updates: list[tuple[UUID, int]]) -> None:
        for finding_id, comment_id in updates:
            orm = await self._session.get(FindingORM, finding_id)
            if orm is None:
                continue
            orm.github_comment_id = comment_id
        await self._session.commit()

    async def _load_findings(self, review_id: UUID) -> list[FindingORM]:
        result = await self._session.execute(
            select(FindingORM).where(FindingORM.review_id == review_id)
        )
        return list(result.scalars().all())


def _to_review_entity(orm: ReviewORM, findings: list[FindingORM]) -> Review:
    return Review(
        id=orm.id,
        job_id=orm.job_id,
        repository_id=orm.repository_id,
        pr_number=orm.pr_number,
        head_sha=orm.head_sha,
        pr_url=orm.pr_url,
        summary=orm.summary,
        total_findings=orm.total_findings,
        critical_count=orm.critical_count,
        high_count=orm.high_count,
        medium_count=orm.medium_count,
        low_count=orm.low_count,
        info_count=orm.info_count,
        agents_run=[AgentType(a) for a in orm.agents_run],
        langfuse_trace_id=orm.langfuse_trace_id,
        posted_to_github=orm.posted_to_github,
        created_at=orm.created_at,
        updated_at=orm.updated_at,
        findings=[_to_finding_entity(f) for f in findings],
    )


def _to_finding_entity(orm: FindingORM) -> Finding:
    from datetime import datetime as dt  # noqa: PLC0415

    created_at = orm.created_at
    if not isinstance(created_at, dt):
        created_at = dt.now(UTC)

    return Finding(
        id=orm.id,
        review_id=orm.review_id,
        severity=Severity(orm.severity),
        category=orm.category,
        agent_source=orm.agent_source,
        file_path=orm.file_path,
        line_start=orm.line_start,
        line_end=orm.line_end,
        title=orm.title,
        description=orm.description,
        fix_suggestion=orm.fix_suggestion,
        github_comment_id=orm.github_comment_id,
        created_at=created_at,
    )
