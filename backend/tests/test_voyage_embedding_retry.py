"""VoyageEmbeddingClient — retry khi Voyage API trả 429 (rate limit).

Phát hiện qua log production thật (2026-08-10): 2 request embed gần như đồng
thời (add_employee liên tiếp) đủ để dính rate-limit free tier của Voyage.
embed() không retry -> index_content() catch Exception, log, rollback, bỏ
qua im lặng (đúng thiết kế "best-effort không phá write chính") -> nhưng hệ
quả là row đó KHÔNG được index, suggest_assignee bỏ sót người mà không ai
biết trừ khi đọc log. Thêm retry ngắn cho riêng lỗi 429 để giảm rủi ro này,
không đổi hành vi các lỗi khác (network/5xx vẫn fail nhanh, để
index_content() catch như cũ)."""
import httpx
import pytest

from app.config import get_settings
from app.services.embedding_service import VoyageEmbeddingClient


@pytest.fixture(autouse=True)
def _voyage_key(monkeypatch):
    monkeypatch.setattr(get_settings(), "embedding_api_key", "test-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _ok_response(request):
    return httpx.Response(200, json={"data": [{"embedding": [0.1] * 1024}]})


@pytest.mark.asyncio
async def test_embed_retries_after_429_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, json={"error": "rate limited"})
        return _ok_response(request)

    monkeypatch.setattr(
        "app.services.embedding_service._voyage_transport", httpx.MockTransport(handler)
    )
    monkeypatch.setattr("app.services.embedding_service._RETRY_SLEEP_SECONDS", 0)

    client = VoyageEmbeddingClient()
    vector = await client.embed("hello")

    assert calls["n"] == 3
    assert len(vector) == 1024


@pytest.mark.asyncio
async def test_embed_gives_up_after_max_retries_on_429(monkeypatch):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(429, json={"error": "rate limited"})

    monkeypatch.setattr(
        "app.services.embedding_service._voyage_transport", httpx.MockTransport(handler)
    )
    monkeypatch.setattr("app.services.embedding_service._RETRY_SLEEP_SECONDS", 0)

    client = VoyageEmbeddingClient()
    with pytest.raises(httpx.HTTPStatusError):
        await client.embed("hello")

    # 1 lần gọi gốc + tối đa số lần retry cấu hình, không lặp vô hạn.
    assert calls["n"] >= 2
    assert calls["n"] <= 5


@pytest.mark.asyncio
async def test_embed_does_not_retry_on_non_429_error(monkeypatch):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(500, json={"error": "server error"})

    monkeypatch.setattr(
        "app.services.embedding_service._voyage_transport", httpx.MockTransport(handler)
    )
    monkeypatch.setattr("app.services.embedding_service._RETRY_SLEEP_SECONDS", 0)

    client = VoyageEmbeddingClient()
    with pytest.raises(httpx.HTTPStatusError):
        await client.embed("hello")

    # Lỗi khác 429 (vd 5xx) fail ngay, không tốn thời gian retry -
    # index_content() catch và bỏ qua như cũ, không đổi hành vi này.
    assert calls["n"] == 1
