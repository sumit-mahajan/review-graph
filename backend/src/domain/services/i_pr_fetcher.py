from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class PullRequestDiff:
    """Raw diff data for one PR fetched from the GitHub API."""

    pr_number: int
    base_sha: str
    head_sha: str
    base_branch: str
    head_branch: str
    file_patches: list["FilePatch"]


@dataclass(frozen=True)
class FilePatch:
    path: str
    status: str  # added | modified | deleted | renamed
    additions: int
    deletions: int
    patch: str  # unified diff text (may be empty for binary files)
    old_path: str | None = None  # set for renames


class IPrFetcher(ABC):
    @abstractmethod
    async def fetch_diff(
        self,
        installation_id: int,
        owner: str,
        repo: str,
        base_sha: str,
        head_sha: str,
    ) -> PullRequestDiff:
        """Fetch the full base→head diff for a PR."""

    @abstractmethod
    async def fetch_file_content(
        self,
        installation_id: int,
        owner: str,
        repo: str,
        path: str,
        ref: str,
    ) -> str:
        """Fetch the raw content of a file at a given git ref."""

    @abstractmethod
    async def fetch_diff_for_pr(
        self,
        installation_id: int,
        owner: str,
        repo: str,
        pr_number: int,
    ) -> PullRequestDiff:
        """Fetch the current base→head diff for an open pull request."""
