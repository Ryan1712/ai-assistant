import uuid

import pytest
import httpx
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import create_app
from app import security
from app.models import Role, User, UserStatus


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
    """Tạo 1 user CÓ THỂ ĐĂNG NHẬP cho test (manager/employee cũ vẫn cần login được
    qua HTTP để test hành vi theo vai trò/quyền — KHÔNG liên quan gì tới add_employee
    sản phẩm, đây thuần là hạ tầng test).

    Trước 2026-07-26: tạo qua POST /invites + POST /auth/activate. Route /activate đã
    tắt (product quyết định chỉ CEO đăng nhập — xem spec employee-as-list) nên tạo
    thẳng qua DB (đã hash mật khẩu, status=active) rồi login thật qua /auth/login.
    GIỮ NGUYÊN chữ ký/kiểu trả về để không sửa lan sang các file test khác đang dùng
    helper này (test_traces_api.py, test_agent_tools_account.py, ...).

    Lấy DB session bằng cách đọc lại override của get_db đã gắn sẵn trên FastAPI app
    của client (client._transport.app.dependency_overrides[get_db]) — KHÔNG dựa vào
    1 attribute riêng gắn thêm lên client (kiểu client.db_maker), vì 6 file test
    (test_chat_api.py, test_embedding_service.py, test_delete_task_project.py,
    test_chat_voice_attachment.py, test_voice_notes.py, test_chat_history_api.py) tự
    định nghĩa fixture client/chat_client/hclient RIÊNG (cần override thêm dependency
    khác, vd get_arq_pool) thay vì dùng chung fixture `client` ở conftest — mọi
    fixture đó đều dựng qua httpx.ASGITransport(app=app) + app.dependency_overrides
    [get_db] nên đọc thẳng qua đường này dùng chung được cho cả conftest.client lẫn
    6 fixture riêng kia, không phải sửa file nào trong số đó."""
    payload = security.decode_access_token(headers["Authorization"].removeprefix("Bearer "))
    workspace_id = uuid.UUID(payload["ws"])
    manager_uuid = uuid.UUID(manager_id) if manager_id else None
    password = "pw123456"
    app = client._transport.app
    db_gen = app.dependency_overrides[get_db]()
    db = await anext(db_gen)
    try:
        user = User(workspace_id=workspace_id, email=email, full_name=email,
                   password_hash=security.hash_password(password),
                   role=Role(role), manager_id=manager_uuid, status=UserStatus.active)
        db.add(user)
        await db.commit()
    finally:
        await db_gen.aclose()
    login = await client.post("/api/v1/auth/login", json={
        "email": email, "password": password, "device_uuid": "d-" + email, "device_name": ""})
    assert login.status_code == 200, login.text
    return login.json()


@pytest.fixture
def storage_dir(tmp_path, monkeypatch):
    from app.config import get_settings
    # get_settings() là lru_cache — monkeypatch attr trên instance, tự hoàn nguyên sau test
    monkeypatch.setattr(get_settings(), "storage_dir", str(tmp_path))
    return tmp_path


@pytest.fixture(autouse=True)
def fake_snapshot_store(monkeypatch):
    # Mọi test dùng FakeSnapshotStore — unit test không cần redis thật, và
    # agent-loop test không ghi rác vào redis dev.
    from app.services import snapshot_service
    store = snapshot_service.FakeSnapshotStore()
    monkeypatch.setattr(snapshot_service, "get_snapshot_store", lambda: store)
    return store
