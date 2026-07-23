"""Phase 0 (spec 4.1): endpoint debug trace — chỉ CEO, lọc workspace."""
import uuid

from app.models import AgentTrace, ChatRequest, Conversation, User
from tests.conftest import _invite_and_join

SIGNUP = {
    "workspace_name": "Cong ty A", "email": "ceo@a.vn", "password": "secret123",
    "full_name": "Sep", "device_uuid": "dev-1", "device_name": "",
}


async def _ceo_headers(client):
    resp = await client.post("/api/v1/auth/signup-workspace", json=SIGNUP)
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _seed_trace(db_session, email="ceo@a.vn"):
    from sqlalchemy import select
    ceo = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    conv = Conversation(workspace_id=ceo.workspace_id, user_id=ceo.id)
    db_session.add(conv)
    await db_session.flush()
    req = ChatRequest(workspace_id=ceo.workspace_id, conversation_id=conv.id,
                      user_id=ceo.id, content="hi", queue_position=1.0)
    db_session.add(req)
    await db_session.flush()
    db_session.add(AgentTrace(workspace_id=ceo.workspace_id, chat_request_id=req.id,
                              model="fake", iterations=1, stop_reason="end_turn",
                              tools_called=[], total_latency_ms=10))
    await db_session.commit()
    return req


async def test_ceo_xem_duoc_trace(client, db_session):
    headers = await _ceo_headers(client)
    req = await _seed_trace(db_session)
    resp = await client.get(f"/api/v1/admin/traces/{req.id}", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["stop_reason"] == "end_turn"
    assert body[0]["model"] == "fake"
    assert body[0]["chat_request_id"] == str(req.id)
    assert body[0]["route"] == "fast"
    assert body[0]["iterations"] == 1
    assert body[0]["tools_called"] == []
    assert body[0]["total_latency_ms"] == 10
    assert body[0]["created_at"] is not None


async def test_request_khong_ton_tai_tra_mang_rong(client):
    headers = await _ceo_headers(client)
    resp = await client.get(f"/api/v1/admin/traces/{uuid.uuid4()}", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


async def test_nhan_vien_bi_403(client, db_session):
    headers = await _ceo_headers(client)
    req = await _seed_trace(db_session)

    mgr = await _invite_and_join(client, headers, "manager", "mgr@a.vn")
    emp = await _invite_and_join(client, headers, "employee", "nv@a.vn",
                                 manager_id=mgr["user"]["id"])
    emp_headers = {"Authorization": f"Bearer {emp['access_token']}"}
    resp = await client.get(f"/api/v1/admin/traces/{req.id}", headers=emp_headers)
    assert resp.status_code == 403


async def test_trace_workspace_khac_khong_lo(client, db_session):
    """Cach ly tenant: CEO workspace A query chat_request_id co trace THAT o
    workspace B phai nhan mang RONG (khong 404 — khong lo ca su ton tai)."""
    headers_a = await _ceo_headers(client)
    resp = await client.post("/api/v1/auth/signup-workspace", json={
        "workspace_name": "Cong ty B", "email": "ceo@b.vn", "password": "secret123",
        "full_name": "Sep B", "device_uuid": "dev-b", "device_name": "",
    })
    assert resp.status_code == 201, resp.text
    req_b = await _seed_trace(db_session, email="ceo@b.vn")
    resp = await client.get(f"/api/v1/admin/traces/{req_b.id}", headers=headers_a)
    assert resp.status_code == 200
    assert resp.json() == []
