from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

from domain.value_objects.agent_type import AgentType
from infrastructure.ai.prompts.supervisor import SUPERVISOR_SYSTEM, build_supervisor_prompt
from infrastructure.observability.tracing import trace_agent

if TYPE_CHECKING:
    from infrastructure.ai.gemini_client import GeminiClient
    from infrastructure.ai.graph.state import ReviewState


class SupervisorOutput(BaseModel):
    agents: list[str]
    rationale: str


class SupervisorAgent:
    def __init__(self, gemini: GeminiClient) -> None:
        self._gemini = gemini

    @trace_agent(name="supervisor_agent")
    async def run(self, state: ReviewState) -> ReviewState:
        prompt = build_supervisor_prompt(state["pr_metadata"])
        output = await self._gemini.generate(
            prompt, SupervisorOutput, system_prompt=SUPERVISOR_SYSTEM
        )

        valid = {a.value for a in AgentType}
        active = [AgentType(a) for a in output.agents if a in valid]
        if not active:
            active = list(AgentType)  # fallback: run all agents
        elif len(state["pr_metadata"].changed_files) > 0 and len(active) == 1:
            # Supervisor under-routed — run all agents when code files changed
            active = list(AgentType)

        return {**state, "active_agents": active}
