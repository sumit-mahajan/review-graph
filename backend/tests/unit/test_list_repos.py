"""Tests for ListReposUseCase."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from application.use_cases.list_repos import ListReposUseCase, assert_repo_access
from domain.entities.user import User
from domain.errors import ForbiddenError
from domain.repositories.i_repo_repository import UpsertRepositoryParams
from tests.support.memory_agent_config_repository import InMemoryAgentConfigRepository
from tests.support.memory_repositories import InMemoryRepoRepository


def _user(login: str = "acme-corp") -> User:
    now = datetime.now(UTC)
    return User(
        id=uuid4(),
        github_id=1,
        login=login,
        email=None,
        avatar_url=None,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_list_repos_returns_accessible_repos() -> None:
    repo_repo = InMemoryRepoRepository()
    config_repo = InMemoryAgentConfigRepository()
    installation_id = uuid4()

    await repo_repo.upsert(
        UpsertRepositoryParams(
            github_id=1,
            installation_id=installation_id,
            owner="acme-corp",
            name="backend",
            full_name="acme-corp/backend",
            default_branch="main",
            language="Python",
        )
    )

    use_case = ListReposUseCase(repo_repo, config_repo)
    repos = await use_case.execute(_user())
    assert len(repos) == 1
    assert repos[0].full_name == "acme-corp/backend"
    assert repos[0].agent_config.security_enabled is True


def test_assert_repo_access_denies_other_owner() -> None:
    with pytest.raises(ForbiddenError):
        assert_repo_access(_user("other"), "acme-corp")
