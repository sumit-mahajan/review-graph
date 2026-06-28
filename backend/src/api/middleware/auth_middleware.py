from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.user import User
from domain.errors import DomainError
from domain.services.i_jwt_service import IJwtService
from infrastructure.db.repositories.user_repository import PostgresUserRepository

if TYPE_CHECKING:
    from domain.repositories.i_user_repository import IUserRepository

_bearer = HTTPBearer(auto_error=False)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    from api.dependencies.session import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        yield session


def resolve_jwt_service() -> IJwtService:
    from api.dependencies.session import get_jwt_service as _factory

    return _factory()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    jwt_service: Annotated[IJwtService, Depends(resolve_jwt_service)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Missing or invalid Bearer token")

    try:
        payload = jwt_service.decode_token(credentials.credentials)
    except DomainError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    user_repo: IUserRepository = PostgresUserRepository(session)
    user = await user_repo.get_by_github_id(payload.github_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User session is no longer valid")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[AsyncSession, Depends(get_db_session)]
