from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = Field(default="dev", alias="APP_ENV")
    app_timezone: str = Field(default="Asia/Shanghai", alias="APP_TIMEZONE")
    app_language_mode: str = Field(default="zh_with_en_terms", alias="APP_LANGUAGE_MODE")

    assistant_db_url: str = Field(alias="ASSISTANT_DB_URL")

    temporal_host: str = Field(alias="TEMPORAL_HOST")
    temporal_namespace: str = Field(default="default", alias="TEMPORAL_NAMESPACE")
    temporal_task_queue_ingest: str = Field(default="ingest", alias="TEMPORAL_TASK_QUEUE_INGEST")
    temporal_task_queue_process: str = Field(default="process", alias="TEMPORAL_TASK_QUEUE_PROCESS")
    temporal_task_queue_verify: str = Field(default="verify", alias="TEMPORAL_TASK_QUEUE_VERIFY")
    temporal_task_queue_push: str = Field(default="push", alias="TEMPORAL_TASK_QUEUE_PUSH")
    temporal_task_queue_digest: str = Field(default="digest", alias="TEMPORAL_TASK_QUEUE_DIGEST")
    temporal_task_queue_deepdive: str = Field(default="deepdive", alias="TEMPORAL_TASK_QUEUE_DEEPDIVE")

    deepseek_api_key: str = Field(alias="DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field(default="https://api.deepseek.com", alias="DEEPSEEK_BASE_URL")
    llm_model_summary: str = Field(default="deepseek-chat", alias="LLM_MODEL_SUMMARY")
    llm_model_score: str = Field(default="deepseek-chat", alias="LLM_MODEL_SCORE")
    llm_model_verify: str = Field(default="deepseek-reasoner", alias="LLM_MODEL_VERIFY")
    llm_model_chat: str = Field(default="deepseek-chat", alias="LLM_MODEL_CHAT")

    tavily_api_key: str | None = Field(default=None, alias="TAVILY_API_KEY")
    tavily_base_url: str = Field(default="https://api.tavily.com", alias="TAVILY_BASE_URL")

    miniflux_base_url: str = Field(alias="MINIFLUX_BASE_URL")
    miniflux_api_token: str = Field(alias="MINIFLUX_API_TOKEN")

    telegram_bot_token: str = Field(alias="TELEGRAM_BOT_TOKEN")
    telegram_webhook_secret: str = Field(alias="TELEGRAM_WEBHOOK_SECRET")
    telegram_target_chat_id: int = Field(alias="TELEGRAM_TARGET_CHAT_ID")
    telegram_admin_user_ids: list[int] = Field(alias="TELEGRAM_ADMIN_USER_IDS")

    a_push_limit_per_day: int = Field(default=10, alias="A_PUSH_LIMIT_PER_DAY")
    rate_limit_user_qpm: int = Field(default=6, alias="RATE_LIMIT_USER_QPM")
    rate_limit_chat_qpm: int = Field(default=60, alias="RATE_LIMIT_CHAT_QPM")
    rate_limit_deepdive_per_day: int = Field(default=5, alias="RATE_LIMIT_DEEPDIVE_PER_DAY")
    monthly_budget_usd: float = Field(default=200.0, alias="MONTHLY_BUDGET_USD")
    internal_api_token: str = Field(alias="INTERNAL_API_TOKEN")

    @field_validator("telegram_admin_user_ids", mode="before")
    @classmethod
    def _parse_admins(cls, value: object) -> list[int]:
        if isinstance(value, list):
            return [int(item) for item in value]
        if isinstance(value, int):
            return [value]
        if isinstance(value, str):
            return [int(chunk.strip()) for chunk in value.split(",") if chunk.strip()]
        raise ValueError("TELEGRAM_ADMIN_USER_IDS must be comma-separated ids")

    @property
    def assistant_db_async_url(self) -> str:
        return _normalize_postgres_scheme(self.assistant_db_url, async_driver=True)

    @property
    def assistant_db_sync_url(self) -> str:
        return _normalize_postgres_scheme(self.assistant_db_url, async_driver=False)


def _normalize_postgres_scheme(url: str, *, async_driver: bool) -> str:
    parsed = urlsplit(url)
    scheme = parsed.scheme

    if scheme in {"postgres", "postgresql"}:
        normalized_scheme = "postgresql+asyncpg" if async_driver else "postgresql"
    elif scheme == "postgresql+asyncpg":
        normalized_scheme = scheme if async_driver else "postgresql"
    else:
        return url

    return urlunsplit((normalized_scheme, parsed.netloc, parsed.path, parsed.query, parsed.fragment))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
