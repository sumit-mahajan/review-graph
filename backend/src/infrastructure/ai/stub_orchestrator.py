"""
StubAgentOrchestrator — used by worker during F-05.

The real pipeline (F-02) replaces this with LangGraph + Gemini.
This stub just returns an empty result so the worker's job-lifecycle
path can be tested end-to-end without a live AI dependency.
"""

from uuid import UUID

from domain.services.i_agent_orchestrator import IAgentOrchestrator, OrchestratorResult


class StubAgentOrchestrator(IAgentOrchestrator):
    async def run(self, job_id: UUID) -> OrchestratorResult:
        return OrchestratorResult(
            job_id=job_id,
            agents_run=[],
            total_findings=0,
        )
