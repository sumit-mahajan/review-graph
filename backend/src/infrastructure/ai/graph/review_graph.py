"""
LangGraph StateGraph for the multi-agent review pipeline.

Flow:
  START → supervisor → specialists (parallel active agents) → synthesis → END

Specialist agents run concurrently via asyncio.gather. All agents start from
the same state snapshot (with RAG chunks pre-fetched in parallel), and their
new findings are merged after all complete. This is safe because each agent
only appends to findings — it never reads the findings its peers produced.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from langgraph.graph import END, START, StateGraph

from domain.value_objects.agent_type import AgentType
from infrastructure.ai.graph.state import ReviewState

if TYPE_CHECKING:
    from infrastructure.ai.agents.arch_agent import ArchAgent
    from infrastructure.ai.agents.perf_agent import PerfAgent
    from infrastructure.ai.agents.security_agent import SecurityAgent
    from infrastructure.ai.agents.supervisor_agent import SupervisorAgent
    from infrastructure.ai.agents.synthesis_agent import SynthesisAgent
    from infrastructure.ai.agents.test_agent import TestAgent

AgentRunner = Callable[[ReviewState], Awaitable[ReviewState]]
RagRetriever = Callable[[ReviewState, AgentType], Awaitable[list[str]]]


def _make_specialists_runner(
    security: SecurityAgent,
    perf: PerfAgent,
    arch: ArchAgent,
    test: TestAgent,
    rag_retriever: RagRetriever | None = None,
) -> AgentRunner:
    runners: dict[AgentType, AgentRunner] = {
        AgentType.SECURITY: security.run,
        AgentType.PERF: perf.run,
        AgentType.ARCH: arch.run,
        AgentType.TEST: test.run,
    }

    async def run_specialists(state: ReviewState) -> ReviewState:
        active: list[AgentType] = state.get("active_agents") or list(AgentType)
        active_pairs = [(at, runners[at]) for at in active if at in runners]
        if not active_pairs:
            return state

        # Pre-fetch RAG chunks for all active agents concurrently.
        rag_chunks = dict(state.get("rag_chunks") or {})
        if rag_retriever is not None:
            rag_results = await asyncio.gather(
                *[rag_retriever(state, at) for at, _ in active_pairs]
            )
            for (at, _), chunks in zip(active_pairs, rag_results):
                rag_chunks[at.value] = chunks

        # Snapshot state with all RAG chunks ready; every agent reads this.
        state_with_rag = {**state, "rag_chunks": rag_chunks}
        prior_findings = list(state_with_rag.get("findings") or [])
        prior_len = len(prior_findings)

        # Run all active agents concurrently.
        agent_states: list[ReviewState] = await asyncio.gather(  # type: ignore[assignment]
            *[runner(state_with_rag) for _, runner in active_pairs]
        )

        # Merge: each agent appended its own findings to prior_findings,
        # so extract only the suffix each one added.
        all_findings = list(prior_findings)
        for agent_state in agent_states:
            returned = list(agent_state.get("findings") or [])
            all_findings.extend(returned[prior_len:])

        return {**state_with_rag, "findings": all_findings}

    return run_specialists


def build_review_graph(
    supervisor: SupervisorAgent,
    security: SecurityAgent,
    perf: PerfAgent,
    arch: ArchAgent,
    test: TestAgent,
    synthesis: SynthesisAgent,
    rag_retriever: RagRetriever | None = None,
) -> StateGraph[ReviewState]:
    graph: StateGraph[ReviewState] = StateGraph(ReviewState)

    graph.add_node("supervisor", supervisor.run)
    graph.add_node(
        "specialists",
        _make_specialists_runner(security, perf, arch, test, rag_retriever),  # type: ignore[arg-type]
    )
    graph.add_node("synthesis", synthesis.run)

    graph.add_edge(START, "supervisor")
    graph.add_edge("supervisor", "specialists")
    graph.add_edge("specialists", "synthesis")
    graph.add_edge("synthesis", END)

    return graph
