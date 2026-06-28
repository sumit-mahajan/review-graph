"""Tests for SupervisorAgent — routing decisions."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from domain.value_objects.agent_type import AgentType
from infrastructure.ai.agents.supervisor_agent import SupervisorAgent, SupervisorOutput
from tests.fixtures.sample_diff import make_state


@pytest.mark.asyncio
async def test_supervisor_sets_active_agents() -> None:
    gemini = MagicMock()
    gemini.generate = AsyncMock(
        return_value=SupervisorOutput(
            agents=["security", "perf"],
            rationale="Auth file changed.",
        )
    )

    agent = SupervisorAgent(gemini)
    state = make_state()
    result = await agent.run(state)

    assert AgentType.SECURITY in result["active_agents"]
    assert AgentType.PERF in result["active_agents"]
    assert AgentType.ARCH not in result["active_agents"]


@pytest.mark.asyncio
async def test_supervisor_falls_back_to_all_agents_on_empty_list() -> None:
    gemini = MagicMock()
    gemini.generate = AsyncMock(return_value=SupervisorOutput(agents=[], rationale="unclear"))

    agent = SupervisorAgent(gemini)
    result = await agent.run(make_state())
    assert len(result["active_agents"]) == len(AgentType)
