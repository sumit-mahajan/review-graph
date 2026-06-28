"""
Eval runner (F-08) — `make eval` / `python -m evals.runner`.

Pipeline:
  load golden fixtures → run each through the real Gemini review pipeline →
  match findings against the answer key (LLM-as-judge) → score → report
  (console + JSON artifact + eval_runs/eval_results rows).

Requires GEMINI_API_KEY. Runs PRs sequentially to respect Gemini free-tier RPM.
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import structlog

from infrastructure.ai.gemini_client import MODEL_ID, GeminiClient
from infrastructure.config.settings import get_settings
from infrastructure.db.session import create_session_factory

from evals import report
from evals.harness import EvalHarness, PipelineRun
from evals.matcher import FindingMatcher, MatchResult, build_gemini_judge
from evals.schema import GoldenPR, golden_root, load_golden_set
from evals.scorer import score

logger = structlog.get_logger()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the golden-set evaluation.")
    parser.add_argument(
        "--category",
        choices=["security", "perf", "arch", "test", "clean"],
        help="Only evaluate fixtures of this category.",
    )
    parser.add_argument("--limit", type=int, help="Evaluate at most N fixtures.")
    parser.add_argument(
        "--no-judge",
        action="store_true",
        help="Skip the LLM-as-judge; use rule-only matching (cheaper, less precise).",
    )
    parser.add_argument(
        "--no-db",
        action="store_true",
        help="Do not persist results to eval_runs/eval_results.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent / "results" / "latest.json",
        help="Path for the JSON results artifact.",
    )
    return parser.parse_args(argv)


def _select(fixtures: list[GoldenPR], args: argparse.Namespace) -> list[GoldenPR]:
    selected = fixtures
    if args.category:
        selected = [g for g in selected if g.category == args.category]
    if args.limit is not None:
        selected = selected[: args.limit]
    return selected


async def run_eval(args: argparse.Namespace) -> int:
    settings = get_settings()
    if not settings.gemini_api_key:
        await logger.aerror("eval_aborted", reason="GEMINI_API_KEY is not set")
        return 1

    fixtures = _select(load_golden_set(golden_root()), args)
    if not fixtures:
        await logger.aerror("eval_aborted", reason="no fixtures found")
        return 1

    await logger.ainfo("eval_started", fixtures=len(fixtures), use_judge=not args.no_judge)

    gemini = GeminiClient(settings.gemini_api_key)
    harness = EvalHarness(gemini)
    matcher = FindingMatcher(judge=None if args.no_judge else build_gemini_judge(gemini))

    items: list[tuple[GoldenPR, PipelineRun, MatchResult | None]] = []
    for golden in fixtures:
        run = await harness.run(golden)
        match: MatchResult | None = None
        if run.error is None and golden.category != "clean":
            match = await matcher.match(
                golden_id=golden.id,
                category=golden.category,
                expected=golden.expected_findings,
                predicted=run.predicted,
            )
        items.append((golden, run, match))

    result = score(items)

    report.print_report(result)
    out_path = report.write_json(result, args.out)
    await logger.ainfo("eval_artifact_written", path=str(out_path))

    if not args.no_db:
        try:
            session_factory = create_session_factory(settings)
            async with session_factory() as session:
                run_id = await report.persist(session, result, model_id=MODEL_ID)
            await logger.ainfo("eval_persisted", run_id=str(run_id))
        except Exception as exc:  # noqa: BLE001
            await logger.awarning("eval_persist_failed", error=str(exc)[:300])

    return 0


def main() -> None:
    args = _parse_args()
    raise SystemExit(asyncio.run(run_eval(args)))


if __name__ == "__main__":
    main()
