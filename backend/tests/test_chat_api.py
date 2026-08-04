import uuid

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.chat import get_arq_pool
from app.db import get_db
from app.main import create_app
from app.models import Conversation
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
    # signup-workspace (Phase 6 onboarding) tu tao san 1 conversation seed
    # (title=None) - liet ke moi nguoi dung "cua chinh minh" nen no cung xuat
    # hien, moi hon len truoc (order_by created_at desc), seed cu hon xep sau.
    assert [c["title"] for c in listed.json()] == ["Cong viec", None]


@pytest.mark.asyncio
async def test_create_conversation_voi_title_tuong_minh_thi_lock_luon(chat_client, engine):
    """Fix 3 (whole-branch review): PATCH rename đã lock title_locked=True (Task 4) —
    nếu POST /conversations kèm title mà không lock luôn, cron retitle sẽ tưởng đây
    là conversation 'chưa đặt tên qua text' và đè lên title người dùng chọn ngay lúc
    tạo."""
    client, _ = chat_client
    ceo_h = await _ceo_headers(client)
    created = await client.post("/api/v1/conversations", headers=ceo_h,
                                json={"title": "Cong viec"})
    assert created.status_code == 201
    conv_id = created.json()["id"]

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        row = await db.get(Conversation, uuid.UUID(conv_id))
        assert row.title_locked is True


@pytest.mark.asyncio
async def test_create_conversation_khong_title_thi_khong_lock(chat_client, engine):
    client, _ = chat_client
    ceo_h = await _ceo_headers(client)
    created = await client.post("/api/v1/conversations", headers=ceo_h, json={})
    assert created.status_code == 201
    conv_id = created.json()["id"]

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        row = await db.get(Conversation, uuid.UUID(conv_id))
        assert row.title_locked is False


@pytest.mark.asyncio
async def test_send_message_enqueues_job_and_creates_queued_request(chat_client):
    client, fake_pool = chat_client
    ceo_h = await _ceo_headers(client)
    conv = (await client.post("/api/v1/conversations", headers=ceo_h, json={})).json()

    resp = await client.post(f"/api/v1/conversations/{conv['id']}/messages", headers=ceo_h,
                             json={"content": "tao task X"})
    assert resp.status_code == 201
    assert resp.json()["status"] == "queued"
    # Phải có đúng 2 jobs: index_chat_message (embedding nền) + process_conversation (AI)
    job_names = [name for name, _args, _kw in fake_pool.enqueued]
    assert "index_chat_message" in job_names
    assert "process_conversation" in job_names
    proc_job = next(j for j in fake_pool.enqueued if j[0] == "process_conversation")
    assert proc_job[2]["_job_id"] == f"conv:{conv['id']}"


@pytest.mark.asyncio
async def test_send_message_khong_await_embedding_dong_bo(chat_client, monkeypatch):
    """Chứng minh send_message không còn await index_content đồng bộ — embedding
    được enqueue vào arq, kể cả khi index_content sẽ treo/lỗi thì response vẫn
    trả 201 ngay lập tức và job index_chat_message vẫn được enqueue."""
    import asyncio
    from app.services import embedding_service

    async def _buoc_treo_va_no(*args, **kwargs):
        # Nếu endpoint còn await trực tiếp, test sẽ treo ≥ 10s / raise RuntimeError
        await asyncio.sleep(10)
        raise RuntimeError("Voyage down — không được gọi trực tiếp trong request")

    monkeypatch.setattr(embedding_service, "index_content", _buoc_treo_va_no)

    client, fake_pool = chat_client
    ceo_h = await _ceo_headers(client)
    conv = (await client.post("/api/v1/conversations", headers=ceo_h, json={})).json()

    resp = await client.post(f"/api/v1/conversations/{conv['id']}/messages", headers=ceo_h,
                             json={"content": "test khong chặn embedding"})
    # Phải trả ngay 201 — index_content không được await trong đường xử lý request
    assert resp.status_code == 201
    # Job embedding vẫn được enqueue (sẽ chạy trong worker riêng)
    job_names = [name for name, _args, _kw in fake_pool.enqueued]
    assert "index_chat_message" in job_names


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


