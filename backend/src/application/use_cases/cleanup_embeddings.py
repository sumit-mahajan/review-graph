"""
CleanupEmbeddingsUseCase — deletes stale pgvector embeddings.

Triggered by two paths:
  1. pull_request.closed webhook → delete embeddings for that specific head_sha
  2. Weekly background job → delete all rows older than N days
"""

from uuid import UUID

import structlog

from domain.repositories.i_embedding_cleanup_repository import IEmbeddingCleanupRepository

logger = structlog.get_logger()

STALE_DAYS = 30


class CleanupEmbeddingsUseCase:
    def __init__(self, cleanup_repo: IEmbeddingCleanupRepository) -> None:
        self._repo = cleanup_repo

    async def cleanup_for_pr(self, repository_id: UUID, head_sha: str) -> int:
        """Delete embeddings for a closed PR's head SHA."""
        deleted = await self._repo.delete_by_repo_and_sha(repository_id, head_sha)
        await logger.ainfo(
            "embeddings_deleted_for_pr",
            repository_id=str(repository_id),
            head_sha=head_sha,
            rows_deleted=deleted,
        )
        return deleted

    async def cleanup_stale(self, days: int = STALE_DAYS) -> int:
        """Delete all embeddings older than ``days`` days."""
        deleted = await self._repo.delete_older_than_days(days)
        await logger.ainfo("stale_embeddings_deleted", days=days, rows_deleted=deleted)
        return deleted
