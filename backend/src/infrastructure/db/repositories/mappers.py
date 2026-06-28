from domain.entities.embedding_cleanup_job import EmbeddingCleanupJob
from domain.entities.github_installation import GithubInstallation
from domain.entities.job import ReviewJob
from domain.entities.repository import Repository
from domain.value_objects.job_status import JobStatus
from infrastructure.db.models.embedding_cleanup_job import EmbeddingCleanupJobORM
from infrastructure.db.models.installation import GithubInstallationORM
from infrastructure.db.models.repository import RepositoryORM
from infrastructure.db.models.review_job import ReviewJobORM


def to_repository_entity(orm: RepositoryORM) -> Repository:
    return Repository(
        id=orm.id,
        github_id=orm.github_id,
        installation_id=orm.installation_id,
        owner=orm.owner,
        name=orm.name,
        full_name=orm.full_name,
        default_branch=orm.default_branch,
        is_active=orm.is_active,
        language=orm.language,
        created_at=orm.created_at,
        updated_at=orm.updated_at,
    )


def to_installation_entity(orm: GithubInstallationORM) -> GithubInstallation:
    return GithubInstallation(
        id=orm.id,
        installation_id=orm.installation_id,
        account_login=orm.account_login,
        account_type=orm.account_type,
        account_avatar_url=orm.account_avatar_url,
        access_token_encrypted=orm.access_token_encrypted,
        access_token_expires_at=orm.access_token_expires_at,
        created_at=orm.created_at,
        updated_at=orm.updated_at,
    )


def to_job_entity(orm: ReviewJobORM) -> ReviewJob:
    return ReviewJob(
        id=orm.id,
        repository_id=orm.repository_id,
        pr_number=orm.pr_number,
        pr_title=orm.pr_title,
        pr_author=orm.pr_author,
        pr_url=orm.pr_url,
        base_sha=orm.base_sha,
        head_sha=orm.head_sha,
        status=JobStatus(orm.status),
        attempt_count=orm.attempt_count,
        retry_after=orm.retry_after,
        error_message=orm.error_message,
        enqueued_at=orm.enqueued_at,
        started_at=orm.started_at,
        completed_at=orm.completed_at,
        created_at=orm.created_at,
        updated_at=orm.updated_at,
    )


def to_embedding_cleanup_job_entity(orm: EmbeddingCleanupJobORM) -> EmbeddingCleanupJob:
    return EmbeddingCleanupJob(
        id=orm.id,
        repository_id=orm.repository_id,
        head_sha=orm.head_sha,
        pr_number=orm.pr_number,
        status=JobStatus(orm.status),
        attempt_count=orm.attempt_count,
        retry_after=orm.retry_after,
        error_message=orm.error_message,
        enqueued_at=orm.enqueued_at,
        started_at=orm.started_at,
        completed_at=orm.completed_at,
        created_at=orm.created_at,
        updated_at=orm.updated_at,
    )
