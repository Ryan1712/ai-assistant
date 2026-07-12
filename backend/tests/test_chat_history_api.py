import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.chat import get_arq_pool, get_redis
from app.db import get_db
from app.main import create_app
from tests.conftest import _ceo_headers, _invite_and_join


class _FakeArqPool:
    async def enqueue_job(self, name, *args, **kwargs):
        return "job"


class _FakeRedis:
    async def set(self, key, value, ex=None):
        pass


@pytest.fixture
async def hclient(engine):
    app = create_app()
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_arq_pool] = _FakeArqPool
    app.dependency_overrides[get_redis] = _FakeRedis
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _h(j):
    return {"Authorization": f"Bearer {j['access_token']}"}


async def _conv(client, headers):
    r = await client.post("/api/v1/conversations", headers=headers, json={"title": "t"})
    return r.json()["id"]


@pytest.mark.asyncio
async def test_get_messages_returns_history_in_order(hclient):
    ceo_h = await _ceo_headers(hclient)
    cid = await _conv(hclient, ceo_h)
    await hclient.post(f"/api/v1/conversations/{cid}/messages", headers=ceo_h,
                       json={"content": "cau 1"})
    await hclient.post(f"/api/v1/conversations/{cid}/messages", headers=ceo_h,
                       json={"content": "cau 2"})
    r = await hclient.get(f"/api/v1/conversations/{cid}/messages", headers=ceo_h)
    assert r.status_code == 200
    msgs = r.json()
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == [{"type": "text", "text": "cau 1"}]
    assert msgs[1]["content"] == [{"type": "text", "text": "cau 2"}]


@pytest.mark.asyncio
async def test_get_requests_returns_queue(hclient):
    ceo_h = await _ceo_headers(hclient)
    cid = await _conv(hclient, ceo_h)
    await hclient.post(f"/api/v1/conversations/{cid}/messages", headers=ceo_h,
                       json={"content": "a"})
    await hclient.post(f"/api/v1/conversations/{cid}/messages", headers=ceo_h,
                       json={"content": "b"})
    r = await hclient.get(f"/api/v1/conversations/{cid}/requests", headers=ceo_h)
    assert r.status_code == 200
    reqs = r.json()
    assert [q["content"] for q in reqs] == ["a", "b"]
    assert all(q["status"] == "queued" for q in reqs)


@pytest.mark.asyncio
async def test_other_users_conversation_404(hclient):
    ceo_h = await _ceo_headers(hclient)
    m1 = await _invite_and_join(hclient, ceo_h, "manager", "m1@a.vn")
    cid = await _conv(hclient, ceo_h)
    assert (await hclient.get(f"/api/v1/conversations/{cid}/messages",
                              headers=_h(m1))).status_code == 404
    assert (await hclient.get(f"/api/v1/conversations/{cid}/requests",
                              headers=_h(m1))).status_code == 404
