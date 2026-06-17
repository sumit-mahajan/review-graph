"""Normalize Postgres URLs for SQLAlchemy asyncpg (Neon-compatible)."""

from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


def normalize_async_database_url(url: str) -> tuple[str, dict[str, object]]:
    """Return (url, connect_args) suitable for create_async_engine + asyncpg."""
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    connect_args: dict[str, object] = {}

    sslmode = query.pop("sslmode", [None])[0]
    if sslmode in ("require", "verify-full", "verify-ca", "prefer"):
        connect_args["ssl"] = True

    # Neon may add channel_binding=require; asyncpg does not accept it.
    query.pop("channel_binding", None)

    clean_query = urlencode({key: values[0] for key, values in query.items()})
    clean_url = urlunparse(parsed._replace(query=clean_query))
    return clean_url, connect_args
