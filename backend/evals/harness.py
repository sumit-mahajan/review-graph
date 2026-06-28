"""
Eval harness — runs a golden PR through the real LangGraph review pipeline.

The harness compiles the same graph the worker uses (Supervisor → specialists →
Synthesis) but feeds it a fixture-provided ReviewState instead of fetching from
GitHub, and passes no RAG retriever (deterministic, no pgvector dependency).
This is the "full pipeline incl. Supervisor routing" eval mode.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import structlog

from domain.value_objects.agent_type import AgentType
from infrastructure.ai.agents.arch_agent import ArchAgent
from infrastructure.ai.agents.perf_agent import PerfAgent
from infrastructure.ai.agents.security_agent import SecurityAgent
from infrastructure.ai.agents.supervisor_agent import SupervisorAgent
from infrastructure.ai.agents.synthesis_agent import SynthesisAgent
from infrastructure.ai.agents.test_agent import TestAgent
from infrastructure.ai.gemini_client import GeminiClient
from infrastructure.ai.graph.review_graph import build_review_graph
from infrastructure.ai.graph.state import AgentFinding, ReviewState

from evals.schema import GoldenPR

logger = structlog.get_logger()


@dataclass
class PipelineRun:
    """Result of running one golden PR through the pipeline."""

    golden_id: str
    predicted: list[AgentFinding] = field(default_factory=list)
    active_agents: list[AgentType] = field(default_factory=list)
    summary: str | None = None
    error: str | None = None


class EvalHarness:
    def __init__(self, gemini: GeminiClient) -> None:
        self._graph = build_review_graph(
            SupervisorAgent(gemini),
            SecurityAgent(gemini),
            PerfAgent(gemini),
            ArchAgent(gemini),
            TestAgent(gemini),
            SynthesisAgent(gemini),
            rag_retriever=None,
        ).compile()

    async def run(self, golden: GoldenPR) -> PipelineRun:
        log = logger.bind(golden_id=golden.id, category=golden.category)
        await log.ainfo("eval_pipeline_started")
        initial: ReviewState = golden.to_review_state()
        try:
            final: ReviewState = await self._graph.ainvoke(initial)  # type: ignore[assignment]
        except Exception as exc:  # noqa: BLE001
            await log.aerror("eval_pipeline_failed", error=str(exc)[:300])
            return PipelineRun(golden_id=golden.id, error=str(exc)[:300])

        predicted = list(final.get("findings", []))
        active = list(final.get("active_agents", []))
        await log.ainfo(
            "eval_pipeline_complete",
            predicted=len(predicted),
            active_agents=[a.value for a in active],
        )
        return PipelineRun(
            golden_id=golden.id,
            predicted=predicted,
            active_agents=active,
            summary=final.get("summary"),
        )
