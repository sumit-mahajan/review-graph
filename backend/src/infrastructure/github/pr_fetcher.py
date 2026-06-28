"""
GitHubPrFetcher — fetches PR diffs and file content via the GitHub REST API.

Uses installation access tokens from GithubAppClient.
"""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING

import httpx

from domain.errors import ExternalServiceError
from domain.services.i_pr_fetcher import FilePatch, IPrFetcher, PullRequestDiff

if TYPE_CHECKING:
    from infrastructure.github.app_client import GithubAppClient

GITHUB_API = "https://api.github.com"


class GitHubPrFetcher(IPrFetcher):
    def __init__(self, app_client: GithubAppClient) -> None:
        self._app = app_client
        self._http = httpx.AsyncClient(timeout=30.0)

    async def _headers(self, installation_id: int) -> dict[str, str]:
        token = await self._app.get_installation_access_token(installation_id)
        return {
            "Authorization": f"Bearer {token.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def fetch_diff(
        self,
        installation_id: int,
        owner: str,
        repo: str,
        base_sha: str,
        head_sha: str,
    ) -> PullRequestDiff:
        headers = await self._headers(installation_id)

        # Compare endpoint returns the full diff between two commits
        url = f"{GITHUB_API}/repos/{owner}/{repo}/compare/{base_sha}...{head_sha}"
        response = await self._http.get(
            url,
            headers={**headers, "Accept": "application/vnd.github.diff"},
        )
        if response.status_code >= 400:
            raise ExternalServiceError(
                f"GitHub compare API failed: {response.status_code} for {owner}/{repo}"
            )

        # Parse the unified diff into file patches
        # Fall back to JSON endpoint for metadata
        json_response = await self._http.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/compare/{base_sha}...{head_sha}",
            headers=headers,
        )
        if json_response.status_code >= 400:
            raise ExternalServiceError(f"GitHub compare JSON failed: {json_response.status_code}")

        data = json_response.json()
        base_commit = data.get("base_commit", {}).get("commit", {}).get("tree", {})
        base_branch = base_commit.get("sha", base_sha)
        head_branch = data.get("merge_base_commit", {}).get("sha", head_sha)

        file_patches: list[FilePatch] = []
        for f in data.get("files", []):
            file_patches.append(
                FilePatch(
                    path=str(f.get("filename", "")),
                    status=str(f.get("status", "modified")),
                    additions=int(f.get("additions", 0)),
                    deletions=int(f.get("deletions", 0)),
                    patch=str(f.get("patch", "")),
                    old_path=f.get("previous_filename"),
                )
            )

        return PullRequestDiff(
            pr_number=0,  # Not available from compare; caller sets this
            base_sha=base_sha,
            head_sha=head_sha,
            base_branch=base_branch,
            head_branch=head_branch,
            file_patches=file_patches,
        )

    async def fetch_file_content(
        self,
        installation_id: int,
        owner: str,
        repo: str,
        path: str,
        ref: str,
    ) -> str:
        headers = await self._headers(installation_id)
        url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}?ref={ref}"
        response = await self._http.get(url, headers=headers)

        if response.status_code == 404:
            return ""  # File doesn't exist at this ref (new file)
        if response.status_code >= 400:
            raise ExternalServiceError(
                f"GitHub contents API failed: {response.status_code} for {path}@{ref}"
            )

        data = response.json()
        if data.get("encoding") == "base64":
            raw = data["content"].replace("\n", "")
            return base64.b64decode(raw).decode("utf-8", errors="replace")

        return str(data.get("content", ""))

    async def fetch_diff_for_pr(
        self,
        installation_id: int,
        owner: str,
        repo: str,
        pr_number: int,
    ) -> PullRequestDiff:
        headers = await self._headers(installation_id)
        url = f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}"
        response = await self._http.get(url, headers=headers)
        if response.status_code >= 400:
            raise ExternalServiceError(
                f"GitHub pull request fetch failed: {response.status_code} "
                f"for {owner}/{repo}#{pr_number}"
            )

        data = response.json()
        base_sha = str(data["base"]["sha"])
        head_sha = str(data["head"]["sha"])
        diff = await self.fetch_diff(
            installation_id=installation_id,
            owner=owner,
            repo=repo,
            base_sha=base_sha,
            head_sha=head_sha,
        )
        return PullRequestDiff(
            pr_number=pr_number,
            base_sha=diff.base_sha,
            head_sha=diff.head_sha,
            base_branch=str(data["base"].get("ref", diff.base_branch)),
            head_branch=str(data["head"].get("ref", diff.head_branch)),
            file_patches=diff.file_patches,
        )
