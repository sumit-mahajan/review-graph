"""Unit tests for the F-08 scorer aggregation."""

from __future__ import annotations

from domain.value_objects.agent_type import AgentType
from evals.harness import PipelineRun
from evals.matcher import Match, MatchResult
from evals.schema import ExpectedFinding, GoldenPR
from evals.scorer import score
from infrastructure.ai.graph.state import AgentFinding


def _golden(category: str, expected: int = 0) -> GoldenPR:
    findings = [
        ExpectedFinding(
            category=category,  # type: ignore[arg-type]
            file_path="app/x.py",
            line_start=1,
            line_end=1,
            title=f"flaw {i}",
            rationale="because",
        )
        for i in range(expected)
    ]
    return GoldenPR(
        id=f"{category}_1",
        category=category,  # type: ignore[arg-type]
        title="t",
        expected_findings=findings,
    )


def _finding(category: str) -> AgentFinding:
    return AgentFinding(
        severity="high",
        category=category,
        agent_source=category,
        file_path="app/x.py",
        line_start=1,
        line_end=1,
        title="f",
        description="d",
        fix_suggestion=None,
    )


def test_flaw_pr_tp_fn_and_routing() -> None:
    golden = _golden("security", expected=2)
    run = PipelineRun(
        golden_id=golden.id,
        predicted=[_finding("security")],
        active_agents=[AgentType.SECURITY],
    )
    match = MatchResult(
        golden_id=golden.id,
        category="security",
        matches=[Match(expected=golden.expected_findings[0], predicted=run.predicted[0])],
        missed=[golden.expected_findings[1]],
        spurious=[],
    )

    result = score([(golden, run, match)])
    sec = result.per_category["security"]
    assert sec.tp == 1
    assert sec.fn == 1
    assert sec.fp == 0
    assert sec.precision == 1.0
    assert sec.recall == 0.5
    assert result.routing_total == 1
    assert result.routing_correct == 1
    assert result.routing_accuracy == 1.0


def test_spurious_finding_buckets_to_its_category() -> None:
    golden = _golden("security", expected=1)
    perf_fp = _finding("perf")
    run = PipelineRun(
        golden_id=golden.id,
        predicted=[perf_fp],
        active_agents=[AgentType.SECURITY],
    )
    match = MatchResult(
        golden_id=golden.id,
        category="security",
        matches=[],
        missed=[golden.expected_findings[0]],
        spurious=[perf_fp],
    )
    result = score([(golden, run, match)])
    assert result.per_category["security"].fn == 1
    assert result.per_category["perf"].fp == 1


def test_routing_miss_counted() -> None:
    golden = _golden("perf", expected=1)
    run = PipelineRun(
        golden_id=golden.id,
        predicted=[],
        active_agents=[AgentType.SECURITY],  # perf not routed
    )
    match = MatchResult(
        golden_id=golden.id,
        category="perf",
        matches=[],
        missed=[golden.expected_findings[0]],
        spurious=[],
    )
    result = score([(golden, run, match)])
    assert result.routing_total == 1
    assert result.routing_correct == 0
    assert result.routing_accuracy == 0.0


def test_clean_pr_false_positive_rate() -> None:
    clean_flagged = _golden("clean")
    clean_ok = _golden("clean")
    run_flagged = PipelineRun(
        golden_id=clean_flagged.id,
        predicted=[_finding("security"), _finding("arch")],
        active_agents=[AgentType.SECURITY],
    )
    run_ok = PipelineRun(golden_id=clean_ok.id, predicted=[], active_agents=[])

    result = score([(clean_flagged, run_flagged, None), (clean_ok, run_ok, None)])
    assert result.clean_pr_count == 2
    assert result.clean_prs_flagged == 1
    assert result.clean_fp_findings == 2
    assert result.clean_false_positive_rate == 0.5
    assert result.per_category["security"].fp == 1
    assert result.per_category["arch"].fp == 1


def test_errored_run_is_recorded_not_scored() -> None:
    golden = _golden("security", expected=1)
    run = PipelineRun(golden_id=golden.id, error="boom")
    result = score([(golden, run, None)])
    assert result.errored == [golden.id]
    assert result.per_category["security"].tp == 0
    assert result.per_category["security"].fn == 0


def test_overall_precision_recall_aggregate() -> None:
    g1 = _golden("security", expected=2)
    r1 = PipelineRun(
        golden_id=g1.id,
        predicted=[_finding("security")],
        active_agents=[AgentType.SECURITY],
    )
    m1 = MatchResult(
        golden_id=g1.id,
        category="security",
        matches=[Match(expected=g1.expected_findings[0], predicted=r1.predicted[0])],
        missed=[g1.expected_findings[1]],
        spurious=[],
    )
    g2 = _golden("perf", expected=1)
    extra = _finding("perf")
    r2 = PipelineRun(
        golden_id=g2.id,
        predicted=[_finding("perf"), extra],
        active_agents=[AgentType.PERF],
    )
    m2 = MatchResult(
        golden_id=g2.id,
        category="perf",
        matches=[Match(expected=g2.expected_findings[0], predicted=r2.predicted[0])],
        missed=[],
        spurious=[extra],
    )
    result = score([(g1, r1, m1), (g2, r2, m2)])
    # TP=2, FP=1, FN=1 → precision 2/3, recall 2/3
    assert round(result.overall_precision, 3) == 0.667
    assert round(result.overall_recall, 3) == 0.667
