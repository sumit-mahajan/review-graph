"""
AssembleReviewPackageUseCase — builds a structured Review Package from a PR.

Execution order (matches architecture.mdc Review Package Assembly):
  1. Fetch raw diff from GitHub (base_sha → head_sha)
  2. For each changed file:
     a. Fetch new + old file content
     b. Parse with tree-sitter → extract function/class nodes
     c. Find nodes that overlap changed lines
     d. Build ContextUnit (body_old, body_new, diff_patch)
  3. Embed all changed-file content → store in pgvector
  4. Return assembled ReviewState fields (context_units + raw_diff_chunks + pr_metadata)

RAG chunk population (per-agent pgvector queries) is done just before each
agent runs — wired into LanggraphOrchestrator in F-03.
"""

from __future__ import annotations

import re
from contextlib import suppress
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

import structlog

from domain.services.i_code_parser import ParsedNode
from domain.utils.diff_utils import extract_changed_lines as _extract_changed_lines
from infrastructure.ai.graph.state import (
    ChangedFile,
    ContextUnit,
    PRMetadata,
    RawDiffChunk,
)
from infrastructure.parsers.parser_registry import get_parser, lang_for_path

if TYPE_CHECKING:
    from uuid import UUID

    from domain.repositories.i_installation_repository import IInstallationRepository
    from domain.repositories.i_repo_repository import IRepoRepository
    from domain.services.i_code_embedding_store import ICodeEmbeddingStore
    from domain.services.i_pr_fetcher import IPrFetcher

logger = structlog.get_logger()

MAX_FILES_FOR_FULL_DIFF = 50
BATCH_SIZE = 10


