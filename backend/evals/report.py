"""
Reporting (F-08): render the eval score as a console table, a JSON artifact,
and persisted rows in eval_runs / eval_results.

`evals/` is an outer app (sibling to worker/), so it may import infrastructure
directly. Persistence writes through the ORM, not via a domain repository.
"""
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.db.models.eval_run import EvalResultORM, EvalRunORM

from evals.scorer import EvalScore


def _per_category_dict(score: EvalScore) -> dict[str, dict[str, float | int]]:
    return {
        cat: {
            "tp": c.tp,
            "fp": c.fp,
            "fn": c.fn,
            "precision": round(c.precision, 4),
            "recall": round(c.recall, 4),
            "f1": round(c.f1, 4),
        }
        for cat, c in score.per_category.items()
    }


def render_console(score: EvalScore) -> str:
    lines: list[str] = []
    lines.append("")
    lines.append("=" * 68)
    lines.append("  GOLDEN-SET EVALUATION REPORT")
    lines.append("=" * 68)
    header = f"  {'category':<10} {'TP':>4} {'FP':>4} {'FN':>4} " \
             f"{'precision':>10} {'recall':>8} {'f1':>7}"
    lines.append(header)
    lines.append("  " + "-" * 64)
    for cat, c in score.per_category.items():
        lines.append(
            f"  {cat:<10} {c.tp:>4} {c.fp:>4} {c.fn:>4} "
            f"{c.precision:>10.3f} {c.recall:>8.3f} {c.f1:>7.3f}"
        )
    lines.append("  " + "-" * 64)
    lines.append(
        f"  {'OVERALL':<10} "
        f"{'':>4} {'':>4} {'':>4} "
        f"{score.overall_precision:>10.3f} "
        f"{score.overall_recall:>8.3f} {score.overall_f1:>7.3f}"
    )
    lines.append("")
    lines.append(
        f"  Clean false-positive rate : {score.clean_false_positive_rate:.3f} "
        f"({score.clean_prs_flagged}/{score.clean_pr_count} clean PRs flagged, "
        f"{score.clean_fp_findings} spurious findings)"
    )
    lines.append(
        f"  Supervisor routing accuracy: {score.routing_accuracy:.3f} "
        f"({score.routing_correct}/{score.routing_total} flaw PRs routed correctly)"
    )
    if score.errored:
        lines.append(f"  Errored PRs ({len(score.errored)}): {', '.join(score.errored)}")
    lines.append("=" * 68)
    lines.append("")
    return "\n".join(lines)


def print_report(score: EvalScore) -> None:
    sys.stdout.write(render_console(score))
    sys.stdout.flush()


def write_json(score: EvalScore, path: Path) -> Path:
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "total_prs": len(score.pr_scores) + len(score.errored),
        "errored_prs": len(score.errored),
        "overall": {
            "precision": round(score.overall_precision, 4),
            "recall": round(score.overall_recall, 4),
            "f1": round(score.overall_f1, 4),
        },
        "clean_false_positive_rate": round(score.clean_false_positive_rate, 4),
        "routing_accuracy": round(score.routing_accuracy, 4),
        "per_category": _per_category_dict(score),
        "pr_scores": [
            {
                "golden_id": p.golden_id,
                "category": p.category,
                "expected": p.expected,
                "tp": p.tp,
                "fp": p.fp,
                "fn": p.fn,
                "routed_correctly": p.routed_correctly,
                "missed_findings": p.missed_findings,
                "spurious_findings": p.spurious_findings,
            }
            for p in score.pr_scores
        ],
        "errored": score.errored,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


async def persist(
    session: AsyncSession,
    score: EvalScore,
    *,
    model_id: str,
    notes: str | None = None,
) -> UUID:
    run_id = uuid4()
    now = datetime.now(UTC)
    run = EvalRunORM(
        id=run_id,
        model_id=model_id,
        total_prs=len(score.pr_scores) + len(score.errored),
        errored_prs=len(score.errored),
        overall_precision=score.overall_precision,
        overall_recall=score.overall_recall,
        overall_f1=score.overall_f1,
        false_positive_rate=score.clean_false_positive_rate,
        routing_accuracy=score.routing_accuracy,
        per_category=_per_category_dict(score),
        notes=notes,
        created_at=now,
        updated_at=now,
    )
    session.add(run)
    # Flush so the eval_runs row exists in the DB before inserting eval_results
    # rows that reference it via FK.
    await session.flush()
    for p in score.pr_scores:
        session.add(
            EvalResultORM(
                id=uuid4(),
                run_id=run_id,
                golden_id=p.golden_id,
                category=p.category,
                expected_count=p.expected,
                true_positives=p.tp,
                false_positives=p.fp,
                false_negatives=p.fn,
                routed_correctly=p.routed_correctly,
                created_at=now,
                updated_at=now,
            )
        )
    await session.commit()
    return run_id
