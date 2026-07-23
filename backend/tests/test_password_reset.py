import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.auth import get_redis
from app.db import get_db
from app.main import create_app


class _FakeRedis:
    """Redis in-memory tối thiểu cho test (không TTL — không kiểm hết hạn ở đây)."""

    def __init__(self):
        self.store: dict[str, str] = {}

    async def set(self, k, v, ex=None):
        self.store[k] = v

    async def get(self, k):
        return self.store.get(k)

    async def delete(self, k):
        self.store.pop(k, None)


@pytest.fixture
async def auth_client(engine):
    app = create_app()
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with maker() as session:
            yield session

    fake_redis = _FakeRedis()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = lambda: fake_redis
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, fake_redis


async def _signup(client, email, password):
    return await client.post("/api/v1/auth/signup-workspace", json={
        "workspace_name": "Cty", "email": email, "password": password,
        "full_name": "Boss", "device_uuid": "d1", "device_name": "iPhone",
    })


@pytest.mark.asyncio
async def test_forgot_then_reset_password_success(auth_client):
    client, fake_redis = auth_client
    assert (await _signup(client, "boss@a.vn", "oldpassword1")).status_code == 201

    fp = await client.post("/api/v1/auth/forgot-password", json={"email": "boss@a.vn"})
    assert fp.status_code == 202
    code = fake_redis.store["pwreset:boss@a.vn"]  # mã do BE sinh, lưu ở redis

    rp = await client.post("/api/v1/auth/reset-password", json={
        "email": "boss@a.vn", "code": code, "new_password": "newpassword1",
    })
    assert rp.status_code == 204, rp.text
    assert "pwreset:boss@a.vn" not in fake_redis.store  # mã dùng-một-lần

    ok = await client.post("/api/v1/auth/login", json={
        "email": "boss@a.vn", "password": "newpassword1", "device_uuid": "d1", "device_name": "x",
    })
    assert ok.status_code == 200
    old = await client.post("/api/v1/auth/login", json={
        "email": "boss@a.vn", "password": "oldpassword1", "device_uuid": "d1", "device_name": "x",
    })
    assert old.status_code == 401


@pytest.mark.asyncio
async def test_forgot_password_unknown_email_still_202(auth_client):
    client, fake_redis = auth_client
    resp = await client.post("/api/v1/auth/forgot-password", json={"email": "nobody@a.vn"})
    assert resp.status_code == 202  # không tiết lộ email tồn tại hay không
    assert fake_redis.store == {}


@pytest.mark.asyncio
async def test_reset_with_wrong_code_400(auth_client):
    client, _ = auth_client
    await _signup(client, "b2@a.vn", "oldpassword1")
    await client.post("/api/v1/auth/forgot-password", json={"email": "b2@a.vn"})
    rp = await client.post("/api/v1/auth/reset-password", json={
        "email": "b2@a.vn", "code": "000000", "new_password": "newpassword1",
    })
    assert rp.status_code == 400
