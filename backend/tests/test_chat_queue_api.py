import uuid

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.chat import get_arq_pool, get_redis
from app.db import get_db
from app.main import create_app
from app.models import ChatRequest, ChatRequestStatus, Conversation, Message, User, UserStatus
from tests.conftest import _ceo_headers


class _FakeArqPool:
    def __init__(self):
        self.enqueued = []

    async def enqueue_job(self, name, *args, **kwargs):
        self.enqueued.append((name, args, kwargs))
        return "job"


class _FakeRedis:
    def __init__(self):
        self.set_calls = []

    async def set(self, key, value, ex=None):
        self.set_calls.append((key, value, ex))


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
        yield c, fake_pool, fake_redis, maker


@pytest.mark.asyncio
async def test_confirm_approved_executes_and_requeues(queue_client):
    client, fake_pool, fake_redis, maker = queue_client
    ceo_h = await _ceo_headers(client)
    me = (await client.get("/api/v1/users/me", headers=ceo_h)).json()

    async with maker() as db:
        ceo = await db.get(User, uuid.UUID(me["id"]))
        target = User(workspace_id=ceo.workspace_id, email="e@a.vn", password_hash="x",
                     full_name="E", role="employee")
        db.add(target)
        await db.flush()
        conv = Conversation(workspace_id=ceo.workspace_id, user_id=ceo.id)
        db.add(conv)
        await db.flush()
        req = ChatRequest(workspace_id=ceo.workspace_id, conversation_id=conv.id,
                          user_id=ceo.id, content="khoa e", queue_position=1.0,
                          status=ChatRequestStatus.awaiting_confirmation,
                          pending_action={"tool_name": "lock_user",
                                         "tool_input": {"target_id": str(target.id)},
                                         "tool_use_id": "t1"})
        db.add(req)
        await db.commit()
        req_id, target_id = req.id, target.id

    resp = await client.post(f"/api/v1/chat-requests/{req_id}/confirm", headers=ceo_h,
                             json={"approved": True})
    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"
    assert len(fake_pool.enqueued) == 1

    async with maker() as db:
        target = await db.get(User, target_id)
        assert target.status == UserStatus.locked


@pytest.mark.asyncio
async def test_confirm_when_not_awaiting_returns_409(queue_client):
    client, *_, maker = queue_client
    ceo_h = await _ceo_headers(client)
    me = (await client.get("/api/v1/users/me", headers=ceo_h)).json()

    async with maker() as db:
        ceo = await db.get(User, uuid.UUID(me["id"]))
        conv = Conversation(workspace_id=ceo.workspace_id, user_id=ceo.id)
        db.add(conv)
        await db.flush()
        req = ChatRequest(workspace_id=ceo.workspace_id, conversation_id=conv.id,
                          user_id=ceo.id, content="x", queue_position=1.0)
        db.add(req)
        await db.commit()
        req_id = req.id

    resp = await client.post(f"/api/v1/chat-requests/{req_id}/confirm", headers=ceo_h,
                             json={"approved": True})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_list_requests_exposes_pending_action_for_confirm_card(queue_client):
    """GET /requests phải trả pending_action đầy đủ (tool_name, tool_input, tool_use_id)
    để FE dựng confirm card sau khi reload màn — không còn duyệt mù."""
    client, *_, maker = queue_client
    ceo_h = await _ceo_headers(client)
    me = (await client.get("/api/v1/users/me", headers=ceo_h)).json()

    async with maker() as db:
        ceo = await db.get(User, uuid.UUID(me["id"]))
        target = User(workspace_id=ceo.workspace_id, email="f@a.vn", password_hash="x",
                     full_name="F", role="employee")
        db.add(target)
        await db.flush()
        conv = Conversation(workspace_id=ceo.workspace_id, user_id=ceo.id)
        db.add(conv)
        await db.flush()
        req = ChatRequest(workspace_id=ceo.workspace_id, conversation_id=conv.id,
                          user_id=ceo.id, content="khoa f", queue_position=1.0,
                          status=ChatRequestStatus.awaiting_confirmation,
                          pending_action={"tool_name": "lock_user",
                                         "tool_input": {"target_id": str(target.id)},
                                         "tool_use_id": "t1"})
        db.add(req)
        await db.commit()
        conv_id = conv.id

    resp = await client.get(f"/api/v1/conversations/{conv_id}/requests", headers=ceo_h)
    assert resp.status_code == 200
    body = resp.json()
    waiting = next(r for r in body if r["status"] == "awaiting_confirmation")
    assert waiting["pending_action"]["tool_name"] == "lock_user"
    assert waiting["pending_action"]["tool_input"] == {"target_id": str(target.id)}
    assert waiting["pending_action"]["tool_use_id"] == "t1"


