"""Unit tests for PostgresAgentConfigRepository.ensure_default SQL shape."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from infrastructure.db.repositories.agent_config_repository import PostgresAgentConfigRepository


@pytest.mark.asyncio
async def test_ensure_default_uses_on_conflict_do_nothing() -> None:
    repository_id = uuid4()
    session = AsyncMock()
    existing_orm = MagicMock()
    existing_orm.id = uuid4()
    existing_orm.repository_id = repository_id
    existing_orm.security_enabled = True
    existing_orm.perf_enabled = True
    existing_orm.arch_enabled = True
    existing_orm.test_enabled = True
    existing_orm.min_severity = "medium"
    existing_orm.created_at = None
    existing_orm.updated_at = None

    select_result = MagicMock()
    select_result.scalar_one_or_none.side_effect = [None, existing_orm]
    session.execute = AsyncMock(return_value=select_result)

    repo = PostgresAgentConfigRepository(session)
    config = await repo.ensure_default(repository_id)

    assert config.repository_id == repository_id
    insert_call = session.execute.await_args_list[1].args[0]
    compiled = str(
        insert_call.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )
    assert "ON CONFLICT" in compiled
    assert "agent_configs_repository_id_key" in compiled
    session.commit.assert_awaited_once()
