from app.config import Settings


def test_chat_settings_defaults():
    s = Settings()
    assert s.anthropic_api_key == ""
    assert s.redis_url == "redis://localhost:6380"
    assert s.model_chat == "claude-haiku-4-5"
