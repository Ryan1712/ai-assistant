import pytest
from sqlalchemy import select

from app.models import Device, LoginEvent

SIGNUP = {
    "workspace_name": "Cong ty A", "email": "ceo@a.vn", "password": "secret123",
    "full_name": "Sep", "device_uuid": "dev-1", "device_name": "iPhone Sep",
}


@pytest.mark.asyncio
async def test_signup_workspace_creates_root_ceo(client):
    resp = await client.post("/api/v1/auth/signup-workspace", json=SIGNUP)
    assert resp.status_code == 201
    data = resp.json()
    assert data["user"]["role"] == "ceo"
    assert data["user"]["is_root"] is True
    assert data["access_token"] and data["refresh_token"]


@pytest.mark.asyncio
async def test_login_ok_and_logs_device(client, db_session):
    await client.post("/api/v1/auth/signup-workspace", json=SIGNUP)
    resp = await client.post("/api/v1/auth/login", json={
        "email": "ceo@a.vn", "password": "secret123",
        "device_uuid": "dev-2", "device_name": "iPad",
    })
    assert resp.status_code == 200
    devices = (await db_session.execute(select(Device))).scalars().all()
    assert {d.device_uuid for d in devices} == {"dev-1", "dev-2"}
    events = (await db_session.execute(select(LoginEvent))).scalars().all()
    assert len(events) == 2  # signup cũng tính là 1 lần đăng nhập


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    await client.post("/api/v1/auth/signup-workspace", json=SIGNUP)
    resp = await client.post("/api/v1/auth/login", json={
        "email": "ceo@a.vn", "password": "WRONG", "device_uuid": "d", "device_name": "",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_signup_duplicate_email_409(client):
    await client.post("/api/v1/auth/signup-workspace", json=SIGNUP)
    resp = await client.post("/api/v1/auth/signup-workspace", json=SIGNUP)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_login_nonexistent_email_401(client):
    resp = await client.post("/api/v1/auth/login", json={
        "email": "ghost@a.vn", "password": "x", "device_uuid": "d", "device_name": "",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_same_device_uuid_upserts_not_duplicates(client, db_session):
    from sqlalchemy import select
    from app.models import Device
    await client.post("/api/v1/auth/signup-workspace", json=SIGNUP)
    for _ in range(2):
        await client.post("/api/v1/auth/login", json={
            "email": "ceo@a.vn", "password": "secret123",
            "device_uuid": "dev-1", "device_name": "iPhone Sep doi ten",
        })
    devices = (await db_session.execute(select(Device))).scalars().all()
    assert len(devices) == 1  # dev-1 upsert, không nhân bản
    assert devices[0].device_name == "iPhone Sep doi ten"


async def _signup(client):
    resp = await client.post("/api/v1/auth/signup-workspace", json=SIGNUP)
    return resp.json()


@pytest.mark.asyncio
async def test_me_requires_valid_token(client):
    data = await _signup(client)
    ok = await client.get("/api/v1/users/me",
                          headers={"Authorization": f"Bearer {data['access_token']}"})
    assert ok.status_code == 200
    assert ok.json()["email"] == "ceo@a.vn"
    bad = await client.get("/api/v1/users/me", headers={"Authorization": "Bearer nope"})
    assert bad.status_code == 401


@pytest.mark.asyncio
async def test_refresh_rotation(client):
    data = await _signup(client)
    old = data["refresh_token"]
    r1 = await client.post("/api/v1/auth/refresh", json={"refresh_token": old})
    assert r1.status_code == 200
    assert r1.json()["refresh_token"] != old
    r2 = await client.post("/api/v1/auth/refresh", json={"refresh_token": old})
    assert r2.status_code == 401  # token cũ đã bị revoke


@pytest.mark.asyncio
async def test_logout_revokes(client):
    data = await _signup(client)
    resp = await client.post("/api/v1/auth/logout", json={"refresh_token": data["refresh_token"]})
    assert resp.status_code == 204
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": data["refresh_token"]})
    assert r.status_code == 401
