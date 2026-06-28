"""Stable content hashes for embedding deduplication."""

from __future__ import annotations

import hashlib


def hash_chunk_content(content: str) -> str:
    """SHA-256 hex digest of normalized chunk text (strip whitespace)."""
    return hashlib.sha256(content.strip().encode("utf-8")).hexdigest()
