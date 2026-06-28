"""
EmbeddingService — wraps GeminiClient.embed for code chunk embedding.

Returns 768-dimensional vectors via gemini-embedding-001 (Matryoshka-truncated).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from infrastructure.ai.gemini_client import GeminiClient

logger = structlog.get_logger()

MAX_CHARS_PER_CHUNK = 8000  # ~2k tokens; well within embedding model limits


class EmbeddingService:
    def __init__(self, gemini: GeminiClient) -> None:
        self._gemini = gemini

    async def embed_text(self, text: str) -> list[float]:
        """Embed document text for storage. Truncates if too long."""
        truncated = text[:MAX_CHARS_PER_CHUNK]
        return await self._gemini.embed(truncated, task_type="RETRIEVAL_DOCUMENT")

    async def embed_query(self, text: str) -> list[float]:
        """Embed a search query for similarity retrieval."""
        truncated = text[:MAX_CHARS_PER_CHUNK]
        return await self._gemini.embed(truncated, task_type="RETRIEVAL_QUERY")

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts sequentially. Returns parallel list of vectors."""
        results: list[list[float]] = []
        for text in texts:
            vector = await self.embed_text(text)
            results.append(vector)
        return results
