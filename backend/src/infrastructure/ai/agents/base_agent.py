"""BaseAgent — shared helpers for all specialist agents."""

from __future__ import annotations

from pydantic import BaseModel

from infrastructure.ai.graph.state import AgentFinding

_VALID_CATEGORIES = {"security", "perf", "arch", "test"}


class FindingSchema(BaseModel):
    severity: str
    category: str
    file_path: str
    line_start: int | None = None
    line_end: int | None = None
    title: str
    description: str
    fix_suggestion: str | None = None


class AgentOutput(BaseModel):
    findings: list[FindingSchema]


def findings_from_output(output: AgentOutput, agent_source: str) -> list[AgentFinding]:
    return [
        AgentFinding(
            severity=_clamp_severity(f.severity),
            category=_clamp_category(f.category),
            agent_source=agent_source,
            file_path=f.file_path or "unknown",
            line_start=f.line_start,
            line_end=f.line_end,
            title=f.title[:512],
            description=f.description,
            fix_suggestion=f.fix_suggestion,
        )
        for f in output.findings
    ]


def _clamp_severity(s: str) -> str:
    valid = {"critical", "high", "medium", "low", "info"}
    return s.lower() if s.lower() in valid else "medium"


def _clamp_category(c: str) -> str:
    """Normalise LLM-returned category to a known lowercase value."""
    normalised = (c or "").strip().lower()
    return normalised if normalised in _VALID_CATEGORIES else "security"
