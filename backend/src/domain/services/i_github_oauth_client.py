from abc import ABC, abstractmethod
from dataclasses import dataclass

from domain.entities.user import User


@dataclass(frozen=True)
class GithubOAuthProfile:
    github_id: int
    login: str
    email: str | None
    avatar_url: str | None


@dataclass(frozen=True)
class AuthToken:
    access_token: str
    user: User


class IGithubOAuthClient(ABC):
    @abstractmethod
    def build_authorize_url(self, state: str) -> str:
        """Return the GitHub OAuth authorize redirect URL."""

    @abstractmethod
    async def exchange_code(self, code: str) -> GithubOAuthProfile:
        """Exchange authorization code for user profile."""
