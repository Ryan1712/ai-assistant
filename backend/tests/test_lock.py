import pytest
from sqlalchemy import select

from app.models import Notification, User
from tests.test_invites import SIGNUP, _ceo_headers, _invite_and_join


@pytest.mark.asyncio
async def test_lock_kicks_user_out(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    uid = m1["user"]["id"]

    assert (await client.post(f"/api/v1/users/{uid}/lock", headers=ceo_h)).status_code == 204

    # refresh token bị thu hồi
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": m1["refresh_token"]})
    assert r.status_code in (401, 403)
    # access token còn hạn cũng bị chặn
    me = await client.get("/api/v1/users/me",
                          headers={"Authorization": f"Bearer {m1['access_token']}"})
    assert me.status_code == 403
    # không đăng nhập lại được
    login = await client.post("/api/v1/auth/login", json={
        "email": "m1@a.vn", "password": "pw123456", "device_uuid": "d", "device_name": "",
    })
    assert login.status_code == 403


@pytest.mark.asyncio
async def test_unlock_restores_access(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    uid = m1["user"]["id"]
    await client.post(f"/api/v1/users/{uid}/lock", headers=ceo_h)
    assert (await client.post(f"/api/v1/users/{uid}/unlock", headers=ceo_h)).status_code == 204
    login = await client.post("/api/v1/auth/login", json={
        "email": "m1@a.vn", "password": "pw123456", "device_uuid": "d", "device_name": "",
    })
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_root_ceo_cannot_be_locked(client, db_session):
    ceo_h = await _ceo_headers(client)
    root = (await db_session.execute(select(User).where(User.is_root))).scalar_one()
    resp = await client.post(f"/api/v1/users/{root.id}/lock", headers=ceo_h)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_manager_cannot_lock(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    m2 = await _invite_and_join(client, ceo_h, "manager", "m2@a.vn")
    h = {"Authorization": f"Bearer {m1['access_token']}"}
    resp = await client.post(f"/api/v1/users/{m2['user']['id']}/lock", headers=h)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_unlock_request_notifies_root_ceo(client, db_session):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    await client.post(f"/api/v1/users/{m1['user']['id']}/lock", headers=ceo_h)

    resp = await client.post("/api/v1/auth/unlock-request",
                             json={"email": "m1@a.vn", "device_uuid": "dev-x"})
    assert resp.status_code == 202
    # email không tồn tại → vẫn 202, không lộ thông tin
    resp2 = await client.post("/api/v1/auth/unlock-request",
                              json={"email": "ghost@a.vn", "device_uuid": "d"})
    assert resp2.status_code == 202

    notes = (await db_session.execute(
        select(Notification).where(Notification.type == "unlock_request")
    )).scalars().all()
    assert len(notes) == 1
    assert notes[0].payload["device_uuid"] == "dev-x"
