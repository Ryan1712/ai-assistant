from functools import lru_cache

from pydantic import AliasChoices, Field
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
    # Model theo tầng tác vụ (spec AI upgrade §3/§4.3): fast = chat mặc định;
    # smart = đường sâu async/distiller/report summary (các phase sau).
    # Env MODEL_CHAT (tên cũ, đang dùng ở .env prod) vẫn được đọc vào model_fast.
    model_fast: str = Field("claude-haiku-4-5",
                            validation_alias=AliasChoices("model_fast", "model_chat"))
    model_smart: str = "claude-sonnet-4-6"
    storage_dir: str = "./storage/reports"
    # Cổng báo cáo CEO (funtional-plan 6.8) — chưa có API spec thật nên mặc định mock
    portal_mock: bool = True
    push_mock: bool = True
    email_mock: bool = True
    # SMTP (dùng khi email_mock=False). smtp_from rỗng → dùng smtp_user làm người gửi.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = Field("", validation_alias=AliasChoices("SMTP_PASSWORD", "SMTP_PASS"))
    smtp_from: str = ""
    smtp_starttls: bool = True
    # Cổng 465 (SMTPS/implicit TLS, vd Gmail) cần use_tls thay vì start_tls —
    # bật cờ này khi dùng cổng 465; mặc định false giữ hành vi cũ (start_tls
    # trên cổng 587) cho môi trường chỉ set SMTP_STARTTLS.
    smtp_secure: bool = False
    stt_mock: bool = True
    # STT thật (Groq Whisper, free tier — https://console.groq.com/keys)
    groq_api_key: str = ""
    portal_base_url: str = "https://ceo.9learning.edu.vn"
    # Embedding cho semantic_search (Phase 6 §10.3) — mock mặc định (hashing
    # bag-of-words, xem embedding_service.py) không cần API key để dev/test.
    embedding_mock: bool = True
    embedding_api_key: str = ""
    # Snapshot workspace (spec AI upgrade §5): TTL fallback khi không có invalidation
    # (ghi từ REST của FE); ghi qua agent tool được invalidate ngay.
    snapshot_ttl_seconds: int = 300
    # Public Reports API cho app mobile 9learning đọc qua bundle-id, không đăng
    # nhập (funtional-plan 6.8, spec 2026-08-03-public-reports-api-design.md).
    # Rỗng = tính năng tắt hoàn toàn.
    public_app_bundle_ids: str = ""
    public_report_workspace_id: str = ""

    model_config = {"env_file": ".env", "populate_by_name": True, "protected_namespaces": ()}


_DEFAULT_SECRETS = {"dev-secret-change-me", "dev-secret", ""}


def assert_safe_config(s: Settings) -> None:
    if s.env == "production" and (s.jwt_secret in _DEFAULT_SECRETS or len(s.jwt_secret) < 32):
        raise RuntimeError("unsafe jwt_secret in production - set a >=32 char JWT_SECRET")


@lru_cache
def get_settings() -> Settings:
    return Settings()
