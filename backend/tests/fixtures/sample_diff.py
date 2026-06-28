"""Sample PR data for agent tests — no real Gemini calls needed."""

from uuid import uuid4

from domain.value_objects.agent_type import AgentType
from infrastructure.ai.graph.state import (
    ChangedFile,
    PRMetadata,
    RawDiffChunk,
    ReviewState,
)

SAMPLE_PATCH = """\
diff --git a/src/auth/handlers.py b/src/auth/handlers.py
index abc..def 100644
--- a/src/auth/handlers.py
+++ b/src/auth/handlers.py
@@ -10,7 +10,7 @@ def get_user(request):
-    user_id = int(request.args.get("id"))
+    user_id = request.args.get("id")   # type: ignore
     user = db.query(User).filter(User.id == user_id).first()
     return user
"""


def make_state(active_agents: list[AgentType] | None = None) -> ReviewState:
    return {
        "job_id": uuid4(),
        "repository_id": uuid4(),
        "trace_id": "test-trace",
        "pr_metadata": PRMetadata(
            pr_number=42,
            title="Fix user lookup in admin endpoint",
            author="john",
            pr_url="https://github.com/acme/backend/pull/42",
            base_sha="a" * 40,
            head_sha="b" * 40,
            base_branch="main",
            head_branch="fix/user-lookup",
            changed_files=[
                ChangedFile(
                    path="src/auth/handlers.py",
                    status="modified",
                    additions=1,
                    deletions=1,
                )
            ],
        ),
        "context_units": [],
        "raw_diff_chunks": [
            RawDiffChunk(
                file_path="src/auth/handlers.py",
                patch=SAMPLE_PATCH,
                language="python",
            )
        ],
        "rag_chunks": {},
        "active_agents": active_agents or list(AgentType),
        "findings": [],
        "summary": None,
        "synthesis_complete": False,
    }
