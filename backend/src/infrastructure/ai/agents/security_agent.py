from infrastructure.ai.agents.base_agent import AgentOutput, findings_from_output
from infrastructure.ai.gemini_client import GeminiClient
from infrastructure.ai.graph.state import ReviewState
from infrastructure.ai.prompts.security import SECURITY_SYSTEM
from infrastructure.ai.prompts.shared import (
    format_context_units,
    format_pr_header,
    format_rag_context,
    format_raw_diffs,
)
from infrastructure.observability.tracing import trace_agent

CATEGORY = "security"


class SecurityAgent:
    def __init__(self, gemini: GeminiClient) -> None:
        self._gemini = gemini

    @trace_agent(name="security_agent")
    async def run(self, state: ReviewState) -> ReviewState:
        prompt = (
            format_pr_header(state["pr_metadata"])
            + format_context_units(state["context_units"])
            + format_raw_diffs(state["raw_diff_chunks"])
            + format_rag_context(state["rag_chunks"].get(CATEGORY, []), "security patterns")
            + "\n\nFind all security vulnerabilities in the changed code above."
        )

        output = await self._gemini.generate(prompt, AgentOutput, system_prompt=SECURITY_SYSTEM)

        new_findings = findings_from_output(output, agent_source=CATEGORY)
        for f in new_findings:
            f.category = CATEGORY

        return {**state, "findings": list(state["findings"]) + new_findings}
