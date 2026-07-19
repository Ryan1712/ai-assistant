"""Phase 0 (spec 4.1): endpoint debug trace — chỉ CEO, lọc workspace."""
import uuid

from app.models import AgentTrace, ChatRequest, Conversation, User

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


async def test_request_khong_ton_tai_tra_mang_rong(client):
    headers = await _ceo_headers(client)
    resp = await client.get(f"/api/v1/admin/traces/{uuid.uuid4()}", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


async def test_nhan_vien_bi_403(client, db_session):
    from sqlalchemy import select
    headers = await _ceo_headers(client)
    req = await _seed_trace(db_session)

    # Create manager
    mgr_inv = await client.post("/api/v1/invites", headers=headers,
                                json={"role": "manager", "manager_id": None})
    assert mgr_inv.status_code == 201, mgr_inv.text
    mgr_join = await client.post("/api/v1/auth/signup-invite", json={
        "token": mgr_inv.json()["token"], "email": "mgr@a.vn", "password": "pw123456",
        "full_name": "MGR", "device_uuid": "d-mgr", "device_name": "",
    })
    mgr = await db_session.execute(select(User).where(User.email == "mgr@a.vn"))
    manager_id = mgr.scalar_one().id

    # Create employee with manager
    emp_inv = await client.post("/api/v1/invites", headers=headers,
                                json={"role": "employee", "manager_id": str(manager_id)})
    assert emp_inv.status_code == 201, emp_inv.text
    emp_join = await client.post("/api/v1/auth/signup-invite", json={
        "token": emp_inv.json()["token"], "email": "nv@a.vn", "password": "pw123456",
        "full_name": "NV", "device_uuid": "d-nv", "device_name": "",
    })
    emp_headers = {"Authorization": f"Bearer {emp_join.json()['access_token']}"}
    resp = await client.get(f"/api/v1/admin/traces/{req.id}", headers=emp_headers)
    assert resp.status_code == 403
