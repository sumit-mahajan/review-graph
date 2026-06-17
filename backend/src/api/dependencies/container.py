from dataclasses import dataclass
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from application.use_cases.enqueue_embedding_cleanup import EnqueueEmbeddingCleanupUseCase
from application.use_cases.handle_github_webhook import HandleGithubWebhookUseCase
from application.use_cases.start_review import StartReviewUseCase
from application.use_cases.sync_installation import SyncInstallationUseCase
from domain.services.i_github_app_client import IGithubAppClient
from domain.services.i_queue_client import IQueueClient
from domain.services.i_webhook_signature_validator import IWebhookSignatureValidator
from infrastructure.config.settings import Settings, get_settings
from infrastructure.db.repositories.installation_repository import PostgresInstallationRepository
from infrastructure.db.repositories.job_repository import PostgresJobRepository
from infrastructure.db.repositories.repo_repository import PostgresRepoRepository
from infrastructure.db.session import create_session_factory
from infrastructure.github.app_client import GithubAppClient
from infrastructure.github.webhook_signature import GithubWebhookSignatureValidator
from infrastructure.queue.upstash_redis_client import UpstashRedisClient
from infrastructure.queue.wake_on_enqueue_queue_client import WakeOnEnqueueQueueClient
from infrastructure.queue.worker_wake_client import HttpWorkerWakeClient, NoOpWorkerWakeClient


@dataclass
class AppContainer:
    settings: Settings
    session_factory: async_sessionmaker[AsyncSession]
    queue_client: IQueueClient
    signature_validator: IWebhookSignatureValidator
    github_app_client: IGithubAppClient | None

    def webhook_use_case(self, session: AsyncSession) -> HandleGithubWebhookUseCase:
        job_repo = PostgresJobRepository(session)
        repo_repo = PostgresRepoRepository(session)
        installation_repo = PostgresInstallationRepository(session)

        start_review = StartReviewUseCase(job_repo, repo_repo, self.queue_client)
        enqueue_cleanup = EnqueueEmbeddingCleanupUseCase(repo_repo, self.queue_client)

        if self.github_app_client is None:
            raise RuntimeError("GitHub App client is not configured")

        sync_installation = SyncInstallationUseCase(
            installation_repo, repo_repo, self.github_app_client
        )

        return HandleGithubWebhookUseCase(start_review, enqueue_cleanup, sync_installation)


@lru_cache
def build_container() -> AppContainer:
    settings = get_settings()
    session_factory = create_session_factory(settings)

    redis_queue = UpstashRedisClient(
        redis_url=settings.upstash_redis_url,
        redis_token=settings.upstash_redis_token,
        stream_name=settings.redis_queue_stream,
    )
    wake_client = (
        HttpWorkerWakeClient(settings.worker_wake_url, settings.worker_wake_secret)
        if settings.worker_wake_url and settings.worker_wake_secret
        else NoOpWorkerWakeClient()
    )
    queue_client: IQueueClient = WakeOnEnqueueQueueClient(redis_queue, wake_client)

    signature_validator = GithubWebhookSignatureValidator(
        webhook_secret=settings.github_webhook_secret
    )

    github_client: IGithubAppClient | None = None
    if settings.github_app_id and (
        settings.github_app_private_key_b64 or settings.github_app_private_key_path
    ):
        github_client = GithubAppClient.from_settings(
            app_id=settings.github_app_id,
            private_key_b64=settings.github_app_private_key_b64,
            private_key_path=settings.github_app_private_key_path,
        )

    return AppContainer(
        settings=settings,
        session_factory=session_factory,
        queue_client=queue_client,
        signature_validator=signature_validator,
        github_app_client=github_client,
    )
