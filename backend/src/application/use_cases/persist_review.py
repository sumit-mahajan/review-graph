"""PersistReviewUseCase — saves pipeline output to reviews + findings tables."""

from uuid import UUID

import structlog

from domain.entities.job import ReviewJob
from domain.entities.review import Review
from domain.repositories.i_review_repository import (
    CreateFindingParams,
    CreateReviewParams,
    IReviewRepository,
)
from domain.services.i_agent_orchestrator import OrchestratorResult
from domain.value_objects.severity import parse_severity

logger = structlog.get_logger()


class PersistReviewUseCase:
    def __init__(self, review_repo: IReviewRepository) -> None:
        self._review_repo = review_repo

    async def get_existing(self, job_id: UUID) -> Review | None:
        return await self._review_repo.get_by_job_id(job_id)

    async def execute(self, job: ReviewJob, result: OrchestratorResult) -> Review:
        existing = await self._review_repo.get_by_job_id(job.id)
        if existing is not None:
            await logger.ainfo(
                "review_persist_idempotent_skip",
                job_id=str(job.id),
                review_id=str(existing.id),
            )
            return existing

        finding_params = [
            CreateFindingParams(
                review_id=job.id,  # placeholder; repo assigns real review_id on flush
                severity=parse_severity(f.severity),
                category=f.category,
                agent_source=f.agent_source,
                file_path=f.file_path,
                line_start=f.line_start,
                line_end=f.line_end,
                title=f.title,
                description=f.description,
                fix_suggestion=f.fix_suggestion,
            )
            for f in result.findings
        ]

        review = await self._review_repo.create(
            CreateReviewParams(
                job_id=job.id,
                repository_id=job.repository_id,
                pr_number=job.pr_number,
                head_sha=job.head_sha,
                pr_url=job.pr_url,
                summary=result.summary,
                agents_run=list(result.agents_run),
                langfuse_trace_id=result.langfuse_trace_id,
                findings=finding_params,
            )
        )

        await logger.ainfo(
            "review_persisted",
            job_id=str(job.id),
            review_id=str(review.id),
            total_findings=review.total_findings,
        )
        return review
