"""Tests for GithubCommentPoster payload formatting."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from domain.services.i_github_comment_poster import ReviewComment
from infrastructure.github.comment_poster import GithubCommentPoster, _to_github_comment


def test_single_line_comment_payload() -> None:
    payload = _to_github_comment(ReviewComment(file_path="a.py", line=10, body="issue"))
    assert payload == {
        "path": "a.py",
        "body": "issue",
        "side": "RIGHT",
        "line": 10,
    }


def test_multiline_comment_payload() -> None:
    payload = _to_github_comment(
        ReviewComment(file_path="a.py", line=10, line_end=15, body="issue")
    )
    assert payload["start_line"] == 10
    assert payload["line"] == 15
    assert payload["start_side"] == "RIGHT"


@pytest.mark.asyncio
async def test_post_review_falls_back_to_summary_on_422() -> None:
    app_client = AsyncMock()
    app_client.get_installation_access_token.return_value = MagicMock(token="tok")

    http = AsyncMock()
    fail_response = MagicMock(status_code=422, text='{"message":"Validation Failed"}')
    ok_response = MagicMock(
        status_code=200,
        json=lambda: {"id": 42, "comments": []},
    )
    http.post = AsyncMock(side_effect=[fail_response, ok_response])

    poster = GithubCommentPoster(app_client, http_client=http)
    result = await poster.post_pull_request_review(
        installation_id=1,
        owner="org",
        repo="repo",
        pr_number=5,
        commit_id="a" * 40,
        summary_body="Summary",
        comments=[ReviewComment(file_path="a.py", line=1, body="issue")],
    )

    assert result.github_review_id == 42
    assert http.post.await_count == 2
    second_payload = http.post.await_args_list[1].kwargs["json"]
    assert "comments" not in second_payload
