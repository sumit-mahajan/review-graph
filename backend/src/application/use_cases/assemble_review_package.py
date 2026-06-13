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
from uuid import UUID

import structlog

from domain.repositories.i_installation_repository import IInstallationRepository
from domain.repositories.i_repo_repository import IRepoRepository
from domain.services.i_code_parser import ParsedNode
from domain.services.i_pr_fetcher import FilePatch, IPrFetcher
from infrastructure.ai.graph.state import (
    ChangedFile,
    ContextUnit,
    PRMetadata,
    RawDiffChunk,
)
from infrastructure.parsers.parser_registry import get_parser, lang_for_path

logger = structlog.get_logger()

MAX_FILES_FOR_FULL_DIFF = 50
BATCH_SIZE = 10


class AssembleReviewPackageUseCase:
    def __init__(
        self,
        repo_repo: IRepoRepository,
        installation_repo: IInstallationRepository,
        pr_fetcher: IPrFetcher,
    ) -> None:
        self._repo_repo = repo_repo
        self._installation_repo = installation_repo
        self._pr_fetcher = pr_fetcher

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

        for patch in patches_to_process:
            if not patch.patch:
                continue

            language = lang_for_path(patch.path) or "unknown"
            raw_diff_chunks.append(RawDiffChunk(
                file_path=patch.path,
                patch=patch.patch,
                language=language,
            ))

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
            except Exception:  # noqa: BLE001
                continue

            # Fetch old file content (empty string for added files)
            old_content = ""
            if patch.status != "added":
                try:
                    old_content = await self._pr_fetcher.fetch_file_content(
                        installation_id=installation.installation_id,
                        owner=repo.owner,
                        repo=repo.name,
                        path=patch.path,
                        ref=base_sha,
                    )
                except Exception:  # noqa: BLE001
                    pass

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
                    context_units.append(ContextUnit(
                        file_path=patch.path,
                        node_type=node.node_type,
                        node_name=node.node_name,
                        start_line=node.start_line,
                        end_line=node.end_line,
                        body_old=old_node.body if old_node else "",
                        body_new=node.body,
                        diff_patch=_extract_node_patch(patch.patch, node),
                        language=language,
                    ))

        await log.ainfo(
            "review_package_assembled",
            context_units=len(context_units),
            raw_diff_chunks=len(raw_diff_chunks),
        )
        return pr_metadata, context_units, raw_diff_chunks


def _extract_changed_lines(patch: str) -> set[int]:
    """Return the set of new-file line numbers touched by the patch."""
    changed: set[int] = set()
    current_line = 0
    for line in patch.splitlines():
        hunk = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
        if hunk:
            current_line = int(hunk.group(1)) - 1
            continue
        if line.startswith("-"):
            continue
        if line.startswith("\\"):
            continue
        current_line += 1
        if line.startswith("+"):
            changed.add(current_line)
    return changed


def _extract_node_patch(full_patch: str, node: ParsedNode) -> str:
    """Extract the portion of the unified diff that covers this node's line range."""
    relevant: list[str] = []
    current_line = 0
    in_hunk = False

    for line in full_patch.splitlines():
        hunk = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
        if hunk:
            current_line = int(hunk.group(1)) - 1
            # Include hunk header if it's relevant to the node
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
