import uuid as uuid_mod

import pytest
from fastapi import HTTPException

from app import security
from app.models import Role, User, UserStatus, Workspace
from app.services import auth_service
from tests.conftest import SIGNUP, _ceo_headers, _invite_and_join


@pytest.mark.asyncio
async def test_full_create_employee_flow(client):
    headers = await _ceo_headers(client)
    mgr = await _invite_and_join(client, headers, "manager", "m1@a.vn")
    emp = await _invite_and_join(client, headers, "employee", "e1@a.vn",
                                 manager_id=mgr["user"]["id"])
    assert emp["user"]["role"] == "employee"


@pytest.mark.asyncio
async def test_employee_create_requires_manager(client):
    headers = await _ceo_headers(client)
    resp = await client.post("/api/v1/invites", headers=headers,
                             json={"email": "e1@a.vn", "full_name": "E1",
                                   "role": "employee", "manager_id": None})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_activation_code_single_use(client):
    headers = await _ceo_headers(client)
    created = await client.post("/api/v1/invites", headers=headers,
                                json={"email": "m2@a.vn", "full_name": "M2",
                                      "role": "manager", "manager_id": None})
    code = created.json()["activation_code"]
    body = {"code": code, "password": "pw123456", "device_uuid": "d", "device_name": ""}
    assert (await client.post("/api/v1/auth/activate", json=body)).status_code == 201
    assert (await client.post("/api/v1/auth/activate", json=body)).status_code == 400


@pytest.mark.asyncio
async def test_non_ceo_cannot_create_employee(client):
    headers = await _ceo_headers(client)
    mgr = await _invite_and_join(client, headers, "manager", "m1@a.vn")
    mgr_headers = {"Authorization": f"Bearer {mgr['access_token']}"}
    resp = await client.post("/api/v1/invites", headers=mgr_headers,
                             json={"email": "e1@a.vn", "full_name": "E1",
                                   "role": "employee", "manager_id": None})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_employee_garbage_role_422(client):
    headers = await _ceo_headers(client)
    resp = await client.post("/api/v1/invites", headers=headers,
                             json={"email": "x@a.vn", "full_name": "X",
                                   "role": "admin", "manager_id": None})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_employee_create_manager_wrong_workspace_422(client):
    headers_a = await _ceo_headers(client)
    mgr_a = await _invite_and_join(client, headers_a, "manager", "ma@a.vn")
    resp_b = await client.post("/api/v1/auth/signup-workspace", json={
        "workspace_name": "Cong ty B", "email": "ceo@b.vn", "password": "secret123",
        "full_name": "Sep B", "device_uuid": "dev-b", "device_name": "",
    })
    headers_b = {"Authorization": f"Bearer {resp_b.json()['access_token']}"}
    resp = await client.post("/api/v1/invites", headers=headers_b,
                             json={"email": "e1@b.vn", "full_name": "E1",
                                   "role": "employee", "manager_id": mgr_a["user"]["id"]})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_manager_create_with_bogus_manager_id_422(client):
    headers = await _ceo_headers(client)
    resp = await client.post("/api/v1/invites", headers=headers,
                             json={"email": "m1@a.vn", "full_name": "M1",
                                   "role": "manager", "manager_id": str(uuid_mod.uuid4())})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_employee_duplicate_email_409(client):
    headers = await _ceo_headers(client)
    resp = await client.post("/api/v1/invites", headers=headers,
                             json={"email": "ceo@a.vn", "full_name": "Trung email",
                                   "role": "manager", "manager_id": None})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_activate_wrong_code_400(client):
    resp = await client.post("/api/v1/auth/activate", json={
        "code": "KHONGTONTAI", "password": "pw123456", "device_uuid": "d", "device_name": ""})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_login_blocked_before_activation(client):
    headers = await _ceo_headers(client)
    created = await client.post("/api/v1/invites", headers=headers,
                                json={"email": "pending@a.vn", "full_name": "Pending",
                                      "role": "manager", "manager_id": None})
    assert created.status_code == 201
    # Chua kich hoat -> khong the login du biet email (password_hash ngau nhien khong ai biet)
    resp = await client.post("/api/v1/auth/login", json={
        "email": "pending@a.vn", "password": "anything", "device_uuid": "d", "device_name": ""})
    assert resp.status_code == 401  # sai password_hash ngau nhien truoc, khong lo trang thai


@pytest.mark.asyncio
async def test_login_service_rejects_pending_status_even_with_known_password(db_session):
    """REST-level test ở trên chỉ chứng minh mật khẩu ngẫu nhiên chặn được login (401) —
    test này gọi thẳng auth_service.login() với password_hash BIẾT TRƯỚC để xác nhận
    nhánh status==pending thật sự chạy (403 account_pending), không phải dead code."""
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    user = User(workspace_id=ws.id, email="pending2@a.vn",
               password_hash=security.hash_password("known123"), full_name="P",
               role=Role.manager, status=UserStatus.pending)
    db_session.add(user)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await auth_service.login(db_session, email="pending2@a.vn", password="known123",
                                 device_uuid="d", device_name="")
    assert exc.value.status_code == 403
    assert exc.value.detail == "account_pending"


@pytest.mark.asyncio
async def test_login_succeeds_after_activation(client):
    headers = await _ceo_headers(client)
    created = await client.post("/api/v1/invites", headers=headers,
                                json={"email": "m9@a.vn", "full_name": "M9",
                                      "role": "manager", "manager_id": None})
    code = created.json()["activation_code"]
    activate = await client.post("/api/v1/auth/activate", json={
        "code": code, "password": "newpass123", "device_uuid": "d", "device_name": ""})
    assert activate.status_code == 201

    login = await client.post("/api/v1/auth/login", json={
        "email": "m9@a.vn", "password": "newpass123", "device_uuid": "d2", "device_name": ""})
    assert login.status_code == 200
