"""Tests for embedding content-hash deduplication."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from domain.utils.content_hash import hash_chunk_content
from infrastructure.vector.pgvector_store import PgvectorStore


def test_hash_chunk_content_normalizes_whitespace() -> None:
    assert hash_chunk_content("hello") == hash_chunk_content("  hello\n")
    assert len(hash_chunk_content("x")) == 64


@pytest.mark.asyncio
async def test_store_skips_gemini_when_hash_exists() -> None:
    content = "def unchanged(): return 1"
    content_hash = hash_chunk_content(content)
    session = AsyncMock()
    lookup_rows = MagicMock()
    lookup_rows.fetchall.return_value = [(content_hash, "[0.1,0.2,0.3]")]
    session.execute = AsyncMock(return_value=lookup_rows)

    embedding_svc = AsyncMock()
    store = PgvectorStore(session, embedding_svc)

    stored = await store.store_file_chunks(
        repository_id=uuid4(),
        commit_sha="c" * 40,
        file_path="src/a.py",
        chunks=[
            {
                "content": content,
                "chunk_index": 0,
                "node_type": "function",
                "node_name": "unchanged",
            }
        ],
    )

    assert stored == 1
    embedding_svc.embed_text.assert_not_awaited()
    assert session.execute.await_count == 2  # lookup + insert


@pytest.mark.asyncio
async def test_store_embeds_when_no_matching_hash() -> None:
    session = AsyncMock()
    lookup_rows = MagicMock()
    lookup_rows.fetchall.return_value = []
    session.execute = AsyncMock(return_value=lookup_rows)

    embedding_svc = AsyncMock()
    embedding_svc.embed_text.return_value = [0.1, 0.2, 0.3]
    store = PgvectorStore(session, embedding_svc)

    stored = await store.store_file_chunks(
        repository_id=uuid4(),
        commit_sha="d" * 40,
        file_path="src/b.py",
        chunks=[{"content": "def new_fn(): pass", "chunk_index": 0}],
    )

    assert stored == 1
    embedding_svc.embed_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_store_dedupes_identical_chunks_in_one_batch() -> None:
    session = AsyncMock()
    lookup_rows = MagicMock()
    lookup_rows.fetchall.return_value = []
    session.execute = AsyncMock(return_value=lookup_rows)

    embedding_svc = AsyncMock()
    embedding_svc.embed_text.return_value = [0.5, 0.6]
    store = PgvectorStore(session, embedding_svc)

    body = "def dup(): pass"
    stored = await store.store_file_chunks(
        repository_id=uuid4(),
        commit_sha="e" * 40,
        file_path="src/c.py",
        chunks=[
            {"content": body, "chunk_index": 0},
            {"content": body, "chunk_index": 1},
        ],
    )

    assert stored == 2
    embedding_svc.embed_text.assert_awaited_once()
