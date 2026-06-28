from uuid import UUID

from api.schemas.dashboard import RepoDTO
from application.dtos.dashboard_mappers import to_repo_dto
from domain.entities.repository import Repository
from domain.entities.user import User
from domain.errors import EntityNotFoundError, ForbiddenError
from domain.repositories.i_agent_config_repository import IAgentConfigRepository
from domain.repositories.i_repo_repository import IRepoRepository


class ListReposUseCase:
    def __init__(
        self,
        repo_repo: IRepoRepository,
        agent_config_repo: IAgentConfigRepository,
    ) -> None:
        self._repo_repo = repo_repo
        self._agent_config_repo = agent_config_repo

    async def execute(self, user: User) -> list[RepoDTO]:
        repos = await self._repo_repo.list_accessible_for_login(user.login)
        result: list[RepoDTO] = []
        for repo in repos:
            config = await self._agent_config_repo.ensure_default(repo.id)
            result.append(to_repo_dto(repo, config))
        return result


def assert_repo_access(user: User, repo_owner: str) -> None:
    """Raise ForbiddenError when user cannot manage this repository."""
    if user.login != repo_owner:
        raise ForbiddenError(
            f"User '{user.login}' cannot access repository owned by '{repo_owner}'"
        )


async def get_repo_for_user(
    repo_repo: IRepoRepository,
    user: User,
    repository_id: UUID,
) -> Repository:
    repo = await repo_repo.get_by_id(repository_id)
    if repo is None:
        raise EntityNotFoundError(f"Repository {repository_id} not found")
    assert_repo_access(user, repo.owner)
    return repo
