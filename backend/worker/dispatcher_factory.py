"""Build WorkerDispatcher with infrastructure dependencies."""

from sqlalchemy.ext.asyncio import AsyncSession

from application.use_cases.cleanup_embeddings import CleanupEmbeddingsUseCase
from application.use_cases.persist_review import PersistReviewUseCase
from application.use_cases.post_review_to_github import PostReviewToGithubUseCase
from application.use_cases.run_review_pipeline import RunReviewPipelineUseCase
from infrastructure.ai.orchestrator_factory import build_orchestrator
from infrastructure.config.settings import Settings
from infrastructure.db.repositories.installation_repository import PostgresInstallationRepository
from infrastructure.db.repositories.job_repository import PostgresJobRepository
from infrastructure.db.repositories.repo_repository import PostgresRepoRepository
from infrastructure.db.repositories.review_repository import PostgresReviewRepository
from infrastructure.db.session import create_session_factory
from infrastructure.github.app_client import GithubAppClient
from infrastructure.github.comment_poster import GithubCommentPoster
from infrastructure.worker.dispatcher import WorkerDispatcher
from tests.support.memory_repositories import InMemoryEmbeddingCleanupRepository


def _build_worker_dispatcher(db: AsyncSession, settings: Settings) -> WorkerDispatcher:
    job_repo = PostgresJobRepository(db)
    review_repo = PostgresReviewRepository(db)
    repo_repo = PostgresRepoRepository(db)
    installation_repo = PostgresInstallationRepository(db)

    persist_review = PersistReviewUseCase(review_repo)
    post_to_github: PostReviewToGithubUseCase | None = None

    if settings.github_app_id and (
        settings.github_app_private_key_b64 or settings.github_app_private_key_path
    ):
        app_client = GithubAppClient.from_settings(
            app_id=settings.github_app_id,
            private_key_b64=settings.github_app_private_key_b64,
            private_key_path=settings.github_app_private_key_path,
        )
        comment_poster = GithubCommentPoster(app_client)
        post_to_github = PostReviewToGithubUseCase(
            review_repo,
            repo_repo,
            installation_repo,
            comment_poster,
        )

    run_review = RunReviewPipelineUseCase(
        job_repo,
        build_orchestrator(settings, job_repo, db),
        persist_review=persist_review,
        post_to_github=post_to_github,
    )
    cleanup_use_case = CleanupEmbeddingsUseCase(InMemoryEmbeddingCleanupRepository())

    return WorkerDispatcher(run_review, cleanup_use_case)


async def dispatch_payload(settings: Settings, raw_payload: str) -> bool:
    """Open a DB session for the duration of dispatch (session must stay open)."""
    session_factory = create_session_factory(settings)
    async with session_factory() as db:
        dispatcher = _build_worker_dispatcher(db, settings)
        return await dispatcher.dispatch(raw_payload)
