"""
LanggraphOrchestrator — implements IAgentOrchestrator using the LangGraph pipeline.

Replaces StubAgentOrchestrator when Gemini API key is configured.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID  # noqa: TC003 — required at runtime for annotation evaluation (Py 3.14+)

import structlog

from domain.services.i_agent_orchestrator import IAgentOrchestrator, OrchestratorResult
from domain.value_objects.agent_type import AgentType
from domain.value_objects.review_finding import ReviewFinding
from infrastructure.ai.agents.arch_agent import ArchAgent
from infrastructure.ai.agents.perf_agent import PerfAgent
from infrastructure.ai.agents.security_agent import SecurityAgent
from infrastructure.ai.agents.supervisor_agent import SupervisorAgent
from infrastructure.ai.agents.synthesis_agent import SynthesisAgent
from infrastructure.ai.agents.test_agent import TestAgent
from infrastructure.ai.graph.review_graph import RagRetriever, build_review_graph
from infrastructure.ai.graph.state import AgentFinding, ContextUnit, PRMetadata, RawDiffChunk
from infrastructure.observability.langfuse_client import ILangfuseClient, NoOpLangfuseClient

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from application.use_cases.assemble_review_package import AssembleReviewPackageUseCase
    from domain.repositories.i_job_repository import IJobRepository
    from domain.services.i_code_embedding_store import ICodeEmbeddingStore
    from infrastructure.ai.gemini_client import GeminiClient
    from infrastructure.ai.graph.state import ReviewState

logger = structlog.get_logger()

# RAG queries per agent — used to populate rag_chunks before each agent runs
_RAG_QUERIES: dict[str, str] = {
    "security": "authentication authorization input validation secrets injection SQL",
    "perf": "database query loop iteration async await N+1 index",
    "arch": "import class hierarchy module dependency layer interface",
    "test": "test assert mock fixture unit test coverage",
}


class LanggraphOrchestrator(IAgentOrchestrator):
    def __init__(
        self,
        gemini: GeminiClient,
        job_repo: IJobRepository,
        assembler: AssembleReviewPackageUseCase | None = None,
        embedding_store: ICodeEmbeddingStore | None = None,
        langfuse: ILangfuseClient | None = None,
        db: AsyncSession | None = None,
    ) -> None:
        self._gemini = gemini
        self._job_repo = job_repo
        self._assembler = assembler
        self._embedding_store = embedding_store
        self._langfuse = langfuse or NoOpLangfuseClient()
        self._db = db

        supervisor = SupervisorAgent(gemini)
        security = SecurityAgent(gemini)
        perf = PerfAgent(gemini)
        arch = ArchAgent(gemini)
        test = TestAgent(gemini)
        synthesis = SynthesisAgent(gemini)

        rag_retriever = self._build_rag_retriever()
        self._graph = build_review_graph(
            supervisor, security, perf, arch, test, synthesis, rag_retriever
        ).compile()

    def _build_rag_retriever(self) -> RagRetriever | None:
        if self._embedding_store is None:
            return None

        store = self._embedding_store

        async def retrieve(state: ReviewState, agent_type: AgentType) -> list[str]:
            query = _RAG_QUERIES.get(agent_type.value, agent_type.value)
            return await store.retrieve_similar(
                repository_id=state["repository_id"],
                commit_sha=state["pr_metadata"].head_sha,
                query_text=query,
                k=5,
            )

        return retrieve

    async def run(self, job_id: UUID) -> OrchestratorResult:
        job = await self._job_repo.get_by_id(job_id)
        if job is None:
            raise ValueError(f"Job {job_id} not found")

        log = logger.bind(job_id=str(job_id), pr_number=job.pr_number)
        trace_id = self._langfuse.start_trace("review_pipeline", job_id=job_id)
        await log.ainfo("pipeline_started", trace_id=trace_id)

        # F-03: Assemble Review Package (diff fetch + tree-sitter parse)
        context_units: list[ContextUnit] = []
        raw_diff_chunks: list[RawDiffChunk] = []
        pr_metadata_override = None

        if self._assembler is not None:
            try:
                (
                    pr_metadata_override,
                    context_units,
                    raw_diff_chunks,
                ) = await self._assembler.execute(
                    repository_id=job.repository_id,
                    pr_number=job.pr_number,
                    pr_title=job.pr_title,
                    pr_author=job.pr_author,
                    pr_url=job.pr_url,
                    base_sha=job.base_sha,
                    head_sha=job.head_sha,
                )
            except Exception as exc:  # noqa: BLE001
                await log.awarning("review_package_assembly_failed", error=str(exc))
                if self._db is not None:
                    await self._db.rollback()
                # Degrade gracefully — proceed with empty context units

        pr_metadata = pr_metadata_override or PRMetadata(
            pr_number=job.pr_number,
            title=job.pr_title,
            author=job.pr_author,
            pr_url=job.pr_url,
            base_sha=job.base_sha,
            head_sha=job.head_sha,
            base_branch="main",
            head_branch="feature",
            changed_files=[],
        )

        initial_state: ReviewState = {
            "job_id": job_id,
            "repository_id": job.repository_id,
            "trace_id": trace_id,
            "pr_metadata": pr_metadata,
            "context_units": context_units,
            "raw_diff_chunks": raw_diff_chunks,
            "rag_chunks": {},
            "active_agents": [],
            "findings": [],
            "summary": None,
            "synthesis_complete": False,
        }

        final_state: ReviewState = await self._graph.ainvoke(initial_state)  # type: ignore[assignment]

        findings = final_state.get("findings", [])
        agents_run = [AgentType(a.value) for a in final_state.get("active_agents", [])]

        self._langfuse.end_trace(trace_id, output={"total_findings": len(findings)})
        await log.ainfo(
            "pipeline_complete",
            findings=len(findings),
            agents_run=[a.value for a in agents_run],
        )

        return OrchestratorResult(
            job_id=job_id,
            agents_run=agents_run,
            total_findings=len(findings),
            langfuse_trace_id=trace_id,
            summary=final_state.get("summary"),
            findings=tuple(_to_review_findings(findings)),
        )


def _to_review_findings(findings: list[AgentFinding]) -> list[ReviewFinding]:
    return [
        ReviewFinding(
            severity=f.severity,
            category=f.category,
            agent_source=f.agent_source,
            file_path=f.file_path,
            line_start=f.line_start,
            line_end=f.line_end,
            title=f.title,
            description=f.description,
            fix_suggestion=f.fix_suggestion,
        )
        for f in findings
    ]
