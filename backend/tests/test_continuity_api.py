"""API test cho 'tiếp tục công việc' (funtional-plan 5.7) — resume qua send_message."""
import uuid

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.chat import get_arq_pool, get_redis
from app.db import get_db
from app.main import create_app
from app.models import Conversation
from tests.conftest import _ceo_headers


class _FakeArqPool:
    def __init__(self):
        self.enqueued = []

    async def enqueue_job(self, name, *args, **kwargs):
        self.enqueued.append((name, args, kwargs))
        return "job"


class _FakeRedis:
    async def set(self, key, value, ex=None):
        pass


@pytest.fixture
async def api_client(engine):
    app = create_app()
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_arq_pool] = lambda: _FakeArqPool()
    app.dependency_overrides[get_redis] = lambda: _FakeRedis()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, maker


async def _held_conversation(client, maker, headers) -> str:
    conv = (await client.post("/api/v1/conversations", headers=headers,
                              json={"title": "t"})).json()
    # tạo việc dang dở rồi hold (như khi socket cuối cùng disconnect)
    await client.post(f"/api/v1/conversations/{conv['id']}/messages", headers=headers,
                      json={"content": "viec dang do"})
    async with maker() as db:
        c = await db.get(Conversation, uuid.UUID(conv["id"]))
        c.queue_held = True
        await db.commit()
    return conv["id"]


@pytest.mark.asyncio
async def test_resume_phrase_clears_hold_and_queues_at_tail(api_client):
    client, maker = api_client
    headers = await _ceo_headers(client)
    conv_id = await _held_conversation(client, maker, headers)

    r = await client.post(f"/api/v1/conversations/{conv_id}/messages", headers=headers,
                          json={"content": "Tiếp tục công việc"})
    assert r.status_code == 201

    convs = (await client.get("/api/v1/conversations", headers=headers)).json()
    assert convs[0]["queue_held"] is False
    reqs = (await client.get(f"/api/v1/conversations/{conv_id}/requests",
                             headers=headers)).json()
    # việc cũ vẫn đứng trước, request "tiếp tục công việc" nằm cuối queue
    assert [q["content"] for q in reqs] == ["viec dang do", "Tiếp tục công việc"]


@pytest.mark.asyncio
async def test_normal_message_keeps_hold(api_client):
    client, maker = api_client
    headers = await _ceo_headers(client)
    conv_id = await _held_conversation(client, maker, headers)

    r = await client.post(f"/api/v1/conversations/{conv_id}/messages", headers=headers,
                          json={"content": "lam cai khac di"})
    assert r.status_code == 201

    convs = (await client.get("/api/v1/conversations", headers=headers)).json()
    assert convs[0]["queue_held"] is True  # vẫn chờ đúng cụm từ


@pytest.mark.asyncio
async def test_resume_phrase_when_not_held_is_normal_message(api_client):
    client, maker = api_client
    headers = await _ceo_headers(client)
    conv = (await client.post("/api/v1/conversations", headers=headers,
                              json={"title": "t"})).json()

    r = await client.post(f"/api/v1/conversations/{conv['id']}/messages", headers=headers,
                          json={"content": "tiếp tục công việc"})
    assert r.status_code == 201

    convs = (await client.get("/api/v1/conversations", headers=headers)).json()
    assert convs[0]["queue_held"] is False


@pytest.mark.asyncio
async def test_conversation_out_exposes_queue_held(api_client):
    client, _maker = api_client
    headers = await _ceo_headers(client)
    conv = (await client.post("/api/v1/conversations", headers=headers,
                              json={"title": "t"})).json()
    assert conv["queue_held"] is False
