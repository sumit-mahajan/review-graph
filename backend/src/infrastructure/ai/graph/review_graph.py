"""
LangGraph StateGraph for the multi-agent review pipeline.

Flow:
  START → supervisor → specialists (sequential active agents) → synthesis → END

Specialist agents run sequentially in one node so findings accumulate reliably
before synthesis (parallel fan-out caused synthesis to run with partial/empty state).
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from langgraph.graph import END, START, StateGraph

from domain.value_objects.agent_type import AgentType
from infrastructure.ai.agents.arch_agent import ArchAgent
from infrastructure.ai.agents.perf_agent import PerfAgent
from infrastructure.ai.agents.security_agent import SecurityAgent
from infrastructure.ai.agents.supervisor_agent import SupervisorAgent
from infrastructure.ai.agents.synthesis_agent import SynthesisAgent
from infrastructure.ai.agents.test_agent import TestAgent
from infrastructure.ai.graph.state import ReviewState

AgentRunner = Callable[[ReviewState], Awaitable[ReviewState]]


def _make_specialists_runner(
    security: SecurityAgent,
    perf: PerfAgent,
    arch: ArchAgent,
    test: TestAgent,
) -> AgentRunner:
    runners: dict[AgentType, AgentRunner] = {
        AgentType.SECURITY: security.run,
        AgentType.PERF: perf.run,
        AgentType.ARCH: arch.run,
        AgentType.TEST: test.run,
    }

    async def run_specialists(state: ReviewState) -> ReviewState:
        for agent_type in state.get("active_agents", list(AgentType)):
            runner = runners.get(agent_type)
            if runner is not None:
                state = await runner(state)
        return state

    return run_specialists


def build_review_graph(
    supervisor: SupervisorAgent,
    security: SecurityAgent,
    perf: PerfAgent,
    arch: ArchAgent,
    test: TestAgent,
    synthesis: SynthesisAgent,
) -> StateGraph:
    graph = StateGraph(ReviewState)

    graph.add_node("supervisor", supervisor.run)
    graph.add_node(
        "specialists",
        _make_specialists_runner(security, perf, arch, test),
    )
    graph.add_node("synthesis", synthesis.run)

    graph.add_edge(START, "supervisor")
    graph.add_edge("supervisor", "specialists")
    graph.add_edge("specialists", "synthesis")
    graph.add_edge("synthesis", END)

    return graph
