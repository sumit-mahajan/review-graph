"""Map domain entities to API DTOs."""

from api.schemas.dashboard import (
    AgentConfigDTO,
    FindingDTO,
    JobStatusDTO,
    RepoDTO,
    ReviewDetailDTO,
    ReviewSummaryDTO,
    UserDTO,
)
from domain.entities.agent_config import AgentConfig
from domain.entities.job import ReviewJob
from domain.entities.repository import Repository
from domain.entities.review import Finding, Review
from domain.entities.user import User


def to_user_dto(user: User) -> UserDTO:
    return UserDTO(
        id=str(user.id),
        github_id=user.github_id,
        login=user.login,
        avatar_url=user.avatar_url,
    )


def to_agent_config_dto(config: AgentConfig) -> AgentConfigDTO:
    return AgentConfigDTO(
        repository_id=str(config.repository_id),
        security_enabled=config.security_enabled,
        perf_enabled=config.perf_enabled,
        arch_enabled=config.arch_enabled,
        test_enabled=config.test_enabled,
        min_severity=config.min_severity,
    )


def to_repo_dto(repo: Repository, config: AgentConfig) -> RepoDTO:
    return RepoDTO(
        id=str(repo.id),
        github_id=repo.github_id,
        full_name=repo.full_name,
        default_branch=repo.default_branch,
        is_active=repo.is_active,
        language=repo.language,
        agent_config=to_agent_config_dto(config),
    )


def to_review_summary_dto(review: Review) -> ReviewSummaryDTO:
    return ReviewSummaryDTO(
        id=str(review.id),
        pr_number=review.pr_number,
        pr_url=review.pr_url,
        head_sha=review.head_sha,
        total_findings=review.total_findings,
        critical_count=review.critical_count,
        high_count=review.high_count,
        medium_count=review.medium_count,
        low_count=review.low_count,
        info_count=review.info_count,
        agents_run=[a.value for a in review.agents_run],
        posted_to_github=review.posted_to_github,
        created_at=review.created_at.isoformat(),
    )


def to_finding_dto(finding: Finding) -> FindingDTO:
    return FindingDTO(
        id=str(finding.id),
        severity=finding.severity.value,
        category=finding.category,
        agent_source=finding.agent_source,
        file_path=finding.file_path,
        line_start=finding.line_start,
        line_end=finding.line_end,
        title=finding.title,
        description=finding.description,
        fix_suggestion=finding.fix_suggestion,
    )


def to_review_detail_dto(review: Review) -> ReviewDetailDTO:
    summary = to_review_summary_dto(review)
    return ReviewDetailDTO(
        **summary.model_dump(),
        summary=review.summary,
        langfuse_trace_id=review.langfuse_trace_id,
        findings=[to_finding_dto(f) for f in review.findings],
    )


def to_job_status_dto(job: ReviewJob) -> JobStatusDTO:
    return JobStatusDTO(
        id=str(job.id),
        pr_number=job.pr_number,
        pr_url=job.pr_url,
        head_sha=job.head_sha,
        status=job.status.value,
        attempt_count=job.attempt_count,
        error_message=job.error_message,
        enqueued_at=job.enqueued_at.isoformat(),
        started_at=job.started_at.isoformat() if job.started_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
    )
