"""Finding #22 (audit 2026-07-26, re-verify 2026-08-08, LOW): edit_request
sửa nội dung Message nhưng KHÔNG enqueue lại index_chat_message -- embedding
trong bảng Embedding vẫn trỏ nội dung GỐC trước khi sửa, semantic_search
trả về text cũ."""
import uuid

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.chat import get_arq_pool, get_redis
from app.db import get_db
from app.main import create_app
from app.models import ChatRequest, ChatRequestStatus, Conversation, Message, MessageRole, User
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

    async def delete(self, key):
        pass


@pytest.fixture
async def queue_client(engine):
    app = create_app()
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with maker() as session:
            yield session

    fake_pool = _FakeArqPool()
    fake_redis = _FakeRedis()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_arq_pool] = lambda: fake_pool
    app.dependency_overrides[get_redis] = lambda: fake_redis
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, fake_pool, maker


@pytest.mark.asyncio
async def test_edit_request_enqueue_reindex(queue_client):
    client, fake_pool, maker = queue_client
    ceo_h = await _ceo_headers(client)
    me = (await client.get("/api/v1/users/me", headers=ceo_h)).json()

    async with maker() as db:
        ceo = await db.get(User, uuid.UUID(me["id"]))
        conv = Conversation(workspace_id=ceo.workspace_id, user_id=ceo.id)
        db.add(conv)
        await db.flush()
        req = ChatRequest(workspace_id=ceo.workspace_id, conversation_id=conv.id,
                          user_id=ceo.id, content="noi dung goc", queue_position=1.0,
                          status=ChatRequestStatus.queued)
        db.add(req)
        await db.flush()
        msg = Message(workspace_id=ceo.workspace_id, conversation_id=conv.id,
                      chat_request_id=req.id, role=MessageRole.user,
                      content=[{"type": "text", "text": "noi dung goc"}])
        db.add(msg)
        await db.commit()
        req_id, msg_id = req.id, msg.id

    fake_pool.enqueued.clear()  # bỏ enqueue lúc setup (nếu có) trước khi test edit thật
    resp = await client.patch(f"/api/v1/chat-requests/{req_id}", headers=ceo_h,
                              json={"content": "noi dung da sua"})
    assert resp.status_code == 200

    reindex_calls = [c for c in fake_pool.enqueued if c[0] == "index_chat_message"]
    assert len(reindex_calls) == 1
    name, args, kwargs = reindex_calls[0]
    assert msg_id in args
    assert "noi dung da sua" in args
