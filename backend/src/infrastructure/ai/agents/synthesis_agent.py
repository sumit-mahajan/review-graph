from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

from infrastructure.ai.agents.base_agent import AgentOutput, FindingSchema, findings_from_output
from infrastructure.ai.prompts.synthesis import SYNTHESIS_SYSTEM
from infrastructure.observability.tracing import trace_agent

if TYPE_CHECKING:
    from infrastructure.ai.gemini_client import GeminiClient
    from infrastructure.ai.graph.state import ReviewState


class SynthesisOutput(BaseModel):
    findings: list[FindingSchema]
    summary: str


class SynthesisAgent:
    def __init__(self, gemini: GeminiClient) -> None:
        self._gemini = gemini

    @trace_agent(name="synthesis_agent")
    async def run(self, state: ReviewState) -> ReviewState:
        if not state["findings"]:
            return {
                **state,
                "summary": "No findings from any agent. The changes look clean.",
                "synthesis_complete": True,
            }

        findings_text = "\n\n".join(
            f"[{f.agent_source.upper()} / {f.severity.upper()}] {f.title}\n"
            f"File: {f.file_path}"
            + (f" lines {f.line_start}–{f.line_end}" if f.line_start else "")
            + f"\n{f.description}"
            + (f"\nFix: {f.fix_suggestion}" if f.fix_suggestion else "")
            for f in state["findings"]
        )

        prompt = (
            f"PR: {state['pr_metadata'].title} (#{state['pr_metadata'].pr_number})\n\n"
            f"RAW FINDINGS FROM SPECIALIST AGENTS:\n\n{findings_text}\n\n"
            "Deduplicate, verify severity, resolve contradictions, and write a summary."
        )

        output = await self._gemini.generate(
            prompt, SynthesisOutput, system_prompt=SYNTHESIS_SYSTEM
        )

        final_findings = findings_from_output(
            AgentOutput(findings=output.findings), agent_source="synthesis"
        )
        # Preserve agent_source from deduplicated findings where available
        for sf, orig in zip(final_findings, output.findings, strict=False):
            sf.agent_source = getattr(orig, "category", "synthesis") or "synthesis"

        return {
            **state,
            "findings": final_findings,
            "summary": output.summary,
            "synthesis_complete": True,
        }
