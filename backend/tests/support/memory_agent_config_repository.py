"""In-memory agent config repository for unit tests."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from domain.entities.agent_config import AgentConfig
from domain.errors import EntityNotFoundError
from domain.repositories.i_agent_config_repository import (
    IAgentConfigRepository,
    UpdateAgentConfigParams,
)


class InMemoryAgentConfigRepository(IAgentConfigRepository):
    def __init__(self) -> None:
        self._configs: dict[UUID, AgentConfig] = {}

    async def get_by_repository_id(self, repository_id: UUID) -> AgentConfig | None:
        return self._configs.get(repository_id)

    async def ensure_default(self, repository_id: UUID) -> AgentConfig:
        existing = self._configs.get(repository_id)
        if existing:
            return existing
        now = datetime.now(UTC)
        config = AgentConfig(
            id=uuid4(),
            repository_id=repository_id,
            security_enabled=True,
            perf_enabled=True,
            arch_enabled=True,
            test_enabled=True,
            min_severity="medium",
            created_at=now,
            updated_at=now,
        )
        self._configs[repository_id] = config
        return config

    async def update(self, repository_id: UUID, params: UpdateAgentConfigParams) -> AgentConfig:
        config = self._configs.get(repository_id)
        if config is None:
            raise EntityNotFoundError(f"Agent config for repository {repository_id} not found")
        if params.security_enabled is not None:
            config.security_enabled = params.security_enabled
        if params.perf_enabled is not None:
            config.perf_enabled = params.perf_enabled
        if params.arch_enabled is not None:
            config.arch_enabled = params.arch_enabled
        if params.test_enabled is not None:
            config.test_enabled = params.test_enabled
        if params.min_severity is not None:
            config.min_severity = params.min_severity
        config.updated_at = datetime.now(UTC)
        return config
