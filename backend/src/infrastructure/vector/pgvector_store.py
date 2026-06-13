"""
PgvectorStore — stores and retrieves code chunk embeddings in Postgres via pgvector.

Uses cosine similarity search with the ivfflat index defined in migration 0001.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import structlog
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from domain.repositories.i_embedding_cleanup_repository import IEmbeddingCleanupRepository
from infrastructure.db.models.code_embedding import CodeEmbeddingORM
from infrastructure.vector.embedding_service import EmbeddingService

logger = structlog.get_logger()


@dataclass
class CodeChunkRecord:
    id: UUID
    repository_id: UUID
    commit_sha: str
    file_path: str
    chunk_index: int
    content: str
    node_type: str | None
    node_name: str | None
    language: str | None


class PgvectorStore:
    def __init__(self, session: AsyncSession, embedding_service: EmbeddingService) -> None:
        self._session = session
        self._embedding = embedding_service

    async def store_chunks(
        self,
        *,
        repository_id: UUID,
        commit_sha: str,
        file_path: str,
        chunks: list[dict[str, object]],
        language: str | None = None,
    ) -> int:
        """
        Upsert code chunks for a file.
        Each chunk: {"content": str, "node_type": str|None, "node_name": str|None, "chunk_index": int}
        Returns the number of chunks stored.
        """
        stored = 0
        for chunk in chunks:
            content = str(chunk["content"])
            vector = await self._embedding.embed_text(content)
            vector_str = "[" + ",".join(str(v) for v in vector) + "]"

            # Upsert via raw SQL to handle the VECTOR type cleanly
            await self._session.execute(
                text("""
                    INSERT INTO code_embeddings
                        (repository_id, commit_sha, file_path, chunk_index,
                         content, embedding, node_type, node_name, language)
                    VALUES
                        (:repo_id, :sha, :path, :idx,
                         :content, :vec::vector(768), :node_type, :node_name, :lang)
                    ON CONFLICT (repository_id, commit_sha, file_path, chunk_index)
                    DO UPDATE SET
                        content = EXCLUDED.content,
                        embedding = EXCLUDED.embedding
                """),
                {
                    "repo_id": str(repository_id),
                    "sha": commit_sha,
                    "path": file_path,
                    "idx": int(chunk.get("chunk_index", stored)),
                    "content": content,
                    "vec": vector_str,
                    "node_type": chunk.get("node_type"),
                    "node_name": chunk.get("node_name"),
                    "lang": language,
                },
            )
            stored += 1

        await self._session.commit()
        return stored

    async def retrieve_similar(
        self,
        *,
        repository_id: UUID,
        query_text: str,
        k: int = 5,
        language: str | None = None,
    ) -> list[str]:
        """
        Return the top-k most similar chunk contents to the query text.
        Uses cosine similarity (<=> operator).
        """
        query_vector = await self._embedding.embed_text(query_text)
        vector_str = "[" + ",".join(str(v) for v in query_vector) + "]"

        lang_filter = "AND language = :lang" if language else ""
        raw = await self._session.execute(
            text(f"""
                SELECT content
                FROM code_embeddings
                WHERE repository_id = :repo_id
                {lang_filter}
                ORDER BY embedding <=> :vec::vector(768)
                LIMIT :k
            """),
            {
                "repo_id": str(repository_id),
                "vec": vector_str,
                "k": k,
                **({"lang": language} if language else {}),
            },
        )
        return [row[0] for row in raw.fetchall()]
