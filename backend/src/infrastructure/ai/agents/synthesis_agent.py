from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

from infrastructure.ai.agents.base_agent import AgentOutput, FindingSchema, findings_from_output
from infrastructure.ai.graph.state import AgentFinding
from infrastructure.ai.prompts.synthesis import SYNTHESIS_SYSTEM
from infrastructure.observability.tracing import trace_agent

if TYPE_CHECKING:
    from infrastructure.ai.gemini_client import GeminiClient
    from infrastructure.ai.graph.state import ReviewState

# Specialist categories that should not be overridden by the catch-all "security".
_SPECIFIC_CATEGORIES = {"arch", "perf", "test"}
_LINE_TOLERANCE = 3


class SynthesisOutput(BaseModel):
    findings: list[FindingSchema]
    summary: str


def _recover_category(sf: AgentFinding, input_findings: list[AgentFinding]) -> str:
    """Restore a specific category (arch/perf/test) if synthesis collapsed it to security.

    When two agents flag the same code location, synthesis sometimes merges them and
    keeps the 'security' label. This override restores the specialist category so that
    the eval scorer (and GitHub review output) reflect the correct domain.
    """
    if sf.category != "security":
        return sf.category  # already specific — nothing to do

    for inp in input_findings:
        if inp.category not in _SPECIFIC_CATEGORIES:
            continue
        if inp.file_path != sf.file_path:
            continue
        # Check line-range overlap with tolerance.
        s1 = sf.line_start if sf.line_start is not None else sf.line_end
        s2 = sf.line_end if sf.line_end is not None else sf.line_start
        i1 = inp.line_start if inp.line_start is not None else inp.line_end
        i2 = inp.line_end if inp.line_end is not None else inp.line_start
        if s1 is None or i1 is None:
            # No line info — file-level match is enough to recover
            return inp.category
        sf_lo = min(s1, s2) - _LINE_TOLERANCE  # type: ignore[arg-type]
        sf_hi = max(s1, s2) + _LINE_TOLERANCE  # type: ignore[arg-type]
        inp_lo = min(i1, i2)  # type: ignore[arg-type]
        inp_hi = max(i1, i2)  # type: ignore[arg-type]
        if not (sf_hi < inp_lo or sf_lo > inp_hi):
            return inp.category

    return sf.category


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

        # Include the agent source and category explicitly so the LLM knows which
        # specialist produced each finding and doesn't change the category.
        findings_text = "\n\n".join(
            f"[AGENT={f.agent_source.upper()} CATEGORY={f.category.upper()} "
            f"SEVERITY={f.severity.upper()}] {f.title}\n"
            f"File: {f.file_path}"
            + (f" lines {f.line_start}–{f.line_end}" if f.line_start else "")
            + f"\n{f.description}"
            + (f"\nFix: {f.fix_suggestion}" if f.fix_suggestion else "")
            for f in state["findings"]
        )

        prompt = (
            f"PR: {state['pr_metadata'].title} (#{state['pr_metadata'].pr_number})\n\n"
            f"RAW FINDINGS FROM SPECIALIST AGENTS:\n\n{findings_text}\n\n"
            "Deduplicate, verify severity, resolve contradictions, and write a summary.\n"
            "Remember: preserve each finding's CATEGORY exactly as shown above."
        )

        output = await self._gemini.generate(
            prompt, SynthesisOutput, system_prompt=SYNTHESIS_SYSTEM
        )

        input_findings = list(state["findings"])
        final_findings = findings_from_output(
            AgentOutput(findings=output.findings), agent_source="synthesis"
        )

        # Code-level safety net: if synthesis still recategorised a specialist finding
        # to "security", restore the original specialist category.
        for sf in final_findings:
            sf.category = _recover_category(sf, input_findings)

        return {
            **state,
            "findings": final_findings,
            "summary": output.summary,
            "synthesis_complete": True,
        }
