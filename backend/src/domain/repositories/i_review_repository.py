from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID

from domain.entities.review import Review
from domain.value_objects.agent_type import AgentType
from domain.value_objects.severity import Severity


@dataclass
class CreateFindingParams:
    review_id: UUID
    severity: Severity
    category: str
    agent_source: str
    file_path: str
    line_start: int | None
    line_end: int | None
    title: str
    description: str
    fix_suggestion: str | None


@dataclass
class CreateReviewParams:
    job_id: UUID
    repository_id: UUID
    pr_number: int
    head_sha: str
    pr_url: str
    summary: str | None
    agents_run: list[AgentType]
    langfuse_trace_id: str | None
    findings: list[CreateFindingParams]


class IReviewRepository(ABC):
    @abstractmethod
    async def create(self, params: CreateReviewParams) -> Review:
        """Persist review + all its findings atomically."""

    @abstractmethod
    async def get_by_id(self, review_id: UUID) -> Review | None:
        """Fetch review with its findings."""

    @abstractmethod
    async def get_by_job_id(self, job_id: UUID) -> Review | None:
        """Fetch review by its parent job."""

    @abstractmethod
    async def list_by_repo(
        self, repository_id: UUID, *, page: int = 1, limit: int = 20
    ) -> tuple[list[Review], int]:
        """Return paginated reviews for a repository. Returns (items, total)."""

    @abstractmethod
    async def mark_posted_to_github(self, review_id: UUID) -> Review:
        """Set posted_to_github = True after comments are published."""

    @abstractmethod
    async def update_finding_comment_ids(self, updates: list[tuple[UUID, int]]) -> None:
        """Persist GitHub comment IDs returned after posting inline comments."""
