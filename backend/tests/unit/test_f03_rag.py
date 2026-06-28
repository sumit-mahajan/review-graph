"""F-03 acceptance tests — embedding index + per-agent RAG retrieval."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from application.use_cases.assemble_review_package import (
    AssembleReviewPackageUseCase,
    _one_hop_import_paths,
)
from domain.entities.github_installation import GithubInstallation
from domain.entities.repository import Repository
from domain.services.i_code_embedding_store import ICodeEmbeddingStore
from domain.services.i_pr_fetcher import FilePatch, PullRequestDiff
from domain.value_objects.agent_type import AgentType
from infrastructure.ai.graph.review_graph import _make_specialists_runner
from infrastructure.ai.graph.state import PRMetadata, ReviewState
from tests.fixtures.python_sample import PYTHON_PATCH, PYTHON_SOURCE


class InMemoryEmbeddingStore(ICodeEmbeddingStore):
    def __init__(self) -> None:
        self.stored: list[tuple[UUID, str, str]] = []
        self.queries: list[tuple[str, str]] = []

    async def store_file_chunks(
        self,
        *,
        repository_id: UUID,
        commit_sha: str,
        file_path: str,
        chunks: list[dict[str, object]],
        language: str | None = None,
    ) -> int:
        self.stored.append((repository_id, commit_sha, file_path))
        return len(chunks)

    async def retrieve_similar(
        self,
        *,
        repository_id: UUID,
        commit_sha: str,
        query_text: str,
        k: int = 5,
        language: str | None = None,
    ) -> list[str]:
        self.queries.append((commit_sha, query_text))
        return [f"context for {query_text[:20]}"]


def _repo() -> Repository:
    now = datetime.now(UTC)
    inst_id = uuid4()
    return Repository(
        id=uuid4(),
        github_id=123,
        installation_id=inst_id,
        owner="acme",
        name="backend",
        full_name="acme/backend",
        default_branch="main",
        is_active=True,
        language="Python",
        created_at=now,
        updated_at=now,
    )


def _installation(installation_id: object) -> GithubInstallation:
    now = datetime.now(UTC)
    return GithubInstallation(
        id=installation_id,  # type: ignore[arg-type]
        installation_id=99001,
        account_login="acme",
        account_type="org",
        account_avatar_url=None,
        access_token_encrypted=None,
        access_token_expires_at=None,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_assembly_stores_embeddings_for_changed_files() -> None:
    repo = _repo()
    installation = _installation(repo.installation_id)
    store = InMemoryEmbeddingStore()

    repo_repo = AsyncMock()
    repo_repo.get_by_id.return_value = repo
    installation_repo = AsyncMock()
    installation_repo.get_by_id.return_value = installation

    pr_fetcher = AsyncMock()
    pr_fetcher.fetch_diff.return_value = PullRequestDiff(
        pr_number=42,
        base_sha="a" * 40,
        head_sha="b" * 40,
        base_branch="main",
        head_branch="fix/auth",
        file_patches=[
            FilePatch(
                path="src/auth/handlers.py",
                status="modified",
                additions=2,
                deletions=2,
                patch=PYTHON_PATCH,
            )
        ],
    )
    pr_fetcher.fetch_file_content.return_value = PYTHON_SOURCE

    use_case = AssembleReviewPackageUseCase(
        repo_repo, installation_repo, pr_fetcher, embedding_store=store
    )
    await use_case.execute(
        repository_id=repo.id,
        pr_number=42,
        pr_title="Fix auth",
        pr_author="dev",
        pr_url="https://github.com/acme/backend/pull/42",
        base_sha="a" * 40,
        head_sha="b" * 40,
    )

    assert len(store.stored) >= 1
    assert store.stored[0][1] == "b" * 40
    assert store.stored[0][2] == "src/auth/handlers.py"


@pytest.mark.asyncio
async def test_specialists_runner_populates_rag_chunks_before_agents() -> None:
    store = InMemoryEmbeddingStore()
    head_sha = "c" * 40
    repo_id = uuid4()

    async def rag_retriever(state: ReviewState, agent_type: AgentType) -> list[str]:
        return await store.retrieve_similar(
            repository_id=state["repository_id"],
            commit_sha=state["pr_metadata"].head_sha,
            query_text=agent_type.value,
            k=5,
        )

    security = AsyncMock()
    security.run = AsyncMock(side_effect=lambda s: s)
    perf = AsyncMock()
    perf.run = AsyncMock(side_effect=lambda s: s)
    arch = AsyncMock()
    arch.run = AsyncMock(side_effect=lambda s: s)
    test = AsyncMock()
    test.run = AsyncMock(side_effect=lambda s: s)

    runner = _make_specialists_runner(security, perf, arch, test, rag_retriever)
    state: ReviewState = {
        "job_id": uuid4(),
        "repository_id": repo_id,
        "trace_id": "trace",
        "pr_metadata": PRMetadata(
            pr_number=1,
            title="t",
            author="dev",
            pr_url="u",
            base_sha="a" * 40,
            head_sha=head_sha,
            base_branch="main",
            head_branch="feature",
            changed_files=[],
        ),
        "context_units": [],
        "raw_diff_chunks": [],
        "rag_chunks": {},
        "active_agents": [AgentType.SECURITY, AgentType.PERF],
        "findings": [],
        "summary": None,
        "synthesis_complete": False,
    }

    final = await runner(state)

    assert final["rag_chunks"]["security"]
    assert final["rag_chunks"]["perf"]
    assert store.queries[0][0] == head_sha
    security.run.assert_awaited_once()
    perf.run.assert_awaited_once()


def test_one_hop_import_paths_resolves_relative_python_import() -> None:
    source = "from .utils import helper\n"
    paths = _one_hop_import_paths(source, "src/auth/handlers.py")
    assert "src/auth/utils.py" in paths
