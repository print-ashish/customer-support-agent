from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    redis_url: str = "redis://127.0.0.1:6380/0"
    rate_limit_enabled: bool = True

    chat_requests_per_minute: int = 20
    auth_requests_per_minute: int = 10
    chat_history_requests_per_minute: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
