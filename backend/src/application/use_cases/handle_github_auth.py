import secrets

from api.schemas.dashboard import AuthTokenDTO
from application.dtos.dashboard_mappers import to_user_dto
from domain.repositories.i_user_repository import IUserRepository, UpsertUserParams
from domain.services.i_github_oauth_client import IGithubOAuthClient
from domain.services.i_jwt_service import IJwtService


class HandleGithubAuthUseCase:
    def __init__(
        self,
        user_repo: IUserRepository,
        oauth_client: IGithubOAuthClient,
        jwt_service: IJwtService,
    ) -> None:
        self._user_repo = user_repo
        self._oauth_client = oauth_client
        self._jwt_service = jwt_service

    def build_login_redirect(self) -> tuple[str, str]:
        """Return (authorize_url, state) for the OAuth redirect."""
        state = secrets.token_urlsafe(32)
        return self._oauth_client.build_authorize_url(state), state

    async def handle_callback(self, code: str) -> AuthTokenDTO:
        profile = await self._oauth_client.exchange_code(code)
        user = await self._user_repo.upsert(
            UpsertUserParams(
                github_id=profile.github_id,
                login=profile.login,
                email=profile.email,
                avatar_url=profile.avatar_url,
            )
        )
        token = self._jwt_service.create_token(
            user_id=user.id,
            github_id=user.github_id,
            login=user.login,
        )
        return AuthTokenDTO(
            access_token=token,
            user=to_user_dto(user),
        )
