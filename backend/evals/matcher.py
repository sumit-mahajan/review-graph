"""
Finding matcher (F-08).

Decides whether a predicted finding from the pipeline corresponds to a planted
ground-truth `ExpectedFinding`. Two stages:

  1. Rule prefilter  — same category, same file, line-range overlap within tolerance.
  2. LLM-as-judge    — a Gemini structured call confirms the two describe the SAME
                       underlying issue (semantic match), since line numbers and
                       wording from the LLM reviewer rarely match the label exactly.

Assignment is greedy 1:1: one prediction can satisfy at most one expected finding.
The judge is injectable so unit tests can run rule-only (judge=None) with no LLM.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from pydantic import BaseModel

from infrastructure.ai.gemini_client import GeminiClient
from infrastructure.ai.graph.state import AgentFinding

from evals.schema import ExpectedFinding

LINE_TOLERANCE = 3

# (expected, predicted) -> is this the same underlying issue?
MatchJudge = Callable[[ExpectedFinding, AgentFinding], Awaitable[bool]]


@dataclass
class Match:
    expected: ExpectedFinding
    predicted: AgentFinding


@dataclass
class MatchResult:
    """Per-golden-PR outcome of matching predictions against the answer key."""

    golden_id: str
    category: str
    matches: list[Match] = field(default_factory=list)        # true positives
    missed: list[ExpectedFinding] = field(default_factory=list)  # false negatives
    spurious: list[AgentFinding] = field(default_factory=list)   # false positives

    @property
    def true_positives(self) -> int:
        return len(self.matches)

    @property
    def false_negatives(self) -> int:
        return len(self.missed)

    @property
    def false_positives(self) -> int:
        return len(self.spurious)


def _norm_category(value: str) -> str:
    return (value or "").strip().lower()


def _same_file(a: str, b: str) -> bool:
    if a == b:
        return True
    return PurePosixPath(a).name == PurePosixPath(b).name


def _lines_overlap(
    expected: ExpectedFinding,
    predicted: AgentFinding,
    tolerance: int = LINE_TOLERANCE,
) -> bool:
    # If the prediction omitted line numbers, defer to the judge.
    if predicted.line_start is None and predicted.line_end is None:
        return True
    p_start = predicted.line_start if predicted.line_start is not None else predicted.line_end
    p_end = predicted.line_end if predicted.line_end is not None else predicted.line_start
    if p_start is None or p_end is None:
        return True
    lo = min(p_start, p_end) - tolerance
    hi = max(p_start, p_end) + tolerance
    return not (hi < expected.line_start or lo > expected.line_end)


def _rule_candidate(expected: ExpectedFinding, predicted: AgentFinding) -> bool:
    return (
        _norm_category(predicted.category) == _norm_category(expected.category)
        and _same_file(predicted.file_path, expected.file_path)
        and _lines_overlap(expected, predicted)
    )


class FindingMatcher:
    def __init__(self, judge: MatchJudge | None = None) -> None:
        self._judge = judge

    async def match(
        self,
        *,
        golden_id: str,
        category: str,
        expected: list[ExpectedFinding],
        predicted: list[AgentFinding],
    ) -> MatchResult:
        result = MatchResult(golden_id=golden_id, category=category)
        used: set[int] = set()

        for exp in expected:
            chosen: int | None = None
            for idx, pred in enumerate(predicted):
                if idx in used or not _rule_candidate(exp, pred):
                    continue
                if self._judge is not None and not await self._judge(exp, pred):
                    continue
                chosen = idx
                break
            if chosen is None:
                result.missed.append(exp)
            else:
                used.add(chosen)
                result.matches.append(Match(expected=exp, predicted=predicted[chosen]))

        result.spurious = [p for i, p in enumerate(predicted) if i not in used]
        return result


class _JudgeVerdict(BaseModel):
    is_match: bool
    confidence: float


def build_gemini_judge(gemini: GeminiClient) -> MatchJudge:
    """LLM-as-judge: confirm a predicted finding describes the planted issue."""

    async def judge(expected: ExpectedFinding, predicted: AgentFinding) -> bool:
        prompt = (
            "Decide whether a code-review tool's finding refers to the SAME underlying "
            "issue as a known planted defect. Ignore differences in wording, exact line "
            "numbers, or severity. Answer is_match=true only if they are the same issue.\n\n"
            f"PLANTED DEFECT ({expected.category}):\n"
            f"  file: {expected.file_path} lines {expected.line_start}-{expected.line_end}\n"
            f"  title: {expected.title}\n"
            f"  why: {expected.rationale}\n\n"
            f"TOOL FINDING ({predicted.category}):\n"
            f"  file: {predicted.file_path} "
            f"lines {predicted.line_start}-{predicted.line_end}\n"
            f"  title: {predicted.title}\n"
            f"  description: {predicted.description}\n"
        )
        verdict = await gemini.generate(prompt, _JudgeVerdict, temperature=0.0)
        return verdict.is_match

    return judge
