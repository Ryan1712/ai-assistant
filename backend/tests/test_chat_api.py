import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.chat import get_arq_pool
from app.db import get_db
from app.main import create_app
from tests.conftest import _ceo_headers, _invite_and_join


class _FakeArqPool:
    def __init__(self):
        self.enqueued = []

    async def enqueue_job(self, name, *args, **kwargs):
        self.enqueued.append((name, args, kwargs))
        return "job"


@pytest.fixture
async def chat_client(engine):
    app = create_app()
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with maker() as session:
            yield session

    fake_pool = _FakeArqPool()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_arq_pool] = lambda: fake_pool
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, fake_pool


@pytest.mark.asyncio
async def test_create_and_list_own_conversations(chat_client):
    client, _ = chat_client
    ceo_h = await _ceo_headers(client)
    created = await client.post("/api/v1/conversations", headers=ceo_h,
                                json={"title": "Cong viec"})
    assert created.status_code == 201
    listed = await client.get("/api/v1/conversations", headers=ceo_h)
    assert [c["title"] for c in listed.json()] == ["Cong viec"]


@pytest.mark.asyncio
async def test_send_message_enqueues_job_and_creates_queued_request(chat_client):
    client, fake_pool = chat_client
    ceo_h = await _ceo_headers(client)
    conv = (await client.post("/api/v1/conversations", headers=ceo_h, json={})).json()

    resp = await client.post(f"/api/v1/conversations/{conv['id']}/messages", headers=ceo_h,
                             json={"content": "tao task X"})
    assert resp.status_code == 201
    assert resp.json()["status"] == "queued"
    assert len(fake_pool.enqueued) == 1
    name, args, kwargs = fake_pool.enqueued[0]
    assert name == "process_conversation"
    assert kwargs["_job_id"] == f"conv:{conv['id']}"


@pytest.mark.asyncio
async def test_send_message_to_others_conversation_404(chat_client):
    client, _ = chat_client
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    conv = (await client.post("/api/v1/conversations", headers=ceo_h, json={})).json()

    m1_headers = {"Authorization": f"Bearer {m1['access_token']}"}
    resp = await client.post(f"/api/v1/conversations/{conv['id']}/messages",
                             headers=m1_headers, json={"content": "x"})
    assert resp.status_code == 404
