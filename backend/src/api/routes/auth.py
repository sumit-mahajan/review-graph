from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.middleware.auth_middleware import DbSession
from api.schemas.dashboard import (
    AuthTokenDTO,
)
from application.use_cases.handle_github_auth import HandleGithubAuthUseCase
from infrastructure.db.repositories.user_repository import PostgresUserRepository

router = APIRouter(prefix="/auth", tags=["auth"])

# In-memory OAuth state store for development (replace with Redis in production)
_oauth_states: set[str] = set()


def _auth_use_case(session: AsyncSession) -> HandleGithubAuthUseCase:
    from api.dependencies.session import get_github_oauth_client, get_jwt_service

    return HandleGithubAuthUseCase(
        PostgresUserRepository(session),
        get_github_oauth_client(),
        get_jwt_service(),
    )


@router.get("/github")
async def github_login(session: DbSession) -> RedirectResponse:
    use_case = _auth_use_case(session)
    url, state = use_case.build_login_redirect()
    _oauth_states.add(state)
    return RedirectResponse(url=url, status_code=302)


@router.get("/callback", response_model=AuthTokenDTO)
async def auth_callback(
    session: DbSession,
    code: str = Query(...),
    state: str = Query(...),
) -> AuthTokenDTO:
    if state not in _oauth_states:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="Invalid OAuth state")
    _oauth_states.discard(state)
    return await _auth_use_case(session).handle_callback(code)
