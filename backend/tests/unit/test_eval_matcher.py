"""Unit tests for the F-08 finding matcher (judge mocked / rule-only)."""

from __future__ import annotations

import pytest

from evals.matcher import FindingMatcher
from evals.schema import ExpectedFinding
from infrastructure.ai.graph.state import AgentFinding


def _expected(**kw: object) -> ExpectedFinding:
    base = {
        "category": "security",
        "file_path": "app/users.py",
        "line_start": 6,
        "line_end": 7,
        "title": "SQL injection",
        "rationale": "concatenated query",
    }
    base.update(kw)
    return ExpectedFinding(**base)  # type: ignore[arg-type]


def _predicted(**kw: object) -> AgentFinding:
    base = {
        "severity": "high",
        "category": "security",
        "agent_source": "security",
        "file_path": "app/users.py",
        "line_start": 6,
        "line_end": 6,
        "title": "SQL injection risk",
        "description": "user input concatenated into query",
        "fix_suggestion": "use params",
    }
    base.update(kw)
    return AgentFinding(**base)  # type: ignore[arg-type]


async def test_rule_only_match_within_tolerance() -> None:
    matcher = FindingMatcher(judge=None)
    result = await matcher.match(
        golden_id="g1",
        category="security",
        expected=[_expected()],
        predicted=[_predicted(line_start=8, line_end=8)],  # within ±3 of 6-7
    )
    assert result.true_positives == 1
    assert result.false_negatives == 0
    assert result.false_positives == 0


async def test_no_line_overlap_is_missed_and_spurious() -> None:
    matcher = FindingMatcher(judge=None)
    result = await matcher.match(
        golden_id="g1",
        category="security",
        expected=[_expected(line_start=6, line_end=6)],
        predicted=[_predicted(line_start=40, line_end=42)],
    )
    assert result.true_positives == 0
    assert result.false_negatives == 1
    assert result.false_positives == 1


async def test_category_mismatch_not_matched() -> None:
    matcher = FindingMatcher(judge=None)
    result = await matcher.match(
        golden_id="g1",
        category="security",
        expected=[_expected()],
        predicted=[_predicted(category="perf")],
    )
    assert result.true_positives == 0
    assert result.false_negatives == 1
    assert result.false_positives == 1


async def test_different_file_not_matched() -> None:
    matcher = FindingMatcher(judge=None)
    result = await matcher.match(
        golden_id="g1",
        category="security",
        expected=[_expected(file_path="app/users.py")],
        predicted=[_predicted(file_path="app/orders.py")],
    )
    assert result.true_positives == 0


async def test_basename_file_match() -> None:
    matcher = FindingMatcher(judge=None)
    result = await matcher.match(
        golden_id="g1",
        category="security",
        expected=[_expected(file_path="app/users.py")],
        predicted=[_predicted(file_path="users.py")],
    )
    assert result.true_positives == 1


async def test_judge_rejects_blocks_match() -> None:
    async def reject(_e: ExpectedFinding, _p: AgentFinding) -> bool:
        return False

    matcher = FindingMatcher(judge=reject)
    result = await matcher.match(
        golden_id="g1",
        category="security",
        expected=[_expected()],
        predicted=[_predicted()],
    )
    assert result.true_positives == 0
    assert result.false_negatives == 1
    assert result.false_positives == 1


async def test_judge_accepts_allows_match() -> None:
    async def accept(_e: ExpectedFinding, _p: AgentFinding) -> bool:
        return True

    matcher = FindingMatcher(judge=accept)
    result = await matcher.match(
        golden_id="g1",
        category="security",
        expected=[_expected()],
        predicted=[_predicted()],
    )
    assert result.true_positives == 1


async def test_greedy_one_to_one_assignment() -> None:
    matcher = FindingMatcher(judge=None)
    result = await matcher.match(
        golden_id="g1",
        category="security",
        expected=[_expected(), _expected(title="second")],
        predicted=[_predicted()],  # only one prediction for two expected
    )
    assert result.true_positives == 1
    assert result.false_negatives == 1
    assert result.false_positives == 0


@pytest.mark.parametrize("p_start,p_end,expect_tp", [(6, 7, 1), (10, 10, 1), (11, 11, 0)])
async def test_line_tolerance_boundary(p_start: int, p_end: int, expect_tp: int) -> None:
    matcher = FindingMatcher(judge=None)
    result = await matcher.match(
        golden_id="g1",
        category="security",
        expected=[_expected(line_start=6, line_end=7)],
        predicted=[_predicted(line_start=p_start, line_end=p_end)],
    )
    assert result.true_positives == expect_tp