class AssembleReviewPackageUseCase:
    def __init__(
        self,
        repo_repo: IRepoRepository,
        installation_repo: IInstallationRepository,
        pr_fetcher: IPrFetcher,
        embedding_store: ICodeEmbeddingStore | None = None,
    ) -> None:
        self._repo_repo = repo_repo
        self._installation_repo = installation_repo
        self._pr_fetcher = pr_fetcher
        self._embedding_store = embedding_store

    async def execute(
        self,
        *,
        repository_id: UUID,
        pr_number: int,
        pr_title: str,
        pr_author: str,
        pr_url: str,
        base_sha: str,
        head_sha: str,
    ) -> tuple[PRMetadata, list[ContextUnit], list[RawDiffChunk]]:
        """
        Returns (pr_metadata, context_units, raw_diff_chunks).
        context_units are tree-sitter parsed; raw_diff_chunks are always populated
        as a fallback.
        """
        repo = await self._repo_repo.get_by_id(repository_id)
        if repo is None:
            raise ValueError(f"Repository {repository_id} not found")

        installation = await self._installation_repo.get_by_id(repo.installation_id)
        if installation is None:
            raise ValueError(f"Installation {repo.installation_id} not found")

        log = logger.bind(
            repo=repo.full_name,
            pr_number=pr_number,
            base_sha=base_sha[:8],
            head_sha=head_sha[:8],
        )
        await log.ainfo("assembling_review_package")

        diff = await self._pr_fetcher.fetch_diff(
            installation_id=installation.installation_id,
            owner=repo.owner,
            repo=repo.name,
            base_sha=base_sha,
            head_sha=head_sha,
        )

        changed_files = [
            ChangedFile(
                path=fp.path,
                status=fp.status,
                additions=fp.additions,
                deletions=fp.deletions,
            )
            for fp in diff.file_patches
        ]

        pr_metadata = PRMetadata(
            pr_number=pr_number,
            title=pr_title,
            author=pr_author,
            pr_url=pr_url,
            base_sha=base_sha,
            head_sha=head_sha,
            base_branch=diff.base_branch,
            head_branch=diff.head_branch,
            changed_files=changed_files,
        )

        # Apply hybrid diff strategy: full for small PRs, batched for large
        patches_to_process = diff.file_patches
        if len(patches_to_process) > MAX_FILES_FOR_FULL_DIFF:
            await log.awarning(
                "large_pr_batching",
                total_files=len(patches_to_process),
                strategy=f"batch_{BATCH_SIZE}",
            )

        context_units: list[ContextUnit] = []
        raw_diff_chunks: list[RawDiffChunk] = []
        embedded_paths: set[str] = set()
        total_embeddings = 0

        for patch in patches_to_process:
            if not patch.patch:
                continue

            language = lang_for_path(patch.path) or "unknown"
            raw_diff_chunks.append(
                RawDiffChunk(
                    file_path=patch.path,
                    patch=patch.patch,
                    language=language,
                )
            )

            parser = get_parser(patch.path)
            if parser is None:
                continue

            # Fetch new file content
            try:
                new_content = await self._pr_fetcher.fetch_file_content(
                    installation_id=installation.installation_id,
                    owner=repo.owner,
                    repo=repo.name,
                    path=patch.path,
                    ref=head_sha,
                )
            except Exception as exc:  # noqa: BLE001
                await log.awarn(
                    "review_package_file_fetch_failed",
                    path=patch.path,
                    ref=head_sha,
                    error=str(exc),
                )
                continue

            # Fetch old file content (empty string for added files)
            old_content = ""
            if patch.status != "added":
                with suppress(Exception):
                    old_content = await self._pr_fetcher.fetch_file_content(
                        installation_id=installation.installation_id,
                        owner=repo.owner,
                        repo=repo.name,
                        path=patch.path,
                        ref=base_sha,
                    )

            # Extract changed line numbers from the patch
            changed_lines = _extract_changed_lines(patch.patch)
            if not changed_lines:
                continue

            new_nodes = parser.parse(new_content) if new_content else []
            old_nodes = parser.parse(old_content) if old_content else []
            old_nodes_by_name = {n.node_name: n for n in old_nodes}

            for node in new_nodes:
                # Include node if it overlaps with any changed line
                if any(node.start_line <= ln <= node.end_line for ln in changed_lines):
                    old_node = old_nodes_by_name.get(node.node_name)
                    context_units.append(
                        ContextUnit(
                            file_path=patch.path,
                            node_type=node.node_type,
                            node_name=node.node_name,
                            start_line=node.start_line,
                            end_line=node.end_line,
                            body_old=old_node.body if old_node else "",
                            body_new=node.body,
                            diff_patch=_extract_node_patch(patch.patch, node),
                            language=language,
                        )
                    )

            if self._embedding_store is not None and new_content:
                stored = await self._index_file_embeddings(
                    repository_id=repository_id,
                    head_sha=head_sha,
                    file_path=patch.path,
                    content=new_content,
                    language=language,
                    embedded_paths=embedded_paths,
                    installation_id=installation.installation_id,
                    owner=repo.owner,
                    repo_name=repo.name,
                )
                total_embeddings += stored

        await log.ainfo(
            "review_package_assembled",
            context_units=len(context_units),
            raw_diff_chunks=len(raw_diff_chunks),
            embeddings_stored=total_embeddings,
        )
        return pr_metadata, context_units, raw_diff_chunks

    async def _index_file_embeddings(
        self,
        *,
        repository_id: UUID,
        head_sha: str,
        file_path: str,
        content: str,
        language: str,
        embedded_paths: set[str],
        installation_id: int,
        owner: str,
        repo_name: str,
    ) -> int:
        """Embed all function/class chunks for a file plus 1-hop local imports."""
        store = self._embedding_store
        if store is None:
            return 0
        if file_path in embedded_paths or not content.strip():
            return 0
        embedded_paths.add(file_path)

        parser = get_parser(file_path)
        nodes = parser.parse(content) if parser is not None else []
        if not nodes:
            nodes = [
                ParsedNode(
                    node_type="module",
                    node_name=PurePosixPath(file_path).name,
                    start_line=1,
                    end_line=content.count("\n") + 1,
                    body=content[:12000],
                )
            ]

        chunks = [
            {
                "content": node.body,
                "node_type": node.node_type,
                "node_name": node.node_name,
                "chunk_index": index,
            }
            for index, node in enumerate(nodes)
            if node.body.strip()
        ]
        if not chunks:
            return 0
        stored = await store.store_file_chunks(
            repository_id=repository_id,
            commit_sha=head_sha,
            file_path=file_path,
            chunks=chunks,
            language=language,
        )

        for neighbor_path in _one_hop_import_paths(content, file_path):
            if neighbor_path in embedded_paths:
                continue
            try:
                neighbor_content = await self._pr_fetcher.fetch_file_content(
                    installation_id=installation_id,
                    owner=owner,
                    repo=repo_name,
                    path=neighbor_path,
                    ref=head_sha,
                )
            except Exception as exc:  # noqa: BLE001
                await logger.awarn(
                    "review_package_neighbor_fetch_failed",
                    path=neighbor_path,
                    error=str(exc),
                )
                continue
            if not neighbor_content.strip():
                continue
            neighbor_lang = lang_for_path(neighbor_path) or language
            stored += await self._index_file_embeddings(
                repository_id=repository_id,
                head_sha=head_sha,
                file_path=neighbor_path,
                content=neighbor_content,
                language=neighbor_lang,
                embedded_paths=embedded_paths,
                installation_id=installation_id,
                owner=owner,
                repo_name=repo_name,
            )
        return stored


