"""Build IAgentOrchestrator for the worker (real pipeline or stub fallback)."""
from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from application.use_cases.assemble_review_package import AssembleReviewPackageUseCase
from domain.repositories.i_job_repository import IJobRepository
from domain.services.i_agent_orchestrator import IAgentOrchestrator
from infrastructure.ai.gemini_client import GeminiClient
from infrastructure.ai.langgraph_orchestrator import LanggraphOrchestrator
from infrastructure.ai.stub_orchestrator import StubAgentOrchestrator
from infrastructure.config.settings import Settings
from infrastructure.db.repositories.installation_repository import PostgresInstallationRepository
from infrastructure.db.repositories.repo_repository import PostgresRepoRepository
from infrastructure.github.app_client import GithubAppClient
from infrastructure.github.pr_fetcher import GitHubPrFetcher
from infrastructure.observability.langfuse_client import build_langfuse_client

logger = structlog.get_logger()


def build_orchestrator(
    settings: Settings,
    job_repo: IJobRepository,
    db: AsyncSession,
) -> IAgentOrchestrator:
    if not settings.gemini_api_key:
        logger.warning(
            "orchestrator_stub_active",
            reason="GEMINI_API_KEY is not set — reviews will have no AI findings",
        )
        return StubAgentOrchestrator()

    gemini = GeminiClient(settings.gemini_api_key)
    langfuse = build_langfuse_client(
        settings.langfuse_public_key,
        settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )

    assembler: AssembleReviewPackageUseCase | None = None
    if settings.github_app_id and (
        settings.github_app_private_key_b64 or settings.github_app_private_key_path
    ):
        app_client = GithubAppClient.from_settings(
            app_id=settings.github_app_id,
            private_key_b64=settings.github_app_private_key_b64,
            private_key_path=settings.github_app_private_key_path,
        )
        pr_fetcher = GitHubPrFetcher(app_client)
        assembler = AssembleReviewPackageUseCase(
            PostgresRepoRepository(db),
            PostgresInstallationRepository(db),
            pr_fetcher,
        )
    else:
        logger.warning(
            "review_package_assembly_disabled",
            reason="GitHub App credentials missing — agents will not see PR diff content",
        )

    logger.info("orchestrator_langgraph_active")
    return LanggraphOrchestrator(
        gemini,
        job_repo,
        assembler=assembler,
        langfuse=langfuse,
    )
