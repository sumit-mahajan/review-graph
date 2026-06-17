from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.agent_config import AgentConfig
from domain.errors import EntityNotFoundError
from domain.repositories.i_agent_config_repository import (
    IAgentConfigRepository,
    UpdateAgentConfigParams,
)
from infrastructure.db.models.agent_config import AgentConfigORM


class PostgresAgentConfigRepository(IAgentConfigRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_repository_id(self, repository_id: UUID) -> AgentConfig | None:
        result = await self._session.execute(
            select(AgentConfigORM).where(AgentConfigORM.repository_id == repository_id)
        )
        orm = result.scalar_one_or_none()
        return _to_entity(orm) if orm else None

    async def ensure_default(self, repository_id: UUID) -> AgentConfig:
        existing = await self.get_by_repository_id(repository_id)
        if existing is not None:
            return existing

        # INSERT … ON CONFLICT avoids UniqueViolation when concurrent requests
        # both pass the SELECT above (e.g. parallel GET /repos on dashboard load).
        stmt = (
            insert(AgentConfigORM)
            .values(repository_id=repository_id)
            .on_conflict_do_nothing(constraint="agent_configs_repository_id_key")
        )
        await self._session.execute(stmt)
        await self._session.commit()

        result = await self._session.execute(
            select(AgentConfigORM).where(AgentConfigORM.repository_id == repository_id)
        )
        orm = result.scalar_one_or_none()
        if orm is None:
            raise EntityNotFoundError(
                f"Agent config for repository {repository_id} not found after upsert"
            )
        return _to_entity(orm)

    async def update(
        self, repository_id: UUID, params: UpdateAgentConfigParams
    ) -> AgentConfig:
        result = await self._session.execute(
            select(AgentConfigORM).where(AgentConfigORM.repository_id == repository_id)
        )
        orm = result.scalar_one_or_none()
        if orm is None:
            raise EntityNotFoundError(f"Agent config for repository {repository_id} not found")

        if params.security_enabled is not None:
            orm.security_enabled = params.security_enabled
        if params.perf_enabled is not None:
            orm.perf_enabled = params.perf_enabled
        if params.arch_enabled is not None:
            orm.arch_enabled = params.arch_enabled
        if params.test_enabled is not None:
            orm.test_enabled = params.test_enabled
        if params.min_severity is not None:
            orm.min_severity = params.min_severity

        await self._session.commit()
        await self._session.refresh(orm)
        return _to_entity(orm)


def _to_entity(orm: AgentConfigORM) -> AgentConfig:
    return AgentConfig(
        id=orm.id,
        repository_id=orm.repository_id,
        security_enabled=orm.security_enabled,
        perf_enabled=orm.perf_enabled,
        arch_enabled=orm.arch_enabled,
        test_enabled=orm.test_enabled,
        min_severity=orm.min_severity,
        created_at=orm.created_at,
        updated_at=orm.updated_at,
    )
