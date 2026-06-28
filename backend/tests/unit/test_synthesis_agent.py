"""Tests for SynthesisAgent — deduplication and summary."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from infrastructure.ai.agents.base_agent import FindingSchema
from infrastructure.ai.agents.synthesis_agent import SynthesisAgent, SynthesisOutput
from infrastructure.ai.graph.state import AgentFinding as StateAgentFinding
from tests.fixtures.sample_diff import make_state


def _finding(agent: str, title: str) -> StateAgentFinding:
    return StateAgentFinding(
        severity="high",
        category=agent,
        agent_source=agent,
        file_path="src/auth.py",
        line_start=10,
        line_end=12,
        title=title,
        description="Test finding",
        fix_suggestion=None,
    )


@pytest.mark.asyncio
async def test_synthesis_deduplicates_and_sets_summary() -> None:
    gemini = MagicMock()
    gemini.generate = AsyncMock(
        return_value=SynthesisOutput(
            findings=[
                FindingSchema(
                    severity="high",
                    category="security",
                    file_path="src/auth.py",
                    title="SQL injection risk",
                    description="Merged finding.",
                    fix_suggestion="Use parameterised queries.",
                )
            ],
            summary="This PR introduces a SQL injection vulnerability.",
        )
    )

    state = make_state()
    state["findings"] = [
        _finding("security", "SQL injection"),
        _finding("arch", "DB call in handler"),  # different agent, same issue area
    ]

    agent = SynthesisAgent(gemini)
    result = await agent.run(state)

    assert result["synthesis_complete"] is True
    assert result["summary"] is not None
    assert len(result["findings"]) == 1  # deduplicated from 2 → 1


@pytest.mark.asyncio
async def test_synthesis_handles_no_findings() -> None:
    gemini = MagicMock()
    gemini.generate = AsyncMock()  # should not be called

    state = make_state()
    state["findings"] = []

    agent = SynthesisAgent(gemini)
    result = await agent.run(state)

    assert result["synthesis_complete"] is True
    assert "clean" in (result["summary"] or "").lower()
    gemini.generate.assert_not_awaited()