@pytest.mark.asyncio
async def test_auto_title_tu_tin_nhan_dau(chat_client):
    client, _ = chat_client
    ceo_h = await _ceo_headers(client)
    conv = (await client.post("/api/v1/conversations", headers=ceo_h, json={})).json()
    assert conv["title"] is None

    await client.post(f"/api/v1/conversations/{conv['id']}/messages", headers=ceo_h,
                      json={"content": "Tao task lam slide quy 3 cho Nam nhe"})

    # Tìm theo id, không dựa convs[0]: signup đã tạo sẵn seed conversation (Phase 6
    # onboarding) — 2 conversation tạo trong cùng tick clock thì thứ tự created_at
    # DESC không xác định (flake từng lộ khi chạy full suite máy chậm).
    convs = (await client.get("/api/v1/conversations", headers=ceo_h)).json()
    target = next(c for c in convs if c["id"] == conv["id"])
    assert target["title"] == "Tao task lam slide quy 3 cho Nam nhe"


@pytest.mark.asyncio
async def test_auto_title_khong_ghi_de_title_co_san(chat_client):
    client, _ = chat_client
    ceo_h = await _ceo_headers(client)
    conv = (await client.post("/api/v1/conversations", headers=ceo_h,
                              json={"title": "Da dat ten"})).json()

    await client.post(f"/api/v1/conversations/{conv['id']}/messages", headers=ceo_h,
                      json={"content": "tin nhan bat ky"})

    convs = (await client.get("/api/v1/conversations", headers=ceo_h)).json()
    target = next(c for c in convs if c["id"] == conv["id"])
    assert target["title"] == "Da dat ten"


@pytest.mark.asyncio
async def test_rename_own_conversation(chat_client):
    client, _ = chat_client
    ceo_h = await _ceo_headers(client)
    conv = (await client.post("/api/v1/conversations", headers=ceo_h, json={})).json()

    resp = await client.patch(f"/api/v1/conversations/{conv['id']}", headers=ceo_h,
                              json={"title": "Ke hoach Q3"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["title"] == "Ke hoach Q3"

    listed = await client.get("/api/v1/conversations", headers=ceo_h)
    assert listed.json()[0]["title"] == "Ke hoach Q3"


@pytest.mark.asyncio
async def test_rename_locks_title_against_auto_retitle(chat_client, engine):
    client, _ = chat_client
    ceo_h = await _ceo_headers(client)
    conv = (await client.post("/api/v1/conversations", headers=ceo_h, json={})).json()

    resp = await client.patch(f"/api/v1/conversations/{conv['id']}", headers=ceo_h,
                              json={"title": "Ke hoach Q3"})
    assert resp.status_code == 200, resp.text

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        row = await db.get(Conversation, uuid.UUID(conv["id"]))
        assert row.title_locked is True


@pytest.mark.asyncio
async def test_rename_others_conversation_404(chat_client):
    client, _ = chat_client
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    conv = (await client.post("/api/v1/conversations", headers=ceo_h, json={})).json()

    m1_headers = {"Authorization": f"Bearer {m1['access_token']}"}
    resp = await client.patch(f"/api/v1/conversations/{conv['id']}", headers=m1_headers,
                              json={"title": "x"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_own_conversation(chat_client):
    client, _ = chat_client
    ceo_h = await _ceo_headers(client)
    conv = (await client.post("/api/v1/conversations", headers=ceo_h, json={})).json()

    resp = await client.delete(f"/api/v1/conversations/{conv['id']}", headers=ceo_h)
    assert resp.status_code == 204, resp.text

    listed = await client.get("/api/v1/conversations", headers=ceo_h)
    assert conv["id"] not in [c["id"] for c in listed.json()]


@pytest.mark.asyncio
async def test_delete_others_conversation_404(chat_client):
    client, _ = chat_client
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    conv = (await client.post("/api/v1/conversations", headers=ceo_h, json={})).json()

    m1_headers = {"Authorization": f"Bearer {m1['access_token']}"}
    resp = await client.delete(f"/api/v1/conversations/{conv['id']}", headers=m1_headers)
    assert resp.status_code == 404
