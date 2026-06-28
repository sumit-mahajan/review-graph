"""Tests for SecurityAgent, PerfAgent, ArchAgent, TestAgent — findings accumulation."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from infrastructure.ai.agents.arch_agent import ArchAgent
from infrastructure.ai.agents.base_agent import AgentOutput, FindingSchema
from infrastructure.ai.agents.perf_agent import PerfAgent
from infrastructure.ai.agents.security_agent import SecurityAgent
from infrastructure.ai.agents.test_agent import TestAgent
from tests.fixtures.sample_diff import make_state

_FINDING = FindingSchema(
    severity="high",
    category="security",
    file_path="src/auth/handlers.py",
    line_start=12,
    line_end=12,
    title="Unsanitised input in DB query",
    description="user_id from request.args is passed directly to filter().",
    fix_suggestion="Cast to int: user_id = int(request.args.get('id'))",
)


def _gemini_with_finding(finding: FindingSchema = _FINDING) -> MagicMock:
    gemini = MagicMock()
    gemini.generate = AsyncMock(return_value=AgentOutput(findings=[finding]))
    return gemini


@pytest.mark.asyncio
async def test_security_agent_appends_findings() -> None:
    agent = SecurityAgent(_gemini_with_finding())
    state = make_state()
    result = await agent.run(state)

    assert len(result["findings"]) == 1
    assert result["findings"][0].agent_source == "security"
    assert result["findings"][0].category == "security"


@pytest.mark.asyncio
async def test_security_agent_no_findings() -> None:
    gemini = MagicMock()
    gemini.generate = AsyncMock(return_value=AgentOutput(findings=[]))
    agent = SecurityAgent(gemini)
    result = await agent.run(make_state())
    assert result["findings"] == []


@pytest.mark.asyncio
async def test_perf_agent_appends_findings() -> None:
    finding = FindingSchema(
        severity="medium",
        category="perf",
        file_path="src/db.py",
        title="N+1 query in loop",
        description="DB called inside a loop.",
        fix_suggestion="Batch query outside loop.",
    )
    agent = PerfAgent(_gemini_with_finding(finding))
    result = await agent.run(make_state())
    assert result["findings"][0].category == "perf"


@pytest.mark.asyncio
async def test_arch_agent_appends_findings() -> None:
    finding = FindingSchema(
        severity="medium",
        category="arch",
        file_path="src/routes.py",
        title="DB call in route handler",
        description="Direct SQLAlchemy call in FastAPI route.",
        fix_suggestion="Move to repository layer.",
    )
    agent = ArchAgent(_gemini_with_finding(finding))
    result = await agent.run(make_state())
    assert result["findings"][0].category == "arch"


@pytest.mark.asyncio
async def test_test_agent_appends_findings() -> None:
    finding = FindingSchema(
        severity="low",
        category="test",
        file_path="src/auth/handlers.py",
        title="Missing test for get_user",
        description="No test covers the modified get_user function.",
        fix_suggestion="Add a unit test for get_user with invalid id.",
    )
    agent = TestAgent(_gemini_with_finding(finding))
    result = await agent.run(make_state())
    assert result["findings"][0].category == "test"


@pytest.mark.asyncio
async def test_findings_accumulate_across_agents() -> None:
    """Simulate sequential agent calls accumulating findings."""
    finding_security = FindingSchema(
        severity="high",
        category="security",
        file_path="a.py",
        title="SQL injection",
        description="...",
        fix_suggestion=None,
    )
    finding_perf = FindingSchema(
        severity="medium",
        category="perf",
        file_path="b.py",
        title="N+1 query",
        description="...",
        fix_suggestion=None,
    )

    state = make_state()
    state = await SecurityAgent(_gemini_with_finding(finding_security)).run(state)
    state = await PerfAgent(_gemini_with_finding(finding_perf)).run(state)

    assert len(state["findings"]) == 2
    assert state["findings"][0].agent_source == "security"
    assert state["findings"][1].agent_source == "perf"
