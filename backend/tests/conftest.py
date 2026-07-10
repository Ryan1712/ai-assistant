import pytest
import httpx
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import create_app


@pytest.fixture
async def engine():
    # StaticPool: bắt buộc với SQLite in-memory — mọi session dùng chung 1 connection,
    # nếu không mỗi connection sẽ là một DB rỗng riêng.
    eng = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def db_session(engine):
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session


@pytest.fixture
async def client(engine):
    app = create_app()
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


SIGNUP = {
    "workspace_name": "Cong ty A", "email": "ceo@a.vn", "password": "secret123",
    "full_name": "Sep", "device_uuid": "dev-1", "device_name": "",
}


async def _ceo_headers(client):
    resp = await client.post("/api/v1/auth/signup-workspace", json=SIGNUP)
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _invite_and_join(client, headers, role, email, manager_id=None):
    inv = await client.post("/api/v1/invites", headers=headers,
                            json={"role": role, "manager_id": manager_id})
    assert inv.status_code == 201, inv.text
    join = await client.post("/api/v1/auth/signup-invite", json={
        "token": inv.json()["token"], "email": email, "password": "pw123456",
        "full_name": email, "device_uuid": "d-" + email, "device_name": "",
    })
    assert join.status_code == 201, join.text
    return join.json()


@pytest.fixture
def storage_dir(tmp_path, monkeypatch):
    from app.config import get_settings
    # get_settings() là lru_cache — monkeypatch attr trên instance, tự hoàn nguyên sau test
    monkeypatch.setattr(get_settings(), "storage_dir", str(tmp_path))
    return tmp_path
