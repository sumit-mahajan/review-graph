"""
ReviewState — the single shared TypedDict flowing through the LangGraph pipeline.

All agent nodes receive this state and return an updated copy.
No agent node may perform DB writes, HTTP calls, or Redis pushes —
those belong in the use case layer that wraps the graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypedDict
from uuid import UUID  # noqa: TC003 — TypedDict fields are evaluated at runtime on Py 3.14+

from domain.value_objects.agent_type import AgentType  # noqa: TC001


@dataclass(frozen=True)
class ChangedFile:
    path: str
    status: str  # added | modified | deleted | renamed
    additions: int
    deletions: int


@dataclass(frozen=True)
class PRMetadata:
    pr_number: int
    title: str
    author: str
    pr_url: str
    base_sha: str
    head_sha: str
    base_branch: str
    head_branch: str
    changed_files: list[ChangedFile] = field(default_factory=list)


@dataclass(frozen=True)
class ContextUnit:
    """One tree-sitter parsed function/class that contains ≥1 changed line."""

    file_path: str
    node_type: str  # function | class | module
    node_name: str
    start_line: int
    end_line: int
    body_old: str  # full old version (empty for added files)
    body_new: str  # full new version
    diff_patch: str  # unified diff for this unit only
    language: str


@dataclass(frozen=True)
class RawDiffChunk:
    """Fallback when tree-sitter parsing is unavailable (F-03 enriches this)."""

    file_path: str
    patch: str
    language: str


@dataclass
class AgentFinding:
    severity: str  # critical|high|medium|low|info
    category: str  # security|perf|arch|test
    agent_source: str
    file_path: str
    line_start: int | None
    line_end: int | None
    title: str
    description: str
    fix_suggestion: str | None


class ReviewState(TypedDict):
    # Identity
    job_id: UUID
    repository_id: UUID
    trace_id: str | None

    # Input — populated before any agent runs
    pr_metadata: PRMetadata
    context_units: list[ContextUnit]  # from tree-sitter (F-03); may be empty
    raw_diff_chunks: list[RawDiffChunk]  # fallback raw diff per file
    rag_chunks: dict[str, list[str]]  # agent_type -> list[chunk_text] (F-03)

    # Pipeline state — mutated by agents
    active_agents: list[AgentType]  # set by SupervisorAgent
    findings: list[AgentFinding]  # accumulated across all agents

    # Output — set by SynthesisAgent
    summary: str | None
    synthesis_complete: bool