@pytest.mark.asyncio
async def test_cancel_queued_request_marks_cancelled(queue_client):
    client, *_, maker = queue_client
    ceo_h = await _ceo_headers(client)
    me = (await client.get("/api/v1/users/me", headers=ceo_h)).json()

    async with maker() as db:
        ceo = await db.get(User, uuid.UUID(me["id"]))
        conv = Conversation(workspace_id=ceo.workspace_id, user_id=ceo.id)
        db.add(conv)
        await db.flush()
        req = ChatRequest(workspace_id=ceo.workspace_id, conversation_id=conv.id,
                          user_id=ceo.id, content="x", queue_position=1.0)
        db.add(req)
        await db.commit()
        req_id = req.id

    resp = await client.post(f"/api/v1/chat-requests/{req_id}/cancel", headers=ceo_h)
    assert resp.status_code == 204

    async with maker() as db:
        req = await db.get(ChatRequest, req_id)
        assert req.status == ChatRequestStatus.cancelled


@pytest.mark.asyncio
async def test_cancel_running_request_sets_redis_flag(queue_client):
    client, fake_pool, fake_redis, maker = queue_client
    ceo_h = await _ceo_headers(client)
    me = (await client.get("/api/v1/users/me", headers=ceo_h)).json()

    async with maker() as db:
        ceo = await db.get(User, uuid.UUID(me["id"]))
        conv = Conversation(workspace_id=ceo.workspace_id, user_id=ceo.id)
        db.add(conv)
        await db.flush()
        req = ChatRequest(workspace_id=ceo.workspace_id, conversation_id=conv.id,
                          user_id=ceo.id, content="x", queue_position=1.0,
                          status=ChatRequestStatus.running)
        db.add(req)
        await db.commit()
        req_id = req.id

    resp = await client.post(f"/api/v1/chat-requests/{req_id}/cancel", headers=ceo_h)
    assert resp.status_code == 204
    assert fake_redis.set_calls == [(f"cancel:{req_id}", "1", 600)]


@pytest.mark.asyncio
async def test_cancel_deep_running_request_sets_redis_flag(queue_client):
    """Phase 4 §8.2 Task 10: request dang chay job nen (deep_running) - CEO bam
    dung phai co tac dung that (khong duoc coi la queued/khong nhan dien)."""
    client, fake_pool, fake_redis, maker = queue_client
    ceo_h = await _ceo_headers(client)
    me = (await client.get("/api/v1/users/me", headers=ceo_h)).json()

    async with maker() as db:
        ceo = await db.get(User, uuid.UUID(me["id"]))
        conv = Conversation(workspace_id=ceo.workspace_id, user_id=ceo.id)
        db.add(conv)
        await db.flush()
        req = ChatRequest(workspace_id=ceo.workspace_id, conversation_id=conv.id,
                          user_id=ceo.id, content="x", queue_position=1.0,
                          status=ChatRequestStatus.deep_running)
        db.add(req)
        await db.commit()
        req_id = req.id

    resp = await client.post(f"/api/v1/chat-requests/{req_id}/cancel", headers=ceo_h)
    assert resp.status_code == 204
    assert fake_redis.set_calls == [(f"cancel:{req_id}", "1", 600)]


@pytest.mark.asyncio
async def test_stop_all_flags_deep_running_request(queue_client):
    """Phase 4 §8.2 Task 10: stop-all phai nhan dien deep_running nhu running -
    dat co huy qua redis, khong bo sot job nen dang chay."""
    client, fake_pool, fake_redis, maker = queue_client
    ceo_h = await _ceo_headers(client)
    me = (await client.get("/api/v1/users/me", headers=ceo_h)).json()

    async with maker() as db:
        ceo = await db.get(User, uuid.UUID(me["id"]))
        conv = Conversation(workspace_id=ceo.workspace_id, user_id=ceo.id)
        db.add(conv)
        await db.flush()
        r_deep = ChatRequest(workspace_id=ceo.workspace_id, conversation_id=conv.id,
                             user_id=ceo.id, content="phan tich sau", queue_position=1.0,
                             status=ChatRequestStatus.deep_running)
        db.add(r_deep)
        await db.commit()
        conv_id, deep_id = conv.id, r_deep.id

    resp = await client.post(f"/api/v1/conversations/{conv_id}/stop-all", headers=ceo_h)
    assert resp.status_code == 204
    assert fake_redis.set_calls == [(f"cancel:{deep_id}", "1", 600)]


