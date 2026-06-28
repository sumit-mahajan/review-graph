from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class InstallationAccessToken:
    token: str
    expires_at: str


@dataclass(frozen=True)
class GithubRepositorySummary:
    github_id: int
    owner: str
    name: str
    full_name: str
    default_branch: str
    language: str | None


class IGithubAppClient(ABC):
    @abstractmethod
    def create_app_jwt(self) -> str:
        """Create a short-lived GitHub App JWT."""

    @abstractmethod
    async def get_installation_access_token(self, installation_id: int) -> InstallationAccessToken:
        """Exchange app JWT for an installation access token."""

    @abstractmethod
    async def list_installation_repositories(
        self, installation_id: int
    ) -> list[GithubRepositorySummary]:
        """List repositories accessible to this installation."""
