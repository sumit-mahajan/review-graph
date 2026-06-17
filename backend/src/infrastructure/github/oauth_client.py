from urllib.parse import urlencode

import httpx

from domain.errors import ExternalServiceError
from domain.services.i_github_oauth_client import GithubOAuthProfile, IGithubOAuthClient

GITHUB_AUTHORIZE = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN = "https://github.com/login/oauth/access_token"
GITHUB_USER = "https://api.github.com/user"


class GithubOAuthClient(IGithubOAuthClient):
    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._http = http_client or httpx.AsyncClient(timeout=30.0)

    def build_authorize_url(self, state: str) -> str:
        params = {
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "scope": "read:user user:email",
            "state": state,
        }
        return f"{GITHUB_AUTHORIZE}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> GithubOAuthProfile:
        token_response = await self._http.post(
            GITHUB_TOKEN,
            headers={"Accept": "application/json"},
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "code": code,
                "redirect_uri": self._redirect_uri,
            },
        )
        if token_response.status_code >= 400:
            raise ExternalServiceError(
                f"GitHub OAuth token exchange failed: {token_response.status_code}"
            )

        token_data = token_response.json()
        if token_data.get("error"):
            description = token_data.get("error_description") or token_data["error"]
            raise ExternalServiceError(f"GitHub OAuth token exchange failed: {description}")

        access_token = token_data.get("access_token")
        if not access_token:
            raise ExternalServiceError("GitHub OAuth token exchange returned no access_token")

        user_response = await self._http.get(
            GITHUB_USER,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
            },
        )
        if user_response.status_code >= 400:
            raise ExternalServiceError(
                f"GitHub user profile fetch failed: {user_response.status_code}"
            )

        data = user_response.json()
        return GithubOAuthProfile(
            github_id=int(data["id"]),
            login=str(data["login"]),
            email=data.get("email"),
            avatar_url=data.get("avatar_url"),
        )