@pytest.mark.asyncio
async def test_reorder_to_front_then_before_sibling(queue_client):
    client, *_, maker = queue_client
    ceo_h = await _ceo_headers(client)
    me = (await client.get("/api/v1/users/me", headers=ceo_h)).json()

    async with maker() as db:
        ceo = await db.get(User, uuid.UUID(me["id"]))
        conv = Conversation(workspace_id=ceo.workspace_id, user_id=ceo.id)
        db.add(conv)
        await db.flush()
        r1 = ChatRequest(workspace_id=ceo.workspace_id, conversation_id=conv.id,
                         user_id=ceo.id, content="1", queue_position=1.0)
        r2 = ChatRequest(workspace_id=ceo.workspace_id, conversation_id=conv.id,
                         user_id=ceo.id, content="2", queue_position=2.0)
        r3 = ChatRequest(workspace_id=ceo.workspace_id, conversation_id=conv.id,
                         user_id=ceo.id, content="3", queue_position=3.0)
        db.add_all([r1, r2, r3])
        await db.commit()
        r1_id, r2_id, r3_id = r1.id, r2.id, r3.id

    resp = await client.post(f"/api/v1/chat-requests/{r3_id}/reorder", headers=ceo_h, json={})
    assert resp.status_code == 200
    async with maker() as db:
        rows = (await db.execute(select(ChatRequest)
                                 .where(ChatRequest.id.in_([r1_id, r2_id, r3_id]))
                                 .order_by(ChatRequest.queue_position.asc()))).scalars().all()
        assert [r.id for r in rows] == [r3_id, r1_id, r2_id]

    resp2 = await client.post(f"/api/v1/chat-requests/{r2_id}/reorder", headers=ceo_h,
                              json={"before_id": str(r3_id)})
    assert resp2.status_code == 200
    async with maker() as db:
        rows = (await db.execute(select(ChatRequest)
                                 .where(ChatRequest.id.in_([r1_id, r2_id, r3_id]))
                                 .order_by(ChatRequest.queue_position.asc()))).scalars().all()
        assert [r.id for r in rows] == [r2_id, r3_id, r1_id]


@pytest.mark.asyncio
async def test_edit_queued_request_updates_content_and_linked_message(queue_client):
    client, *_, maker = queue_client
    ceo_h = await _ceo_headers(client)
    conv = (await client.post("/api/v1/conversations", headers=ceo_h, json={})).json()
    sent = await client.post(f"/api/v1/conversations/{conv['id']}/messages", headers=ceo_h,
                             json={"content": "ban dau"})
    req_id = sent.json()["id"]

    resp = await client.patch(f"/api/v1/chat-requests/{req_id}", headers=ceo_h,
                              json={"content": "da sua"})
    assert resp.status_code == 200
    assert resp.json()["content"] == "da sua"

    async with maker() as db:
        msg = (await db.execute(select(Message).where(
            Message.chat_request_id == uuid.UUID(req_id)))).scalar_one()
        assert msg.content == [{"type": "text", "text": "da sua"}]


@pytest.mark.asyncio
async def test_stop_all_cancels_queued_and_flags_running(queue_client):
    client, fake_pool, fake_redis, maker = queue_client
    ceo_h = await _ceo_headers(client)
    me = (await client.get("/api/v1/users/me", headers=ceo_h)).json()

    async with maker() as db:
        ceo = await db.get(User, uuid.UUID(me["id"]))
        conv = Conversation(workspace_id=ceo.workspace_id, user_id=ceo.id)
        db.add(conv)
        await db.flush()
        r_running = ChatRequest(workspace_id=ceo.workspace_id, conversation_id=conv.id,
                                user_id=ceo.id, content="dang chay", queue_position=1.0,
                                status=ChatRequestStatus.running)
        r_queued = ChatRequest(workspace_id=ceo.workspace_id, conversation_id=conv.id,
                               user_id=ceo.id, content="cho", queue_position=2.0)
        db.add_all([r_running, r_queued])
        await db.commit()
        conv_id, running_id, queued_id = conv.id, r_running.id, r_queued.id

    resp = await client.post(f"/api/v1/conversations/{conv_id}/stop-all", headers=ceo_h)
    assert resp.status_code == 204

    async with maker() as db:
        queued = await db.get(ChatRequest, queued_id)
        assert queued.status == ChatRequestStatus.cancelled
    assert fake_redis.set_calls == [(f"cancel:{running_id}", "1", 600)]
