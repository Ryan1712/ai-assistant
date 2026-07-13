from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///:memory:"
    jwt_secret: str = "dev-secret-change-me"
    access_ttl_minutes: int = 15
    refresh_ttl_days: int = 30
    env: str = "dev"
    anthropic_api_key: str = ""
    # Rỗng = api.anthropic.com; set khi đi qua gateway tương thích Anthropic API
    # (lưu ý model id có thể cần prefix theo gateway, vd "anthropic/claude-...")
    anthropic_base_url: str = ""
    # Host port 6380/5435 — cổng mặc định 6379/5433 hay bị project khác trên máy dev chiếm
    redis_url: str = "redis://localhost:6380"
    model_chat: str = "claude-haiku-4-5"
    storage_dir: str = "./storage/reports"
    # Cổng báo cáo CEO (funtional-plan 6.8) — chưa có API spec thật nên mặc định mock
    portal_mock: bool = True
    push_mock: bool = True
    email_mock: bool = True
    stt_mock: bool = True
    portal_base_url: str = "https://ceo.9learning.edu.vn"

    model_config = {"env_file": ".env"}


_DEFAULT_SECRETS = {"dev-secret-change-me", "dev-secret", ""}


def assert_safe_config(s: Settings) -> None:
    if s.env == "production" and (s.jwt_secret in _DEFAULT_SECRETS or len(s.jwt_secret) < 32):
        raise RuntimeError("unsafe jwt_secret in production - set a >=32 char JWT_SECRET")


@lru_cache
def get_settings() -> Settings:
    return Settings()
