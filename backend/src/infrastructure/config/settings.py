from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/src/infrastructure/config/settings.py → repo root is 4 levels up
_REPO_ROOT = Path(__file__).resolve().parents[4]
_ENV_FILE = _REPO_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE if _ENV_FILE.is_file() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = Field(default="development", alias="ENVIRONMENT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/pr_reviewer",
        alias="DATABASE_URL",
    )

    upstash_redis_url: str | None = Field(default=None, alias="UPSTASH_REDIS_URL")
    upstash_redis_token: str | None = Field(default=None, alias="UPSTASH_REDIS_TOKEN")
    redis_queue_stream: str = Field(default="review_jobs", alias="REDIS_QUEUE_STREAM")

    worker_poll_interval_seconds: float = Field(default=5.0, alias="WORKER_POLL_INTERVAL_SECONDS")
    worker_stale_running_minutes: int = Field(default=15, alias="WORKER_STALE_RUNNING_MINUTES")

    github_app_id: str = Field(default="", alias="GITHUB_APP_ID")
    github_app_private_key_b64: str | None = Field(default=None, alias="GITHUB_APP_PRIVATE_KEY_B64")
    github_app_private_key_path: str | None = Field(
        default=None, alias="GITHUB_APP_PRIVATE_KEY_PATH"
    )
    github_webhook_secret: str = Field(default="", alias="GITHUB_WEBHOOK_SECRET")
    github_client_id: str = Field(default="", alias="GITHUB_CLIENT_ID")
    github_client_secret: str = Field(default="", alias="GITHUB_CLIENT_SECRET")

    jwt_secret: str = Field(default="dev-only-change-me", alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_expire_days: int = Field(default=7, alias="JWT_EXPIRE_DAYS")
    frontend_url: str = Field(default="http://localhost:5173", alias="FRONTEND_URL")
    api_base_url: str = Field(default="http://localhost:8000", alias="API_BASE_URL")

    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    langfuse_public_key: str | None = Field(default=None, alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str | None = Field(default=None, alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field(
        default="https://cloud.langfuse.com",
        validation_alias=AliasChoices("LANGFUSE_HOST", "LANGFUSE_BASE_URL"),
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