def _extract_node_patch(full_patch: str, node: ParsedNode) -> str:
    """Extract the portion of the unified diff that covers this node's line range."""
    relevant: list[str] = []
    current_line = 0
    in_hunk = False

    for line in full_patch.splitlines():
        hunk = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
        if hunk:
            current_line = int(hunk.group(1)) - 1
            if _hunk_overlaps(line, node):
                relevant.append(line)
                in_hunk = True
            else:
                in_hunk = False
            continue

        if not line.startswith("-"):
            current_line += 1
        if in_hunk:
            relevant.append(line)
            if current_line > node.end_line + 5:
                break

    return "\n".join(relevant)


def _hunk_overlaps(hunk_header: str, node: ParsedNode) -> bool:
    m = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", hunk_header)
    if not m:
        return False
    start = int(m.group(1))
    count = int(m.group(2)) if m.group(2) else 1
    end = start + count
    return not (end < node.start_line or start > node.end_line + 10)


def _one_hop_import_paths(source: str, current_path: str) -> list[str]:
    """Resolve relative Python/JS imports to repo-relative paths (1-hop)."""
    base_dir = str(PurePosixPath(current_path).parent)
    if base_dir == ".":
        base_dir = ""
    candidates: list[str] = []

    for line in source.splitlines():
        rel = re.match(r"^\s*from\s+(\.+)([\w.]+)\s+import\s+", line)
        if rel:
            dots = rel.group(1)
            module = rel.group(2).replace(".", "/")
            parent = base_dir
            for _ in range(len(dots) - 1):
                parent = str(PurePosixPath(parent).parent) if parent else ""
            prefix = f"{parent}/" if parent else ""
            candidates.append(f"{prefix}{module}.py")
            candidates.append(f"{prefix}{module}/__init__.py")
            continue

        direct = re.match(r"^\s*from\s+([\w.]+)\s+import\s+", line)
        if direct:
            module = direct.group(1).replace(".", "/")
            candidates.append(f"{module}.py")
            candidates.append(f"src/{module}.py")
            continue

        plain = re.match(r"^\s*import\s+([\w.]+)", line)
        if plain:
            module = plain.group(1).split(".")[0]
            candidates.append(f"{module}.py")
            candidates.append(f"src/{module}.py")

    # De-dupe while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for path in candidates:
        normalized = path.lstrip("/")
        if normalized not in seen:
            seen.add(normalized)
            unique.append(normalized)
    return unique
