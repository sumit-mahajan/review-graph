"""PostReviewToGithubUseCase — publishes review summary + inline comments to GitHub."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from domain.errors import EntityNotFoundError
from domain.services.i_github_comment_poster import IGithubCommentPoster, ReviewComment
from domain.utils.diff_utils import build_diff_line_index, is_comment_on_diff
from domain.value_objects.severity import Severity, severity_meets_minimum

if TYPE_CHECKING:
    from domain.entities.review import Finding, Review
    from domain.repositories.i_installation_repository import IInstallationRepository
    from domain.repositories.i_repo_repository import IRepoRepository
    from domain.repositories.i_review_repository import IReviewRepository
    from domain.services.i_pr_fetcher import IPrFetcher

logger = structlog.get_logger()


class PostReviewToGithubUseCase:
    def __init__(
        self,
        review_repo: IReviewRepository,
        repo_repo: IRepoRepository,
        installation_repo: IInstallationRepository,
        comment_poster: IGithubCommentPoster,
        *,
        pr_fetcher: IPrFetcher | None = None,
        min_severity: Severity = Severity.MEDIUM,
    ) -> None:
        self._review_repo = review_repo
        self._repo_repo = repo_repo
        self._installation_repo = installation_repo
        self._comment_poster = comment_poster
        self._pr_fetcher = pr_fetcher
        self._min_severity = min_severity

    async def execute(self, review: Review) -> Review:
        if review.posted_to_github:
            await logger.ainfo(
                "github_post_idempotent_skip",
                review_id=str(review.id),
            )
            return review

        repository = await self._repo_repo.get_by_id(review.repository_id)
        if repository is None:
            raise EntityNotFoundError(
                f"Repository {review.repository_id} not found for review {review.id}"
            )

        installation = await self._installation_repo.get_by_id(repository.installation_id)
        if installation is None:
            raise EntityNotFoundError(
                f"Installation {repository.installation_id} not found for review {review.id}"
            )

        postable = [
            f for f in review.findings if severity_meets_minimum(f.severity, self._min_severity)
        ]

        inline_findings = [f for f in postable if f.line_start is not None]
        comments = _build_review_comments(inline_findings)

        if self._pr_fetcher is not None and comments:
            try:
                diff = await self._pr_fetcher.fetch_diff_for_pr(
                    installation_id=installation.installation_id,
                    owner=repository.owner,
                    repo=repository.name,
                    pr_number=review.pr_number,
                )
                diff_lines = build_diff_line_index(diff.file_patches)
                comments, dropped = _filter_comments_to_diff(comments, diff_lines)
                if dropped:
                    await logger.awarning(
                        "github_inline_comments_dropped_not_in_diff",
                        review_id=str(review.id),
                        dropped=dropped,
                        kept=len(comments),
                    )
            except Exception as exc:  # noqa: BLE001
                await logger.awarning(
                    "github_diff_lookup_failed",
                    review_id=str(review.id),
                    error=str(exc)[:300],
                )

        summary_body = build_summary_body(review.summary, postable)

        result = await self._comment_poster.post_pull_request_review(
            installation_id=installation.installation_id,
            owner=repository.owner,
            repo=repository.name,
            pr_number=review.pr_number,
            commit_id=review.head_sha,
            summary_body=summary_body,
            comments=comments,
        )

        if inline_findings and result.comment_ids:
            posted_findings = inline_findings[: len(result.comment_ids)]
            updates = list(
                zip(
                    (f.id for f in posted_findings),
                    result.comment_ids,
                    strict=False,
                )
            )
            if updates:
                await self._review_repo.update_finding_comment_ids(updates)

        updated = await self._review_repo.mark_posted_to_github(review.id)
        await logger.ainfo(
            "github_review_posted",
            review_id=str(review.id),
            github_review_id=result.github_review_id,
            inline_comments=len(comments),
        )
        return updated


def _build_review_comments(findings: list[Finding]) -> list[ReviewComment]:
    comments: list[ReviewComment] = []
    for finding in findings:
        if finding.line_start is None or finding.line_start < 1:
            continue
        body = format_finding_comment(finding).strip()
        if not body or not finding.file_path.strip():
            continue
        comments.append(
            ReviewComment(
                file_path=finding.file_path,
                line=finding.line_start,
                line_end=finding.line_end,
                body=body,
            )
        )
    return comments


def _filter_comments_to_diff(
    comments: list[ReviewComment],
    diff_lines: dict[str, set[int]],
) -> tuple[list[ReviewComment], int]:
    kept: list[ReviewComment] = []
    dropped = 0
    for comment in comments:
        if is_comment_on_diff(
            file_path=comment.file_path,
            line=comment.line,
            line_end=comment.line_end,
            diff_lines=diff_lines,
        ):
            kept.append(comment)
        else:
            dropped += 1
    return kept, dropped


def format_finding_comment(finding: Finding) -> str:
    parts = [
        f"**{finding.title}** (`{finding.severity.value}` / {finding.category})",
        "",
        finding.description,
    ]
    if finding.fix_suggestion:
        parts.extend(["", f"**Suggested fix:** {finding.fix_suggestion}"])
    return "\n".join(parts)


def build_summary_body(summary: str | None, findings: list[Finding]) -> str:
    header = "## AI Code Review\n\n"
    if summary:
        body = f"{header}{summary}\n"
    elif not findings:
        body = f"{header}No findings met the configured severity threshold.\n"
    else:
        body = f"{header}Found {len(findings)} issue(s) in this PR.\n"

    if findings:
        body += "\n### Findings\n\n"
        for finding in findings:
            line_ref = ""
            if finding.line_start is not None:
                if finding.line_end and finding.line_end != finding.line_start:
                    line_ref = f" (lines {finding.line_start}–{finding.line_end})"
                else:
                    line_ref = f" (line {finding.line_start})"
            body += (
                f"- **[{finding.severity.value.upper()}]** {finding.title} "
                f"— `{finding.file_path}`{line_ref}\n"
            )
    return body
