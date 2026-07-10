from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///:memory:"
    jwt_secret: str = "dev-secret-change-me"
    access_ttl_minutes: int = 15
    refresh_ttl_days: int = 30
    env: str = "dev"
    anthropic_api_key: str = ""
    redis_url: str = "redis://localhost:6379"
    model_chat: str = "claude-haiku-4-5"
    storage_dir: str = "./storage/reports"

    model_config = {"env_file": ".env"}


_DEFAULT_SECRETS = {"dev-secret-change-me", "dev-secret", ""}


def assert_safe_config(s: Settings) -> None:
    if s.env == "production" and (s.jwt_secret in _DEFAULT_SECRETS or len(s.jwt_secret) < 32):
        raise RuntimeError("unsafe jwt_secret in production - set a >=32 char JWT_SECRET")


@lru_cache
def get_settings() -> Settings:
    return Settings()
