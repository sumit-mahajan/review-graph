import asyncio
import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from infrastructure.db.database_url import normalize_async_database_url
from infrastructure.db.models.base import Base
from infrastructure.db.models.code_embedding import CodeEmbeddingORM  # noqa: F401
from infrastructure.db.models.finding import FindingORM  # noqa: F401
from infrastructure.db.models.installation import GithubInstallationORM  # noqa: F401
from infrastructure.db.models.repository import RepositoryORM  # noqa: F401
from infrastructure.db.models.review import ReviewORM  # noqa: F401
from infrastructure.db.models.review_job import ReviewJobORM  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

_REPO_ROOT = Path(__file__).resolve().parents[5]


def _load_database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        for env_file in (_REPO_ROOT / ".env", Path.cwd() / ".env"):
            if not env_file.is_file():
                continue
            for line in env_file.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith("DATABASE_URL="):
                    url = stripped.split("=", 1)[1].strip().strip('"').strip("'")
                    break
            if url:
                break

    return url


_raw_database_url = _load_database_url()
if not _raw_database_url:
    msg = (
        "DATABASE_URL is not set. Add it to the repo root .env or export it in your shell."
    )
    raise RuntimeError(msg)

database_url, database_connect_args = normalize_async_database_url(_raw_database_url)

# ConfigParser treats '%' specially; escape for alembic.ini storage.
config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = create_async_engine(
        database_url,
        poolclass=pool.NullPool,
        connect_args=database_connect_args,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
