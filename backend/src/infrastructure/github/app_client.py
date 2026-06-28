import base64
import time
from pathlib import Path

import httpx
from jose import jwt

from domain.errors import ExternalServiceError
from domain.services.i_github_app_client import (
    GithubRepositorySummary,
    IGithubAppClient,
    InstallationAccessToken,
)

GITHUB_API = "https://api.github.com"


class GithubAppClient(IGithubAppClient):
    def __init__(
        self,
        app_id: str,
        private_key_pem: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._app_id = app_id
        self._private_key_pem = private_key_pem
        self._http = http_client or httpx.AsyncClient(timeout=30.0)

    @classmethod
    def from_settings(
        cls,
        app_id: str,
        private_key_b64: str | None,
        private_key_path: str | None,
    ) -> "GithubAppClient":
        pem = _load_private_key(private_key_b64, private_key_path)
        return cls(app_id=app_id, private_key_pem=pem)

    def create_app_jwt(self) -> str:
        now = int(time.time())
        payload = {
            "iat": now - 60,
            "exp": now + 9 * 60,
            "iss": self._app_id,
        }
        return jwt.encode(payload, self._private_key_pem, algorithm="RS256")

    async def get_installation_access_token(self, installation_id: int) -> InstallationAccessToken:
        app_jwt = self.create_app_jwt()
        url = f"{GITHUB_API}/app/installations/{installation_id}/access_tokens"
        response = await self._http.post(
            url,
            headers={
                "Authorization": f"Bearer {app_jwt}",
                "Accept": "application/vnd.github+json",
            },
        )
        if response.status_code >= 400:
            raise ExternalServiceError(
                f"GitHub installation token request failed: {response.status_code}"
            )
        data = response.json()
        return InstallationAccessToken(
            token=str(data["token"]),
            expires_at=str(data["expires_at"]),
        )

    async def list_installation_repositories(
        self, installation_id: int
    ) -> list[GithubRepositorySummary]:
        token = await self.get_installation_access_token(installation_id)
        url = f"{GITHUB_API}/installation/repositories"
        response = await self._http.get(
            url,
            headers={
                "Authorization": f"Bearer {token.token}",
                "Accept": "application/vnd.github+json",
            },
        )
        if response.status_code >= 400:
            raise ExternalServiceError(f"GitHub list repositories failed: {response.status_code}")

        data = response.json()
        repositories = data.get("repositories", [])
        return [
            GithubRepositorySummary(
                github_id=int(repo["id"]),
                owner=str(repo["owner"]["login"]),
                name=str(repo["name"]),
                full_name=str(repo["full_name"]),
                default_branch=str(repo.get("default_branch") or "main"),
                language=repo.get("language"),
            )
            for repo in repositories
        ]


def _load_private_key(private_key_b64: str | None, private_key_path: str | None) -> str:
    if private_key_b64:
        return base64.b64decode(private_key_b64).decode()
    if private_key_path:
        return Path(private_key_path).read_text(encoding="utf-8")
    raise ExternalServiceError("GitHub App private key is not configured")
