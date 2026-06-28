from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID

from domain.entities.agent_config import AgentConfig


@dataclass
class UpdateAgentConfigParams:
    security_enabled: bool | None = None
    perf_enabled: bool | None = None
    arch_enabled: bool | None = None
    test_enabled: bool | None = None
    min_severity: str | None = None


class IAgentConfigRepository(ABC):
    @abstractmethod
    async def get_by_repository_id(self, repository_id: UUID) -> AgentConfig | None:
        """Fetch agent config for a repository."""

    @abstractmethod
    async def ensure_default(self, repository_id: UUID) -> AgentConfig:
        """Create default config if missing (called on repo install)."""

    @abstractmethod
    async def update(self, repository_id: UUID, params: UpdateAgentConfigParams) -> AgentConfig:
        """Patch agent toggles and min severity."""
