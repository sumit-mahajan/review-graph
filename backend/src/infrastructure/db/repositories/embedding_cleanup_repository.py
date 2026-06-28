from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from domain.repositories.i_embedding_cleanup_repository import IEmbeddingCleanupRepository
from infrastructure.db.models.code_embedding import CodeEmbeddingORM


class PostgresEmbeddingCleanupRepository(IEmbeddingCleanupRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def delete_by_repo_and_sha(self, repository_id: UUID, commit_sha: str) -> int:
        result = await self._session.execute(
            delete(CodeEmbeddingORM).where(
                CodeEmbeddingORM.repository_id == repository_id,
                CodeEmbeddingORM.commit_sha == commit_sha,
            )
        )
        await self._session.commit()
        return int(getattr(result, "rowcount", 0) or 0)

    async def delete_older_than_days(self, days: int) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        result = await self._session.execute(
            delete(CodeEmbeddingORM).where(CodeEmbeddingORM.created_at < cutoff)
        )
        await self._session.commit()
        return int(getattr(result, "rowcount", 0) or 0)
