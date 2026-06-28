"""
Scorer (F-08).

Aggregates per-golden-PR match results into precision / recall / F1 per agent
category, plus the false-positive rate measured on clean PRs and the Supervisor
routing accuracy on flaw PRs.

Counting rules:
  - Flaw PR (category C): matched expected → TP[C]; unmatched expected → FN[C];
    each spurious prediction → FP[its own category].
  - Clean PR: no expected findings; every prediction is a false positive
    (bucketed by its category) and counts toward the clean FP rate.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from domain.value_objects.agent_type import AgentType

from evals.harness import PipelineRun
from evals.matcher import MatchResult
from evals.schema import GoldenPR

CATEGORIES = [a.value for a in AgentType]  # security, perf, arch, test


@dataclass
class CategoryScore:
    category: str
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.tp + self.fn
        return self.tp / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0


@dataclass
class PRScore:
    golden_id: str
    category: str
    expected: int
    tp: int
    fp: int
    fn: int
    routed_correctly: bool


@dataclass
class EvalScore:
    per_category: dict[str, CategoryScore] = field(default_factory=dict)
    pr_scores: list[PRScore] = field(default_factory=list)
    clean_pr_count: int = 0
    clean_prs_flagged: int = 0      # clean PRs with ≥1 spurious finding
    clean_fp_findings: int = 0      # total spurious findings on clean PRs
    routing_correct: int = 0
    routing_total: int = 0
    errored: list[str] = field(default_factory=list)

    @property
    def clean_false_positive_rate(self) -> float:
        return self.clean_prs_flagged / self.clean_pr_count if self.clean_pr_count else 0.0

    @property
    def routing_accuracy(self) -> float:
        return self.routing_correct / self.routing_total if self.routing_total else 0.0

    @property
    def overall_precision(self) -> float:
        tp = sum(c.tp for c in self.per_category.values())
        fp = sum(c.fp for c in self.per_category.values())
        return tp / (tp + fp) if (tp + fp) else 0.0

    @property
    def overall_recall(self) -> float:
        tp = sum(c.tp for c in self.per_category.values())
        fn = sum(c.fn for c in self.per_category.values())
        return tp / (tp + fn) if (tp + fn) else 0.0

    @property
    def overall_f1(self) -> float:
        p, r = self.overall_precision, self.overall_recall
        return 2 * p * r / (p + r) if (p + r) else 0.0


def score(
    items: list[tuple[GoldenPR, PipelineRun, MatchResult | None]],
) -> EvalScore:
    result = EvalScore(
        per_category={c: CategoryScore(category=c) for c in CATEGORIES}
    )

    for golden, run, match in items:
        if run.error is not None:
            result.errored.append(golden.id)
            continue

        if golden.category == "clean":
            result.clean_pr_count += 1
            spurious = len(run.predicted)
            result.clean_fp_findings += spurious
            if spurious:
                result.clean_prs_flagged += 1
            for pred in run.predicted:
                bucket = result.per_category.get(pred.category)
                if bucket is not None:
                    bucket.fp += 1
            result.pr_scores.append(
                PRScore(
                    golden_id=golden.id,
                    category="clean",
                    expected=0,
                    tp=0,
                    fp=spurious,
                    fn=0,
                    routed_correctly=True,
                )
            )
            continue

        if match is None:
            result.errored.append(golden.id)
            continue

        # Flaw PR
        cat = golden.category
        bucket = result.per_category[cat]
        bucket.tp += match.true_positives
        bucket.fn += match.false_negatives
        for pred in match.spurious:
            spur_bucket = result.per_category.get(pred.category)
            if spur_bucket is not None:
                spur_bucket.fp += 1

        routed = any(a.value == cat for a in run.active_agents)
        result.routing_total += 1
        if routed:
            result.routing_correct += 1

        result.pr_scores.append(
            PRScore(
                golden_id=golden.id,
                category=cat,
                expected=len(golden.expected_findings),
                tp=match.true_positives,
                fp=match.false_positives,
                fn=match.false_negatives,
                routed_correctly=routed,
            )
        )

    return result
