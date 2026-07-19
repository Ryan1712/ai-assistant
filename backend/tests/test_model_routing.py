"""Phase 0 (spec AI upgrade 4.3): config model theo tầng fast/smart."""
import pytest

from app.agent.llm_client import AnthropicLLMClient, FakeLLMClient
from app.config import Settings


def test_model_fast_smart_mac_dinh():
    s = Settings(_env_file=None)
    assert s.model_fast == "claude-haiku-4-5"
    assert s.model_smart == "claude-sonnet-4-6"


def test_env_model_chat_cu_van_doc_vao_model_fast(monkeypatch):
    # .env prod đang set MODEL_CHAT (có prefix gateway) — đổi tên field không được phá nó.
    monkeypatch.setenv("MODEL_CHAT", "anthropic/claude-haiku-4-5")
    s = Settings(_env_file=None)
    assert s.model_fast == "anthropic/claude-haiku-4-5"


def test_env_model_fast_moi_cung_doc_duoc(monkeypatch):
    monkeypatch.setenv("MODEL_FAST", "claude-haiku-9-9")
    s = Settings(_env_file=None)
    assert s.model_fast == "claude-haiku-9-9"


def test_llm_client_mang_model_public():
    fake = FakeLLMClient(turns=[])
    assert fake.model == "fake"
    fake2 = FakeLLMClient(turns=[], model="test-model")
    assert fake2.model == "test-model"

    class _C:  # client anthropic giả, không dùng tới trong test này
        pass

    real = AnthropicLLMClient(_C(), model="claude-haiku-4-5")
    assert real.model == "claude-haiku-4-5"
