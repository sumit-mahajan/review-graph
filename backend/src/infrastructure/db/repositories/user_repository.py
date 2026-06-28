from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.user import User
from domain.repositories.i_user_repository import IUserRepository, UpsertUserParams
from infrastructure.db.models.user import UserORM


class PostgresUserRepository(IUserRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_github_id(self, github_id: int) -> User | None:
        result = await self._session.execute(select(UserORM).where(UserORM.github_id == github_id))
        orm = result.scalar_one_or_none()
        return _to_entity(orm) if orm else None

    async def upsert(self, params: UpsertUserParams) -> User:
        result = await self._session.execute(
            select(UserORM).where(UserORM.github_id == params.github_id)
        )
        orm = result.scalar_one_or_none()

        if orm is None:
            orm = UserORM(
                github_id=params.github_id,
                login=params.login,
                email=params.email,
                avatar_url=params.avatar_url,
            )
            self._session.add(orm)
        else:
            orm.login = params.login
            orm.email = params.email
            orm.avatar_url = params.avatar_url

        await self._session.commit()
        await self._session.refresh(orm)
        return _to_entity(orm)


def _to_entity(orm: UserORM) -> User:
    return User(
        id=orm.id,
        github_id=orm.github_id,
        login=orm.login,
        email=orm.email,
        avatar_url=orm.avatar_url,
        created_at=orm.created_at,
        updated_at=orm.updated_at,
    )
