from app.config import Settings


def test_chat_settings_defaults():
    # _env_file=None: test default thật, không để .env của dev lẫn vào
    s = Settings(_env_file=None)
    assert s.anthropic_api_key == ""
    assert s.anthropic_base_url == ""  # rỗng = API Anthropic chính thức
    assert s.redis_url == "redis://localhost:6380"
    assert s.model_chat == "claude-haiku-4-5"
