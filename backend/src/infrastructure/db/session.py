from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from infrastructure.config.settings import Settings
from infrastructure.db.database_url import normalize_async_database_url


def create_engine(database_url: str) -> AsyncEngine:
    url, connect_args = normalize_async_database_url(database_url)
    return create_async_engine(
        url,
        echo=False,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


def create_session_factory(settings: Settings) -> async_sessionmaker[AsyncSession]:
    engine = create_engine(settings.database_url)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as session:
        yield session
