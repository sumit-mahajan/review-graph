"""
GithubCommentPoster — posts PR reviews and inline comments via the GitHub REST API.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import structlog

from domain.errors import ExternalServiceError
from domain.services.i_github_comment_poster import (
    IGithubCommentPoster,
    PostedReviewResult,
    ReviewComment,
)

if TYPE_CHECKING:
    from infrastructure.github.app_client import GithubAppClient

logger = structlog.get_logger()
GITHUB_API = "https://api.github.com"


class GithubCommentPoster(IGithubCommentPoster):
    def __init__(
        self,
        app_client: GithubAppClient,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._app = app_client
        self._http = http_client or httpx.AsyncClient(timeout=30.0)

    async def post_pull_request_review(
        self,
        *,
        installation_id: int,
        owner: str,
        repo: str,
        pr_number: int,
        commit_id: str,
        summary_body: str,
        comments: list[ReviewComment],
    ) -> PostedReviewResult:
        token = await self._app.get_installation_access_token(installation_id)
        headers = {
            "Authorization": f"Bearer {token.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        payload: dict[str, object] = {
            "commit_id": commit_id,
            "body": summary_body,
            "event": "COMMENT",
        }

        if comments:
            payload["comments"] = [_to_github_comment(comment) for comment in comments]

        url = f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}/reviews"
        response = await self._http.post(url, headers=headers, json=payload)
        if response.status_code >= 400 and comments:
            await logger.awarning(
                "github_review_inline_comments_rejected",
                status_code=response.status_code,
                pr_number=pr_number,
                inline_comments=len(comments),
                error=response.text[:500],
            )
            payload.pop("comments", None)
            response = await self._http.post(url, headers=headers, json=payload)

        if response.status_code >= 400:
            raise ExternalServiceError(
                "GitHub PR review post failed: "
                f"{response.status_code} for {owner}/{repo}#{pr_number} — {response.text[:300]}"
            )

        data = response.json()
        review_id = int(data["id"])

        comment_ids: list[int] = []
        for item in data.get("comments", []) or []:
            if isinstance(item, dict) and "id" in item:
                comment_ids.append(int(item["id"]))

        return PostedReviewResult(
            github_review_id=review_id,
            comment_ids=tuple(comment_ids),
        )


def _to_github_comment(comment: ReviewComment) -> dict[str, object]:
    body: dict[str, object] = {
        "path": comment.file_path,
        "body": comment.body,
        "side": "RIGHT",
    }
    if comment.line_end is not None and comment.line_end != comment.line:
        body["start_line"] = comment.line
        body["line"] = comment.line_end
        body["start_side"] = "RIGHT"
    else:
        body["line"] = comment.line
    return body
