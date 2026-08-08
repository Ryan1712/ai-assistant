"""PO #2 (2026-08-08): gắn project cho conversation đang mở, dùng làm default
project cho create_task khi user không chỉ rõ project khác. Xem
docs/superpowers/specs/2026-08-05-conversation-project-scope-design.md và
docs/superpowers/plans/2026-08-08-conversation-project-scope.md.

Hành vi ON DELETE SET NULL (project bị xóa -> conversation.project_id tự về
NULL) KHÔNG có test tự động ở đây — đã thử bật PRAGMA foreign_keys=ON cho
SQLite (engine test không enforce FK mặc định) nhưng lộ ra 32 test KHÁC trong
suite đang "ăn gian" workspace_id/user_id ngẫu nhiên (không tạo record thật),
sửa hết là việc lớn ngoài phạm vi PO #2 — đã revert. Hành vi SET NULL dựa vào
khai báo SQLAlchemy đúng cú pháp (đã xác nhận bằng migration Alembic áp lên
Postgres dev thật, xem Task 1 plan) + Postgres luôn enforce FK constraint,
không cần test riêng ở tầng model."""
import uuid

import pytest

from app.models import Conversation
from tests.conftest import _ceo_headers


async def _mk_conv(db, project_id=None):
    ws, user = uuid.uuid4(), uuid.uuid4()
    conv = Conversation(workspace_id=ws, user_id=user, project_id=project_id)
    db.add(conv)
    await db.flush()
    return conv, ws


@pytest.mark.asyncio
async def test_conversation_project_id_nullable_default_none(db_session):
    conv, _ = await _mk_conv(db_session)
    await db_session.commit()
    assert conv.project_id is None


@pytest.mark.asyncio
async def test_patch_conversation_sets_project_id(client):
    ceo_h = await _ceo_headers(client)
    proj = (await client.post("/api/v1/projects", json={"name": "P1", "goal": "g"},
                              headers=ceo_h)).json()
    conv = (await client.get("/api/v1/conversations/active", headers=ceo_h)).json()

    resp = await client.patch(f"/api/v1/conversations/{conv['id']}",
                              json={"project_id": proj["id"]}, headers=ceo_h)
    assert resp.status_code == 200
    body = resp.json()
    assert body["project_id"] == proj["id"]
    assert body["project_name"] == "P1"


@pytest.mark.asyncio
async def test_patch_conversation_unsets_project_id(client):
    ceo_h = await _ceo_headers(client)
    proj = (await client.post("/api/v1/projects", json={"name": "P1", "goal": "g"},
                              headers=ceo_h)).json()
    conv = (await client.get("/api/v1/conversations/active", headers=ceo_h)).json()
    await client.patch(f"/api/v1/conversations/{conv['id']}",
                       json={"project_id": proj["id"]}, headers=ceo_h)

    resp = await client.patch(f"/api/v1/conversations/{conv['id']}",
                              json={"project_id": None}, headers=ceo_h)
    assert resp.status_code == 200
    body = resp.json()
    assert body["project_id"] is None
    assert body["project_name"] is None


@pytest.mark.asyncio
async def test_patch_conversation_title_only_keeps_project_id(client):
    ceo_h = await _ceo_headers(client)
    proj = (await client.post("/api/v1/projects", json={"name": "P1", "goal": "g"},
                              headers=ceo_h)).json()
    conv = (await client.get("/api/v1/conversations/active", headers=ceo_h)).json()
    await client.patch(f"/api/v1/conversations/{conv['id']}",
                       json={"project_id": proj["id"]}, headers=ceo_h)

    resp = await client.patch(f"/api/v1/conversations/{conv['id']}",
                              json={"title": "Tên mới"}, headers=ceo_h)
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Tên mới"
    assert body["project_id"] == proj["id"]  # KHÔNG bị mất khi chỉ đổi title


@pytest.mark.asyncio
async def test_patch_conversation_rejects_project_from_other_workspace(client):
    ceo_h = await _ceo_headers(client)
    conv = (await client.get("/api/v1/conversations/active", headers=ceo_h)).json()
    fake_project_id = str(uuid.uuid4())

    resp = await client.patch(f"/api/v1/conversations/{conv['id']}",
                              json={"project_id": fake_project_id}, headers=ceo_h)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_conversations_includes_project_name(client):
    ceo_h = await _ceo_headers(client)
    proj = (await client.post("/api/v1/projects", json={"name": "P1", "goal": "g"},
                              headers=ceo_h)).json()
    conv = (await client.get("/api/v1/conversations/active", headers=ceo_h)).json()
    await client.patch(f"/api/v1/conversations/{conv['id']}",
                       json={"project_id": proj["id"]}, headers=ceo_h)

    listed = (await client.get("/api/v1/conversations", headers=ceo_h)).json()
    found = next(c for c in listed if c["id"] == conv["id"])
    assert found["project_name"] == "P1"

    active = (await client.get("/api/v1/conversations/active", headers=ceo_h)).json()
    assert active["project_name"] == "P1"
