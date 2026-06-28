from uuid import UUID

from api.schemas.dashboard import AgentConfigDTO, UpdateAgentConfigRequest
from application.dtos.dashboard_mappers import to_agent_config_dto
from application.use_cases.list_repos import get_repo_for_user
from domain.entities.user import User
from domain.repositories.i_agent_config_repository import (
    IAgentConfigRepository,
    UpdateAgentConfigParams,
)
from domain.repositories.i_repo_repository import IRepoRepository


class ConfigureRepoUseCase:
    def __init__(
        self,
        repo_repo: IRepoRepository,
        agent_config_repo: IAgentConfigRepository,
    ) -> None:
        self._repo_repo = repo_repo
        self._agent_config_repo = agent_config_repo

    async def get_config(self, user: User, repository_id: UUID) -> AgentConfigDTO:
        repo = await get_repo_for_user(self._repo_repo, user, repository_id)
        config = await self._agent_config_repo.ensure_default(repo.id)
        return to_agent_config_dto(config)

    async def update_config(
        self,
        user: User,
        repository_id: UUID,
        body: UpdateAgentConfigRequest,
    ) -> AgentConfigDTO:
        repo = await get_repo_for_user(self._repo_repo, user, repository_id)

        if body.is_active is not None:
            await self._repo_repo.update_is_active(repo.id, body.is_active)

        config = await self._agent_config_repo.ensure_default(repo.id)
        has_config_updates = any(
            value is not None
            for value in (
                body.security_enabled,
                body.perf_enabled,
                body.arch_enabled,
                body.test_enabled,
                body.min_severity,
            )
        )
        if has_config_updates:
            config = await self._agent_config_repo.update(
                repo.id,
                UpdateAgentConfigParams(
                    security_enabled=body.security_enabled,
                    perf_enabled=body.perf_enabled,
                    arch_enabled=body.arch_enabled,
                    test_enabled=body.test_enabled,
                    min_severity=body.min_severity,
                ),
            )
        return to_agent_config_dto(config)
