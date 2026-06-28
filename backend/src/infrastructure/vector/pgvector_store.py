"""
PgvectorStore — stores and retrieves code chunk embeddings in Postgres via pgvector.

Uses cosine similarity search with the ivfflat index defined in migration 0001.
Reuses existing embeddings when chunk content is unchanged across commit SHAs
(content_hash dedup — migration 0004).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import text

from domain.services.i_code_embedding_store import ICodeEmbeddingStore
from domain.utils.content_hash import hash_chunk_content
from infrastructure.ai.gemini_client import EMBEDDING_DIMENSION

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

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


class PgvectorStore(ICodeEmbeddingStore):
    def __init__(self, session: AsyncSession, embedding_service: EmbeddingService) -> None:
        self._session = session
        self._embedding = embedding_service

    async def store_file_chunks(
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
        Each chunk: content, node_type, node_name, chunk_index keys.
        Returns the number of chunks stored.
        """
        prepared: list[tuple[int, str, str, dict[str, object]]] = []
        for chunk in chunks:
            content = str(chunk["content"]).strip()
            if not content:
                continue
            chunk_index = int(str(chunk.get("chunk_index", len(prepared))))
            content_hash = hash_chunk_content(content)
            prepared.append((chunk_index, content, content_hash, chunk))

        if not prepared:
            return 0

        reuse_map = await self._find_reusable_embeddings(
            repository_id=repository_id,
            file_path=file_path,
            content_hashes={item[2] for item in prepared},
        )

        stored = 0
        embedded = 0
        reused = 0
        vec_type = f"vector({EMBEDDING_DIMENSION})"
        insert_sql = text(f"""
            INSERT INTO code_embeddings
                (repository_id, commit_sha, file_path, chunk_index,
                 content, content_hash, embedding, node_type, node_name, language)
            VALUES
                (:repo_id, :sha, :path, :idx,
                 :content, :content_hash, CAST(:vec AS {vec_type}), :node_type, :node_name, :lang)
            ON CONFLICT (repository_id, commit_sha, file_path, chunk_index)
            DO UPDATE SET
                content = EXCLUDED.content,
                content_hash = EXCLUDED.content_hash,
                embedding = EXCLUDED.embedding
        """)
        try:
            for chunk_index, content, content_hash, chunk in prepared:
                vector_str = reuse_map.get(content_hash)
                if vector_str is None:
                    vector = await self._embedding.embed_text(content)
                    vector_str = "[" + ",".join(str(v) for v in vector) + "]"
                    reuse_map[content_hash] = vector_str
                    embedded += 1
                else:
                    reused += 1

                await self._session.execute(
                    insert_sql,
                    {
                        "repo_id": str(repository_id),
                        "sha": commit_sha,
                        "path": file_path,
                        "idx": chunk_index,
                        "content": content,
                        "content_hash": content_hash,
                        "vec": vector_str,
                        "node_type": chunk.get("node_type"),
                        "node_name": chunk.get("node_name"),
                        "lang": language,
                    },
                )
                stored += 1

            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

        if reused:
            await logger.ainfo(
                "embedding_chunks_reused",
                file_path=file_path,
                commit_sha=commit_sha[:8],
                reused=reused,
                embedded=embedded,
            )
        return stored

    async def _find_reusable_embeddings(
        self,
        *,
        repository_id: UUID,
        file_path: str,
        content_hashes: set[str],
    ) -> dict[str, str]:
        """Return content_hash → vector literal for chunks already embedded in this repo/file."""
        if not content_hashes:
            return {}

        raw = await self._session.execute(
            text("""
                SELECT DISTINCT ON (content_hash)
                    content_hash,
                    embedding::text
                FROM code_embeddings
                WHERE repository_id = :repo_id
                  AND file_path = :path
                  AND content_hash = ANY(:hashes)
                ORDER BY content_hash, created_at DESC
            """),
            {
                "repo_id": str(repository_id),
                "path": file_path,
                "hashes": list(content_hashes),
            },
        )

        reuse: dict[str, str] = {}
        for content_hash, embedding_text in raw.fetchall():
            if content_hash and embedding_text:
                reuse[str(content_hash)] = str(embedding_text)
        return reuse

    async def retrieve_similar(
        self,
        *,
        repository_id: UUID,
        commit_sha: str,
        query_text: str,
        k: int = 5,
        language: str | None = None,
    ) -> list[str]:
        """
        Return the top-k most similar chunk contents to the query text.
        Scoped to a single commit SHA. Uses cosine similarity (<=> operator).
        """
        query_vector = await self._embedding.embed_query(query_text)
        vector_str = "[" + ",".join(str(v) for v in query_vector) + "]"

        lang_filter = "AND language = :lang" if language else ""
        vec_type = f"vector({EMBEDDING_DIMENSION})"
        raw = await self._session.execute(
            text(f"""
                SELECT content
                FROM code_embeddings
                WHERE repository_id = :repo_id
                  AND commit_sha = :sha
                {lang_filter}
                ORDER BY embedding <=> CAST(:vec AS {vec_type})
                LIMIT :k
            """),
            {
                "repo_id": str(repository_id),
                "sha": commit_sha,
                "vec": vector_str,
                "k": k,
                **({"lang": language} if language else {}),
            },
        )
        return [row[0] for row in raw.fetchall()]
