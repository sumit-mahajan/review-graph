"""
Golden-PR fixture schema (F-08).

A golden PR is a pre-assembled Review Package: it carries everything the LangGraph
pipeline needs (`pr_metadata` + `context_units` + `raw_diff_chunks`) plus the
ground-truth `expected_findings` a correct review should surface. Fixtures are
authored synthetically (no live GitHub) so eval runs are deterministic and free of
network/quota cost. See `architecture.mdc` § Review Package Assembly.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from infrastructure.ai.graph.state import (
    ChangedFile,
    ContextUnit,
    PRMetadata,
    RawDiffChunk,
    ReviewState,
)

FlawCategory = Literal["security", "perf", "arch", "test"]
PRCategory = Literal["security", "perf", "arch", "test", "clean"]


class ExpectedFinding(BaseModel):
    """A single ground-truth issue a correct review should flag."""

    model_config = ConfigDict(extra="forbid")

    category: FlawCategory
    file_path: str
    line_start: int
    line_end: int
    title: str          # human-readable description of what SHOULD be flagged
    rationale: str      # why it is a flaw — fed to the LLM-as-judge matcher


class FixtureContextUnit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_path: str
    node_type: str = "function"
    node_name: str
    start_line: int
    end_line: int
    body_old: str = ""
    body_new: str
    diff_patch: str = ""
    language: str = "python"


class FixtureRawDiff(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_path: str
    patch: str
    language: str = "python"


class FixtureChangedFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    status: str = "modified"
    additions: int = 0
    deletions: int = 0


class GoldenPR(BaseModel):
    """One synthetic known-bad (or clean) PR fixture."""

    model_config = ConfigDict(extra="forbid")

    id: str
    category: PRCategory
    title: str
    author: str = "eval-bot"
    base_sha: str = "0" * 40
    head_sha: str = "1" * 40
    base_branch: str = "main"
    head_branch: str = "feature"
    changed_files: list[FixtureChangedFile] = Field(default_factory=list)
    context_units: list[FixtureContextUnit] = Field(default_factory=list)
    raw_diff_chunks: list[FixtureRawDiff] = Field(default_factory=list)
    expected_findings: list[ExpectedFinding] = Field(default_factory=list)

    def to_review_state(
        self,
        *,
        job_id: UUID | None = None,
        repository_id: UUID | None = None,
    ) -> ReviewState:
        """Convert this fixture into the LangGraph initial ReviewState."""
        changed = self.changed_files or [
            FixtureChangedFile(path=cu.file_path) for cu in self.context_units
        ]
        pr_metadata = PRMetadata(
            pr_number=0,
            title=self.title,
            author=self.author,
            pr_url=f"https://example.test/eval/{self.id}",
            base_sha=self.base_sha,
            head_sha=self.head_sha,
            base_branch=self.base_branch,
            head_branch=self.head_branch,
            changed_files=[
                ChangedFile(
                    path=c.path,
                    status=c.status,
                    additions=c.additions,
                    deletions=c.deletions,
                )
                for c in changed
            ],
        )
        context_units = [
            ContextUnit(
                file_path=cu.file_path,
                node_type=cu.node_type,
                node_name=cu.node_name,
                start_line=cu.start_line,
                end_line=cu.end_line,
                body_old=cu.body_old,
                body_new=cu.body_new,
                diff_patch=cu.diff_patch,
                language=cu.language,
            )
            for cu in self.context_units
        ]
        raw_diff_chunks = [
            RawDiffChunk(file_path=r.file_path, patch=r.patch, language=r.language)
            for r in self.raw_diff_chunks
        ]
        return {
            "job_id": job_id or uuid4(),
            "repository_id": repository_id or uuid4(),
            "trace_id": None,
            "pr_metadata": pr_metadata,
            "context_units": context_units,
            "raw_diff_chunks": raw_diff_chunks,
            "rag_chunks": {},
            "active_agents": [],
            "findings": [],
            "summary": None,
            "synthesis_complete": False,
        }


def load_golden_pr(path: Path) -> GoldenPR:
    return GoldenPR.model_validate_json(path.read_text(encoding="utf-8"))


def load_golden_set(root: Path) -> list[GoldenPR]:
    """Load every *.json fixture under root (recursively), sorted by id."""
    fixtures = [
        load_golden_pr(p)
        for p in sorted(root.rglob("*.json"))
        if p.is_file()
    ]
    return sorted(fixtures, key=lambda g: g.id)


def golden_root() -> Path:
    return Path(__file__).resolve().parent / "golden_prs"


def dump_golden_pr(golden: GoldenPR, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(golden.model_dump(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
