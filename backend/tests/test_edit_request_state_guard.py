import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.chat import get_arq_pool, get_redis
from app.db import get_db
from app.main import create_app
from app.models import ChatRequest
from tests.conftest import _ceo_headers

"""Finding #6 (audit 2026-07-26, re-verify 2026-08-08): edit_request chỉ
guard status==queued, KHÔNG check started_at — sau khi 1 request đã chạy
qua 1 vòng confirm/tool (started_at được set), resolve_confirmation đưa
status về lại queued và ghi THÊM 1 Message role=user (tool_result) với
cùng chat_request_id — lúc đó DB có >=2 Message role=user cùng
chat_request_id, edit_request query .scalar_one_or_none() crash
MultipleResultsFound (500 không kiểm soát) thay vì 409 rõ ràng."""


class _FakeArqPool:
    async def enqueue_job(self, name, *args, **kwargs):
        return "job"


class _FakeRedis:
    async def set(self, key, value, ex=None):
        pass

    async def delete(self, key):
        pass


@pytest.fixture
async def queue_client(engine):
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


@pytest.mark.asyncio
async def test_edit_request_tra_409_khi_da_tung_chay(queue_client):
    client, maker = queue_client
    ceo_h = await _ceo_headers(client)
    # Gửi 1 tin nhắn tạo ChatRequest queued
    conv = (await client.get("/api/v1/conversations/active", headers=ceo_h)).json()
    req = (await client.post(f"/api/v1/conversations/{conv['id']}/messages",
                             json={"content": "hello"}, headers=ceo_h)).json()

    # Giả lập request đã CHẠY (started_at != None) bằng cách set trực tiếp qua DB
    # session (lấy qua async_sessionmaker `maker`, cùng cách test_chat_queue_api.py
    # dùng — không phải qua dependency_overrides thô như phác thảo ban đầu trong
    # brief, vì fixture ở đây tự expose maker sẵn).
    import datetime as dt
    import uuid

    from sqlalchemy import update
    async with maker() as db:
        await db.execute(update(ChatRequest).where(ChatRequest.id == uuid.UUID(req["id"]))
                         .values(started_at=dt.datetime.now(dt.timezone.utc)))
        await db.commit()

    resp = await client.patch(f"/api/v1/chat-requests/{req['id']}",
                              json={"content": "edited"}, headers=ceo_h)
    assert resp.status_code == 409
